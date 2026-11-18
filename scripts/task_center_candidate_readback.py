"""Read candidate bytes from an existing host-selected authority lifecycle root.

The host, not an RPC caller, selects the root and installs this callback on its
HostAuthAdapter. No identity, backup completeness or deployment is implied.
"""
import hashlib
import json
import os
import re
import sqlite3
import stat

class LifecycleCandidateReadback:
    def __init__(self, db, tenant_id, lifecycle_root):
        paths=[r[2] for r in db.execute("PRAGMA database_list") if r[1]=="main"]
        if len(paths)!=1 or not paths[0]:raise ValueError("PERSISTENT_HOST_DB_REQUIRED")
        self.db_path=os.path.realpath(paths[0])
        self.tenant_id = tenant_id
        self.artifacts = os.path.join(os.path.realpath(lifecycle_root), 'artifacts')

    def __call__(self, binding):
        if binding.get('tenant_id') != self.tenant_id:
            return None
        db=sqlite3.connect("file:"+self.db_path+"?mode=ro",uri=True)
        try:
            return self._read(db,binding)
        finally:
            db.close()

    def _read(self,db,binding):
        row = db.execute('''SELECT task_id,attempt_id,artifact_sha256 FROM delivery_candidates
          WHERE tenant_id=? AND candidate_id=?''', (self.tenant_id,binding['candidate_id'])).fetchone()
        snapshot = db.execute('''SELECT snapshot_sha256 FROM candidate_snapshots
          WHERE tenant_id=? AND candidate_id=?''', (self.tenant_id,binding['candidate_id'])).fetchone()
        digest = binding['artifact_sha256']
        if (row is None or snapshot is None or tuple(row) != (binding['task_id'],binding['attempt_id'],digest)
            or snapshot[0] != binding['snapshot_sha256'] or not re.fullmatch('[0-9a-f]{64}',digest)):
            return None
        events = db.execute('''SELECT payload_json FROM events WHERE task_id=? AND attempt_id=?
          AND kind='AUTHENTICATED_HANDOFF_VERIFIED' AND evidence_ref='HOST_AUTHENTICATED' ''',
          (binding['task_id'],binding['attempt_id'])).fetchall()
        matches=[]
        for event in events:
            try: payload=json.loads(event[0])
            except (ValueError,TypeError): continue
            if (isinstance(payload,dict) and payload.get('tenant_id')==self.tenant_id
                and payload.get('snapshot_digest')==binding['snapshot_sha256']
                and payload.get('provider_ref')==binding['provider_ref']
                and all(payload.get(k)==binding[k] for k in ('contract_id','contract_version','contract_sha256'))):
                matches.append(payload.get('event_id'))
        if len(matches)!=1: return None
        fd=os.open(os.path.join(self.artifacts,digest),os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):return None
            h=hashlib.sha256()
            with os.fdopen(fd,'rb') as stream:
                fd=None
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        finally:
            if fd is not None:os.close(fd)
        if h.hexdigest()!=digest:return None
        return {'candidate_id':binding['candidate_id'],'artifact_sha256':digest,
          'snapshot_sha256':binding['snapshot_sha256'],'read_location_ref':'lifecycle-artifact:'+digest,
          'handoff_event_id':matches[0]}
