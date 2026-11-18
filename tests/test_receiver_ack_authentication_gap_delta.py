"""Contract probe only: a stored receiver ack is not authenticated identity."""
import sqlite3, unittest
from task_supervisor import Supervisor

class ReceiverAckAuthenticationGap(unittest.TestCase):
    def test_stored_receiver_identifiers_are_caller_supplied(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('''CREATE TABLE tasks(task_id TEXT PRIMARY KEY, authority_state TEXT,
          attempt_id TEXT, resource_scope_digest TEXT, coverage_digest TEXT,
          spec_sha256 TEXT, checkpoint_sha256 TEXT, receiver_ack_sha256 TEXT,
          receiver_ack_json TEXT, updated_at REAL)''')
        db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)',
                   ('task-1','REVOKED','old','scope','coverage','spec','checkpoint','UNKNOWN','{}',1))
        db.commit();s=Supervisor.__new__(Supervisor);s.db=db;s.clock=lambda:2
        ack={'schema':1,'task_id':'task-1','old_attempt_id':'old',
          'new_attempt_id':'new','new_owner':'unverified-owner','new_entry':'entry',
          'new_caller_id':'unverified-caller','new_run_id':'unverified-run',
          'new_session_id':'unverified-session','new_lease_id':'unverified-lease',
          'new_gateway_id':'unverified-gateway','new_lock_provider_id':'provider',
          'resource_scope_digest':'scope','coverage_digest':'coverage',
          'spec_sha256':'spec','checkpoint_sha256':'checkpoint'}
        result=s.record_receiver_ack('task-1',ack)
        self.assertFalse(result['duplicate'])
        self.assertEqual(db.execute('SELECT receiver_ack_json FROM tasks').fetchone()[0].find('unverified-session')>=0,True)
        self.assertTrue(s.record_receiver_ack('task-1',ack)['duplicate'])
        db.close()

if __name__=='__main__':unittest.main()
