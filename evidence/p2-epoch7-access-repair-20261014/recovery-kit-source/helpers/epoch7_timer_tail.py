"""Retained renewal scheduling only after all long post-install checks.

Exact v239 timespan/decimal query grammar; raw baseline is a measured, reviewed
input. Unknown/infinity/nonzero prior renewal execution refuses before start.
No certbot command exists. A successful schedule is distinct from TLS issuance.
"""
import copy
import re
import time

from epoch7_host_phases import need
from epoch7_command_runner import ExactCommandRunner
from epoch7_recovery_sequence import observation, check_observation
from epoch7_runtime_effects import (Epoch7RuntimeEffects, START_UNITS, GATEWAY_SERVICE,
    MANIFEST, ENV)
import epoch7_delta as d

TIMER='xuanjun-p2-tls-renew.timer'
SERVICE='xuanjun-p2-tls-renew.service'
PROPERTIES={TIMER:('NextElapseUSecMonotonic','LastTriggerUSecMonotonic','ActiveEnterTimestampMonotonic'),
            SERVICE:('ActiveEnterTimestampMonotonic','ExecMainStartTimestampMonotonic')}
UNITS=(('y',31557600000000),('month',2629800000000),('w',604800000000),
       ('d',86400000000),('h',3600000000),('min',60000000),('s',1000000),('ms',1000),('us',1))
MAX_US=(1<<64)-2
TAIL_SECONDS=60
MIN_MARGIN_SECONDS=180


def timespan_us(raw):
    need(type(raw) is str and 1<=len(raw)<=256,'TIMER_TIMESPAN_BOUND')
    if raw=='0':return 0
    parts=raw.split(' ');need(' '.join(parts)==raw and all(parts),'TIMER_TIMESPAN_FORMAT')
    scale=dict(UNITS);order={name:i for i,(name,unused) in enumerate(UNITS)}
    previous=-1;result=0
    for part in parts:
        match=re.fullmatch(r'(0|[1-9][0-9]{0,19})(?:\.([0-9]{1,6}))?(month|min|ms|us|y|w|d|h|s)',part)
        need(match is not None,'TIMER_TIMESPAN_FORMAT')
        number,fraction,unit=match.groups();index=order[unit]
        need(fraction is None or scale[unit]<60000000,'TIMER_TIMESPAN_FRACTION_SCOPE')
        need(index>previous,'TIMER_TIMESPAN_ORDER');previous=index
        amount=int(number)*scale[unit]
        if fraction is not None:
            numerator=int(fraction)*scale[unit];denominator=10**len(fraction)
            need(numerator%denominator==0,'TIMER_FRACTION_MICROSECOND_PRECISION')
            amount+=numerator//denominator
        result+=amount;need(result<=MAX_US,'TIMER_TIMESPAN_OVERFLOW')
    return result


def parse_query(raw,unit,allow_disarmed_next=False):
    need(type(raw) is bytes and len(raw)<=4096 and unit in PROPERTIES,'TIMER_QUERY_SCOPE')
    result={}
    for line in raw.decode('ascii','strict').splitlines():
        need('=' in line,'TIMER_QUERY_LINE');key,value=line.split('=',1)
        need(key in PROPERTIES[unit] and key not in result and len(value)<=256,'TIMER_QUERY_FIELDS')
        if key=='NextElapseUSecMonotonic' and value=='infinity':
            need(allow_disarmed_next is True,'TIMER_ACTIVE_EXPIRY_MUST_BE_FINITE')
            result[key]=None
        elif 'USec' in key:result[key]=timespan_us(value)
        else:
            need(re.fullmatch(r'0|[1-9][0-9]{0,19}',value) is not None,'TIMER_DECIMAL_MICROSECONDS')
            result[key]=int(value);need(result[key]<=MAX_US,'TIMER_DECIMAL_OVERFLOW')
    need(set(result)==set(PROPERTIES[unit]),'TIMER_QUERY_REQUIRED_FIELDS')
    return result


def timer_baseline_from_observation(value):
    need(type(value) is dict and type(value.get('raw')) is dict and
         set(value['raw'])==set(PROPERTIES) and value.get('missing_fields')==[],
         'TIMER_COMPLETE_MEASURED_OBSERVATION')
    raw={}
    for unit,properties in PROPERTIES.items():
        row=value['raw'][unit]
        need(type(row) is dict and set(row)==set(properties),'TIMER_MEASURED_PROPERTY_SET')
        need(all(type(row[p]) is str and len(row[p])<=256 and '\n' not in row[p] and '\r' not in row[p]
                 for p in properties),'TIMER_MEASURED_PROPERTY_BYTES')
        raw[unit]=''.join(p+'='+row[p]+'\n' for p in properties).encode('ascii','strict')
    compile_timer_contract(raw)
    return raw


