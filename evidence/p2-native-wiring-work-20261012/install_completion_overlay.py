"""Complete offline callback staging and preserve adopted masks on rollback."""
import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);mp=r/'deploy/integration-manifest.json';m=json.loads(mp.read_text())
def load(p):
 b=(r/p).read_bytes()
 if hashlib.sha256(b).hexdigest()!=m['files'][p]:raise ValueError('COMPLETION_INPUT_MANIFEST')
 return b.decode()
def replace(s,a,b):
 if s.count(a)!=1:raise ValueError('COMPLETION_ANCHOR_'+a[:60])
 return s.replace(a,b)
p='stage1/ledger_install_stage.py';s=load(p)
s=replace(s,'    after = verify(staged_generation)', '''    # Existing callback tables stay byte-logically unchanged; add the missing
    # replay side table only on the isolated generation, before activation.
    from uk_owner_callback_core import install_schema, validate_schema
    install_schema(staged_generation)
    validate_schema(staged_generation)
    after = verify(staged_generation)''')
texts={p:s}
p='stage1/legacy_host_adapter.py';s=load(p)
s=replace(s,'    def restore_legacy_files(self, gateway_only=False):','    def restore_legacy_files(self, gateway_only=False, preserve_mask=False):')
s=replace(s,"        state = self._state()\n        gateway=", "        if type(preserve_mask) is not bool or (preserve_mask and gateway_only):\n            raise ValueError('INVALID_LEGACY_MASK_SELECTION')\n        state = self._state()\n        gateway=")
anchor='        for unit, data in payloads.items():\n            if gateway_only and unit!=gateway:'
new='''        if preserve_mask:
            # All backups and current targets above are verified first. A known
            # restored gateway is atomically re-masked; never write old unit
            # bytes or restart old execution on an adopted rollback.
            for unit in sorted(payloads):
                path=state['units'][unit]['path']
                if os.path.islink(path) and os.readlink(path)=='/dev/null':
                    continue
                fd,temporary=tempfile.mkstemp(prefix='.p2-mask-',dir=os.path.dirname(path))
                os.close(fd);os.unlink(temporary)
                try:
                    os.symlink('/dev/null',temporary)
                    os.replace(temporary,path)
                    directory=os.open(os.path.dirname(path),os.O_RDONLY|os.O_DIRECTORY)
                    try:os.fsync(directory)
                    finally:os.close(directory)
                finally:
                    if os.path.lexists(temporary):os.unlink(temporary)
            self._command('daemon-reload')
            return {'unit_files_restored':True,'services_restarted':False,'masks_preserved':True}
        for unit, data in payloads.items():
            if gateway_only and unit!=gateway:'''
s=replace(s,anchor,new);texts[p]=s
p='stage1/p2_install_entrypoint.py';s=load(p)
old='self.cutover.adapter.restore_legacy_files()'
if s.count(old)!=2:raise ValueError('COMPLETION_ROLLBACK_CALLERS')
# Keep original adapter API for unadopted plans/fixtures.
s=s.replace(old,"(self.cutover.adapter.restore_legacy_files(preserve_mask=True)\n             if 'legacy_isolation' in plan['cutover'] else self.cutover.adapter.restore_legacy_files())")
texts[p]=s
p='stage1/execution_ledger.py';s=load(p)
s=replace(s,"                if columns != required:\n                    raise SchemaMismatch('Owner callback schema mismatch: ' + table)","""                legacy_replay = table=='owner_callback_replays' and columns==required|{'task_id'}
                if legacy_replay:
                    extra=next(row for row in conn.execute('PRAGMA table_info(owner_callback_replays)').fetchall() if row['name']=='task_id')
                    if extra['type'].upper()!='TEXT' or extra['notnull']!=0 or extra['pk']!=0:
                        raise SchemaMismatch('unsafe legacy Owner replay task column')
                if columns != required and not legacy_replay:
                    raise SchemaMismatch('Owner callback schema mismatch: ' + table)""")
s=replace(s,"            conn.execute('INSERT INTO owner_callback_replays VALUES(?,?)',\n                         (update_id, request_id))", """            replay_columns={row['name'] for row in conn.execute('PRAGMA table_info(owner_callback_replays)').fetchall()}
            if 'task_id' in replay_columns:
                conn.execute('INSERT INTO owner_callback_replays(update_id,request_id,task_id) VALUES(?,?,?)',(update_id,request_id,task_id))
            else:
                conn.execute('INSERT INTO owner_callback_replays(update_id,request_id) VALUES(?,?)',(update_id,request_id))""")
texts[p]=s
for p,s in texts.items():
 compile(s,p,'exec');(r/p).write_text(s);m['files'][p]=hashlib.sha256(s.encode()).hexdigest()
mp.write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
print('OFFLINE_CALLBACK_STAGE_AND_ADOPTED_MASK_ROLLBACK_WIRED')
