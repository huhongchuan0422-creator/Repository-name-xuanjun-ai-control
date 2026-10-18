"""Static-only, exact GitHub dual authority. No enrollment or write functions.

Only the protected static configuration and the fixed repository's live API
responses establish identities. Comment text never selects an account, URL,
fetcher, trust file or algorithm. Anchors are excluded from the configuration
digest to avoid the plan -> Owner body -> anchor -> plan hash cycle.

Explicit PUBLIC_GITHUB binds a fixed comments page and startup/restart metadata
checks in protected config, plan, and both approvals. Its 54-request process
allowance is distinct from the durable five-attempt execution ledger. Observed
rate headroom is checked fail-closed, but cannot reserve GitHub shared-IP quota.
"""
import json
import copy
import os
import urllib.request
import re
import time

from scripts.pr122_customer_core import Denied, canonical, digest

MODE = 'STATIC_GITHUB_DUAL_APPROVAL'
CONFIG_NAME = 'STATIC_GITHUB_DUAL_APPROVAL.json'
REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REPOSITORY_ID = 1413132159
OWNER_ID = 332398908
REVIEWER_ID = 95597695
ISSUE_URL = 'https://api.github.com/repos/' + REPOSITORY + '/issues/122'
WORKFLOW = '.github/workflows/pr122-unified-release-review.yml'
OWNER_PREFIX = 'XUANJUN_STATIC_INSTALL_V1\n'
REVIEW_PREFIX = 'XUANJUN_STATIC_GITHUB_REVIEW_V1\n'
CONFIG_FIELDS = frozenset({'schema', 'authorization_mode', 'repository_id',
    'repository_full_name', 'owner_id', 'reviewer_id', 'source_writer_id',
    'revoked_review_ids', 'install_anchors'})
ANCHOR_FIELDS = frozenset({'install_comment_id', 'install_body_sha256',
    'review_comment_id', 'review_body_sha256'})
COMMON_FIELDS = frozenset({'authorization_mode', 'transaction', 'plan_sha256',
    'github_authority_sha256', 'deployment_profile', 'attempt_policy',
    'workflow_contract_sha256', 'source_commit', 'source_tree', 'manifest_sha256',
    'artifact_tar_sha256', 'artifact_zip_sha256', 'artifact_id', 'ci_run_id',
    'scope_sha256', 'static_baseline_sha256', 'host_pins_sha256',
    'permit_window_seconds', 'max_executions', 'issued_unix', 'expires_unix'})
PUBLIC_MODE = 'PUBLIC_GITHUB'
TRANSPORT_FIELD = 'github_transport'
TRANSPORT_FIELDS = frozenset({'mode', 'comments_page', 'per_page', 'metadata_policy', 'request_budget'})
_PUBLIC_CONTEXTS = {}

OWNER_FIELDS = COMMON_FIELDS | {'decision', 'rollback_approved',
    'review_comment_id', 'review_body_sha256'}
REVIEW_FIELDS = COMMON_FIELDS | {'decision', 'owner_id', 'reviewer_id',
    'source_writer_id', 'findings'}
HASH_FIELDS = ('plan_sha256', 'github_authority_sha256',
    'workflow_contract_sha256', 'manifest_sha256', 'artifact_tar_sha256',
    'artifact_zip_sha256', 'scope_sha256', 'static_baseline_sha256', 'host_pins_sha256')
PLAN_BINDINGS = ('source_commit', 'source_tree', 'manifest_sha256',
    'artifact_tar_sha256', 'artifact_zip_sha256', 'artifact_id', 'ci_run_id',
    'scope_sha256', 'static_baseline_sha256', 'host_pins_sha256',
    'deployment_profile', 'permit_window_seconds', 'github_authority_sha256')


class _Hold(Denied):
    """Only local constant diagnostics may cross this verifier's boundary."""


def _need(ok, code):
    if not ok:
        raise _Hold('HOLD:STATIC_GITHUB_' + code)


