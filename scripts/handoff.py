"""Fail-closed handoff. No trusted metadata provider has been connected.

Only fixed internal code can construct this record: there is no input surface for
caller-provided checks, evidence ids, token values, paths, or arbitrary messages.
"""
import hashlib, json, re
import source_adapter
SCHEMA = 'source-backup-handoff/v1'
REQUIRED = ('source_artifact', 'authorization_records_and_scope', 'permission_acquisition_entry',
            'installation_commands_and_dependencies', 'configuration_entries',
            'protected_config_refs', 'credential_refs', 'reauthorization_process',
            'secure_restore', 'protected_content_backup', 'effects_checkpoint', 'backup_acceptance')

def envelope(cycle_id, source_manifest_sha256, source_result, source_verified, *, pending=False):
    if not isinstance(cycle_id, str) or not re.fullmatch(r'[0-9a-f]{32}', cycle_id):
        raise ValueError('invalid cycle id')
    if source_manifest_sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}', source_manifest_sha256):
        raise ValueError('invalid source manifest hash')
    if source_result is not None and not re.fullmatch(r'[0-9a-f]{40}', source_result):
        raise ValueError('invalid source result')
    # Only this fixed adapter reads the original producer; its cycle is not
    # the candidate UUID or its local snapshot, so never claim that binding.
    evidence = source_adapter.collect()
    source_valid = False
    statuses = {name: {'status': 'unknown'} for name in REQUIRED}
    missing = [name for name in REQUIRED if statuses[name]['status'] != 'verified']
    key = hashlib.sha256(json.dumps([source_manifest_sha256, missing, bool(pending)],separators=(',', ':')).encode()).hexdigest()
    return {'schema': SCHEMA, 'cycle_id': cycle_id, 'source_manifest_sha256': source_manifest_sha256,
            'source_result': evidence.get('result') if source_valid else None, 'source_verified': source_valid,
            'original_source_evidence': evidence, 'dots_provider': 'NOT_CONNECTED',
            'overall_status': 'incomplete', 'requirements': statuses, 'missing': missing,
            'reconciliation_required': bool(pending),
            'alert': {'state': 'open', 'dedupe_key': key, 'delivery_receipt': 'NOT_SENT'}}
