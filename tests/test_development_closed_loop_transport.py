import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT=pathlib.Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

for name,path in (
    ('task_supervisor',ROOT/'scripts/task_supervisor.py'),
    ('development_closed_loop',ROOT/'scripts/development_closed_loop.py'),
    ('development_closed_loop_transport',ROOT/'scripts/development_closed_loop_transport.py')):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    globals()[name]=module


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.sup=task_supervisor.Supervisor(
            str(pathlib.Path(self.tmp.name)/'s.sqlite'),clock=lambda:100)
        self.sup.register(dict(task_id='task',parent_task_id='parent',
            stage='DELIVERY',owner='owner',entry='CHATGPT',
            checkpoint_sha256='a'*64,spec_sha256='b'*64,
            next_action='DELIVER',dependencies=[],
            completion_conditions=['done'],
            progress_deadline=500,receipt_deadline=500,started_deadline=500,
            terminal_deadline=1000,handoff_deadline=500),now=100)
        self.sup.claim('task','attempt','owner','CHATGPT','run','session',
                       'lease',1,1,now=101)
        self.sup.record('task','attempt','start','STARTED',102,
                        evidence_kind='PHASE_EXECUTION',evidence_ref='start')
        development_closed_loop.record_terminal(
            self.sup,'task','attempt','terminal',103,'terminal',
            'SUCCESS','c'*64,'NONE',['done'])
        self.row=self.sup.due_outbox(now=103)[0]

    def tearDown(self):
        self.sup.close();self.tmp.cleanup()

    def fake(self,mode):
        calls=[];posted=[]
        def run(argv,**kw):
            calls.append((list(argv),kw))
            if argv[-1]=='user':
                value={'login':development_closed_loop_transport.OWNER}
            elif '--method' in argv:
                if mode=='unknown':
                    posted.append(json.loads(kw['input'].decode())['body'])
                    raise TimeoutError('unknown')
                body=json.loads(kw['input'].decode())['body'];posted.append(body)
                value={'id':321,'body':body,'user':{'login':development_closed_loop_transport.OWNER}}
            else:
                marker=development_closed_loop_transport._marker(self.row['outbox_id'])
                envelope=json.dumps({'schema':1,'kind':'TASK45_OUTBOX_DELIVERY',
                    'outbox_id':self.row['outbox_id'],'payload':json.loads(self.row['payload_json'])})
                if mode=='existing' or (mode=='unknown' and posted):
                    value=[[{'id':99,'body':marker+'\n'+envelope,
                             'user':{'login':development_closed_loop_transport.OWNER}}]]
                elif mode=='duplicate':
                    item={'id':99,'body':marker+'\n'+envelope,'user':{'login':development_closed_loop_transport.OWNER}}
                    value=[[item,item]]
                elif mode=='conflict':
                    wrong=json.dumps({'schema':1,'kind':'TASK45_OUTBOX_DELIVERY',
                        'outbox_id':self.row['outbox_id'],'payload':{'different':True}})
                    value=[[{'id':99,'body':marker+'\n'+wrong,
                             'user':{'login':development_closed_loop_transport.OWNER}}]]
                elif mode=='malformed':
                    value=[[{'id':99,'body':marker+'\nnot-json',
                             'user':{'login':development_closed_loop_transport.OWNER}}]]
                else:value=[[]]
            return SimpleNamespace(returncode=0,stdout=json.dumps(value).encode(),stderr=b'')
        return development_closed_loop_transport.FixedPr17Transport(
            gh_bin='/usr/bin/gh',runner=run),calls

    def test_malformed_marker_does_not_ack(self):
        tr,calls=self.fake('malformed')
        result=development_closed_loop_transport.deliver_one(self.sup,tr,103)
        self.assertEqual(result['state'],'DELIVERY_RECONCILE_REQUIRED')
        self.assertFalse(any('--method' in a for a,k in calls))

    def test_conflicting_payload_never_posts_or_acks(self):
        tr,calls=self.fake('conflict')
        result=development_closed_loop_transport.deliver_one(self.sup,tr,103)
        self.assertEqual(result['state'],'DELIVERY_RECONCILE_REQUIRED')
        self.assertFalse(any('--method' in a for a,k in calls))

    def test_missing_required_payload_is_rejected(self):
        tr,calls=self.fake('ok')
        with self.assertRaises(ValueError):
            tr.send({'outbox_id':self.row['outbox_id']})
        self.assertFalse(any('--method' in a for a,k in calls))

    def test_paginated_reconciliation_uses_slurp(self):
        tr,calls=self.fake('existing')
        receipt=tr.reconcile(self.row)
        self.assertEqual(receipt['message_id'],'99')
        self.assertIn('--slurp',calls[0][0])

    def test_send_then_ack_closes_loop(self):
        tr,calls=self.fake('ok')
        result=development_closed_loop_transport.deliver_one(self.sup,tr,103)
        self.assertEqual(result['state'],'DELIVERED_ACKNOWLEDGED')
        self.assertEqual(development_closed_loop.closed_loop_status(
            self.sup,'task')['state'],'DONE')
        self.assertEqual(sum('--method' in a for a,k in calls),1)

    def test_existing_marker_no_second_post(self):
        tr,calls=self.fake('existing')
        result=development_closed_loop_transport.deliver_one(self.sup,tr,103)
        self.assertEqual(result['state'],'DELIVERED_ACKNOWLEDGED')
        self.assertFalse(any('--method' in a for a,k in calls))

    def test_unknown_write_not_blind_retried(self):
        tr,calls=self.fake('unknown')
        result=development_closed_loop_transport.deliver_one(self.sup,tr,103)
        self.assertEqual(result['state'],'DELIVERY_RECONCILE_REQUIRED')
        self.assertEqual(sum('--method' in a for a,k in calls),1)
        later=self.sup.due_outbox(now=result['next_attempt_at'])[0]
        self.assertEqual(later['outbox_id'],self.row['outbox_id'])
        result=development_closed_loop_transport.deliver_one(
            self.sup,tr,result['next_attempt_at'])
        self.assertEqual(result['state'],'DELIVERED_ACKNOWLEDGED')
        self.assertEqual(sum('--method' in a for a,k in calls),1)

    def test_duplicate_marker_holds_and_never_posts(self):
        tr,calls=self.fake('duplicate')
        result=development_closed_loop_transport.deliver_one(self.sup,tr,103)
        self.assertEqual(result['state'],'DELIVERY_RECONCILE_REQUIRED')
        self.assertFalse(any('--method' in a for a,k in calls))

if __name__=='__main__':unittest.main(verbosity=2)
