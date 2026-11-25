"""Isolated fixture generator/mutator; never imported by production plugin."""
import json,os,pathlib,shutil,sqlite3,sys,time
import test_handoff_backup_script_main_delta as original

root=pathlib.Path(sys.argv[1]);action=sys.argv[2]
if action=='prepare':
    f=original.ScriptMainBackup();f.setUp()
    try:
        result=f.host.record(f.sessions.get(f.token),f.req)
        db=f.s.db
        db.execute('CREATE TABLE IF NOT EXISTS authority_runtime_profile(singleton INTEGER,profile TEXT)')
        db.execute('DELETE FROM authority_runtime_profile')
        db.execute("INSERT INTO authority_runtime_profile VALUES(1,'FORMAL')")
        db.execute('''CREATE TABLE IF NOT EXISTS formal_approval_roles(
          tenant_id TEXT,task_id TEXT,attempt_id TEXT,principal_id TEXT,approval_kind TEXT,valid_until REAL,granted_by TEXT)''')
        db.execute("UPDATE model_assignments SET principal_id='alice' WHERE task_id='demo-b'")
        db.execute('INSERT INTO formal_approval_roles VALUES(?,?,?,?,?,?,?)',
            ('tenant-1','demo-b','attempt-1','alice','handoff:READ',time.time()+600,'admin:fixture'))
        db.commit()
        binding=dict(gateway_profile_id='profile-fixture',tenant_id='tenant-1',principal_id='alice',
            session_hash=f.sessions._hash(f.token),task_id='demo-b',attempt_id='attempt-1',expires_at=time.time()+600)
        config=dict(schema_version=1,enabled=True,tenant_id='tenant-1',issuer=f.host.issuer,
            lifecycle_root=str(root/'lifecycle'),ledger_root=str(root/'ledger'),namespace='tenant-ledger',writer='writer',
            contracts=list(f.host.role_contract.contracts),intake_plans=[])
        dispatch=f.host.mcp_config
        db_path=root/'canonical.sqlite'
        f.s.close();shutil.copyfile(f.path,str(db_path))
        for name,value in [('runtime.json',config),('dispatch.json',dispatch)]:
            p=root/name;p.write_text(json.dumps(value));p.chmod(0o600)
        doc=dict(enabled=True,python='/usr/bin/python3',database=str(db_path),runtimeConfig=str(root/'runtime.json'),
            dispatchConfig=str(root/'dispatch.json'),bindings=[binding])
        request=dict(sessionKey='fixture-resource-not-identity',task_id='demo-b',attempt_id='attempt-1',
            event_id=f.req['event_id'],operation_id='read-fixture-1')
        print(json.dumps(dict(config=doc,params=request)))
    finally:f.doCleanups()
else:
    db=sqlite3.connect(str(root/'canonical.sqlite'))
    try:
        if action=='revoke-grant':db.execute('DELETE FROM formal_approval_roles')
        elif action=='revoke-session':db.execute('UPDATE task_center_sessions SET revoked_at=?',(time.time(),))
        elif action=='test-profile':db.execute("UPDATE authority_runtime_profile SET profile='TEST_ONLY'")
        else:raise ValueError('unknown fixture mutation')
        db.commit()
    finally:db.close()
