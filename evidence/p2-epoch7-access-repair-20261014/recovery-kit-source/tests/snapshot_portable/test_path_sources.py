"""Private bounded-source and selected-PATH fixtures; no host commands."""
import base64
import contextlib
import copy
import io
import os
import pathlib
import stat
import sys
import types
import unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate')]
import epoch7_snapshot as c
import snapshot_io as s
import unit_metadata as u
from test_unit_metadata import Fake,NODE,ENTRY,SECRET
from test_probe_metadata import packed,h

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.io=Fake();self.io.absent=lambda path:path not in self.io.files
        self.io.add('/etc/nginx/mime.types',b'types {\n text/html html htm;\n application/json json;\n}\n',mode=0o644)
        self.package=os.path.dirname(ENTRY)+'/package.json'
        self.io.add(self.package,packed({'name':'openclaw','version':'2026.10.1','bin':{'openclaw':'openclaw.mjs'},'engines':{'node':'>=22'}}),uid=1002,gid=1002,mode=0o644)
        self.io.add(ENTRY,b'import "./child.mjs";\nconsole.log("public source");\n',uid=1002,gid=1002,mode=0o644)
        self.child=os.path.dirname(ENTRY)+'/child.mjs';self.io.add(self.child,b'export const safe = 1;\n',uid=1002,gid=1002,mode=0o644)
        self.facts={'sections':{'launcher':{'evidence':{'sha256':h('launcher'),'recipe':{'entry_script':ENTRY}}}}}
    def collect(self):return u.collect_source_review_inputs(self.io,self.facts)
    def test_only_exact_literal_package_entry_and_child_read(self):
        r=self.collect();self.assertEqual(r['state'],'COMPLETE_UNREVIEWED')
        e=r['sections']['openclaw_literal_sources']['evidence'];self.assertEqual(set(e['files']),{ENTRY,self.child})
        self.assertEqual(base64.b64decode(e['files'][ENTRY]['private_content_base64']),self.io.files[ENTRY])
        self.assertEqual(e['source_closure'],'NOT_VERIFIED');self.assertEqual(e['topology_state'],'ISOLATED_STARTUP_VERIFICATION_REQUIRED')
        self.assertEqual(set(path for path,limit in self.io.reads),{'/etc/nginx/mime.types',self.package,ENTRY,self.child})
        self.assertEqual(r['public_source_output'],'FORBIDDEN')
    def test_package_private_fields_not_returned(self):
        value=c.decode(self.io.files[self.package]);value['token']=SECRET
        self.io.add(self.package,packed(value),uid=1002,gid=1002,mode=0o644)
        self.assertNotIn(SECRET.encode(),packed(self.collect()))
    def test_credential_literal_source_omitted(self):
        self.io.add(self.child,('const token = "'+SECRET+'";\n').encode(),uid=1002,gid=1002,mode=0o644)
        e=self.collect()['sections']['openclaw_literal_sources']['evidence'];row=e['files'][self.child]
        self.assertEqual(row['reason'],'OPENCLAW_LITERAL_SECRET_PATTERN');self.assertNotIn('private_content_base64',row)
        self.assertNotIn(base64.b64encode(SECRET.encode()),packed(e))
    def test_computed_external_and_escape_imports_aggregate(self):
        self.io.add(ENTRY,b'import x from "external-module"; import("../../escape.mjs"); import(dynamic);\n',uid=1002,gid=1002,mode=0o644)
        e=self.collect()['sections']['openclaw_literal_sources']['evidence'];reasons={x['reason'] for x in e['unresolved']}
        self.assertEqual(reasons,{'OPENCLAW_EXTERNAL_DEPENDENCY_NOT_FOLLOWED','OPENCLAW_LITERAL_IMPORT_ESCAPE','OPENCLAW_COMPUTED_IMPORT_UNSUPPORTED'})
        self.assertEqual(set(e['files']),{ENTRY})
    def test_missing_child_keeps_other_captured_inputs(self):
        del self.io.files[self.child];r=self.collect();e=r['sections']['openclaw_literal_sources']['evidence']
        self.assertEqual(e['files'][self.child]['state'],'UNKNOWN');self.assertIn('private_content_base64',e['files'][ENTRY])
    def test_no_literal_entry_is_explicit_no_crawl(self):
        self.facts['sections']['launcher']['evidence'].pop('recipe');r=self.collect()
        self.assertIn('openclaw_literal_sources',r['unsupported_sections'])
        self.assertEqual({path for path,limit in self.io.reads},{'/etc/nginx/mime.types'})
    def test_package_name_and_authority_fail_closed(self):
        self.io.add(self.package,packed({'name':'not-openclaw','version':'1'}),uid=1002,gid=1002)
        self.assertIn('openclaw_literal_sources',self.collect()['unsupported_sections'])
        self.setUp();self.io.metadata[self.package]['mode']=0o666
        self.assertIn('openclaw_literal_sources',self.collect()['unsupported_sections'])
    def test_mime_extra_directive_or_secret_text_rejected(self):
        for raw in (b'types { text/html html; }\ninclude /etc/secret;',b'types { password SECRET; }',b'types { text/html html }'):
            self.io.add('/etc/nginx/mime.types',raw,mode=0o644)
            r=self.collect();self.assertIn('nginx_mime_types',r['unsupported_sections'])
            self.assertNotIn('evidence',r['sections']['nginx_mime_types'])
    def test_depth_bound_does_not_execute_or_crawl(self):
        for n in range(5):
            name=ENTRY if n==0 else os.path.dirname(ENTRY)+'/d%d.mjs'%n
            self.io.add(name,('import "./d%d.mjs";\n'%(n+1)).encode(),uid=1002,gid=1002,mode=0o644)
        e=self.collect()['sections']['openclaw_literal_sources']['evidence']
        self.assertEqual(len(e['files']),4);self.assertIn('OPENCLAW_CLOSURE_COUNT_OR_DEPTH_BOUND',{x['reason'] for x in e['unresolved']})
    def exact_release(self):
        self.io.add(self.package,packed({'name':'openclaw','version':'2026.9.9','bin':{'openclaw':'openclaw.mjs'},'engines':{'node':'>=22'}}),uid=1002,gid=1002,mode=0o644)
        self.io.add(ENTRY,b'await tryImport("./dist/entry.js");\nawait tryImport("./dist/entry.mjs");\n',uid=1002,gid=1002,mode=0o644)
        self.built=os.path.dirname(ENTRY)+'/dist/entry.js';self.build_info=os.path.dirname(ENTRY)+'/dist/build-info.json'
        self.io.add(self.built,b'export const built = true;\n',uid=1002,gid=1002,mode=0o644)
        self.io.add(self.build_info,packed({'version':'2026.9.9','commit':'a'*40,'secret':SECRET}),uid=1002,gid=1002,mode=0o644)
    def test_exact_2026_9_9_tryimport_candidates_and_public_build_fields(self):
        self.exact_release();e=self.collect()['sections']['openclaw_literal_sources']['evidence'];known=e['known_2026_9_9_inputs']
        self.assertIn(self.built,e['files']);self.assertEqual(known['entry_candidates'][self.built]['state'],'CAPTURED_UNREVIEWED')
        self.assertEqual(known['entry_candidates'][self.built[:-2]+'mjs']['state'],'ABSENT')
        self.assertEqual(known['build_info']['public_fields'],{'version':'2026.9.9','commit':'a'*40})
        self.assertNotIn(SECRET.encode(),packed(e));self.assertEqual(e['source_closure'],'NOT_VERIFIED')
    def test_wrong_package_version_or_bin_does_not_add_known_paths(self):
        self.exact_release();value=c.decode(self.io.files[self.package]);value['version']='2026.10.1'
        self.io.add(self.package,packed(value),uid=1002,gid=1002,mode=0o644);self.collect()
        self.assertNotIn(self.built,[path for path,limit in self.io.reads])
        self.io.reads=[];value['version']='2026.9.9';value['bin']['openclaw']='other.mjs'
        self.io.add(self.package,packed(value),uid=1002,gid=1002,mode=0o644);e=self.collect()['sections']['openclaw_literal_sources']['evidence']
        self.assertEqual(e['known_2026_9_9_inputs']['state'],'UNKNOWN');self.assertNotIn(self.build_info,[path for path,limit in self.io.reads])
    def test_known_built_absence_and_unsupported_build_info_aggregate(self):
        self.exact_release();del self.io.files[self.built]
        self.io.add(self.build_info,packed({'version':'wrong','commit':'not-a-commit'}),uid=1002,gid=1002,mode=0o644)
        e=self.collect()['sections']['openclaw_literal_sources']['evidence']
        self.assertEqual(e['known_2026_9_9_inputs']['build_info']['state'],'UNKNOWN')
        self.assertIn('OPENCLAW_2026_9_9_BOTH_ENTRIES_ABSENT',{row['reason'] for row in e['unresolved']})
    def test_legitimate_large_package_and_actual_engine_range_fit_bounds(self):
        self.exact_release();package=c.decode(self.io.files[self.package])
        package.update(description='x'*145276,engines={'node':'>=24.16.0 <25 || >=26.1.0'})
        self.io.add(self.package,packed(package),uid=1002,gid=1002,mode=0o644)
        e=self.collect()['sections']['openclaw_literal_sources']['evidence']
        self.assertGreater(e['package']['metadata']['size'],145276)
        self.assertNotIn('description',e['package']['public_fields'])
        self.assertLess(e['source_bytes'],33554432)