def compile_timer_contract(raw_baseline):
    need(type(raw_baseline) is dict and set(raw_baseline)==set(PROPERTIES),'TIMER_REVIEWED_BASELINE_REQUIRED')
    parsed={unit:parse_query(raw,unit,allow_disarmed_next=True) for unit,raw in raw_baseline.items()}
    # No old service-trigger history is silently assumed safe for OnUnitActiveSec.
    need(parsed[TIMER]['LastTriggerUSecMonotonic']==0 and
         parsed[SERVICE]['ActiveEnterTimestampMonotonic']==0 and
         parsed[SERVICE]['ExecMainStartTimestampMonotonic']==0,'TIMER_PRIOR_TRIGGER_REQUIRES_REVIEW')
    return {'schema':1,'baseline':parsed,'raw_sha256':{u:__import__('hashlib').sha256(v).hexdigest()
             for u,v in raw_baseline.items()},'tail_seconds':TAIL_SECONDS,
            'minimum_margin_seconds':MIN_MARGIN_SECONDS,'timer_unit':TIMER,
            'timer_start_phase':'post_install_checks','production_acceptance':'PENDING'}


class RetainedRenewalTail(object):
    def __init__(self,context,authority,diagnostics,executable,raw_baseline,expected_sha256,controls):
        self.context,self.authority,self.diagnostics=copy.deepcopy(context),authority,diagnostics
        self.controls=controls
        self.executable=executable;self.contract=compile_timer_contract(raw_baseline)
        need(d.digest(self.contract)==expected_sha256,'TIMER_REVIEWED_CONTRACT_BINDING')
        self.binding=expected_sha256;self.deadline=None;self.started=False
        commands={}
        for index,unit in enumerate((TIMER,SERVICE)):
            commands['show_%d'%index]={'phase':'post_install_checks','operation':'service_show',
                'argv':['/usr/bin/systemctl','show',unit,'--property='+','.join(PROPERTIES[unit])],
                'cwd':'/','env':dict(ENV),'timeout':5,'accepted_returncodes':[0]}
        commands['start']={'phase':'post_install_checks','operation':'service_start',
            'argv':['/usr/bin/systemctl','start',TIMER],'cwd':'/','env':dict(ENV),
            'timeout':15,'accepted_returncodes':[0]}
        self.runner=ExactCommandRunner(commands,self._guard,diagnostics)

    def _guard(self):
        self.authority.phase('post_install_checks')
        need(self.deadline is not None and time.monotonic()<self.deadline and
             d.digest(self.contract)==self.binding,'TIMER_TAIL_DEADLINE_OR_BINDING')
        self.executable.begin_guard(min(self.deadline,time.monotonic()+5))
        need(self.executable('/usr/bin/systemctl') is True,'TIMER_SYSTEMCTL_PIN')
        return True

    def _query(self,allow_disarmed_next=False):
        result={}
        for index,unit in enumerate((TIMER,SERVICE)):
            result[unit]=parse_query(self.runner.run('show_%d'%index).stdout,unit,allow_disarmed_next)
            self._guard()
        return result

    def activate(self,context,diagnostics):
        need(context==self.context and diagnostics is self.diagnostics and not self.started,
             'TIMER_TAIL_ONE_ATTEMPT')
        self.started=True
        need(self.controls.open_phase=='post_install_checks' and self.controls.phase_deadline is not None,
             'TIMER_OUTER_PHASE_BUDGET')
        self.deadline=min(time.monotonic()+TAIL_SECONDS,self.controls.phase_deadline)
        before=self._query(allow_disarmed_next=True)
        need(before==self.contract['baseline'],'TIMER_BASELINE_CHANGED')
        started=time.monotonic();self.runner.run('start');after=self._query()
        need(after[SERVICE]==before[SERVICE] and after[TIMER]['LastTriggerUSecMonotonic']==
             before[TIMER]['LastTriggerUSecMonotonic'],'TIMER_UNEXPECTED_RENEWAL_EXECUTION')
        active=after[TIMER]['ActiveEnterTimestampMonotonic']
        now=time.monotonic();next_at=after[TIMER]['NextElapseUSecMonotonic']
        need(int(started*1000000)<=active<=int(now*1000000) and next_at-int(now*1000000)>=MIN_MARGIN_SECONDS*1000000 and now<self.deadline,
             'TIMER_FINAL_EXPIRY_MARGIN')
        self._guard()
        return {'retained_renewal_timer_scheduled':True,'query_sha256':d.digest(after),
                'minimum_observed_margin_seconds':MIN_MARGIN_SECONDS,
                'timer_or_service_trigger_advanced':False,'direct_tls_issue_renew_dry_run_commands':0}


