"""Offline synthetic Gateway bootstrap families; no process or source execution."""
import copy
import hashlib
import pathlib
import unittest
HERE=pathlib.Path(__file__).resolve().parent
import epoch7_service_roles as sr
from test_epoch7_service_roles import fixture2
import epoch7_live_controls as live
import os

GATEWAY='xuanjun-uk-openclaw.service'


class GatewayUnionTests(unittest.TestCase):
    def setUp(self):
        self.context,self.contract,self.view=fixture2()
        block=self.contract['service_role_contract']['units'][GATEWAY]
        main=block['roles'][0]
        self.parent_argv=[main['identity']['executable'],'/fixture/openclaw.mjs','gateway','--port','18789']
        self.child_argv=[main['identity']['executable'],'/fixture/physical/openclaw.mjs','gateway','--port','18789']
        main['command']={'mode':'EXACT_ARGV_OR_NUL_PADDED_TITLES',
            'sha256':sr.argv_hash(self.parent_argv),'values':['openclaw','openclaw-gateway']}
        child=copy.deepcopy(main);child.update(name='compile_cache_child',main=False,parent={'kind':'ROLE','role':'main'})
        child['command']['sha256']=sr.argv_hash(self.child_argv);block['roles'].append(child)
        import epoch7_openclaw_recipe as oc
        root='/home/xuanjun_dev/.openclaw/tools/node/lib/node_modules/openclaw'
        quiet={'schema':1,'package_root':root,'selected_environment':dict({key:None for key in oc.ENV_KEYS},HOME='/home/xuanjun_dev'),
            'config_projection':{'env_shell_enabled':False,'proxy_enabled':False,'proxy_url_present':False,'include_present':False},
            'package_absence':{name:'ABSENT' for name in oc.ABSENT},'node_exec_argv':[],
            'relay_environment':{'HOME':'/home/xuanjun_dev','PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}}
        block['quiet_startup']=quiet;block['sources'].update({root+'/'+name:pin for name,pin in oc.SOURCE_HASHES.items()})
        self.view['service_role_evidence']['units'][GATEWAY]['quiet_startup']=copy.deepcopy(quiet)
        self.view['service_role_evidence']['units'][GATEWAY]['sources']=copy.deepcopy(block['sources'])
        for point in self.contract['checkpoints']:
            if point['units'][GATEWAY]['main_required']:point['units'][GATEWAY]['main_role_sha256']=live.digest(main)
        self.main=self.view['units'][GATEWAY]['before']['MainPID']
        self.command(self.main,argv=self.parent_argv)

    def command(self,pid,argv=None,title=None):
        raw=b'\0'.join(x.encode() for x in argv)+b'\0' if argv is not None else title.encode()+b'\0'*7
        for when in ('before','after'):
            self.view['processes'][str(pid)][when]['argv_sha256']=hashlib.sha256(raw).hexdigest()
            row=self.view['service_role_evidence']['processes'][str(pid)][when]
            row.update(cmdline_title=title,cmdline_size=len(raw))

    def add_child(self,pid=None):
        pid=pid or self.main+20000
        row=copy.deepcopy(self.view['processes'][str(self.main)])
        for when in ('before','after'):row[when].update(pid=pid,starttime=pid+90000)
        self.view['processes'][str(pid)]=row
        meta=copy.deepcopy(self.view['service_role_evidence']['processes'][str(self.main)])
        for when in ('before','after'):
            meta[when].update(ppid=self.main,parent_starttime=self.view['processes'][str(self.main)][when]['starttime'])
        self.view['service_role_evidence']['processes'][str(pid)]=meta
        self.view['units'][GATEWAY]['cgroups']['/sys/fs/cgroup/systemd/system.slice/'+GATEWAY+'/cgroup.procs'].append(pid)
        self.view['pids_before']=self.view['pids_after']=sorted(int(x) for x in self.view['processes'])
        self.command(pid,argv=self.child_argv)
        return pid

    def check(self):
        live.validate_contract(self.contract,self.context)
        return live.validate_process_view(self.view,self.contract,self.contract['checkpoints'][16],os.getpid(),
            context_sha256=self.context['context_sha256'],checkpoint_index=16)

    def test_exact_initial_argv_then_both_exact_titles(self):
        self.check()
        for title in ('openclaw','openclaw-gateway'):
            self.command(self.main,title=title);self.check()

    def test_optional_direct_child_uses_separately_derived_argv(self):
        child=self.add_child();self.check()
        self.command(child,title='openclaw-gateway');self.check()

    def test_child_does_not_inherit_unreviewed_parent_argv_hash(self):
        child=self.add_child();self.command(child,argv=self.parent_argv)
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()

    def test_second_child_exceeds_maximum(self):
        self.add_child();self.add_child(self.main+20001)
        with self.assertRaisesRegex(ValueError,'COUNT_EXCEEDED'):self.check()

    def test_child_sibling_or_reparenting_is_not_allowed(self):
        child=self.add_child()
        for when in ('before','after'):
            self.view['service_role_evidence']['processes'][str(child)][when].update(
                ppid=1,parent_starttime=self.view['processes']['1'][when]['starttime'])
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE|SAME_CGROUP_PARENT'):self.check()

    def test_main_title_spoof_cannot_match_raw_hash(self):
        self.command(self.main,title='openclaw-gateway')
        for when in ('before','after'):self.view['processes'][str(self.main)][when]['argv_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()

    def test_foreign_title_suffix_is_rejected(self):
        self.command(self.main,title='openclaw-gateway --extra')
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()

    def test_changed_child_executable_inode_is_rejected(self):
        child=self.add_child()
        for when in ('before','after'):self.view['service_role_evidence']['processes'][str(child)][when]['executable_ino']+=1
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()

    def test_union_cannot_be_used_for_nginx(self):
        block=self.contract['service_role_contract']['units']['nginx.service']
        block['roles'][0]['command']=copy.deepcopy(self.contract['service_role_contract']['units'][GATEWAY]['roles'][0]['command'])
        with self.assertRaisesRegex(ValueError,'GATEWAY_FINITE_BOOTSTRAP_UNION'):self.check()

    def test_third_same_node_role_is_refused_in_contract(self):
        block=self.contract['service_role_contract']['units'][GATEWAY]
        extra=copy.deepcopy(block['roles'][1]);extra.update(name='extra')
        extra['command']={'mode':'EXACT_ARGV_SHA256','sha256':'1'*64};block['roles'].append(extra)
        with self.assertRaisesRegex(ValueError,'TWO_NODE'):self.check()

    def test_missing_own_start_still_refused(self):
        self.view['service_role_evidence']['units'][GATEWAY]['start']=None
        with self.assertRaisesRegex(ValueError,'RECEIPT_SCHEMA'):self.check()


if __name__=='__main__':unittest.main()