class PathTests(unittest.TestCase):
    def setUp(self):
        self.io=object.__new__(s.LocalReadOnlyIO);self.io.deadline=999999999
        self.io.check_locks=lambda:None;self.io.probe_manager=lambda:{'identity':'fixture'}
        def read(path,maximum):
            raw=b'\x7fELFfixture';return raw,{'uid':0,'gid':0,'mode':0o755,'sha256':c.sha(raw),'dev':1,'ino':2}
        self.io.read=read
        self.io.directory=lambda path:{'uid':0,'gid':0,'mode':0o755,'dev':1,'ino':3}
        self.io.absent=lambda path:path!='/usr/bin/git'
    def collect(self,raw=b'PATH=/usr/local/bin:/usr/bin\nSECRET=private-do-not-return\n'):
        with mock.patch.object(s,'bounded_query',return_value=raw) as query,mock.patch.object(s.os.path,'realpath',side_effect=lambda path:path):
            value=self.io.dispatcher_manager_path();return value,query.call_args_list
    def test_only_selected_path_preserved_exact_query(self):
        value,calls=self.collect();self.assertEqual(value['path_environment'],'/usr/local/bin:/usr/bin')
        self.assertEqual(value['entries'][0]['git'],None);self.assertEqual(value['entries'][1]['git']['path'],'/usr/bin/git')
        self.assertNotIn(b'private-do-not-return',packed(value));self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][0][0],['/usr/bin/systemctl','show-environment'])
        self.assertEqual(value['provenance']['distro_matching_build'],'NOT_VERIFIED')
    def test_missing_duplicate_or_unapproved_path_rejected(self):
        for raw in (b'SECRET=x\n',b'PATH=/usr/bin\nPATH=/usr/bin\n',b'PATH=/home/xuanjun_dev/bin:/usr/bin\n',b'PATH=/usr/bin:/usr/bin\n',b'PATH=:/usr/bin\n'):
            with self.assertRaises(ValueError):self.collect(raw)
    def test_shadow_binary_missing_and_noncanonical_fail(self):
        self.io.absent=lambda path:False
        with self.assertRaisesRegex(ValueError,'SHADOWED'):self.collect()
        self.io.absent=lambda path:True
        with self.assertRaisesRegex(ValueError,'MISSING'):self.collect()
        with mock.patch.object(s,'bounded_query',return_value=b'PATH=/bin\n'),mock.patch.object(s.os.path,'realpath',return_value='/usr/bin'):
            with self.assertRaisesRegex(ValueError,'NONCANONICAL'):self.io.dispatcher_manager_path()
    def test_unit_environment_names_only_and_override_rejection(self):
        e=u.path_override_evidence(b'[Service]\nEnvironment="LANG=C" "TOKEN=private-secret"\nExecStart=/fixed/program\n')
        self.assertEqual(e['environment_names'],['LANG','TOKEN']);self.assertNotIn(b'private-secret',packed(e))
        for directive in ('Environment=PATH=/bad','EnvironmentFile=/etc/secret','PassEnvironment=PATH','PAMName=login','BindPaths=/other:/usr','UnsetEnvironment=PATH','RootDirectory=/other'):
            with self.assertRaises(ValueError):u.path_override_evidence(('[Service]\n'+directive+'\n').encode())
    def test_manager_ids_are_numeric_not_root_nss(self):
        value=s.manager_ids(b'Uid: 0 0 0 0\nGid: 0 0 0 0\nGroups: 42 0\n')
        self.assertEqual(value,{'uids':[0]*4,'gids':[0]*4,'groups':[0,42]})
        for raw in (b'Uid: 0 0 0 0\nGid: 1 1 1 1\nGroups: 0\n',b'Uid: 0 0 0 0\nGid: 0 0 0 0\n',b'Uid: 0 0 0 0\nGid: 0 0 0 0\nGroups: private\n'):
            with self.assertRaises(ValueError):s.manager_ids(raw)

if __name__=='__main__':unittest.main()
