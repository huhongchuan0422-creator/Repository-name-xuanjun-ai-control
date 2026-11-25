"""Synthetic formal admin only; no live credentials or grant management calls."""
import hashlib,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
import task_center_app as app
from task_center_handoff_runtime import HostIdentityProvider
import test_handoff_canonical_backend_delta as fixture

class BindingProjection(unittest.TestCase):
    write_config=fixture.CanonicalBackend.write_config
    setUp=fixture.CanonicalBackend.setUp
    query='/api/admin/handoff-binding-status?task_id=demo-b&attempt_id=attempt-1&principal_id=alice'

    def handler(self,enabled=True,provider=None):
        identity=provider or HostIdentityProvider('tenant-1',self.backend)
        captured=[]
        class Stop(Exception):pass
        def intercept(*args,**kwargs):
            captured.append(app.build_handler(args[0],args[1],args[2],args[3],
                identity_provider=args[10],session_store=args[11],
                handoff_binding_projection_enabled=kwargs['handoff_binding_projection_enabled']))
            raise Stop()
        with patch.object(app,'make_server',side_effect=intercept):
            with self.assertRaises(Stop):app.main(self.argv,identity_provider=identity,session_store=self.sessions,
                handoff_binding_projection_enabled=enabled)
        return captured[0]

    def call(self,handler,path=None,token=True):
        h=handler.__new__(handler);h.path=path or self.query;h.command='GET'
        h.headers={'Host':'localhost:8765'};h.server=SimpleNamespace(server_port=8765)
        if token:h.headers['Cookie']=self.sessions.COOKIE+'='+self.token
        out=[];h._send=lambda status,body,kind,extra_headers=None:out.append((status,json.loads(body)))
        with patch.object(h,'_model_control',side_effect=AssertionError('must not construct mutating control')):
            h.do_GET()
        return out[0]

    def test_original_main_route_is_default_off(self):
        self.assertEqual(self.call(self.handler(False))[0],404)

    def test_formal_admin_reads_bounded_facts_no_tokens_or_writes(self):
        before=self.root.joinpath('task-center.sqlite').read_bytes()
        status,value=self.call(self.handler());self.assertEqual(status,200)
        self.assertTrue(value['formal_profile']);self.assertTrue(value['unique_current_session'])
        self.assertTrue(value['unique_enabled_assignment']);self.assertTrue(value['live_handoff_read_grant'])
        self.assertFalse(value['authority_created']);self.assertEqual(value['readiness'],'FACTS_ONLY_NOT_AUTHORIZATION')
        raw=json.dumps(value)
        self.assertNotIn(self.session['session_hash'],raw);self.assertNotIn(self.token,raw)
        self.assertNotIn('csrf',raw);self.assertNotIn('granted_by',raw)
        self.assertEqual(before,self.root.joinpath('task-center.sqlite').read_bytes())

    def test_anonymous_viewer_filetest_and_revoked_source_do_not_get_projection(self):
        handler=self.handler();self.assertEqual(self.call(handler,token=False)[0],403)
        self.s.db.execute("UPDATE task_center_sessions SET roles_json='[\"TASK_CENTER_VIEWER\"]'");self.s.db.commit()
        self.assertEqual(self.call(handler)[0],403)
        self.s.db.execute("UPDATE task_center_sessions SET roles_json='[\"TASK_CENTER_ADMIN\"]'");self.s.db.commit()
        fake=app.FileTestIdentityProvider.__new__(app.FileTestIdentityProvider)
        self.assertEqual(self.call(self.handler(provider=fake))[0],403)
        self.provider.active=False;self.assertEqual(self.call(handler)[0],403)

    def test_exact_query_tenant_attempt_and_missing_schema_are_fail_closed(self):
        handler=self.handler()
        self.assertEqual(self.call(handler,self.query+'&roles=admin')[0],400)
        self.assertEqual(self.call(handler,self.query+'&task_id=demo-b')[0],400)
        self.assertEqual(self.call(handler,self.query.replace('attempt-1','other'))[0],404)
        self.assertEqual(self.call(handler,self.query.replace('demo-b','not-this-tenant'))[0],404)
        self.s.db.execute('DROP TABLE formal_approval_roles');self.s.db.commit()
        self.assertEqual(self.call(handler)[0],503)

    def test_grant_absence_is_a_fact_not_authority_and_source_rechecked_before_disclosure(self):
        handler=self.handler()
        self.s.db.execute("DELETE FROM formal_approval_roles WHERE approval_kind='handoff:READ'");self.s.db.commit()
        status,value=self.call(handler);self.assertEqual(status,200)
        self.assertFalse(value['live_handoff_read_grant']);self.assertIsNone(value['grant_valid_until'])
        import task_center_binding_projection as projection
        original=projection.read_binding_status
        def revoke(*args,**kwargs):
            value=original(*args,**kwargs);self.provider.active=False;return value
        with patch.object(projection,'read_binding_status',side_effect=revoke):
            status,value=self.call(handler)
        self.assertEqual(status,403);self.assertNotIn('current_session_count',value)
