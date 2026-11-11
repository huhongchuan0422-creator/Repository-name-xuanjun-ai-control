import hashlib,importlib.util,io,json,pathlib,sqlite3,tarfile,tempfile
p=pathlib.Path(__file__).with_name("selective_restore.py")
spec=importlib.util.spec_from_file_location("selective_restore",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as td:
 d=pathlib.Path(td);db=d/"original.db"
 con=sqlite3.connect(str(db));con.execute("CREATE TABLE recovery_test (n INTEGER)");con.execute("INSERT INTO recovery_test VALUES(7)");con.commit();con.close()
 dbbytes=db.read_bytes();dbsha=hashlib.sha256(dbbytes).hexdigest()
 base=[("opt/trading-system/app/main.py",b"print('synthetic')\n",None),
 ("opt/trading-system/requirements.txt",b"synthetic-dependency==1\n",None),
 ("root/xj-db-backup.cea2af8k/trading.db",dbbytes,None),
 ("etc/systemd/system/unwanted.service",b"DO NOT INSTALL",None),
 ("opt/trading-system/.env",b"SYNTHETIC_SECRET_DO_NOT_COPY",None),
 ("opt/trading-system/config/keys.py",b"SYNTHETIC_CONFIG_DO_NOT_COPY",None),
 ("opt/trading-system/runtime/credentials.json",b"SYNTHETIC_CONFIG_DO_NOT_COPY",None)]
 def archive(rows):
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode="w:gz") as t:
   for name,data,link in rows:
    info=tarfile.TarInfo(name)
    if link is not None:info.type=tarfile.SYMTYPE;info.linkname=link;t.addfile(info)
    else:info.size=len(data);t.addfile(info,io.BytesIO(data))
  return out.getvalue()
 payload=archive(base);w=d/"good";w.mkdir(mode=0o700)
 result=m.recover_stream(io.BytesIO(payload),w,hashlib.sha256(payload).hexdigest(),dbsha)
 assert result["files"]==3 and result["dependency_manifests"]==1
 assert not (w/"code/config").exists() and not (w/"code/.env").exists()
 assert not (w/"etc").exists()
 assert (w/"code/app/main.py").stat().st_mode&0o777==0o400
 assert db.read_bytes()==dbbytes
 passed=["selective_regular_files_and_exact_sqlite","excluded_config_env_units_not_restored","sqlite_integrity_and_source_unchanged","restored_files_readonly"]
 cases=[
 ("traversal",base+[("../escape.py",b"x",None)],None,None),
 ("symlink",base+[("opt/trading-system/app/link.py",b"","/etc/passwd")],None,None),
 ("duplicate",base+[base[0]],None,None),
 ("wrong_archive_hash",base,"0"*64,None),
 ("wrong_database_hash",base,None,"0"*64)]
 for name,rows,plain,expected_db in cases:
  data=archive(rows);work=d/name;work.mkdir(mode=0o700)
  try:m.recover_stream(io.BytesIO(data),work,plain or hashlib.sha256(data).hexdigest(),expected_db or dbsha)
  except RuntimeError:passed.append(name+"_rejected")
  else:raise AssertionError(name+" incorrectly passed")
  assert not (d/"escape.py").exists()
 print(json.dumps({"checks":passed,"passed":len(passed),"server_execution":False,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size}))
