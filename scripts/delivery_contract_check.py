"""Validate batch delivery metadata; no approval, dispatch or production authority."""
import argparse
import hashlib
import json
import re
from pathlib import Path

VERSION = '2026.10.15.1'
RULES = 'docs/DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md'
COVERAGE = {'permissions', 'input_files', 'concurrency_idempotency', 'timeout_interrupt',
            'restart_recovery', 'partial_unknown', 'transaction_cleanup'}
FIELDS = {'rules_version', 'rules_sha256', 'head_sha', 'task', 'batch', 'developer',
          'changed_files', 'nodes', 'coverage', 'wiring_evidence', 'continuation'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def text(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 4096


def evidence(value):
    return (type(value) is list and 1 <= len(value) <= 128
            and all(text(item) for item in value))


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'NONFINITE_JSON'))


def validate(body, head, changed, rules_raw):
    """External callers must supply GitHub-derived HEAD and full changed-file list.

    The body remains developer-authored metadata, never authenticated review or
    proof that the referenced work really happened. Do not execute its contents.
    """
    require(type(body) is str and len(body.encode()) <= 65536, 'BODY_BOUND')
    blocks = re.findall(r'^```xj-delivery\s*\n(.*?)^```\s*$', body, re.M | re.S)
    require(len(blocks) == 1, 'ONE_DELIVERY_CONTRACT_REQUIRED')
    value = strict_json(blocks[0])
    require(type(value) is dict and set(value) == FIELDS, 'EXACT_CONTRACT_FIELDS')
    require(value['rules_version'] == VERSION, 'RULE_VERSION_MISMATCH')
    require(value['rules_sha256'] == hashlib.sha256(rules_raw).hexdigest(), 'RULE_HASH_MISMATCH')
    require(type(head) is str and re.fullmatch('[0-9a-f]{40}', head)
            and value['head_sha'] == head, 'CURRENT_HEAD_REQUIRED')
    require(type(value['task']) is str and re.fullmatch(r'#[1-9][0-9]*', value['task']), 'ORIGINAL_TASK_REQUIRED')
    require(text(value['batch']) and text(value['developer']), 'BATCH_DEVELOPER_REQUIRED')
    paths = value['changed_files']
    require(type(changed) is list and changed and len(changed) <= 3000
            and len(set(changed)) == len(changed), 'FULL_CHANGED_INVENTORY_REQUIRED')
    require(type(paths) is list and all(type(p) is str for p in paths)
            and len(paths) == len(set(paths)) and set(paths) == set(changed), 'CHANGED_SCOPE_MISMATCH')
    for path in paths:
        require(not path.startswith('/') and '\\' not in path and '\x00' not in path
                and all(part not in ('', '.', '..') for part in path.split('/')), 'INVALID_SCOPE_PATH')
    nodes = value['nodes']
    require(type(nodes) is list and 1 <= len(nodes) <= 256, 'NODE_INVENTORY_REQUIRED')
    ids = set()
    for node in nodes:
        require(type(node) is dict and set(node) == {'id', 'state', 'criteria', 'evidence',
                'blocker', 'owner', 'next_action', 'next_check'}, 'NODE_SCHEMA')
        require(text(node['id']) and node['id'] not in ids, 'UNIQUE_NODE_ID_REQUIRED')
        ids.add(node['id'])
        require(evidence(node['criteria']) and evidence(node['evidence']), 'CRITERIA_EVIDENCE_REQUIRED')
        require(node['state'] in ('DONE', 'EXTERNAL_BLOCKED'), 'INCOMPLETE_BATCH')
        if node['state'] == 'DONE':
            require(all(node[k] is None for k in ('blocker', 'owner', 'next_action', 'next_check')), 'DONE_WITH_BLOCKER')
        else:
            require(all(text(node[k]) for k in ('blocker', 'owner', 'next_action', 'next_check')), 'ACTIONABLE_EXTERNAL_BLOCKER_REQUIRED')
    coverage = value['coverage']
    require(type(coverage) is dict and set(coverage) == COVERAGE, 'ALL_FAILURE_DOMAINS_REQUIRED')
    for row in coverage.values():
        require(type(row) is dict and set(row) == {'state', 'evidence'}
                and row['state'] in ('TESTED', 'NOT_APPLICABLE') and evidence(row['evidence']), 'COVERAGE_EVIDENCE_REQUIRED')
    require(evidence(value['wiring_evidence']), 'WIRING_EVIDENCE_REQUIRED')
    require(type(value['continuation']) is dict and set(value['continuation']) == {'eligible_remaining', 'next_action'}
            and value['continuation']['eligible_remaining'] == []
            and text(value['continuation']['next_action']), 'ELIGIBLE_WORK_MUST_CONTINUE')
    return {'state': 'DELIVERY_METADATA_VALID', 'head_sha': head,
            'independent_review': 'NOT_PROVEN_BY_METADATA', 'authority_effect': 'NONE'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', required=True)
    parser.add_argument('--changed', required=True, help='JSON array of complete PR filenames')
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    try:
        event = strict_json(Path(args.event).read_text())
        pr = event['pull_request']
        result = validate(pr['body'] or '', pr['head']['sha'],
                          strict_json(Path(args.changed).read_text()),
                          (Path(args.root) / RULES).read_bytes())
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print('DELIVERY_BLOCKED: invalid, incomplete or stale delivery contract')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
