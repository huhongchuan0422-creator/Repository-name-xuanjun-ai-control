import json,sqlite3,unittest
import test_correction_rules as fixtures
from task_supervisor_runtime import CorrectionObserver
from task_center_app import make_server
class ObserverTests(unittest.TestCase):
 setUp=fixtures.CorrectionRulesTests.setUp
 tearDown=fixtures.CorrectionRulesTests.tearDown
 def snapshot(self):
  return {t:[tuple(r) for r in self.s.db.execute('SELECT * FROM '+t)] for t in ('tasks','events','outbox','supervisor_heartbeats')}
 def test_observe_rules_query_only_no_business_write(self):
  before=self.snapshot();self.s.db.execute('PRAGMA query_only=ON')
  result=self.s.correction_rules(observe_only=True)
  self.assertEqual('OBSERVATION_ONLY',result['state']);self.assertEqual(before,self.snapshot())
 def test_existing_loop_hook_and_interval_without_new_thread(self):
  before=self.snapshot();clock=[1000.];o=CorrectionObserver(self.s.path,300,clock=lambda:clock[0])
  o.tick();first=o.last_report
  self.assertEqual('OBSERVATION_ONLY',o.status['state']);clock[0]+=299;o.tick();self.assertIs(first,o.last_report)
  clock[0]+=1;o.tick();self.assertIsNot(first,o.last_report);self.assertEqual(before,self.snapshot())
 def test_http_factory_default_off_and_explicit_original_hook(self):
  before=self.snapshot();server=make_server(self.s.path,b'x'*32,'tenant','owner','127.0.0.1',0)
  try:
   self.assertIsNone(server.correction_observer);server.service_actions()
  finally:server.server_close()
  server=make_server(self.s.path,b'x'*32,'tenant','owner','127.0.0.1',0,correction_observer_interval=180)
  try:
   server.service_actions();self.assertEqual('OBSERVATION_ONLY',server.correction_observer.status['state'])
   self.assertEqual(180,server.correction_observer.status['interval'])
  finally:server.server_close()
  self.assertEqual(before,self.snapshot())
 def test_bad_interval_rejected_before_server_start(self):
  for n in (True,60,301):
   with self.assertRaises(ValueError):make_server(self.s.path,b'x'*32,'tenant','owner','127.0.0.1',0,correction_observer_interval=n)
 def test_missing_db_hold_no_creation(self):
  import os
  path=self.tmp.name+'/absent';o=CorrectionObserver(path);o.tick()
  self.assertEqual('HOLD_OBSERVATION_SOURCE_UNAVAILABLE',o.status['state']);self.assertFalse(os.path.exists(path))
if __name__=='__main__':unittest.main()

class ObserverBoundsTests(unittest.TestCase):
 setUp=ObserverTests.setUp
 tearDown=ObserverTests.tearDown
 snapshot=ObserverTests.snapshot
 def test_oversize_json_is_unknown_without_decoding_or_writes(self):
  self.s.db.execute("UPDATE tasks SET dependencies_json=? WHERE task_id='task'",('['+' '*5000+']',));self.s.db.commit();before=self.snapshot()
  o=CorrectionObserver(self.s.path);o.tick()
  self.assertEqual('HOLD_OBSERVATION_SOURCE_UNAVAILABLE',o.status['state']);self.assertIsNone(o.last_report);self.assertEqual(before,self.snapshot())
 def test_malformed_source_type_cannot_escape_original_http_loop(self):
  self.s.db.execute("UPDATE tasks SET dependencies_json='3' WHERE task_id='task'");self.s.db.commit();before=self.snapshot()
  server=make_server(self.s.path,b'x'*32,'tenant','owner','127.0.0.1',0,correction_observer_interval=300)
  try:
   server.service_actions();self.assertEqual('HOLD_OBSERVATION_SOURCE_UNAVAILABLE',server.correction_observer.status['state'])
  finally:server.server_close()
  self.assertEqual(before,self.snapshot())
 def test_task_count_bound_returns_unknown_not_partial_success(self):
  for i in range(16):
   self.s.register(dict(task_id='extra'+str(i),parent_task_id='parent',stage='dev',owner='developer',entry='WORK',checkpoint_sha256='a'*64,spec_sha256='b'*64,next_action='implement',dependencies=[],completion_conditions=['tests'],progress_deadline=2000,receipt_deadline=1500,started_deadline=1800,terminal_deadline=4000,handoff_deadline=3000),now=self.now)
  before=self.snapshot();o=CorrectionObserver(self.s.path);o.tick()
  self.assertEqual('HOLD_OBSERVATION_SOURCE_UNAVAILABLE',o.status['state']);self.assertIsNone(o.last_report);self.assertEqual(before,self.snapshot())
