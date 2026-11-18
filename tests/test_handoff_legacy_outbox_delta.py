"""Old outbox readback compatibility: no migrations, writes or real transport."""
import hashlib, json
from types import SimpleNamespace
from test_handoff_host_delta import HostDelta
from task_center_app import build_handler
from task_center_handoff_host import FormalHandoffIdentityProvider

class LegacyOutbox(HostDelta):
    def test_legacy_outbox_read_and_protected_get_preserve_unknown_without_write(self):
        self.auth.backup={'state':'INCOMPLETE','missing':['RESTORE'],'cycle_at':990}
        req=self.req();self.assertEqual(self.host.record('alice',req)['alert_delivery'],'UNKNOWN')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(outbox)')}
        self.assertNotIn('attempts',columns);self.assertNotIn('last_error',columns)
        def snapshot():return hashlib.sha256('\n'.join(self.db.iterdump()).encode()).hexdigest()
        before=snapshot();view=self.host.read_receipt('alice','task-1','attempt-1',req['event_id'])
        self.assertEqual(view['alert_delivery'],'UNKNOWN');self.assertEqual(view['history'][0]['alert_delivery'],'UNKNOWN')
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(this,token):return 'alice' if token=='good' else None
            def verify_csrf(this,session,token):return token=='good'
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(this,session):return session=='alice'
        handler=build_handler(self.path,b'0'*32,'tenant-1','viewer',identity_provider=Identity(),session_store=Sessions(),handoff_host=self.host)
        def get(cookie):
            h=handler.__new__(handler);h.command='GET';h.path='/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id='+req['event_id'];h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765','Cookie':'session='+cookie};out=[]
            h._send=lambda status,data,kind,extra_headers=None:out.append((status,json.loads(data)));h.do_GET();return out[0]
        status,body=get('good');self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN')
        self.assertEqual(get('bad')[0],401);self.assertEqual(before,snapshot())
        self.assertEqual(columns,{r[1] for r in self.db.execute('PRAGMA table_info(outbox)')})
