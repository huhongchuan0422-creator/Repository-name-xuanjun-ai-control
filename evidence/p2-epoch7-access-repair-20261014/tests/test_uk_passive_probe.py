"""Collector tests use fixture reads only; never query actual host services."""
import ast
import errno
import json
import os
import subprocess
import sys
import unittest
import time
from unittest import mock
from design import uk_passive_probe as probe


class FixtureBackend(object):
    def __init__(self): self.calls=[]; self.fail=None
    def metadata(self,path):
        self.calls.append(('metadata',path))
        if self.fail: raise self.fail
        return {'status':'PASS_OBSERVED','kind':'file','uid':0,'gid':0,'mode':0o644,
                'dev':1,'inode':10,'nlink':1,'size':1,'acl':{'status':'ABSENT'}}
    def unit(self,unit,properties=probe.PROPERTIES):
        self.calls.append(('unit',unit))
        if self.fail: raise self.fail
        return {'Id':unit,'LoadState':'loaded','ActiveState':'inactive','SubState':'dead',
                'MainPID':'0','FragmentPath':'/etc/systemd/system/'+unit,'DropInPaths':''}
    def read(self,path,maximum):
        self.calls.append(('read',path))
        if self.fail: raise self.fail
        if path==probe.ACTIVATION:
            return json.dumps({'state':'ACTIVE','epoch':8,'ledger_uuid':'uuid',
                'secret_should_not_print':'never-output-this'}).encode()
        if path.endswith('/boot_id'): return b'12345678-1234-1234-1234-123456789abc\n'
        if path.endswith('/stat'): return ('1 (systemd) S '+'0 '*18+'123 0 0').encode()
        if path.endswith('/status'): return b'Name:\tprivate-name\nUid:\t0 0 0 0\nCapEff:\t0000\n'
        if path.endswith('/cmdline'): return b'/usr/lib/systemd/systemd\0SECRET_ARG=never-output-this\0'
        if path.endswith('/cgroup'): return b'1:name=systemd:/init.scope\n'
        if path=='/proc/net/unix': return b'Num RefCount Protocol Flags Type St Inode Path\n'
        return b'[Service]\nEnvironment=SECRET=never-output-this\n'
    def link(self,path):
        self.calls.append(('link',path)); return '/usr/lib/systemd/systemd'


