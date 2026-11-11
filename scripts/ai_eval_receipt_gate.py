"""Offline exact-output evidence checker. Never invokes an AI or grants release.

The expected binding is supplied separately by the existing admitted collector.
Hash equality proves identity, not provenance/authenticity or semantic quality.
"""
from __future__ import print_function
import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys

MAX_BYTES = 1024 * 1024
MAX_CASES = 256


def require(condition):
    if not condition:
        raise ValueError('INVALID_EVAL_INPUT')


def shape(value, keys):
    require(type(value) is dict and set(value) == set(keys))


def identifier(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) is not None


def digest_text(value, size):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % size, value) is not None


def validate_json(value, depth=0, budget=None):
    budget = [10000] if budget is None else budget
    budget[0] -= 1
    require(depth <= 64 and budget[0] >= 0)
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        require(len(str(abs(value))) <= 64)
    elif type(value) is float:
        require(math.isfinite(value))
    elif type(value) is str:
        require(len(value) <= 65536)
        value.encode('utf-8', 'strict')
    elif type(value) is list:
        for item in value:
            validate_json(item, depth + 1, budget)
    elif type(value) is dict:
        for key, item in value.items():
            require(type(key) is str and len(key) <= 128)
            key.encode('utf-8', 'strict')
            validate_json(item, depth + 1, budget)
    else:
        require(False)


def canonical(value):
    validate_json(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)


def sha256(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('INVALID_EVAL_INPUT')


def _float(token):
    value = float(token)
    require(math.isfinite(value))
    return value


def _int(token):
    require(len(token.lstrip('-')) <= 64)
    return int(token)


def loads(text):
    require(type(text) is str and len(text.encode('utf-8')) <= MAX_BYTES)
    # Bound nesting before calling recursive parsers on any supported Python.
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            require(depth <= 64)
        elif char in ']}':
            depth -= 1
    value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant,
                       parse_float=_float, parse_int=_int)
    validate_json(value)
    return value


def read_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES)
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES)
        return loads(raw.decode('utf-8', 'strict'))
    finally:
        if fd is not None:
            os.close(fd)


def validate_binding(value):
    shape(value, ('source_commit', 'source_tree', 'artifact_sha256',
                  'environment', 'runner_run_id', 'mode', 'delegated_model_calls'))
    require(digest_text(value['source_commit'], 40))
    require(digest_text(value['source_tree'], 40))
    require(digest_text(value['artifact_sha256'], 64))
    require(value['environment'] in ('LOCAL_FIXTURE', 'HOSTED_FIXTURE', 'UK_HOST'))
    require(identifier(value['runner_run_id']))
    require(value['mode'] in ('FIXTURE', 'RECORDED_OUTPUT'))
    require(type(value['delegated_model_calls']) is int and value['delegated_model_calls'] == 0)
    # The zero-call policy forbids generating new model results through this gate.
    # Recorded results may be supplied, but their authenticity is not certified.


def evaluate(suite, receipt, expected_binding):
    for value in (suite, receipt, expected_binding):
        validate_json(value)
    shape(suite, ('schema', 'suite_id', 'version', 'cases'))
    require(suite['schema'] == 'xuanjun.ai_eval.suite.v1')
    require(identifier(suite['suite_id']) and type(suite['version']) is int and suite['version'] >= 1)
    require(type(suite['cases']) is list and 1 <= len(suite['cases']) <= MAX_CASES)
    cases = {}
    for case in suite['cases']:
        shape(case, ('id', 'category', 'weight', 'expected'))
        require(identifier(case['id']) and identifier(case['category']))
        require(type(case['weight']) is int and 1 <= case['weight'] <= 100)
        require(type(case['expected']) is dict and case['expected'])
        require(case['id'] not in cases)
        cases[case['id']] = case
    shape(receipt, ('schema', 'suite_sha256', 'binding', 'cases'))
    require(receipt['schema'] == 'xuanjun.ai_eval.receipt.v1')
    require(receipt['suite_sha256'] == sha256(suite))
    validate_binding(expected_binding)
    validate_binding(receipt['binding'])
    require(canonical(receipt['binding']) == canonical(expected_binding))
    require(type(receipt['cases']) is list and len(receipt['cases']) <= MAX_CASES)
    seen = {}
    for item in receipt['cases']:
        shape(item, ('case_id', 'state', 'output', 'output_sha256', 'execution_ref'))
        require(identifier(item['case_id']))
        require(item['case_id'] in cases and item['case_id'] not in seen)
        require(item['state'] in ('COMPLETED', 'NOT_RUN'))
        if item['state'] == 'NOT_RUN':
            require(item['output'] is None and item['output_sha256'] is None and item['execution_ref'] is None)
        else:
            require(type(item['output']) is dict and identifier(item['execution_ref']))
            require(item['output_sha256'] == sha256(item['output']))
        seen[item['case_id']] = item
    rows, passed_weight, total_weight = [], 0, 0
    for key in sorted(cases):
        case, item = cases[key], seen.get(key)
        total_weight += case['weight']
        if item is None or item['state'] == 'NOT_RUN':
            state = 'NOT_RUN'
        elif canonical(item['output']) == canonical(case['expected']):
            state = 'PASS'
            passed_weight += case['weight']
        else:
            state = 'FAIL'
        rows.append({'case_id': key, 'state': state})
    counts = {state: sum(row['state'] == state for row in rows)
              for state in ('PASS', 'FAIL', 'NOT_RUN')}
    state = 'FAIL' if counts['FAIL'] else ('NOT_RUN' if counts['NOT_RUN'] else 'PASS')
    return {'schema': 'xuanjun.ai_eval.report.v1', 'state': state,
            'scope': 'FIXTURE_CHECK_ONLY' if expected_binding['mode'] == 'FIXTURE' else 'RECORDED_OUTPUT_CHECK_ONLY',
            'suite_sha256': sha256(suite), 'receipt_sha256': sha256(receipt),
            'binding_sha256': sha256(expected_binding), 'cases': rows, 'counts': counts,
            'score_basis_points': passed_weight * 10000 // total_weight,
            'authenticity': 'NOT_VERIFIED_BY_THIS_TOOL',
            'semantic_review': 'NOT_PERFORMED', 'runtime_acceptance': 'NOT_GRANTED',
            'release_granted': False, 'dispatch_performed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--expected-binding', required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(read_json(args.suite), read_json(args.receipt), read_json(args.expected_binding))
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError, OSError):
        print('{"state":"INVALID_INPUT","release_granted":false,"dispatch_performed":false}')
        return 2
    print(canonical(report))
    return {'PASS': 0, 'FAIL': 1, 'NOT_RUN': 3}[report['state']]


if __name__ == '__main__':
    sys.exit(main())
