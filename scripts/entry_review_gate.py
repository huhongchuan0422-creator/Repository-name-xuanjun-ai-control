"""Pure data gates; authenticated receipts supplied by canonical integration.

Keyrings are trusted runtime inputs, never part of an uploaded bundle. No
execution, task queue, release grant or lease/fence mutation occurs here.
"""
import hashlib
import hmac
import json
import math
import re

ENTRIES = ('WORK', 'CHATGPT', 'DOTS')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identity(value,with_key=False):
    fields={'issuer','subject'} | ({'key_id','role'} if with_key else set())
    if not isinstance(value,dict) or set(value)!=fields:
        raise ValueError('EXACT_AUTHENTICATED_IDENTITY_REQUIRED')
    for field in fields:
        if not isinstance(value[field],str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',value[field]):
            raise ValueError('EXACT_AUTHENTICATED_IDENTITY_REQUIRED')
    if with_key and value['role'] not in ('QA','SECURITY'):
        raise ValueError('REVIEW_ROLE_REQUIRED')
    return (value['issuer'],value['subject'])


def authenticated(record,keyring):
    if (not isinstance(record,dict) or set(record)!={'schema','key_id','record_id','payload','signature'}
            or type(record['schema']) is not int or record['schema']!=1
            or not isinstance(record['key_id'],str) or not isinstance(record['payload'],dict)
            or not isinstance(record['record_id'],str) or not isinstance(record['signature'],str)
            or not re.fullmatch('[0-9a-f]{64}',record['record_id'])
            or not re.fullmatch('[0-9a-f]{64}',record['signature'])
            or not isinstance(keyring,dict)):
        raise ValueError('AUTHENTICATED_IMMUTABLE_RECEIPT_REQUIRED')
    key=keyring.get(record['key_id'])
    if type(key) is not bytes or len(key)<32:
        raise ValueError('TRUSTED_AUTHORITY_KEY_UNAVAILABLE')
    if record['record_id']!=digest(canonical(record['payload'])):
        raise ValueError('IMMUTABLE_RECORD_ID_MISMATCH')
    signed={k:v for k,v in record.items() if k!='signature'}
    expected=hmac.new(key,canonical(signed),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,record['signature']):
        raise ValueError('AUTHORITY_SIGNATURE_INVALID')
    return record['payload']


def review_bundle(contract,files,reviews,review_keys=None):
    required={'task_id','spec_sha256','checkpoint_sha256','target_repository','target_base_sha',
              'code_commit','entry','developer','allowed_files','trusted_reviewers'}
    if not isinstance(contract,dict) or set(contract)!=required:
        raise ValueError('EXACT_TRUSTED_CONTRACT_REQUIRED')
    if contract['entry'] not in ENTRIES:
        raise ValueError('UNKNOWN_ENTRY')
    if (not isinstance(contract['task_id'],str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',contract['task_id'])
            or not isinstance(contract['target_repository'],str)
            or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',contract['target_repository'])):
        raise ValueError('EXACT_TASK_REPOSITORY_REQUIRED')
    developer=identity(contract['developer'])
    if (not isinstance(contract['trusted_reviewers'],list) or len(contract['trusted_reviewers'])!=2
            or not isinstance(contract['allowed_files'],list) or not contract['allowed_files']
            or any(not isinstance(p,str) for p in contract['allowed_files'])
            or len(set(contract['allowed_files']))!=len(contract['allowed_files'])):
        raise ValueError('STRICT_POLICY_ARRAYS_REQUIRED')
    for path in contract['allowed_files']:
        if not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or any(p in ('','.','..') for p in path.split('/')):
            raise ValueError('CANONICAL_POLICY_PATH_REQUIRED')
    policies={}
    for policy in contract['trusted_reviewers']:
        who=identity(policy,True)
        if (who==developer or who in policies or any(p['key_id']==policy['key_id'] or p['role']==policy['role'] for p in policies.values())):
            raise ValueError('DISTINCT_INDEPENDENT_REVIEWERS_REQUIRED')
        policies[who]=policy
    for field,size in [('spec_sha256',64),('checkpoint_sha256',64),('target_base_sha',40),('code_commit',40)]:
        if not isinstance(contract[field],str) or not re.fullmatch('[0-9a-f]{%d}'%size,contract[field]):
            raise ValueError('HASH_BINDING_REQUIRED')
    if not isinstance(files,dict) or not files or len(files)>32:
        raise ValueError('BOUNDED_FILES_REQUIRED')
    if set(files)!=set(contract['allowed_files']):
        raise ValueError('EXACT_AUTHORIZED_FILE_SET_REQUIRED')
    manifest={};total=0
    for path,raw in files.items():
        if (not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',path)
                or any(p in ('','.','..') for p in path.split('/')) or path not in contract['allowed_files']):
            raise ValueError('PATH_NOT_AUTHORIZED')
        if type(raw) is not bytes or len(raw)>131072:
            raise ValueError('BOUNDED_PLAIN_BYTES_REQUIRED')
        total+=len(raw)
        if total>524288:raise ValueError('BUNDLE_TOO_LARGE')
        text=raw.decode('utf-8','strict')
        if '\x00' in text or '\r' in text:raise ValueError('CANONICAL_UTF8_LF_REQUIRED')
        # Mechanical syntax checking is separate, before independent review.
        manifest[path]=digest(raw)
    binding={'contract':contract,'files':manifest}
    bundle_sha=digest(canonical(binding))
    roles=set();record_ids=set();review_record_ids={}
    if not isinstance(reviews,list) or len(reviews)>2:raise ValueError('BOUNDED_REVIEWS_REQUIRED')
    for record in reviews:
        value=authenticated(record,review_keys)
        if set(value)!={'reviewer','role','bundle_sha256','decision'}:
            raise ValueError('EXACT_REVIEW_PAYLOAD_REQUIRED')
        who=identity(value['reviewer']);policy=policies.get(who)
        if (policy is None or record['key_id']!=policy['key_id'] or value['role']!=policy['role']
                or value['role'] in roles or record['record_id'] in record_ids
                or value['bundle_sha256']!=bundle_sha or value['decision']!='PASS'):
            raise ValueError('INDEPENDENT_EXACT_VERSION_REVIEW_REQUIRED')
        roles.add(value['role']);record_ids.add(record['record_id']);review_record_ids[value['role']]=record['record_id']
    if roles=={'QA','SECURITY'}:
        values=[review_keys[p['key_id']] for p in policies.values()]
        if hmac.compare_digest(values[0],values[1]):
            raise ValueError('DISTINCT_REVIEW_AUTHORITY_KEYS_REQUIRED')
    return {'state':'ISOLATED_TEST_ELIGIBLE' if roles=={'QA','SECURITY'} else 'HOLD_INDEPENDENT_REVIEW_REQUIRED',
            'bundle_sha256':bundle_sha,'binding':binding,
            'review_record_ids':review_record_ids,
            'authority_effect':'NONE','release_approved':False}


def complete_reviewed_candidate(supervisor, contract, files, reviews,
                                review_keys, candidate_binding,
                                completion_event_id,
                                next_action='DEPENDENCIES_RECHECK'):
    """Verify exact reviews, then atomically complete the canonical task.

    Test/source identities here do not grant production approval; this only
    converts already-authenticated QA+SECURITY records into canonical task
    completion evidence.
    """
    result = review_bundle(contract, files, reviews, review_keys)
    if result['state'] != 'ISOLATED_TEST_ELIGIBLE':
        return dict(result, canonical_completion='HOLD_INDEPENDENT_REVIEW_REQUIRED')
    canonical_contract = {k:v for k,v in contract.items()
                          if k != 'code_commit'}
    if (not isinstance(candidate_binding, dict)
            or candidate_binding.get('candidate', {}).get('contract_sha256')
               != digest(canonical(canonical_contract))
            or candidate_binding.get('candidate', {}).get('task_id')
               != contract.get('task_id')
            or candidate_binding.get('candidate', {}).get('code_commit')
               != contract.get('code_commit')
            or candidate_binding.get('candidate', {}).get('spec_sha256')
               != contract.get('spec_sha256')
            or candidate_binding.get('candidate', {}).get('checkpoint_sha256')
               != contract.get('checkpoint_sha256')
            or candidate_binding.get('candidate', {}).get('target_repository')
               != contract.get('target_repository')
            or candidate_binding.get('candidate', {}).get('target_base_sha')
               != contract.get('target_base_sha')
            or candidate_binding.get('candidate', {}).get('entry')
               != contract.get('entry')
            or candidate_binding.get('candidate', {}).get('files')
               != result.get('binding', {}).get('files')):
        raise ValueError('REVIEW_CANDIDATE_BINDING_MISMATCH')
    completion = supervisor.complete_development_candidate(
        contract['task_id'],
        candidate_binding['candidate_event_id'],
        result['bundle_sha256'],
        result['review_record_ids'],
        completion_event_id,
        next_action=next_action)
    return dict(result, canonical_completion=completion)


def continuation_due(binding,receipt_read_at,now,evidence=None,ledger_keys=None):
    fields={'task_id','attempt_id','run_id','session_id','fence','checkpoint_sha256',
            'ledger_revision','receipt_sha256','authority_key_id'}
    if not isinstance(binding,dict) or set(binding)!=fields:
        raise ValueError('EXACT_CANONICAL_CONTINUATION_BINDING_REQUIRED')
    for name in fields-{'fence','ledger_revision','checkpoint_sha256','receipt_sha256'}:
        if not isinstance(binding[name],str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',binding[name]):
            raise ValueError('INVALID_CANONICAL_BINDING')
    for name in ('fence','ledger_revision'):
        if type(binding[name]) is not int or binding[name]<1:raise ValueError('INVALID_CANONICAL_REVISION')
    for name in ('checkpoint_sha256','receipt_sha256'):
        if not isinstance(binding[name],str) or not re.fullmatch('[0-9a-f]{64}',binding[name]):
            raise ValueError('INVALID_CANONICAL_DIGEST')
    for number in (receipt_read_at,now):
        if type(number) not in (int,float) or not math.isfinite(number):raise ValueError('FINITE_TIME_REQUIRED')
    if now<receipt_read_at:raise ValueError('CLOCK_RECONCILIATION_REQUIRED')
    if evidence is not None:
        value=authenticated(evidence,ledger_keys)
        if (evidence['key_id']!=binding['authority_key_id'] or set(value)!={'binding','kind','observed_at','proof'}
                or value['binding']!=binding or type(value['observed_at']) not in (int,float)
                or not math.isfinite(value['observed_at']) or not receipt_read_at<=value['observed_at']<=now
                or not isinstance(value['proof'],dict)):
            raise ValueError('SAME_ATTEMPT_FRESH_CANONICAL_EVIDENCE_REQUIRED')
        kind=value['kind'];proof=value['proof']
        if kind=='CONTINUED' and proof=={'verified_execution':True}:
            return {'state':kind,'authority_effect':'NONE','record_id':evidence['record_id']}
        if kind=='HANDOFF_ACKNOWLEDGED' and proof==dict(receiver_accepted=True,old_writer_stopped=True,old_fence_invalidated=True,effects_reconciled=True):
            return {'state':kind,'authority_effect':'NONE','record_id':evidence['record_id']}
        if kind=='HOLD' and set(proof)=={'blocker','checkpoint','next_action'} and all(isinstance(v,str) and v.strip() for v in proof.values()) and proof['checkpoint']==binding['checkpoint_sha256']:
            return {'state':kind,'authority_effect':'NONE','record_id':evidence['record_id']}
    age=now-receipt_read_at
    action='HOLD_CONTINUATION_MISSING' if age>=900 else 'INSPECT_AND_RESUME_SAME_ATTEMPT' if age>=600 else 'RECOVER_INTAKE' if age>=300 else 'AWAIT_EXECUTION_EVIDENCE'
    return {'state':action,'authority_effect':'NONE','takeover_allowed':False,'read_or_heartbeat_is_progress':False}



def continuation_batch(records, now, ledger_keys=None):
    """Assess every supplied canonical receipt; never dispatch or mutate authority.

    The caller must supply the complete task inventory from the existing ledger.
    One invalid receipt becomes a visible HOLD without hiding other tasks.
    """
    if not isinstance(records, list) or len(records) > 256:
        raise ValueError('BOUNDED_CANONICAL_INVENTORY_REQUIRED')
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('FINITE_TIME_REQUIRED')
    results = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {'binding', 'receipt_read_at', 'evidence'}:
            results.append({'index': index, 'state': 'HOLD_INVALID_INVENTORY_RECORD',
                            'authority_effect': 'NONE', 'takeover_allowed': False})
            continue
        try:
            decision = continuation_due(record['binding'], record['receipt_read_at'],
                                        now, record['evidence'], ledger_keys)
            results.append(dict(decision, index=index))
        except (ValueError, TypeError, OverflowError):
            results.append({'index': index, 'state': 'HOLD_INVALID_CONTINUATION_EVIDENCE',
                            'authority_effect': 'NONE', 'takeover_allowed': False})
    return results