class PassiveProbeTests(unittest.TestCase):
    def test_fixed_passive_report_with_no_secret_contents(self):
        backend=FixtureBackend(); report=probe.collect(backend)
        raw=probe.encode_report(report)
        self.assertIs(report['no_effects'],True)
        self.assertFalse(report['production_admission'])
        self.assertEqual(report['mode'],'PASSIVE_METADATA_ONLY')
        self.assertNotIn(b'never-output-this',raw)
        self.assertNotIn(b'private-name',raw)
        self.assertEqual(set(report['units']),set(probe.UNITS))
        self.assertTrue(all(not path.startswith('/etc/xuanjun-owner-callback/')
            for method,path in backend.calls if method=='read'))
    def test_release_client_config_and_generation_are_metadata_only(self):
        targets={'/opt/xuanjun-control-releases', '/etc/xuanjun-development',
            '/etc/xuanjun-development/p2-native-ledger-client.json',
            '/etc/xuanjun-development/dispatcher.json',
            '/var/lib/xuanjun-development/generations',
            '/var/lib/xuanjun-development/generations/1',
            '/var/lib/xuanjun-development/generations/1/state.sqlite'}
        self.assertTrue(targets.issubset(set(probe.FIXED_PATHS)))
        backend=FixtureBackend(); report=probe.collect(backend)
        self.assertTrue(targets.issubset(set(report['paths'])))
        self.assertFalse(any(method=='read' and path in targets for method,path in backend.calls))
    def test_masked_and_inactive_units_never_require_live_process_evidence(self):
        backend=FixtureBackend(); original=backend.unit
        def unit(name,properties=probe.PROPERTIES):
            value=original(name,properties)
            if name=='xuanjun-ledger.service': value['LoadState']='masked'
            return value
        backend.unit=unit; report=probe.collect(backend)
        masked=report['units']['xuanjun-ledger.service']
        self.assertEqual(masked['status'],'NOT_VERIFIED')
        self.assertEqual(masked['properties']['LoadState'],'masked')
        inactive=report['units']['xj-root-broker.service']
        self.assertEqual(inactive['process']['reason'],'UNIT_NOT_ACTIVE')
        self.assertFalse(any(method=='read' and path.startswith('/proc/0/') for method,path in backend.calls))
    def test_missing_socket_does_not_infer_peer_or_access(self):
        backend=FixtureBackend(); original=backend.metadata
        def metadata(path):
            if path in probe.SOCKETS: raise FileNotFoundError(errno.ENOENT,'missing')
            return original(path)
        backend.metadata=metadata
        report=probe.collect(backend)
        self.assertTrue(all(report['paths'][p]['status']=='NOT_VERIFIED' for p in probe.SOCKETS))
        self.assertEqual(report['creator_peercred']['status'],'NOT_VERIFIED')
        self.assertEqual(report['actual_dashboard_connect']['status'],'NOT_VERIFIED')
    def test_permission_denials_are_bounded_metadata(self):
        backend=FixtureBackend(); backend.fail=PermissionError(errno.EACCES,'secret-error-data')
        report=probe.collect(backend); raw=probe.encode_report(report)
        self.assertNotIn(b'secret-error-data',raw)
        self.assertEqual(report['pid1']['errno'],errno.EACCES)
    def test_global_budget_exhaustion_stops_provider_work(self):
        backend=FixtureBackend(); backend.fail=probe.ProbeLimit()
        report=probe.collect(backend)
        self.assertEqual(report['pid1']['reason'],'DEADLINE_OR_SIZE_BOUND')
    def test_untrusted_unit_path_is_never_read(self):
        backend=FixtureBackend(); original=backend.unit
        def unit(name,properties=probe.PROPERTIES):
            result=original(name,properties); result['FragmentPath']='/etc/shadow'; return result
        backend.unit=unit
        report=probe.collect(backend)
        self.assertFalse(any(method=='read' and path=='/etc/shadow' for method,path in backend.calls))
        self.assertEqual(report['units'][probe.UNITS[0]]['files']['/etc/shadow']['status'],'NOT_VERIFIED')
    def test_unit_path_allowlist(self):
        unit='xuanjun-ledger.service'
        self.assertTrue(probe.valid_unit_file('/etc/systemd/system/'+unit,unit))
        self.assertTrue(probe.valid_unit_file('/etc/systemd/system/'+unit+'.d/10-identity.conf',unit))
        for path in ('/etc/shadow','/etc/systemd/system/../shadow',
                     '/etc/systemd/system/'+unit+'.d/../../shadow'):
            self.assertFalse(probe.valid_unit_file(path,unit))
    def test_socket_map_keeps_inode_namespace_and_unknown_creator(self):
        raw=b'000: 000 000 00010000 0001 01 777 /run/xuanjun-development/ledger.sock\n'
        value=probe.socket_map(raw)
        self.assertEqual(value['entries'][0]['kernel_socket_inode'],777)
        self.assertEqual(value['creator_credentials'],'NOT_VERIFIED')
    def test_output_size_is_bounded_failclosed(self):
        raw=probe.encode_report({'oversized':'x'*probe.MAX_OUTPUT})
        self.assertLess(len(raw),probe.MAX_OUTPUT)
        self.assertEqual(json.loads(raw.decode())['reason'],'TOTAL_OUTPUT_BOUND')
    def test_process_restart_is_unverified(self):
        backend=FixtureBackend(); original=backend.read; count=[0]
        def read(path,maximum):
            raw=original(path,maximum)
            if path.endswith('/stat'):
                count[0]+=1
                if count[0]>1: raw=raw.replace(b'123 0 0',b'124 0 0')
            return raw
        backend.read=read
        self.assertEqual(probe.process_evidence(backend,1)['reason'],'PROCESS_LIFETIME_CHANGED')
    def test_help_and_version_do_not_collect(self):
        for argument in ('--help','--version'):
            result=subprocess.run([sys.executable,'-B',probe.__file__,argument],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertLess(len(result.stdout),8192)
    def test_cli_rejects_arbitrary_paths(self):
        result=subprocess.run([sys.executable,'-B',probe.__file__,'--path','/etc/shadow'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn(b'PASSIVE_METADATA_ONLY',result.stdout)
    def run_fixture_child(self, script, budget=1):
        backend=probe.Backend(); backend.end=time.monotonic()+budget
        real_popen=subprocess.Popen
        calls=[]
        def child(argv,**kwargs):
            calls.append(argv)
            self.assertEqual(argv[:4],['/usr/bin/systemctl','show','--no-pager',
                '--property='+','.join(probe.PROPERTIES)])
            self.assertIn(argv[4],probe.UNITS)
            return real_popen([sys.executable,'-B','-c',script],**kwargs)
        with mock.patch.object(probe.subprocess,'Popen',side_effect=child):
            result=backend.unit(probe.UNITS[0])
        return result,calls
    def test_manager_reader_only_executes_fixed_show_argv(self):
        value,calls=self.run_fixture_child("print('Id=xuanjun-ledger.socket\\nLoadState=loaded')")
        self.assertEqual(value['LoadState'],'loaded')
        self.assertEqual(len(calls),1)
    def test_manager_reader_kills_slow_fixture_at_deadline(self):
        started=time.monotonic()
        with self.assertRaises(probe.ProbeLimit):
            self.run_fixture_child('import time; time.sleep(10)',budget=0.05)
        self.assertLess(time.monotonic()-started,1)
    def test_manager_reader_rejects_oversized_output(self):
        with self.assertRaises(probe.ProbeLimit):
            self.run_fixture_child("print('x'*20000)")
    def test_source_has_no_socket_or_mutating_service_api(self):
        with open(probe.__file__) as stream: tree=ast.parse(stream.read())
        imported=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): imported.extend(alias.name for alias in node.names)
            if isinstance(node,ast.ImportFrom): imported.append(node.module)
        self.assertNotIn('socket',imported)
        self.assertNotIn('sqlite3',imported)
        with open(probe.__file__) as stream: source=stream.read()
        self.assertNotIn("'start',",source); self.assertNotIn("'restart',",source)
        self.assertNotIn('os.chmod(',source); self.assertNotIn('os.chown(',source)


if __name__=='__main__': unittest.main()