def _integer(value):
    return type(value) is int and value > 0


def _hash(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def strict_json(raw):
    """Bounded JSON object, rejecting duplicate keys and all non-finite values."""
    try:
        _need(type(raw) in (str, bytes) and len(raw) <= 2_000_000, 'JSON_BOUND')
        def pairs(items):
            result = {}
            for key, value in items:
                _need(key not in result, 'JSON_DUPLICATE')
                result[key] = value
            return result
        def nonfinite(_):
            raise _Hold('HOLD:STATIC_GITHUB_JSON_NONFINITE')
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
        _need(type(result) is dict, 'JSON_OBJECT')
        # JSON exponent overflow (1e999) is not a parse_constant callback.
        canonical(result)
        return result
    except _Hold as error:
        raise _Hold(str(error)) from None
    except Exception:
        raise _Hold('HOLD:STATIC_GITHUB_JSON_INVALID') from None


def _transport(value):
    _need(type(value) is dict and set(value) == TRANSPORT_FIELDS, 'TRANSPORT_SCHEMA')
    _need(value['mode'] == PUBLIC_MODE and value['metadata_policy'] == 'PROCESS_START_AND_RESTART'
          and type(value['comments_page']) is int and 1 <= value['comments_page'] <= 10000
          and type(value['per_page']) is int and value['per_page'] == 100
          and type(value['request_budget']) is int and value['request_budget'] == 54,
          'TRANSPORT_CONTRACT')
    return value


def _public(obj):
    return type(obj) is dict and TRANSPORT_FIELD in obj


def _config(trust):
    extra = {TRANSPORT_FIELD} if _public(trust) else set()
    _need(type(trust) is dict and set(trust) == CONFIG_FIELDS | extra
          and type(trust['schema']) is int and trust['schema'] == 1
          and trust['authorization_mode'] == MODE, 'CONFIG_SCHEMA')
    if extra:
        _transport(trust[TRANSPORT_FIELD])
    for name, expected in (('repository_id', REPOSITORY_ID), ('owner_id', OWNER_ID),
                           ('reviewer_id', REVIEWER_ID), ('source_writer_id', OWNER_ID)):
        _need(_integer(trust[name]) and trust[name] == expected, 'CONFIG_IDENTITY')
    _need(trust['repository_full_name'] == REPOSITORY
          and trust['source_writer_id'] != trust['reviewer_id'], 'INDEPENDENT_REVIEWER')
    revoked = trust['revoked_review_ids']
    _need(type(revoked) is list and len(revoked) <= 10000
          and all(_integer(value) for value in revoked)
          and len(set(revoked)) == len(revoked), 'REVOKED_IDS_SCHEMA')
    anchors = trust['install_anchors']
    _need(type(anchors) is dict and len(anchors) <= 10000, 'ANCHORS_SCHEMA')
    for transaction, anchor in anchors.items():
        _need(type(transaction) is str and re.fullmatch(r'pr122-[a-z0-9-]{1,90}', transaction)
              and type(anchor) is dict and set(anchor) == ANCHOR_FIELDS, 'ANCHOR_SCHEMA')
        _need(_integer(anchor['install_comment_id']) and _integer(anchor['review_comment_id'])
              and anchor['install_comment_id'] != anchor['review_comment_id']
              and _hash(anchor['install_body_sha256']) and _hash(anchor['review_body_sha256']),
              'ANCHOR_IDENTITY')


def trust_digest(trust):
    """The two exact body anchors are enrolled only after the plan is fixed."""
    try:
        _config(trust)
        return digest(canonical({key: value for key, value in trust.items()
                                 if key != 'install_anchors'}))
    except _Hold as error:
        raise _Hold(str(error)) from None
    except Exception:
        raise _Hold('HOLD:STATIC_GITHUB_CONFIG_INVALID') from None


def _comment(comment, comment_id, user_id, prefix):
    _need(type(comment) is dict and _integer(comment.get('id'))
          and comment['id'] == comment_id and comment.get('issue_url') == ISSUE_URL,
          'COMMENT_ORIGIN')
    user = comment.get('user')
    _need(type(user) is dict and _integer(user.get('id'))
          and user['id'] == user_id and user.get('type') == 'User', 'COMMENT_IDENTITY')
    body = comment.get('body')
    _need(type(body) is str and body.startswith(prefix), 'COMMENT_PREFIX')
    return strict_json(body[len(prefix):])


def _repository(value, *, owner=False):
    _need(type(value) is dict and _integer(value.get('id'))
          and value['id'] == REPOSITORY_ID and value.get('full_name') == REPOSITORY,
          'REPOSITORY_IDENTITY')
    if owner:
        _need(type(value.get('owner')) is dict and _integer(value['owner'].get('id'))
              and value['owner']['id'] == OWNER_ID, 'REPOSITORY_OWNER')


def _verify(comment, approval_comment, approval, plan, trust, fetch):
    _config(trust)
    _need(type(plan) is dict and plan.get('authorization_mode') == MODE, 'EXPLICIT_MODE')
    extra = {TRANSPORT_FIELD} if _public(trust) else set()
    _need(_public(plan) == bool(extra), 'TRANSPORT_PLAN_BINDING')
    _need(type(approval) is dict and set(approval) == OWNER_FIELDS | extra, 'OWNER_SCHEMA')
    _need(_integer(approval.get('review_comment_id')), 'REVIEW_COMMENT_ID')
    owner_body = _comment(approval_comment, approval_comment.get('id'), OWNER_ID, OWNER_PREFIX)
    _need(owner_body == approval, 'OWNER_BODY_BINDING')
    payload = _comment(comment, approval['review_comment_id'], REVIEWER_ID, REVIEW_PREFIX)
    _need(set(payload) == REVIEW_FIELDS | extra, 'REVIEW_SCHEMA')
    if extra:
        expected = _transport(trust[TRANSPORT_FIELD])
        _need(all(type(obj.get(TRANSPORT_FIELD)) is dict
                  and canonical(obj[TRANSPORT_FIELD]) == canonical(expected)
                  for obj in (plan, approval, payload)), 'TRANSPORT_EXACT_BINDING')
    _need(comment['id'] != approval_comment['id'], 'DISTINCT_COMMENTS')
    transaction = approval['transaction']
    _need(type(transaction) is str and re.fullmatch(r'pr122-[a-z0-9-]{1,90}', transaction)
          and plan.get('transaction') == transaction, 'TRANSACTION')
    anchor = trust['install_anchors'].get(transaction)
    _need(type(anchor) is dict and anchor['install_comment_id'] == approval_comment['id']
          and anchor['install_body_sha256'] == digest(approval_comment['body'].encode('utf-8'))
          and anchor['review_comment_id'] == comment['id']
          and anchor['review_body_sha256'] == digest(comment['body'].encode('utf-8')),
          'IMMUTABLE_COMMENT_ANCHORS')
    _need(comment['id'] not in trust['revoked_review_ids'], 'REVIEW_REVOKED')
    _need(approval['review_body_sha256'] == anchor['review_body_sha256'], 'OWNER_REVIEW_BINDING')
    _need(approval['decision'] == 'INSTALL_APPROVED' and approval['rollback_approved'] is True
          and payload['decision'] == 'AUDIT_PASS', 'DECISION')
    for name, expected in (('owner_id', OWNER_ID), ('reviewer_id', REVIEWER_ID),
                           ('source_writer_id', OWNER_ID)):
        _need(_integer(payload[name]) and payload[name] == expected, 'REVIEW_IDENTITY')
    for name in COMMON_FIELDS:
        _need(type(payload[name]) is type(approval[name]) and payload[name] == approval[name],
              'DUAL_BINDING')
    _need(approval['authorization_mode'] == MODE, 'EXPLICIT_MODE')
    for name in HASH_FIELDS:
        _need(_hash(approval[name]), 'HASH_FORMAT')
    for name in ('source_commit', 'source_tree'):
        _need(_hash(approval[name], 40), 'GIT_HASH_FORMAT')
    for name in ('artifact_id', 'ci_run_id'):
        _need(_integer(approval[name]) and _integer(plan.get(name)), 'ARTIFACT_ID')
    _need(approval['plan_sha256'] == digest(canonical(plan)), 'EXACT_PLAN')
    _need(approval['github_authority_sha256'] == trust_digest(trust), 'CONFIG_DRIFT')
    for name in PLAN_BINDINGS:
        _need(type(approval[name]) is type(plan.get(name)) and approval[name] == plan[name],
              'EXACT_PLAN_BINDING')
    from scripts.pr122_static_workflow import validate_permission
    validate_permission(plan, approval)
    _need(_integer(approval['issued_unix']) and _integer(approval['expires_unix'])
          and approval['expires_unix'] - approval['issued_unix'] == 18000
          and approval['issued_unix'] <= time.time() < approval['expires_unix'], 'EXPIRED')
    findings = payload['findings']
    _need(type(findings) is dict and set(findings) == {'R1', 'R2', 'R3'}, 'FINDINGS_SCHEMA')
    for finding in findings.values():
        _need(type(finding) is dict and set(finding) == {'state', 'evidence_sha256'}
              and finding['state'] == 'CLOSED' and type(finding['evidence_sha256']) is list
              and bool(finding['evidence_sha256'])
              and all(_hash(value) for value in finding['evidence_sha256']), 'FINDINGS_CLOSED')
    _need(plan['static_baseline_sha256'] in findings['R3']['evidence_sha256'], 'BASELINE_EVIDENCE')
    # Authenticated mode is always live. Explicit PUBLIC_GITHUB mode rechecks
    # metadata at process start/restart and live dual comments at every gate.
    # Artifacts and CI metadata are NOT treated as immutable authority.
    # The existing bounded GitHub client appends '/' before a relative path.
    # Repository-root '' would yield an unsupported trailing-slash endpoint.
    # The same live CI response authenticates repository ID/name/owner below.
    commit = fetch('git/commits/' + payload['source_commit'])
    _need(commit['sha'] == payload['source_commit'] and commit['tree']['sha'] == payload['source_tree'],
          'IMMUTABLE_GIT_TREE')
    artifact = fetch('actions/artifacts/' + str(payload['artifact_id']))
    _need(_integer(artifact['id']) and artifact['id'] == payload['artifact_id']
          and artifact['expired'] is False and artifact['digest'] == 'sha256:' + payload['artifact_zip_sha256']
          and _integer(artifact['workflow_run']['id']) and artifact['workflow_run']['id'] == payload['ci_run_id']
          and artifact['workflow_run']['head_sha'] == payload['source_commit'], 'ARTIFACT_IDENTITY')
    ci = fetch('actions/runs/' + str(payload['ci_run_id']))
    _need(_integer(ci['id']) and ci['id'] == payload['ci_run_id']
          and ci['status'] == 'completed' and ci['conclusion'] == 'success'
          and ci['head_sha'] == payload['source_commit'] and ci['path'] == WORKFLOW
          and ci['event'] in ('push', 'workflow_dispatch'), 'EXACT_CI')
    _repository(ci['repository'], owner=True)
    _repository(ci['head_repository'])
    _need(approval['issued_unix'] <= time.time() < approval['expires_unix'], 'EXPIRED')
    return payload


def verify(comment, approval_comment, approval, plan, trust, fetch):
    """Pure verifier seam for offline tests; production fetch is fixed in gate."""
    try:
        return _verify(comment, approval_comment, approval, plan, trust, fetch)
    except _Hold as error:
        raise Denied(str(error)) from None
    except Exception:
        # Foreign exceptions may contain credential/URL/response data.
        raise Denied('HOLD:STATIC_GITHUB_AUTHORITY_UNAVAILABLE') from None


def gate(comment_id, plan, transaction):
    """Reopen the fixed protected configuration and re-fetch both comments."""
    try:
        from scripts import pr122_customer_release as customer
        from scripts.pr122_customer_attempts import read_private
        _need(customer.REPO == REPOSITORY, 'FIXED_API_REPOSITORY')
        _need(_integer(comment_id) and type(plan) is dict
              and plan.get('authorization_mode') == MODE, 'EXPLICIT_MODE')
        path = customer.CONFIG / CONFIG_NAME
        # Reuse the existing bounded, no-follow, root-owned 0600 reader.
        # Do not first perform an unbounded stat-then-read through private_config.
        trust = read_private(path)
        _config(trust)
        if _public(trust):
            return _public_gate(comment_id, plan, transaction, trust)
        _need(not _public(plan), 'TRANSPORT_PLAN_BINDING')
        owner = customer.github('issues/comments/' + str(comment_id))
        approval = _comment(owner, comment_id, OWNER_ID, OWNER_PREFIX)
        _need(set(approval) == OWNER_FIELDS and approval['transaction'] == transaction
              and _integer(approval['review_comment_id']), 'OWNER_SCHEMA')
        review = customer.github('issues/comments/' + str(approval['review_comment_id']))
        _verify(review, owner, approval, plan, trust, customer.github)
        return approval
    except _Hold as error:
        raise Denied(str(error)) from None
    except Exception:
        raise Denied('HOLD:STATIC_GITHUB_AUTHORITY_UNAVAILABLE') from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Hold('HOLD:STATIC_GITHUB_PUBLIC_REDIRECT')


def _context_key(plan):
    return (os.getpid(), digest(canonical(plan)))


def public_budget_context(plan):
    """Read-only snapshot; contains no credentials, URLs, or comment bodies."""
    context = _PUBLIC_CONTEXTS.get(_context_key(plan))
    _need(context is not None and not context['failed'], 'PUBLIC_CONTEXT_REQUIRED')
    return {name: context[name] for name in ('requests_used', 'remaining', 'reserved_remaining', 'last_status', 'reset_unix')}


def require_public_budget(plan, calls_needed):
    """Phase pre-write check. Caller must bound all remaining authority GETs.

    No waiting for rate-limit reset and no budget refresh from another process.
    Each resumed process must establish its own fresh initial metadata check.
    """
    _need(type(calls_needed) is int and calls_needed >= 0, 'PUBLIC_PHASE_BUDGET')
    snapshot = public_budget_context(plan)
    _need(snapshot['remaining'] >= calls_needed
          and snapshot['reserved_remaining'] >= calls_needed, 'PUBLIC_PHASE_BUDGET')
    return snapshot


def _public_get(relative, context):
    """Only the four prebound anonymous endpoint paths are admissible."""
    _need(relative in context['allowed'], 'PUBLIC_URL_SCOPE')
    _need(not context['failed'] and context['reserved_remaining'] > 0, 'PUBLIC_REQUEST_BUDGET')
    if context['remaining'] is not None:
        _need(context['remaining'] >= context['reserved_remaining'], 'PUBLIC_RATE_BUDGET')
    context['requests_used'] += 1
    context['reserved_remaining'] -= 1
    try:
        # Explicit no-proxy opener: no credential readers, cookies, environment
        # auth, retries, redirect following, pagination, or Link processing.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + '/' + relative,
            headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'pr122-static-public-authority',
                     'X-GitHub-Api-Version': '2022-11-28'})
        with opener.open(request, timeout=15) as response:
            context['last_status'] = response.status
            _need(response.status == 200, 'PUBLIC_HTTP_STATUS')
            remaining = response.headers.get('X-RateLimit-Remaining')
            _need(type(remaining) is str and re.fullmatch(r'[0-9]{1,6}', remaining) is not None,
                  'PUBLIC_RATE_HEADER')
            reset = response.headers.get('X-RateLimit-Reset')
            _need(type(reset) is str and re.fullmatch(r'[0-9]{1,12}', reset) is not None
                  and int(reset) > 0, 'PUBLIC_RESET_HEADER')
            context['reset_unix'] = int(reset)
            context['remaining'] = int(remaining)
            _need(context['remaining'] >= context['reserved_remaining'], 'PUBLIC_RATE_BUDGET')
            raw = response.read(2_000_001)
            _need(len(raw) <= 2_000_000, 'PUBLIC_RESPONSE_BOUND')
        if relative == context['comments_path']:
            # strict_json handles duplicate keys and nonfinite numbers recursively.
            value = strict_json(b'{"comments":' + raw + b'}')['comments']
            _need(type(value) is list and len(value) <= 100, 'PUBLIC_COMMENTS_SCHEMA')
            return value
        return strict_json(raw)
    except Exception:
        # An uncertain/error request never becomes a successful cache entry or
        # switches to the authenticated client. Restart requires new live checks.
        context['failed'] = True
        raise


