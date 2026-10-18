"""Static-only, exact GitHub dual authority. No enrollment or write functions.

Only the protected static configuration and the fixed repository's live API
responses establish identities. Comment text never selects an account, URL,
fetcher, trust file or algorithm. Anchors are excluded from the configuration
digest to avoid the plan -> Owner body -> anchor -> plan hash cycle.
"""
import json
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


def _config(trust):
    _need(type(trust) is dict and set(trust) == CONFIG_FIELDS
          and type(trust['schema']) is int and trust['schema'] == 1
          and trust['authorization_mode'] == MODE, 'CONFIG_SCHEMA')
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
    _need(type(approval) is dict and set(approval) == OWNER_FIELDS, 'OWNER_SCHEMA')
    _need(_integer(approval.get('review_comment_id')), 'REVIEW_COMMENT_ID')
    owner_body = _comment(approval_comment, approval_comment.get('id'), OWNER_ID, OWNER_PREFIX)
    _need(owner_body == approval, 'OWNER_BODY_BINDING')
    payload = _comment(comment, approval['review_comment_id'], REVIEWER_ID, REVIEW_PREFIX)
    _need(set(payload) == REVIEW_FIELDS, 'REVIEW_SCHEMA')
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
    # Always live; no cached approval, successful earlier request or error fallback.
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
