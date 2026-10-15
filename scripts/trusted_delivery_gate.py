"""Trusted-base delivery gate. Never imports, checks out or executes PR files.

Loaded only by the default-branch pull_request_target workflow. Candidate tests
are not this authority. Platform must require the workflow source, not its name.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

from delivery_contract_check import RULES, validate

REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
PROTECTED = ('AGENTS.md', RULES, 'governance/features.json',
             'scripts/delivery_contract_check.py', 'scripts/trusted_delivery_gate.py',
             'scripts/feature_compliance_check.py')


def require(ok, reason):
    if not ok: raise ValueError(reason)


def evaluate(root, event, pr, rows, trusted_sha):
    """All PR-derived values are inert JSON. No PR blob/path is opened."""
    require(re.fullmatch('[0-9a-f]{40}', trusted_sha or ''), 'TRUSTED_COMMIT_REQUIRED')
    require(event.get('repository', {}).get('full_name') == REPOSITORY
            and event.get('repository', {}).get('default_branch') == 'main', 'FIXED_REPOSITORY_REQUIRED')
    require(pr['base']['repo']['full_name'] == REPOSITORY and pr['base']['ref'] == 'main', 'FIXED_BASE_REQUIRED')
    require(pr['head']['sha'] == event['pull_request']['head']['sha']
            and pr['number'] == event['pull_request']['number'], 'CURRENT_PR_HEAD_REQUIRED')
    require(type(rows) is list and 0 < len(rows) <= 3000
            and len(rows) == pr['changed_files'], 'COMPLETE_FILES_REQUIRED')
    names = [r['filename'] for r in rows]
    require(len(names) == len(set(names)), 'UNIQUE_FILES_REQUIRED')
    for row in rows:
        require(type(row) is dict and type(row.get('filename')) is str
                and row.get('status') in ('added', 'modified', 'removed', 'renamed', 'copied', 'changed', 'unchanged'), 'FILE_SCHEMA')
        paths = [row['filename']]
        if row['status'] == 'renamed':
            require(type(row.get('previous_filename')) is str, 'RENAME_SOURCE_REQUIRED')
            paths.append(row['previous_filename'])
        # New/renamed workflow files can forge the same job name too. Treat the
        # entire workflow directory, not just the current gate, as trust-root scope.
        for path in paths:
            require(path not in PROTECTED and not path.startswith('.github/workflows/'),
                    'HOLD_TRUST_ROOT_UPDATE_REQUIRES_SEPARATE_REVIEW')
    result = validate(pr['body'] or '', pr['head']['sha'], names, (root / RULES).read_bytes())
    return dict(result, trusted_source_sha=trusted_sha, workflow_event='pull_request_target',
                required_workflow_binding='ADMIN_CONFIGURATION_REQUIRED')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    args = ap.parse_args()
    try:
        require(os.environ.get('GITHUB_EVENT_NAME') == 'pull_request_target', 'TRUSTED_EVENT_REQUIRED')
        require(os.environ.get('GITHUB_REF') == 'refs/heads/main', 'DEFAULT_BRANCH_WORKFLOW_REQUIRED')
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        number = event['pull_request']['number']
        require(type(number) is int and number > 0, 'PR_NUMBER_REQUIRED')
        source = os.environ['GITHUB_SHA']
        require((Path(args.root) / '.trusted-source-sha').read_text().strip() == source, 'CHECKOUT_SOURCE_MISMATCH')
        endpoint = 'https://api.github.com/repos/' + REPOSITORY + '/pulls/' + str(number)
        def get(url):
            request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                                                          'Accept': 'application/vnd.github+json'})
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
            require(len(raw) <= 4 * 1024 * 1024, 'API_BOUND')
            return json.loads(raw)
        pr = get(endpoint)
        rows = []
        for page in range(1, 32):
            part = get(endpoint + '/files?per_page=100&page=' + str(page))
            require(type(part) is list, 'FILES_ARRAY_REQUIRED')
            if not part: break
            rows.extend(part)
        result = evaluate(Path(args.root), event, pr, rows, source)
        after = get(endpoint)
        require(after['head']['sha'] == pr['head']['sha'] and after['base']['sha'] == pr['base']['sha']
                and after['body'] == pr['body'], 'PR_CHANGED_DURING_CHECK')
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print('TRUSTED_DELIVERY_HOLD: invalid delivery or protected trust-root update')
        return 1


if __name__ == '__main__':
    sys.exit(main())