def _public_gate(comment_id, plan, transaction, trust):
    transport = _transport(trust[TRANSPORT_FIELD])
    _need(type(plan.get(TRANSPORT_FIELD)) is dict
          and canonical(plan[TRANSPORT_FIELD]) == canonical(transport), 'TRANSPORT_PLAN_BINDING')
    _need(plan.get('transaction') == transaction, 'TRANSACTION')
    anchor = trust['install_anchors'].get(transaction)
    _need(type(anchor) is dict and anchor['install_comment_id'] == comment_id, 'IMMUTABLE_COMMENT_ANCHORS')
    # Scope is validated before constructing any URL, even before first approval.
    _need(_hash(plan.get('source_commit'), 40) and _integer(plan.get('artifact_id'))
          and _integer(plan.get('ci_run_id')), 'PUBLIC_PLAN_IDENTITIES')
    comments_path = 'issues/122/comments?per_page=100&page=' + str(transport['comments_page'])
    paths = ('git/commits/' + plan['source_commit'],
             'actions/artifacts/' + str(plan['artifact_id']),
             'actions/runs/' + str(plan['ci_run_id']))
    key = _context_key(plan)
    binding = digest(canonical({'trust': trust_digest(trust), 'anchor': anchor}))
    context = _PUBLIC_CONTEXTS.get(key)
    if context is None:
        context = {'requests_used': 0, 'remaining': None,
                   'reserved_remaining': transport['request_budget'], 'failed': False,
                   'comments_path': comments_path, 'allowed': frozenset((comments_path,) + paths),
                   'binding': binding, 'metadata': None, 'last_status': None, 'reset_unix': None}
        _PUBLIC_CONTEXTS[key] = context
    _need(context['binding'] == binding and not context['failed'], 'PUBLIC_CONTEXT_DRIFT')
    try:
        comments = _public_get(comments_path, context)
        owner_matches = [row for row in comments if type(row) is dict and row.get('id') == comment_id]
        review_matches = [row for row in comments if type(row) is dict
                          and row.get('id') == anchor['review_comment_id']]
        _need(len(owner_matches) == len(review_matches) == 1, 'PUBLIC_EXACT_COMMENTS_PAGE')
        owner, review = owner_matches[0], review_matches[0]
        approval = _comment(owner, comment_id, OWNER_ID, OWNER_PREFIX)
        metadata = context['metadata']
        pending = {}
        def fetch(relative):
            _need(relative in paths, 'PUBLIC_METADATA_SCOPE')
            if metadata is not None:
                return copy.deepcopy(metadata[relative])
            value = _public_get(relative, context)
            pending[relative] = copy.deepcopy(value)
            return value
        _verify(review, owner, approval, plan, trust, fetch)
        if metadata is None:
            _need(set(pending) == set(paths), 'PUBLIC_METADATA_COMPLETE')
            context['metadata'] = pending
        return approval
    except Exception:
        context['failed'] = True
        raise
