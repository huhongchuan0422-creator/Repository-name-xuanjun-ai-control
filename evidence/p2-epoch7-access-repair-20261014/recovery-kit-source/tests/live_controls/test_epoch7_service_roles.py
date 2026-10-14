"""Pure schema2 fixtures. No systemd, process signals or production paths read."""
import copy
import hashlib
import os
import pathlib
import sys
import unittest
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from test_epoch7_live_controls import fixture,process_view,identity,h
import epoch7_live_controls as live
import epoch7_service_roles as sr


def role(unit,name,uid,exe,title,main,parent,maximum=1):
    return {'unit':unit,'name':name,'identity':{'uids':[uid]*4,'gids':[uid]*4,'groups':[uid],
        'executable':exe,'executable_sha256':h(exe)},'executable_dev':8,'executable_ino':100+uid,
        'command':{'mode':'EXACT_NUL_PADDED_TITLE','values':[title]},'parent':parent,
        'maximum':maximum,'main':main}


def fixture2():
    rig,context,contract,unused=fixture()
    old=process_view(contract,16)
    blocks={}
    for unit,uid,exe,title in [('nginx.service',0,'/usr/sbin/nginx','nginx: master process /usr/sbin/nginx -c /etc/xuanjun-development/nginx-main.conf'),
                             ('xuanjun-uk-openclaw.service',1002,'/home/xuanjun_dev/.openclaw/tools/node/bin/node','fixture-reviewed-gateway')]:
        main=role(unit,'main',uid,exe,title,True,{'kind':'MANAGER','pid':1})
        sources={'/etc/systemd/system/'+unit:h(unit),exe:h(exe)}
        if unit=='nginx.service':
            sources.update({'/etc/xuanjun-development/nginx-main.conf':h('mainconfig'),
                            '/etc/nginx/conf.d/xuanjun-p2-owner.conf':h('ownerconfig')})
            worker=role(unit,'worker',990,exe,'nginx: worker process',False,{'kind':'ROLE','role':'main'},4)
            worker['executable_ino']=main['executable_ino']
            roles=[main,worker]
        else:
            sources.update({'/home/xuanjun_dev/.openclaw/bin/openclaw':h('launcher'),
                            '/etc/xuanjun-development/p2-native-controller.binding.json':h('binding')})
            roles=[main]
        blocks[unit]={'sources':sources,'topology_source_sha256':h(unit),'roles':roles}
    contract['schema']=2;contract['unit_transition_contract']={'schema':1,'targets':{},'units':{}};contract['service_role_contract']={'schema':1,'units':blocks}
    contract['process_roles']=[r for r in contract['process_roles'] if r['unit'] not in blocks]
    for point in contract['checkpoints']:
        for unit,block in blocks.items():
            if point['units'][unit]['main_required']:
                point['units'][unit]['main_role_sha256']=live.digest(block['roles'][0])
    evidence={'context_sha256':context['context_sha256'],'units':{},'processes':{}}
    for index,(unit,block) in enumerate(sorted(blocks.items())):
        main_pid=old['units'][unit]['before']['MainPID'];main=block['roles'][0]
        def add(pid,spec,parent):
            title=spec['command']['values'][0];raw=title.encode()+b'\0'*7
            item=identity(pid,dict(spec['identity'],argv_sha256=hashlib.sha256(raw).hexdigest(),unit=unit))
            old['processes'][str(pid)]={'before':item,'after':copy.deepcopy(item)}
            metadata={'ppid':parent,'parent_starttime':old['processes'][str(parent)]['before']['starttime'],
                'executable_dev':spec['executable_dev'],'executable_ino':spec['executable_ino'],
                'cmdline_title':title,'cmdline_size':len(raw)}
            evidence['processes'][str(pid)]={'before':metadata,'after':copy.deepcopy(metadata)}
        add(main_pid,main,1)
        if unit=='nginx.service':
            child=main_pid+10000;add(child,block['roles'][1],main_pid)
            old['units'][unit]['cgroups']['/sys/fs/cgroup/systemd/system.slice/'+unit+'/cgroup.procs'].append(child)
        def receipt(operation,sequence):
            argv=['/usr/bin/systemctl','daemon-reload'] if operation=='daemon_reload' else ['/usr/bin/systemctl','start',unit]
            return {'context_sha256':context['context_sha256'],'phase':'activate_new_services','operation':operation,
                    'argv_sha256':sr.argv_hash(argv),'sequence':sequence,'returncode':0}
        evidence['units'][unit]={'sources':copy.deepcopy(block['sources']),'reload':receipt('daemon_reload',10),
            'start':receipt('service_start',11+index),'persistence':'PERSISTED'}
    old['pids_before']=old['pids_after']=sorted(int(x) for x in old['processes'])
    old['service_role_evidence']=evidence;old['unit_transition_evidence']=None
    return context,contract,old


