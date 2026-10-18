"""Independent-auditor signature verification against Owner-enrolled trust.
Trust and exact comment anchors are root-private target inputs, never supplied by
GitHub comments, installed source, request JSON, or the source author's workflow.
No key generation/enrollment/signing function exists in production code.
"""
import base64
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from scripts.pr122_customer_core import Denied,canonical,digest

def need(ok,msg):
    if not ok:raise Denied('HOLD:'+msg)

def verify(comment,approval_comment,approval,plan,trust,fetch):
    need(set(trust)=={'schema','source_writer_principal','reviewers','revoked_review_ids','install_anchors'} and trust['schema']==1,'REVIEW_TRUST_SCHEMA')
    anchor=trust['install_anchors'].get(approval['transaction'])
    need(type(anchor) is dict and set(anchor)=={'install_comment_id','install_body_sha256','review_comment_id','review_body_sha256','custody_evidence_sha256'},'OWNER_ANCHOR_REQUIRED')
    need(anchor['install_comment_id']==approval_comment['id'] and anchor['install_body_sha256']==digest(approval_comment['body'].encode()) and anchor['review_comment_id']==comment['id'] and anchor['review_body_sha256']==digest(comment['body'].encode()),'IMMUTABLE_COMMENT_ANCHORS')
    need(type(anchor['custody_evidence_sha256']) is str and len(anchor['custody_evidence_sha256'])==64 and all(c in '0123456789abcdef' for c in anchor['custody_evidence_sha256']),'OWNER_CUSTODY_EVIDENCE_REQUIRED')
    need(comment['id'] not in trust['revoked_review_ids'],'REVIEW_REVOKED')
    need(comment['body'].startswith('XUANJUN_CUSTOMER_REVIEW_V2\n'),'SIGNED_REVIEW_REQUIRED')
    from scripts.pr122_customer_http import strict_json
    envelope=strict_json(comment['body'].split('\n',1)[1].encode())
    need(set(envelope)=={'payload','signature','reviewer_key_id'},'SIGNED_ENVELOPE_SCHEMA')
    key=trust['reviewers'].get(envelope['reviewer_key_id'])
    need(type(key) is dict and set(key)=={'public_key_b64','principal','status','custody_evidence_sha256'} and key['status']=='ACTIVE' and key['principal']!=trust['source_writer_principal'] and key['custody_evidence_sha256']==anchor['custody_evidence_sha256'],'INDEPENDENT_ENROLLED_KEY_REQUIRED')
    payload=envelope['payload']
    expected_fields={'decision','reviewer_principal','source_writer_principal','source_commit','source_tree','manifest_sha256','artifact_zip_sha256','artifact_tar_sha256','artifact_id','ci_run_id','scope_sha256','findings','issued_unix','expires_unix'}
    whole=approval.get('attempt_policy')=='CONTROLLED_WHOLE_WEBSITE_V3'
    if whole:expected_fields.add('workflow_contract_sha256')
    from scripts import pr122_customer_profile as deployment
    login_only=deployment.is_login(plan)
    if login_only:expected_fields.update({'deployment_profile','login_acceptance_sha256'})
    if 'permit_window_seconds' in plan or 'permit_window_seconds' in approval:expected_fields.add('permit_window_seconds')
    need(type(payload) is dict and set(payload)==expected_fields,'REVIEW_PAYLOAD_SCHEMA')
    try:
        pub=base64.b64decode(key['public_key_b64'],validate=True);signature=base64.b64decode(envelope['signature'],validate=True)
        Ed25519PublicKey.from_public_bytes(pub).verify(signature,canonical(payload))
    except Exception:raise Denied('HOLD:INDEPENDENT_REVIEW_SIGNATURE') from None
    if whole:
        need(type(plan.get('workflow_contract')) is dict and
             payload['workflow_contract_sha256']==approval.get('workflow_contract_sha256')==
             digest(canonical(plan['workflow_contract'])),'EXACT_INDEPENDENT_WORKFLOW_SCOPE')
    if login_only:
        need(whole and payload['deployment_profile']==approval.get('deployment_profile')==deployment.LOGIN_ONLY
             and payload['login_acceptance_sha256']==approval.get('login_acceptance_sha256')==plan['login_acceptance_sha256'],
             'EXACT_INDEPENDENT_LOGIN_SCOPE')
    if 'permit_window_seconds' in expected_fields:
        need(type(payload['permit_window_seconds']) is int and payload['permit_window_seconds']==approval.get('permit_window_seconds')==plan.get('permit_window_seconds')==deployment.WINDOW_SECONDS,'SIGNED_FIVE_HOUR_WINDOW')
    need(payload['decision']=='AUDIT_PASS' and payload['reviewer_principal']==key['principal'] and payload['source_writer_principal']==trust['source_writer_principal'],'INDEPENDENT_REVIEW_DECISION')
    need(type(payload['issued_unix']) is int and type(payload['expires_unix']) is int and payload['issued_unix']<=time.time()<payload['expires_unix'] and 0<payload['expires_unix']-payload['issued_unix']<=7*86400,'INDEPENDENT_REVIEW_EXPIRED')
    for name in ('source_commit','source_tree','manifest_sha256','artifact_tar_sha256','scope_sha256'):
        need(payload[name]==plan[name] and approval[name]==plan[name],'EXACT_REVIEW_OBJECT:'+name)
    for name in ('ci_run_id','artifact_id','artifact_zip_sha256'):
        need(payload[name]==approval[name],'EXACT_REVIEW_ARTIFACT:'+name)
    findings=payload['findings'];need(type(findings) is dict and set(findings)=={'R1','R2','R3'},'COMPLETE_FINDINGS_REQUIRED')
    for finding in findings.values():
        need(type(finding) is dict and set(finding)=={'state','evidence_sha256'} and finding['state']=='CLOSED' and type(finding['evidence_sha256']) is list and bool(finding['evidence_sha256']),'FINDINGS_NOT_CLOSED')
        need(all(type(x) is str and len(x)==64 and all(c in '0123456789abcdef' for c in x) for x in finding['evidence_sha256']),'FINDING_EVIDENCE_REQUIRED')
    if login_only:
        need(plan['login_acceptance_sha256'] in findings['R3']['evidence_sha256'],'LOGIN_TARGET_EVIDENCE_REQUIRED')
    else:need(plan['telegram_credential_evidence_sha256'] in findings['R3']['evidence_sha256'],'TELEGRAM_TARGET_EVIDENCE_REQUIRED')
    commit=fetch('git/commits/'+payload['source_commit']);need(commit['sha']==payload['source_commit'] and commit['tree']['sha']==payload['source_tree'],'IMMUTABLE_GIT_TREE')
    artifact=fetch('actions/artifacts/'+str(payload['artifact_id']))
    need(artifact['id']==payload['artifact_id'] and artifact['expired'] is False and artifact['digest']=='sha256:'+payload['artifact_zip_sha256'] and artifact['workflow_run']['id']==payload['ci_run_id'] and artifact['workflow_run']['head_sha']==payload['source_commit'],'REVIEWED_ARTIFACT_IDENTITY')
    return payload

def trust_digest(trust):
    # Install anchors are enrolled AFTER plan and therefore cannot be part of
    # the plan's own hash (which the exact install-comment anchor contains).
    return digest(canonical({k:v for k,v in trust.items() if k!='install_anchors'}))