class DeferredRenewalRuntime(Epoch7RuntimeEffects):
    """Same finite runtime effects; defer only the reviewed renewal timer start."""
    def __init__(self,*args,**kwargs):
        self.successful_commands={}
        self.legacy=None
        self.timer_tail=kwargs.pop('timer_tail')
        need(isinstance(self.timer_tail,RetainedRenewalTail),'TIMER_CONCRETE_TAIL_REQUIRED')
        super(DeferredRenewalRuntime,self).__init__(*args,**kwargs)
        need(self.timer_tail.context==self.context and self.timer_tail.diagnostics is self.diagnostics,
             'TIMER_SHARED_COMPOSITION')
        index=START_UNITS.index(TIMER)
        for prefix in ('start_','active_','post_active_'):self.contract.pop(prefix+'%02d'%index)
        self.runner=ExactCommandRunner(self.contract,self._live_forward,self.diagnostics)

    def bind_legacy(self,legacy):
        from epoch7_host_containment import BoundLegacyFiles
        need(self.legacy is None and isinstance(legacy,BoundLegacyFiles) and
             legacy.context==self.context and legacy.diagnostics is self.diagnostics,
             'RUNTIME_CONCRETE_SHARED_GATEWAY_RESTORE')
        self.legacy=legacy

    def _boot_evidence(self,row):
        need(self.legacy is not None,'RUNTIME_GATEWAY_RESTORE_BOUND')
        restored=self.legacy.restoration_evidence()
        need(restored is not None and restored['reload'] is not None,'RUNTIME_GATEWAY_RESTORE_COMPLETE')
        return dict(row,successful_commands=copy.deepcopy(self.successful_commands),
                    gateway_restoration=restored)

    def _create(self,name,row):
        if name=='runtime-boot.json':row=self._boot_evidence(row)
        return super(DeferredRenewalRuntime,self)._create(name,row)

    def _save(self,name,before,after):
        if name=='runtime-boot.json':after=self._boot_evidence(after)
        return super(DeferredRenewalRuntime,self)._save(name,before,after)

    def _command(self,key,runner=None,capture_profile=False):
        result=super(DeferredRenewalRuntime,self)._command(key,runner,capture_profile)
        if runner is None and self.phase=='activate_new_services':
            spec=self.contract[key]
            if spec['operation'] in ('daemon_reload','service_start'):
                from epoch7_service_roles import argv_hash
                need(result.returncode==0,'SERVICE_SUCCESS_RETURN_CODE')
                receipt={'context_sha256':self.context['context_sha256'],'phase':self.phase,
                    'operation':spec['operation'],'argv_sha256':argv_hash(spec['argv']),
                    'sequence':self.diagnostics.sequence,'returncode':0}
                label='daemon_reload' if spec['operation']=='daemon_reload' else spec['argv'][-1]
                need(label not in self.successful_commands,'SERVICE_SUCCESS_NO_REPLAY')
                self.successful_commands[label]=receipt
                # A guard inside publication may inspect the just-captured
                # successful command. Only activation effect guards allow that
                # pending state; phase boundaries require this exact durable map.
                if __import__('os').path.lexists(self._path('runtime-boot.json')):
                    before=self._read('runtime-boot.json')
                    self._save('runtime-boot.json',before,dict(before))
        return result

    def activate_new_services(self,context,diagnostics):
        self._enter(context,diagnostics,'activate_new_services')
        need(self.timer_authorized is True,'RENEWAL_TIMER_REVIEW_REQUIRED')
        self._descriptor('ACTIVE')
        from owner_feishu_https import installed_binding
        need(installed_binding()['package_sha256']==MANIFEST,'OWNER_BINDING_RELEASE')
        self._command('daemon_reload');self._command('nginx_test');self._enable_boot()
        for index,unit in enumerate(START_UNITS):
            if unit==TIMER:continue
            self._command('start_%02d'%index);self._command('active_%02d'%index)
            if unit==GATEWAY_SERVICE:self._inspect('inspect_activate')
        return self._result(self.phase,{'services_active_except_retained_tls_timer':True,
            'retained_renewal_timer_scheduled':False,'direct_tls_issue_renew_dry_run_commands':0})

    def post_install_checks(self,context,diagnostics):
        self._enter(context,diagnostics,'post_install_checks');self._descriptor('ACTIVE')
        for index,unit in enumerate(START_UNITS):
            if unit!=TIMER:self._command('post_active_%02d'%index)
        self._inspect('inspect_post')
        checked=check_observation(self.postcheck(copy.deepcopy(context),diagnostics),context,self.phase)
        need(self._live_forward(),'TIMER_LAST_FULL_LIVE_GUARD')
        # All long work is done. Only these fixed bounded commands may follow.
        scheduled=self.timer_tail.activate(context,diagnostics)
        return observation(context,self.phase,d.digest({'acceptance':checked,'timer':scheduled}))