class RoleTests(unittest.TestCase):
    def setUp(self):self.context,self.contract,self.view=fixture2()
    def check(self,**kwargs):
        live.validate_contract(self.contract,self.context)
        return live.validate_process_view(self.view,self.contract,self.contract['checkpoints'][16],os.getpid(),
                                         context_sha256=self.context['context_sha256'],checkpoint_index=16,**kwargs)
    def scoped_pid(self,unit='nginx.service',child=False):
        main=self.view['units'][unit]['before']['MainPID']
        return main+10000 if child else main
    def mutate_meta(self,pid,key,value):
        for when in ('before','after'):self.view['service_role_evidence']['processes'][str(pid)][when][key]=value
    def test_valid_opt_in(self):self.assertEqual(len(self.check()),64)
    def test_schema1_unchanged(self):
        rig,ctx,c,unused=fixture();v=process_view(c,16)
        live.validate_contract(c,ctx);live.validate_process_view(v,c,c['checkpoints'][16],os.getpid())
        v['service_role_evidence']={}
        with self.assertRaises(ValueError):live.validate_process_view(v,c,c['checkpoints'][16],os.getpid())
    def test_no_legacy_exact_role_bypass(self):
        pid=self.scoped_pid();self.contract['process_roles'].append({k:self.view['processes'][str(pid)]['before'][k] for k in live.ROLE_FIELDS})
        with self.assertRaisesRegex(ValueError,'BYPASS'):self.check()
    def test_foreign_cgroup(self):
        pid=self.scoped_pid(child=True)
        for when in ('before','after'):self.view['processes'][str(pid)][when]['unit']=None
        with self.assertRaises(ValueError):self.check()
    def test_sibling_parent(self):
        self.mutate_meta(self.scoped_pid(child=True),'ppid',1)
        self.mutate_meta(self.scoped_pid(child=True),'parent_starttime',self.view['processes']['1']['before']['starttime'])
        with self.assertRaisesRegex(ValueError,'SAME_CGROUP_PARENT'):self.check()
    def test_parent_pid_reuse(self):
        self.mutate_meta(self.scoped_pid(child=True),'parent_starttime',1)
        with self.assertRaisesRegex(ValueError,'STARTTIME'):self.check()
    def test_parent_drift(self):
        self.view['service_role_evidence']['processes'][str(self.scoped_pid(child=True))]['after']['ppid']=1
        with self.assertRaisesRegex(ValueError,'RACE'):self.check()
    def test_wrong_executable_with_valid_title(self):
        for when in ('before','after'):self.view['processes'][str(self.scoped_pid())][when]['executable']='/usr/bin/evil'
        with self.assertRaises(ValueError):self.check()
    def test_wrong_inode_with_valid_hash(self):
        self.mutate_meta(self.scoped_pid(),'executable_ino',999)
        with self.assertRaises(ValueError):self.check()
    def test_title_detached_from_raw_hash(self):
        pid=self.scoped_pid()
        for when in ('before','after'):self.view['processes'][str(pid)][when]['argv_sha256']=h('other argv')
        with self.assertRaises(ValueError):self.check()
    def test_title_suffix_and_prefix_rejected(self):
        for suffix in (' --evil','x'):
            ctx,c,v=fixture2();self.context,self.contract,self.view=ctx,c,v
            self.mutate_meta(self.scoped_pid(),'cmdline_title',self.view['service_role_evidence']['processes'][str(self.scoped_pid())]['before']['cmdline_title']+suffix)
            with self.assertRaises(ValueError):self.check()
    def test_wrong_credentials(self):
        for when in ('before','after'):self.view['processes'][str(self.scoped_pid(child=True))][when]['groups']=[0]
        with self.assertRaises(ValueError):self.check()
    def test_unlisted_child(self):
        self.contract['service_role_contract']['units']['nginx.service']['roles'][1]['command']['values']=['different']
        with self.assertRaises(ValueError):self.check()
    def test_excess_workers(self):
        block=self.contract['service_role_contract']['units']['nginx.service'];block['roles'][1]['maximum']=1
        child=self.scoped_pid(child=True);other=child+1
        row=copy.deepcopy(self.view['processes'][str(child)])
        for when in ('before','after'):row[when]['pid']=other;row[when]['starttime']=999999
        self.view['processes'][str(other)]=row
        self.view['service_role_evidence']['processes'][str(other)]=copy.deepcopy(self.view['service_role_evidence']['processes'][str(child)])
        self.view['units']['nginx.service']['cgroups']['/sys/fs/cgroup/systemd/system.slice/nginx.service/cgroup.procs'].append(other)
        self.view['pids_before']=self.view['pids_after']=sorted(int(x) for x in self.view['processes'])
        with self.assertRaisesRegex(ValueError,'COUNT_EXCEEDED'):self.check()
    def test_cycle_contract(self):
        self.contract['service_role_contract']['units']['nginx.service']['roles'][1]['parent']['role']='worker'
        with self.assertRaises(ValueError):self.check()
    def test_ancestry_cycle_process(self):
        pid=self.scoped_pid(child=True);self.mutate_meta(pid,'ppid',pid)
        self.mutate_meta(pid,'parent_starttime',self.view['processes'][str(pid)]['before']['starttime'])
        with self.assertRaises(ValueError):self.check()
    def test_wrong_context(self):
        self.view['service_role_evidence']['units']['nginx.service']['start']['context_sha256']=h('old attempt')
        with self.assertRaisesRegex(ValueError,'BINDING'):self.check()
    def test_missing_receipt(self):
        self.view['service_role_evidence']['units']['nginx.service']['start']=None
        with self.assertRaises(ValueError):self.check()
    def test_wrong_source(self):
        self.view['service_role_evidence']['units']['nginx.service']['sources']['/etc/xuanjun-development/nginx-main.conf']=h('new config')
        with self.assertRaisesRegex(ValueError,'SOURCE'):self.check()
    def test_start_before_reload(self):
        self.view['service_role_evidence']['units']['nginx.service']['start']['sequence']=9
        with self.assertRaisesRegex(ValueError,'RELOAD_BEFORE'):self.check()
    def test_pending_only_explicit_effect_scope(self):
        self.view['service_role_evidence']['units']['nginx.service']['persistence']='OWN_CAPTURE_PENDING_PUBLICATION'
        with self.assertRaisesRegex(ValueError,'PERSISTED'):self.check()
        self.check(allow_pending_service_receipts=True)
    def test_no_scope_on_third_unit(self):
        block=self.contract['service_role_contract']['units'].pop('nginx.service')
        self.contract['service_role_contract']['units']['xj-root-broker.service']=block
        with self.assertRaises(ValueError):self.check()
    def test_no_implicit_manager_parent(self):
        self.contract['service_role_contract']['units']['nginx.service']['roles'][0]['parent']={'kind':'ANY'}
        with self.assertRaises(ValueError):self.check()
    def test_title_normalizer_keeps_internal_nul_and_controls_invalid(self):
        self.assertEqual(sr.normalized_title(b'nginx: worker process\0\0'),'nginx: worker process')
        for raw in (b'node\0evil',b'abc\n',b'',b'a'*16385):
            with self.assertRaises(ValueError):sr.normalized_title(raw)

if __name__=='__main__':unittest.main()
