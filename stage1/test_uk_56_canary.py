import importlib.util
import os
import unittest
import io
from unittest.mock import patch, mock_open

spec = importlib.util.spec_from_file_location('fallback_canary', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'uk-56-canary.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CanaryTests(unittest.TestCase):
    def main_with(self, auth):
        calls = []
        def command(args, timeout=40):
            calls.append(args)
            if args[:3] == ['models', 'auth', 'list']:
                return 0, auth, 'UNKNOWN'
            return 0, {}, 'UNKNOWN'
        command.last_error = ''
        config = '{"agents":{"defaults":{"model":{"primary":"openai/gpt-6.1-sol","fallbacks":[]}}}}'
        output = io.StringIO()
        with patch.object(c.os, 'geteuid', return_value=0), patch.object(c.socket, 'gethostname', return_value='iZd7oeikknn1z21sq6ji6zZ'), patch.object(c.sys, 'argv', ['probe']), patch('builtins.open', mock_open(read_data=config)), patch.object(c, 'command', command), patch('sys.stdout', output):
            c.main()
        return calls, output.getvalue()

    def test_unverified_or_api_auth_prevents_inference(self):
        for auth in ({}, {'profiles': [{'provider': 'openai', 'type': 'api_key'}]}):
            calls, output = self.main_with(auth)
            self.assertEqual(len(calls), 1)
            self.assertIn('NOT_STARTED_OAUTH_ROUTE_UNCONFIRMED', output)

    def test_oauth_probe_is_only_56_no_delivery_or_local(self):
        calls, output = self.main_with({'profiles': [{'provider': 'openai', 'type': 'oauth'}]})
        agent = calls[-1]
        self.assertEqual(agent[0], 'agent')
        self.assertEqual(agent[agent.index('--model') + 1], 'openai/gpt-5.6-sol')
        self.assertNotIn('--deliver', agent)
        self.assertNotIn('--local', agent)
        self.assertIn('"production_configuration_mutation": false', output)

    def test_empty_catalog_is_not_model_unavailability(self):
        self.assertEqual(c.catalog_summary({}), {'target_rows': [], 'provider_outcomes': []})

    def test_model_key_and_flags_without_secret_disclosure(self):
        data = {'models': [{'key': c.TARGET, 'available': True, 'secret': 'private'}],
                'providerOutcomes': [{'provider': 'openai', 'status': 'auth-rejected', 'profileId': 'private'}]}
        s = c.catalog_summary(data)
        self.assertEqual(s['target_rows'][0]['available'], True)
        self.assertEqual(s['provider_outcomes'], ['auth-rejected'])
        self.assertNotIn('private', str(s))

    def test_exact_reply_and_model_metadata_required(self):
        data = {'status': 'ok', 'result': {'payloads': [{'text': 'canary'}],
                                         'meta': {'agentMeta': {'model': 'gpt-5.6-sol', 'provider': 'openai'}}}}
        self.assertTrue(c.evaluate(data, 0, 'canary')['inference_verified'])
        self.assertFalse(c.evaluate(data, 1, 'canary')['inference_verified'])
        self.assertFalse(c.evaluate(data, 0, 'other')['inference_verified'])
        data['result']['meta']['agentMeta']['model'] = 'different-model'
        self.assertFalse(c.evaluate(data, 0, 'canary')['inference_verified'])

    def test_reply_without_metadata_or_with_error_never_passes(self):
        self.assertFalse(c.evaluate({'text': 'canary'}, 0, 'canary')['inference_verified'])
        data = {'text': 'canary', 'model': 'gpt-5.6-sol', 'provider': 'openai', 'error': {'message': 'private'}}
        self.assertFalse(c.evaluate(data, 0, 'canary')['inference_verified'])
        self.assertNotIn('private', str(c.evaluate(data, 0, 'canary')))

    def test_error_output_is_categorized_without_raw_text(self):
        self.assertEqual(c.classify_error('private token: selected model is unavailable'), 'MODEL_UNAVAILABLE')

    def test_safe_diagnostic_retains_scope_error_and_masks_credentials(self):
        raw = 'Error: missing scope operator.write token=private-value Bearer private-bearer https://example.test/?token=private-url'
        text = c.safe_diagnostic(raw)
        self.assertIn('missing scope operator.write', text)
        self.assertNotIn('private-', text)
        self.assertEqual(c.classify_error(raw), 'GATEWAY_PERMISSION')

    def test_json_secrets_and_jwt_redacted_before_truncation(self):
        raw = 'Error: {"access_token":"private-value"} eyJabc.defgh.ijklmn'
        self.assertNotIn('private-value', c.safe_diagnostic(raw))
        self.assertNotIn('eyJabc', c.safe_diagnostic(raw))
