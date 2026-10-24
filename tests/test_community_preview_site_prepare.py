"""Post-receipt correction and proposed carrier/reasons, no site execution."""
import ast
import hashlib
import io
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from email.message import Message
from unittest.mock import patch
from scripts import community_preview_release_plan as plan
from scripts import community_preview_update_composition as comp
from scripts import community_preview_preupdate_bundle as bundle
from scripts import community_preview_three_diagnostics as diag
from scripts import community_preview_root_loader as loader
from scripts import community_preview_control_carrier as carrier

GOOD='2330dd55c07f58d7f45a7c4510a9761d0d4735d6'
BAD='2330dd55c07f58d7f45a7c4510a97610dd4735d6'

class SitePreparation(unittest.TestCase):
    def test_exact_git_oci_and_strict_rejection_of_old_typo(self):
        import test_community_preview_release_plan as f
        self.assertEqual(plan.OBSERVED_OCI,GOOD);self.assertEqual(comp.plan.OBSERVED_OCI,GOOD)
        c=f.current();c['oci_revision']=BAD
        with self.assertRaisesRegex(ValueError,'CURRENT_OCI_DIFF'):plan.current_identity(c)
        c['oci_revision']=GOOD;self.assertEqual(plan.current_identity(c)['oci_revision'],GOOD)
        self.assertEqual(comp.PINS[plan],hashlib.sha256(Path(plan.__file__).read_bytes()).hexdigest())
    def test_refreshed_bundles_pin_only_exact_corrected_sources(self):
        python,shell=bundle.build();three,three_shell=bundle.build_three()
        for content in (python,three):ast.parse(content,feature_version=(3,6))
        for content in (shell,three_shell):self.assertEqual(subprocess.run(['/bin/bash','-n'],input=content,capture_output=True,timeout=3).returncode,0)
        self.assertEqual(three,Path('deploy/community-preview/three-reasons-readonly.py').read_bytes())
        self.assertEqual(three_shell,Path('deploy/community-preview/three-reasons-readonly.sh').read_bytes())
        for path,pin in bundle.PINS.items():self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),pin)
    def test_private_root_and_missing_header_rejected_by_actual_trust_method_ast(self):
        # Execute exact original trust class AST, avoiding unrelated crypto/IAM
        # dependencies. Real trust logic, synthetic socket peer/header only.
        src=Path('scripts/pr122_customer_source.py').read_text();tree=ast.parse(src)
        nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TrustedNginxSource']
        ns=dict(socket=socket,struct=struct,Denied=PermissionError,HEADER='X-Xuanjun-Client-IP',normalize=lambda s:s)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<original-trust>','exec'),ns)
        trust=ns['TrustedNginxSource'](1008)
        peer=types.SimpleNamespace(family=socket.AF_UNIX,getsockopt=lambda *a:struct.pack('3i',1,0,0));headers=Message()
        with self.assertRaisesRegex(PermissionError,'NGINX_PEER_REQUIRED'):trust(peer,headers)
        peer.getsockopt=lambda *a:struct.pack('3i',1,1008,1008)
        with self.assertRaisesRegex(PermissionError,'SINGLE_PROXY_ORIGIN_REQUIRED'):trust(peer,headers)
        self.assertNotIn('setuid',diag.PRIVATE_DIAGNOSTIC);self.assertNotIn('X-Xuanjun-Client-IP',diag.PRIVATE_DIAGNOSTIC)
    def test_private_diagnostic_403_enum_not_body_or_acceptance(self):
        body=json.dumps(dict(error='PROXY_DENIED',secret='NEVER_RELAY')).encode().hex()
        with patch.object(diag.base.v,'capture',return_value=json.dumps(dict(http_status=403,body_hex=body))):
            value=diag.private_health();self.assertEqual(value['http_status'],403);self.assertEqual(value['error_enum'],'PROXY_DENIED')
            self.assertNotIn('NEVER_RELAY',json.dumps(value));self.assertFalse(value['private_origin_header_sent'])
    def test_bounded_reason_enums_never_expose_unknown_error_text(self):
        self.assertEqual(diag.reason(RuntimeError('SECRET=/private/key')),'UNCLASSIFIED_UNKNOWN')
        self.assertEqual(diag.reason(diag.base.v.Hold('COMMAND_REJECTED')),'COMMAND_REJECTED')
        self.assertEqual(diag.reason(RuntimeError('CONTAINER_SCOPE_CHANGED')),'CONTAINER_SCOPE_CHANGED')
        with patch.object(diag.base.v,'capture',side_effect=diag.base.v.Hold('COMMAND_TIMEOUT')):
            r=diag.one('CURRENT',diag.projected_current)
        self.assertEqual(r['stage'],'CURRENT_NAME_ID_LOOKUP');self.assertEqual(r['reason'],'COMMAND_TIMEOUT')
    def test_current_recheck_field_difference_is_bounded_names_only(self):
        a=dict(container_id='a'*64,image_id='sha256:'+'b'*64,oci_revision=GOOD,observed_at=1,routing_sha256='c'*64)
        b=dict(a,observed_at=2,routing_sha256='d'*64)
        with patch.object(diag,'projected_current',side_effect=[a,b]):r=diag.current_recheck()
        self.assertEqual(r['changed_fields'],['routing_sha256']);self.assertEqual(r['status'],'HOLD_CHANGED')
        self.assertNotIn('d'*64,json.dumps(r))
    def test_carrier_exact_files_modes_manifest_and_disabled_default(self):
        archive,raw=carrier.build();m=json.loads(raw);z=zipfile.ZipFile(io.BytesIO(archive))
        self.assertEqual(m['install_root'],loader.INSTALL_ROOT);self.assertFalse(m['updates_enabled'])
        self.assertEqual(set(z.namelist()),loader.PATHS|{'manifest.json'})
        for p,meta in m['files'].items():
            b=z.read(p);self.assertEqual(hashlib.sha256(b).hexdigest(),meta['sha256']);self.assertEqual(len(b),meta['bytes'])
            self.assertEqual(meta['uid'],0);self.assertEqual(meta['mode'],'0600');self.assertEqual((z.getinfo(p).external_attr>>16)&0o777,0o600)
        self.assertEqual(raw,Path('deploy/community-preview/control-oci2330-v1-manifest.json').read_bytes())
        ast.parse(Path(loader.__file__).read_text(),feature_version=(3,6))
        with patch.object(loader.os,'geteuid',return_value=1000),patch.object(loader,'read_file') as read:
            with self.assertRaises(loader.Hold):loader.load(hashlib.sha256(raw).hexdigest())
            read.assert_not_called()
    def child_loader(self,tamper=False,symlink=False):
        archive,raw=carrier.build()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/loader.INSTALL_ROOT.lstrip('/');target.mkdir(parents=True,mode=0o700)
            z=zipfile.ZipFile(io.BytesIO(archive))
            for p in z.namelist():
                q=target/p;q.parent.mkdir(parents=True,exist_ok=True,mode=0o700);q.write_bytes(z.read(p));q.chmod(0o600);os.utime(q,(1,1))
            for d in target.rglob('*'):
                if d.is_dir():d.chmod(0o700)
            if tamper:(target/'scripts/community_preview_release_plan.py').write_bytes(b'corrupt')
            if symlink:
                q=target/'scripts/community_preview_release_plan.py';q.unlink();q.symlink_to('/etc/passwd')
            code="""import os,sys,types
ns={'__name__':'isolated_root_loader'}
exec(compile(open(sys.argv[1]).read(),sys.argv[1],'exec'),ns)
ns['ROOT_ANCHOR']=sys.argv[2];ns['ROOT_UID']=os.getuid()
os.getuid=lambda:0;os.geteuid=lambda:0;os.uname=lambda:types.SimpleNamespace(nodename=ns['HOST'])
try:
 m=ns['load'](sys.argv[3]);print('LOADED:'+m.plan.OBSERVED_OCI)
except Exception as error:print('HOLD:'+type(error).__name__+':'+str(error))
"""
            r=subprocess.run([sys.executable,'-I','-B','-S','-c',code,str(Path(loader.__file__).resolve()),tmp,hashlib.sha256(raw).hexdigest()],capture_output=True,text=True,timeout=8)
            self.assertEqual(r.returncode,0,r.stderr);return r.stdout.strip()
    def test_proposed_root_carrier_real_isolated_load_without_update(self):
        self.assertEqual(self.child_loader(),'LOADED:'+GOOD)
    def test_proposed_root_carrier_tampered_or_symlink_source_holds(self):
        self.assertTrue(self.child_loader(tamper=True).startswith('HOLD:'))
        self.assertTrue(self.child_loader(symlink=True).startswith('HOLD:'))
