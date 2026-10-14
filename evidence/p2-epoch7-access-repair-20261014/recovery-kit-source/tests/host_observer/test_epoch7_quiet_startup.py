"""Concrete quiet reader orchestration with only host-read boundaries mocked."""
import copy
import types
import unittest
from unittest import mock
import epoch7_quiet_startup as q
import epoch7_delta as d
from openclaw_metadata import quiet_projection,dotenv_paths,ENV_KEYS
from unit_metadata import UNITS


class QuietTests(unittest.TestCase):
    def make(self):
        value=object.__new__(q.BoundedQuietStartup);value.authority=mock.Mock()
        manager={'fixture':'exact measured manager'}
        value.census=types.SimpleNamespace(_manager=mock.Mock(return_value=manager),manager_pin=manager)
        value.deadline=None;value.phase=None;value.relay_metadata=None
        value.bind_resource_views([{'targets':[{'path':q.RELAY,'kind':'FILE','uid':0,'gid':1002,'mode':0o640}]} for unused in range(17)])
        selected={name:None for name in ENV_KEYS};selected['HOME']='/home/xuanjun_dev'
        value._environment=mock.Mock(return_value=selected)
        account={'user':'xuanjun_dev','uid':1002,'gid':1002,'home':'/home/xuanjun_dev'}
        root='/home/xuanjun_dev/tools/lib/node_modules/openclaw';node='/home/xuanjun_dev/tools/bin/node'
        unit=b'[Service]\nUser=xuanjun_dev\nGroup=xuanjun_dev\nExecStart=/home/xuanjun_dev/.openclaw/bin/openclaw gateway --port 18789\n'
        wrapper=('#!/bin/sh\nexec '+node+' '+root+'/openclaw.mjs "$@"\n').encode()
        profile=d.canonical({'agents':{},'plugins':{},'env':{'shellEnv':{'enabled':False}},'proxy':{'enabled':False}})
        relay=d.canonical({'openclaw_bin':q.LAUNCHER,'openclaw_sha256':q.sha(wrapper),'openclaw_owner_uid':1002,
            'gateway_home':'/home/xuanjun_dev','gateway_path':'/usr/bin:/bin','dispatcher_user':'xuanjun-dispatcher'})
        raw={q.BACKUP:unit,q.BASE:unit,q.LAUNCHER:wrapper,q.snap.PROFILE:profile,q.RELAY:relay}
        inventory={u:{root+'/'+u+'.d':{'present':False,'files':{}} for root in
            ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')} for u in UNITS}
        def metadata(path):return {'kind':'FILE','uid':1002 if path in (q.LAUNCHER,q.snap.PROFILE) else 0,
            'gid':1002 if path in (q.LAUNCHER,q.snap.PROFILE,q.RELAY) else 0,
            'mode':0o640 if path==q.RELAY else 0o600,'nlink':1,'ino':1,'sha256':q.sha(raw[path])}
        io=mock.Mock();io.read.side_effect=lambda path,maximum:(raw[path],metadata(path))
        io.absent.side_effect=lambda path:path not in raw
        io.gateway_account_home.return_value=account;io.unit_dropins.side_effect=lambda *args:copy.deepcopy(inventory)
        io.mask.return_value={'kind':'MASK','link':'/dev/null','ino':2};value.io=io
        projected=quiet_projection(selected,account,unit,wrapper,node,profile,{p:None for p in dotenv_paths(unit)},relay)
        wanted={'schema':1,'package_root':root,'package_absence':{name:'ABSENT' for name in q.ABSENT}}
        wanted.update({k:projected[k] for k in ('selected_environment','config_projection','node_exec_argv','relay_environment')})
        block={'quiet_startup':wanted,'sources':{q.BASE:q.sha(unit),q.LAUNCHER:q.sha(wrapper)},
               'roles':[{'identity':{'executable':node}}]}
        return value,{q.GATEWAY:block},raw,inventory
    def observe(self,value,blocks):
        with mock.patch.object(q.time,'monotonic',return_value=10):return value.observe(blocks,'install_verified_plugin',30)
    def test_config_can_change_outside_quiet_projection_after_owned_plugin_edit(self):
        value,blocks,raw,unused=self.make();before=self.observe(value,blocks)
        config=q.snap.decode(raw[q.snap.PROFILE]);config['plugins']={'entries':{'p2-native-controller':{'enabled':True}}}
        raw[q.snap.PROFILE]=d.canonical(config)
        self.assertEqual(self.observe(value,blocks),before)
    def test_restored_base_is_observed_when_mask_is_gone(self):
        value,blocks,raw,unused=self.make();value.io.mask.side_effect=ValueError('regular file')
        self.assertEqual(self.observe(value,blocks),blocks[q.GATEWAY]['quiet_startup'])
        self.assertTrue(any(call[0][0]==q.BASE for call in value.io.read.call_args_list))
    def test_relay_uses_exact_reviewed_service_readable_metadata(self):
        value,blocks,raw,unused=self.make()
        self.assertEqual(self.observe(value,blocks),blocks[q.GATEWAY]['quiet_startup'])
        for key,changed in (('uid',1002),('gid',0),('gid',1003),('mode',0o600),('mode',0o664)):
            value,blocks,raw,unused=self.make();original=value.io.read.side_effect
            def read(path,maximum):
                data,row=original(path,maximum)
                if path==q.RELAY:row[key]=changed
                return data,row
            value.io.read.side_effect=read
            with self.subTest(key=key,changed=changed),self.assertRaisesRegex(ValueError,'FILE_AUTHORITY'):
                self.observe(value,blocks)
    def test_relay_metadata_requires_complete_invariant_bound_views(self):
        good={'targets':[{'path':q.RELAY,'kind':'FILE','uid':0,'gid':1002,'mode':0o640}]}
        for kind in ('missing','duplicate','changed','unsafe','unbound'):
            value,blocks,raw,unused=self.make();value.relay_metadata=None
            views=[copy.deepcopy(good) for index in range(17)]
            if kind=='missing':views[7]['targets']=[]
            elif kind=='duplicate':views[7]['targets']*=2
            elif kind=='changed':views[7]['targets'][0]['gid']=1003
            elif kind=='unsafe':
                for view in views:view['targets'][0]['mode']=0o666
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                if kind=='unbound':self.observe(value,blocks)
                else:value.bind_resource_views(views)
    def test_proxy_shell_env_preload_or_unknown_package_artifact_holds(self):
        for kind in ('proxy','shell','preload','package'):
            value,blocks,raw,unused=self.make()
            if kind in ('proxy','shell'):
                config=q.snap.decode(raw[q.snap.PROFILE])
                if kind=='proxy':config['proxy']['enabled']=True
                else:config['env']['shellEnv']['enabled']=True
                raw[q.snap.PROFILE]=d.canonical(config)
            elif kind=='preload':value._environment.return_value['NODE_OPTIONS']='--require=evil'
            else:raw[blocks[q.GATEWAY]['quiet_startup']['package_root']+'/.git']=b'present'
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.observe(value,blocks)
    def test_unknown_dropin_or_credentials_never_get_skipped(self):
        value,blocks,raw,inventory=self.make();root='/run/systemd/system/'+q.GATEWAY+'.d'
        inventory[q.GATEWAY][root]={'present':None,'state':'UNKNOWN','files':{}}
        with self.assertRaisesRegex(ValueError,'UNKNOWN_DROPIN'):self.observe(value,blocks)
        value,blocks,raw,inventory=self.make()
        inventory[q.GATEWAY][root]={'present':True,'files':{root+'/override.conf':(
            b'[Service]\nEnvironment=NODE_OPTIONS=evil\n',{'uid':0,'gid':0,'nlink':1})}}
        with self.assertRaisesRegex(ValueError,'DROPIN_SERVICE_DIRECTIVE'):self.observe(value,blocks)
    def test_changed_source_and_late_environment_are_not_accepted(self):
        value,blocks,raw,unused=self.make();raw[q.LAUNCHER]+=b'# drift\n'
        with self.assertRaisesRegex(ValueError,'WRAPPER_SOURCE_PIN'):self.observe(value,blocks)
        value,blocks,raw,unused=self.make();before=value._environment.return_value
        value._environment.side_effect=[before,dict(before,OPENCLAW_PROFILE='other')]
        with self.assertRaisesRegex(ValueError,'LATE_ENVIRONMENT'):self.observe(value,blocks)
    def test_selected_output_bounded_unique_and_does_not_return_unrelated_secret(self):
        value=q.BoundedQuietStartup.selected_environment(b'UNRELATED_SECRET=never-return\nHOME=/home/xuanjun_dev\n')
        self.assertEqual(set(value),set(ENV_KEYS));self.assertNotIn('never-return',str(value))
        for raw in (b'HOME=x\nHOME=y\n',b'x'*65537,b'HOME="unterminated'):
            with self.assertRaises(ValueError):q.BoundedQuietStartup.selected_environment(raw)
    def test_expired_guard_does_not_query_environment(self):
        value,blocks,raw,unused=self.make()
        with mock.patch.object(q.time,'monotonic',return_value=31),self.assertRaisesRegex(ValueError,'DEADLINE'):
            value.observe(blocks,'install_verified_plugin',30)
        value._environment.assert_not_called();value.io.read.assert_not_called()

if __name__=='__main__':unittest.main()
