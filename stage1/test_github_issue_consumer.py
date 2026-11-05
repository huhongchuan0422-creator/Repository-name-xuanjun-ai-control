import os
import sqlite3
import tempfile
import unittest
from github_issue_consumer import collect, ingest

R='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
def issue(n,state='open'):
    return {'number':n,'title':'Task '+str(n),'state':state,'updated_at':'2026-10-11T01:00:00Z'}
class Tests(unittest.TestCase):
    def test_pull_requests_filtered(self):
        self.assertEqual(collect([dict(issue(4),pull_request={}),issue(13)]),[(13,'Task 13','open','2026-10-11T01:00:00Z')])
    def test_closed_filtered(self):
        self.assertEqual(collect([issue(1,'closed')]),[])
    def test_invalid_shape(self):
        with self.assertRaises(ValueError): collect({})
    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            db=os.path.join(d,'x.sqlite')
            self.assertEqual(ingest(db,R,[issue(13)]),1)
            self.assertEqual(ingest(db,R,[issue(13)]),0)
            con=sqlite3.connect(db)
            self.assertEqual(con.execute('select count(*) from github_issue_intake').fetchone()[0],1)
            self.assertEqual(con.execute('select intake_state from github_issue_intake').fetchone()[0],'INTAKE_READY')
            con.close()
    def test_does_not_execute_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            db=os.path.join(d,'x.sqlite')
            ingest(db,R,[issue(13)])
            con=sqlite3.connect(db)
            self.assertNotIn('tasks',[r[0] for r in con.execute("select name from sqlite_master where type='table'")])
            con.close()
if __name__=='__main__':unittest.main()
