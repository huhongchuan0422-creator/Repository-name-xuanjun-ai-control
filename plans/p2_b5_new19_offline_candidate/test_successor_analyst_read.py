import base64
import json
import unittest
from pathlib import Path

from successor_analyst_read import receive_all
from successor_contract import Hold, sha

ROOT = Path(__file__).resolve().parent


class AnalystReadTests(unittest.TestCase):
    def setUp(self):
        spec = json.loads((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        self.catalog = 'a'*64
        self.project = spec['actor']['project']
        self.recipient = spec['actor']['recipient']
        self.objects = []
        self.requests = []
        self.bodies = {}
        self.invokes = {}
        for i, item in enumerate(spec['objects'], 1):
            ref = 'b5-material-%02d'%i
            rid = 'l2-b5-disposable-unit-test-%02d'%i
            body = bytes([i])*item['bytes']
            self.bodies[rid] = body
            self.objects.append(dict(bytes=len(body),sha256=sha(body)))
            self.requests.append(dict(request_id=rid,project=self.project,
                         operation='fetch_approved_object',arguments=dict(
                             manifest_sha256=self.catalog,object_ref=ref,
                             recipient_id=self.recipient)))
            self.invokes[rid] = 'fixture-invoke-%02d'%i
        self.custody = dict(state='MATERIAL_CUSTODY_COMPLETE', objects=19,
                            bytes=93592,catalog_sha256=self.catalog)

    def tool(self, **args):
        rid = args['request_id']
        body = self.bodies[rid]
        return dict(manifest_sha256=self.catalog,project=self.project,
                    request_id=rid,object_ref=args['object_ref'],
                    recipient_id=self.recipient,invoke_id=self.invokes[rid],
                    bytes=len(body),sha256=sha(body),offset=args['offset'],
                    chunk_sha256=sha(body),data=base64.b64encode(body).decode())

    def run_read(self, tool=None):
        return receive_all(requests=self.requests,objects=self.objects,
            catalog_sha=self.catalog,project=self.project,recipient=self.recipient,
            success_invokes=self.invokes,custody=self.custody,
            read_project_chunk=self.tool if tool is None else tool)

    def test_all_exact_bytes_no_close_claim(self):
        result=self.run_read()
        self.assertEqual((result['objects'],result['bytes']),(19,93592))
        self.assertEqual(result['close_approval'],'NOT_PROVEN')
        self.assertEqual(result['state'],
                         'B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING')

    def test_wrong_invoke_or_body_rejected(self):
        def bad_invoke(**args):
            row=self.tool(**args)
            row['invoke_id']='wrong'
            return row
        with self.assertRaisesRegex(Hold,'B5_HTTP_ENVELOPE_BINDING'):
            self.run_read(bad_invoke)
        def bad_byte(**args):
            row=self.tool(**args)
            row['data']=base64.b64encode(b'X'*row['bytes']).decode()
            return row
        with self.assertRaisesRegex(Hold,'B5_HTTP_WHOLE_SHA'):
            self.run_read(bad_byte)

    def test_no_custody_or_missing_success_prevents_first_read(self):
        self.custody['objects']=18
        calls=[]
        with self.assertRaisesRegex(Hold,'B5_ORIGINAL_CUSTODY_NOT_PROVEN'):
            self.run_read(lambda **args:calls.append(args))
        self.assertEqual(calls,[])
        self.custody['objects']=19
        self.invokes.pop(self.requests[0]['request_id'])
        with self.assertRaisesRegex(Hold,'B5_READ_SET'):
            self.run_read(lambda **args:calls.append(args))
        self.assertEqual(calls,[])


if __name__=='__main__':
    unittest.main()
