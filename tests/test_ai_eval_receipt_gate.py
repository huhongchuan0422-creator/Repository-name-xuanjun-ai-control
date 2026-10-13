import copy
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ai_eval_receipt_gate as gate


class EvalReceiptTests(unittest.TestCase):
    def setUp(self):
        self.suite = gate.read_json(str(ROOT / 'fixtures/ai_eval/v1.json'))
        self.binding = {'source_commit': 'a' * 40, 'source_tree': 'b' * 40,
                        'artifact_sha256': 'c' * 64, 'environment': 'LOCAL_FIXTURE',
                        'runner_run_id': 'fixture:1', 'mode': 'FIXTURE',
                        'delegated_model_calls': 0}
        self.receipt = {'schema': 'xuanjun.ai_eval.receipt.v1',
                        'suite_sha256': gate.sha256(self.suite),
                        'binding': copy.deepcopy(self.binding), 'cases': []}
        for case in self.suite['cases']:
            output = copy.deepcopy(case['expected'])
            self.receipt['cases'].append({'case_id': case['id'], 'state': 'COMPLETED',
                'output': output, 'output_sha256': gate.sha256(output),
                'execution_ref': 'fixture:' + case['id']})

    def evaluate(self):
        return gate.evaluate(self.suite, self.receipt, self.binding)

    def test_complete_exact_fixture_not_runtime_pass(self):
        report = self.evaluate()
        self.assertEqual(report['state'], 'PASS')
        self.assertEqual(report['score_basis_points'], 10000)
        self.assertEqual(report['counts'], {'PASS': 8, 'FAIL': 0, 'NOT_RUN': 0})
        self.assertEqual(report['scope'], 'FIXTURE_CHECK_ONLY')
        self.assertEqual(report['authenticity'], 'NOT_VERIFIED_BY_THIS_TOOL')
        self.assertEqual(report['semantic_review'], 'NOT_PERFORMED')
        self.assertEqual(report['runtime_acceptance'], 'NOT_GRANTED')
        self.assertFalse(report['release_granted']);self.assertFalse(report['dispatch_performed'])

    def test_baseline_fingerprint_is_frozen(self):
        self.assertEqual(gate.sha256(self.suite), '5dc1552bb89e9fc367b7b317d42da5873a4ede5c0a13a6b1265a800880e3d90a')

    def test_missing_case_not_inflated_to_pass(self):
        self.receipt['cases'].pop()
        report = self.evaluate()
        self.assertEqual(report['state'], 'NOT_RUN')
        self.assertEqual(report['score_basis_points'], 8750)

    def test_empty_receipt_not_run(self):
        self.receipt['cases'] = []
        report = self.evaluate()
        self.assertEqual(report['state'], 'NOT_RUN')
        self.assertEqual(report['score_basis_points'], 0)

    def test_explicit_not_run_has_no_fabricated_output(self):
        item = self.receipt['cases'][0]
        item.update(state='NOT_RUN', output=None, output_sha256=None, execution_ref=None)
        self.assertEqual(self.evaluate()['state'], 'NOT_RUN')
        item['output'] = {}
        with self.assertRaises(ValueError):self.evaluate()

    def test_bad_output_fails_even_with_missing_case(self):
        item = self.receipt['cases'][0]
        item['output'] = {'state': 'PASS', 'can_claim_pass': True}
        item['output_sha256'] = gate.sha256(item['output'])
        self.receipt['cases'].pop()
        self.assertEqual(self.evaluate()['state'], 'FAIL')

    def test_boolean_not_equal_integer(self):
        item = next(x for x in self.receipt['cases'] if x['case_id']=='model_route_denied')
        item['output']['delegated_calls'] = False
        item['output_sha256'] = gate.sha256(item['output'])
        self.assertEqual(self.evaluate()['state'], 'FAIL')

    def test_no_raw_output_echo(self):
        item = self.receipt['cases'][0]
        item['output'] = {'secret': 'SENSITIVE_SENTINEL'}
        item['output_sha256'] = gate.sha256(item['output'])
        self.assertNotIn('SENSITIVE_SENTINEL', gate.canonical(self.evaluate()))

    def test_mutated_output_digest_rejected(self):
        self.receipt['cases'][0]['output']['unexpected'] = True
        with self.assertRaises(ValueError):self.evaluate()

    def test_duplicate_or_unknown_case_rejected(self):
        original = copy.deepcopy(self.receipt)
        self.receipt['cases'].append(copy.deepcopy(self.receipt['cases'][0]))
        with self.assertRaises(ValueError):self.evaluate()
        self.receipt = original
        self.receipt['cases'][0]['case_id'] = 'unregistered'
        with self.assertRaises(ValueError):self.evaluate()

    def test_wrong_suite_or_case_set_rejected(self):
        self.suite['version'] += 1
        with self.assertRaises(ValueError):self.evaluate()

    def test_duplicate_suite_case_rejected(self):
        self.suite['cases'].append(copy.deepcopy(self.suite['cases'][0]))
        self.receipt['suite_sha256'] = gate.sha256(self.suite)
        with self.assertRaises(ValueError):self.evaluate()

    def test_all_binding_fields_are_exact(self):
        original = copy.deepcopy(self.receipt)
        changes = {'source_commit': 'd'*40, 'source_tree': 'e'*40,
                   'artifact_sha256': 'f'*64, 'environment': 'UK_HOST',
                   'runner_run_id': 'fixture:2', 'mode': 'RECORDED_OUTPUT'}
        for key,value in changes.items():
            self.receipt = copy.deepcopy(original)
            self.receipt['binding'][key] = value
            with self.subTest(field=key):
                with self.assertRaises(ValueError):self.evaluate()

    def test_model_calls_unknown_nonzero_boolean_reject(self):
        for count in (1, 'UNKNOWN', False, -1, 0.0):
            self.binding['delegated_model_calls'] = count
            self.receipt['binding']['delegated_model_calls'] = count
            with self.subTest(count=count):
                with self.assertRaises(ValueError):self.evaluate()

    def test_recorded_output_still_not_authentication(self):
        self.binding.update(mode='RECORDED_OUTPUT', environment='UK_HOST')
        self.receipt['binding'] = copy.deepcopy(self.binding)
        report = self.evaluate()
        self.assertEqual(report['scope'], 'RECORDED_OUTPUT_CHECK_ONLY')
        self.assertEqual(report['authenticity'], 'NOT_VERIFIED_BY_THIS_TOOL')
        self.assertFalse(report['release_granted'])

    def test_reordering_deterministic_score_and_case_order(self):
        a = self.evaluate()
        self.receipt['cases'].reverse()
        b = self.evaluate()
        self.assertEqual(a['cases'], b['cases'])
        self.assertEqual(a['score_basis_points'], b['score_basis_points'])
        # Raw receipt identity must still distinguish its order.
        self.assertNotEqual(a['receipt_sha256'], b['receipt_sha256'])

    def test_unknown_fields_and_invalid_weights_rejected(self):
        for value in (0, True, 101, 1.0):
            self.suite['cases'][0]['weight'] = value
            self.receipt['suite_sha256'] = gate.sha256(self.suite)
            with self.assertRaises(ValueError):self.evaluate()
        self.setUp();self.receipt['extra'] = 'untrusted'
        with self.assertRaises(ValueError):self.evaluate()

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":{"a":1,"a":2}}',
                     'NaN','Infinity','-Infinity','1e9999','-1e9999','{"x":[1e9999]}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):gate.loads(text)

    def test_normal_numbers_keep_types(self):
        value = gate.loads('{"i":123,"f":1.5}')
        self.assertIs(type(value['i']), int);self.assertIs(type(value['f']), float)

    def test_json_bounds_and_escaped_brackets(self):
        for text in ('['*65+'0'+']'*65, '1'*65, '"'+'x'*65537+'"'):
            with self.assertRaises(ValueError):gate.loads(text)
        value = {'text': '[{'*100+'\\"'+']}'*100}
        self.assertEqual(gate.loads(json.dumps(value)), value)

    def test_direct_invalid_values_rejected(self):
        for value in (float('nan'), float('inf'), {'x':(1,2)}, {'x':'\ud800'}):
            with self.assertRaises((ValueError,UnicodeError)):gate.canonical(value)

    def test_symlink_and_nonregular_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = pathlib.Path(directory)
            (p/'file').write_text('{}');(p/'link').symlink_to(p/'file')
            with self.assertRaises(OSError):gate.read_json(str(p/'link'))
            os.mkfifo(str(p/'fifo'))
            with self.assertRaises(ValueError):gate.read_json(str(p/'fifo'))

    def test_cli_exit_codes_and_no_input_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            p = pathlib.Path(directory)
            paths = [p/'suite', p/'receipt', p/'binding']
            def run():
                for path,value in zip(paths,(self.suite,self.receipt,self.binding)):
                    path.write_text(json.dumps(value))
                stream = io.StringIO()
                with redirect_stdout(stream):
                    code = gate.main(['--suite',str(paths[0]),'--receipt',str(paths[1]),'--expected-binding',str(paths[2])])
                return code,gate.loads(stream.getvalue())
            self.assertEqual(run()[0],0)
            self.receipt['cases'].pop();self.assertEqual(run()[0],3)
            self.receipt['bad'] = 'SENSITIVE_SENTINEL'
            code,result = run();self.assertEqual(code,2)
            self.assertNotIn('SENSITIVE_SENTINEL',repr(result))

    def test_no_hidden_execution_path(self):
        with patch('subprocess.Popen', side_effect=AssertionError('process forbidden')), \
             patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.evaluate()['state'],'PASS')


if __name__ == '__main__':unittest.main()
