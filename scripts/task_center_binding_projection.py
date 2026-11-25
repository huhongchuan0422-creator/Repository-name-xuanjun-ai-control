"""Metadata only; no identity, grant, mapping or session creation."""
import math,time
from task_center_handoff_host import ID

def read_binding_status(db_path,tenant_id,task_id,attempt_id,principal_id):
    if any(not isinstance(x,str) or not ID.fullmatch(x) for x in (tenant_id,task_id,attempt_id,principal_id)):
        raise ValueError('EXACT_BINDING_QUERY_REQUIRED')
    from task_center_app import _read_only_connection
    try:
        db=_read_only_connection(db_path,('tasks','gateway_task_metadata','task_center_sessions',
            'authority_runtime_profile','model_assignments','role_templates','formal_approval_roles'))
    except ValueError:
        raise RuntimeError('BINDING_SCHEMA_UNAVAILABLE') from None
    try:
        db.execute('BEGIN')
        now=time.time()
        row=db.execute('''SELECT t.attempt_id,t.spec_sha256,t.checkpoint_sha256
          FROM tasks t JOIN gateway_task_metadata m ON m.task_id=t.task_id
          WHERE m.tenant_id=? AND t.task_id=?''',(tenant_id,task_id)).fetchone()
        if row is None or row['attempt_id']!=attempt_id:raise LookupError('BINDING_TARGET_UNAVAILABLE')
        profile=db.execute('SELECT profile FROM authority_runtime_profile WHERE singleton=1').fetchone()
        sessions=db.execute('''SELECT count(*) FROM task_center_sessions
          WHERE tenant_id=? AND principal_id=? AND revoked_at IS NULL AND expires_at>?''',
          (tenant_id,principal_id,now)).fetchone()[0]
        assignments=db.execute('''SELECT count(*) FROM model_assignments a JOIN role_templates r
          ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
          WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.principal_id=?
            AND a.state='ASSIGNED' AND r.enabled=1''',(tenant_id,task_id,attempt_id,principal_id)).fetchone()[0]
        grant=db.execute('''SELECT valid_until,granted_by FROM formal_approval_roles
          WHERE tenant_id=? AND task_id=? AND attempt_id=? AND principal_id=? AND approval_kind='handoff:READ' ''',
          (tenant_id,task_id,attempt_id,principal_id)).fetchone()
        live=(grant is not None and type(grant['valid_until']) in (int,float) and math.isfinite(grant['valid_until'])
            and grant['valid_until']>now and isinstance(grant['granted_by'],str) and grant['granted_by'].startswith('admin:'))
        return dict(schema_version=1,mode='READ_ONLY',authority_created=False,
            task_id=task_id,attempt_id=attempt_id,principal_id=principal_id,
            task_spec_sha256=row['spec_sha256'],checkpoint_sha256=row['checkpoint_sha256'],
            formal_profile=profile is not None and profile['profile']=='FORMAL',
            current_session_count=sessions,unique_current_session=sessions==1,
            enabled_assignment_count=assignments,unique_enabled_assignment=assignments==1,
            live_handoff_read_grant=bool(live),grant_valid_until=grant['valid_until'] if live else None,
            source_mapping='UNVERIFIED_NOT_STORED_IN_THIS_PROJECTION',
            readiness='FACTS_ONLY_NOT_AUTHORIZATION')
    finally:db.close()
