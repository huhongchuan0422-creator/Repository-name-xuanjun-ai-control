"""Owner-direct authority policy over the SAME published Journal and protocol.

No synthetic review ID, permit issuer, new Journal/claim/store or Writer epoch.
Only the superseded review policy changes. Fixed scope, exact source/data
bindings, expiry, event identity and effect ordering remain required.
"""
import re
import migration_transaction as original

Journal=original.Journal
Hold=original.Hold
require=original.require
encode=original.encode
digest=original.digest
exact_keys=original.exact_keys
request=original.request
validate_receipt=original.validate_receipt
validate_event=original.validate_event
STEPS=original.STEPS
ROLLBACK=original.ROLLBACK
time=original.time
SHA=original.SHA
TOKEN=original.TOKEN
OWNER_AUTHORITY={'mode':'OWNER_DIRECT','instruction_at':'2026-10-19T00:29:13+08:00','scope':'PR99_DOMESTIC_MIGRATION'}


def source_manifest():return original.source_manifest()


def validate_plan(plan,expected_digest,now):
    exact_keys(plan,('action','transaction_id','head','host','source_host','release',
      'issued_at','expires_at','owner_authority','source_hashes','bindings','steps'),'OWNER_PLAN_SCHEMA')
    require(type(expected_digest)is str and SHA.fullmatch(expected_digest) and digest(plan)==expected_digest,'PLAN_DIGEST')
    require(plan['owner_authority']==OWNER_AUTHORITY,'OWNER_AUTHORITY_BINDING')
    require(plan['action']==original.ACTION and plan['host']==original.HOST and
      plan['source_host']==original.SOURCE_HOST and plan['release']==original.RELEASE,'FIXED_SCOPE')
    require(type(plan['transaction_id'])is str and TOKEN.fullmatch(plan['transaction_id']),'TRANSACTION_ID')
    require(type(plan['head'])is str and re.fullmatch('[0-9a-f]{40}',plan['head']),'HEAD')
    require(type(plan['issued_at'])is type(plan['expires_at'])is int and
      plan['issued_at']<=now<plan['expires_at']<=plan['issued_at']+7200,'PLAN_EXPIRED')
    require(plan['steps']==list(STEPS),'EXACT_STEP_ORDER')
    hashes=plan['source_hashes']
    exact_keys(hashes,('migration_transaction.py','production_start.py','stopped_transaction.py','final_materials.py','production_transport.py'),'SOURCE_SET')
    require(all(type(v)is str and SHA.fullmatch(v) for v in hashes.values()),'SOURCE_DIGEST')
    bindings=plan['bindings']
    exact_keys(bindings,('writer_inventory','protected_inventory','final_manifest_contract','runtime_identity',
      'unit_manifest','business_acceptance_contract','route_contract'),'BINDING_SET')
    require(all(type(v)is str and SHA.fullmatch(v) for v in bindings.values()),'BINDING_DIGEST')
    return plan
