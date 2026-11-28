"""Synthetic provider tests, NOT evidence of installed real usage or billing."""
import io
import json
import unittest
from test_model_orchestration import ModelOrchestrationTests as Fixture
from model_orchestration import OpenAICompatibleAdapter, ModelControl, ModelScheduler

class MeteringTests(unittest.TestCase):
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    provider=Fixture.provider
    model=Fixture.model
    role=Fixture.role
    qualify=Fixture.qualify
    assigned=Fixture.assigned

    def parsed(self, usage):
        body={'id':'synthetic-request','choices':[{'message':{'content':'synthetic'}}],
              'usage':usage}
        return OpenAICompatibleAdapter(opener=lambda *a,**k:io.BytesIO(
          json.dumps(body).encode())).invoke('http://localhost','synthetic-key','fixture',[],1)

    def execute(self, result):
        self.assigned()
        request=self.control.queue_request('demo-b','developer',[], 'metering-case')
        class Adapter:
            def invoke(self,*a,**k):return result
        done=ModelScheduler(self.control,{'openai-compatible':Adapter()}).run_once()
        self.assertEqual(done['state'],'SUCCEEDED')
        return request

    def test_provider_fields_overlap_and_task_readback(self):
        result=self.parsed({'prompt_tokens':10,'completion_tokens':6,'total_tokens':16,
          'prompt_tokens_details':{'cached_tokens':4},
          'completion_tokens_details':{'reasoning_tokens':2}})
        request=self.execute(result)
        view=self.control.finance_usage_readback('demo-b')
        self.assertEqual(len(view['resource_attempts']),1)
        row=view['resource_attempts'][0]
        self.assertEqual((row['input_tokens'],row['output_tokens'],row['cached_tokens'],row['reasoning_tokens']),(10,6,4,2))
        self.assertEqual(row['request_id'],request['request_id'])
        self.assertEqual(row['task_id'],'demo-b')
        self.assertEqual(row['attempt_id'],'attempt-b')
        self.assertIsNone(view['customer_receivable'])
        self.assertIsNone(view['collected'])
        # Internal free model must not infer the customer's contract price.
        self.assertEqual(view['customer_rule_state'],'NOT_CONNECTED')
        self.assertEqual(view['conversion'],'NONE')
        self.assertTrue(self.control.queue_request('demo-b','developer',[], 'metering-case')['duplicate'])
        self.assertEqual(len(self.control.finance_usage_readback('demo-b')['resource_attempts']),1)

    def test_absent_usage_is_unknown_not_zero(self):
        self.execute(self.parsed({}))
        row=self.control.finance_usage_readback('demo-b')['resource_attempts'][0]
        for name in ('input_tokens','output_tokens','cached_tokens','reasoning_tokens','cost_value'):
            self.assertIsNone(row[name])
        self.assertEqual(row['cost_state'],'UNKNOWN')

    def test_optional_detail_does_not_block_business(self):
        result=self.parsed({'prompt_tokens':3,'completion_tokens':2,'total_tokens':5,
          'prompt_tokens_details':{'cached_tokens':30}})
        self.assertIsNone(result['usage']['cached_tokens'])
        self.execute(result)

    def test_cross_tenant_or_missing_task_cannot_read(self):
        self.execute(self.parsed({}))
        other=ModelControl(self.gateway,self.other,self.master)
        with self.assertRaises((ValueError,KeyError)):
            other.finance_usage_readback('demo-b')
        with self.assertRaises((ValueError,KeyError)):
            self.control.finance_usage_readback('tampered-task')

    def test_native_receipt_usage_and_failed_attempt_are_attributed(self):
        from test_model_fallback_delta import RuntimeFixture
        class Runtime(RuntimeFixture):
            def receipt(self, context):
                out=super().receipt(context)
                out['usage']={'input_tokens':11,'output_tokens':5,
                  'cached_tokens':4,'reasoning_tokens':3,'not_allowed':'ignored'}
                out['actualRoute']={'provider':'synthetic-native','model':'fixture',
                  'billingRoute':'oauth-subscription'}
                return out
        self.assigned()
        runtime=Runtime();runtime.response='FAILED'
        self.control.gateway_runtime=runtime
        self.control.queue_request('demo-b','developer',[], 'native-meter',dispatch_mode='gateway-native')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'FAILED')
        rows=self.control.finance_usage_readback('demo-b')['resource_attempts']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['input_tokens'],11)
        self.assertEqual(rows[0]['outcome'],'FAILED')
        self.assertEqual(rows[0]['billing_route'],'oauth-subscription')
        self.assertIsNone(rows[0]['cost_value'])
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'IDLE')
        self.assertEqual(len(self.control.finance_usage_readback('demo-b')['resource_attempts']),1)

    def test_native_receipt_without_usage_records_unknown(self):
        from test_model_fallback_delta import RuntimeFixture
        self.assigned();self.control.gateway_runtime=RuntimeFixture()
        self.control.queue_request('demo-b','developer',[], 'native-unknown',dispatch_mode='gateway-native')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'SUCCEEDED')
        row=self.control.finance_usage_readback('demo-b')['resource_attempts'][0]
        self.assertIsNone(row['input_tokens'])
        self.assertIsNone(row['cost_value'])
        self.assertEqual(row['provider_id'],'UNKNOWN')

    def test_native_unknown_query_enriches_same_attempt_without_rebooking(self):
        from test_model_fallback_delta import RuntimeFixture
        class Runtime(RuntimeFixture):
            def receipt(self,context):
                out=super().receipt(context)
                if self.response=='SUCCEEDED':
                    out['usage']={'input_tokens':8,'output_tokens':3}
                return out
        self.assigned();runtime=Runtime();runtime.response='THROW'
        self.control.gateway_runtime=runtime
        self.control.queue_request('demo-b','developer',[], 'native-recovery',dispatch_mode='gateway-native')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'UNKNOWN')
        self.assertIsNone(self.control.finance_usage_readback('demo-b')['resource_attempts'][0]['input_tokens'])
        runtime.response='SUCCEEDED'
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'SUCCEEDED')
        rows=self.control.finance_usage_readback('demo-b')['resource_attempts']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['input_tokens'],8)
        self.assertEqual(len(runtime.calls),1)
        self.assertEqual(len(runtime.queries),1)

if __name__=='__main__':unittest.main()
