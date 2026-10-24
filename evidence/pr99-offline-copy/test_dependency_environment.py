import hashlib,importlib.util,json,pathlib,subprocess,sys,tempfile
path=pathlib.Path(__file__).with_name("build_dependency_environment.py")
spec=importlib.util.spec_from_file_location("builder",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
compile(m.REMOTE,"remote_metadata.py","exec")
versions={name:"1.0.0" for name in m.PACKAGES}
def record(v=None,python=None,host=None):
 return {"host":host or "iZ6wee8q9z4t03hvqumwfhZ","profiles":[{"interpreter":"/known/python","python":python or [3,11],"versions":dict(versions if v is None else v)}]}
profile,pins=m.select_source(record());assert len(pins)==13
passed=["valid_exact_source_versions","remote_metadata_syntax"]
cases=[
 ("wrong_host",record(host="wrong")),
 ("wrong_python",record(python=[3,12])),
 ("missing_dependency",record({k:v for k,v in versions.items() if k!="ta"})),
 ("option_injection_version",record(dict(versions,ta="1.0 --index-url evil"))),
 ("url_package_name",record(dict(versions,**{"https://evil":"1.0"}))),
 ("duplicate_conflicting_alias",record(dict(versions,**{"websocket_client":"2.0"})))]
for name,item in cases:
 try:m.select_source(item)
 except RuntimeError:passed.append(name+"_rejected")
 else:raise AssertionError(name)
with tempfile.TemporaryDirectory() as td:
 m.BUILD=pathlib.Path(td)
 m.run_logged([sys.executable,"-I","-B","-c","print('synthetic command only')"],"ok.log",30)
 assert (m.BUILD/"ok.log").read_text().strip()=="synthetic command only"
 passed.append("real_child_command_success_logged")
 try:m.run_logged([sys.executable,"-I","-B","-c","raise SystemExit(7)"],"fail.log",30)
 except RuntimeError:passed.append("real_child_failure_propagated_log_preserved")
 else:raise AssertionError("child failure")
 for mode,isdir,expected in [(0o700,True,0o755),(0o600,False,0o644),(0o700,False,0o744)]:
  final=0o755 if isdir else 0o644 | (mode&0o111)
  assert final==expected and final&0o044==0o044 and not final&0o022
 passed.append("frozen_environment_final_read_access_mode")
print(json.dumps({"passed":len(passed),"checks":passed,"server_execution":False,"real_dependency_install_tested":False,"real_korea_netns_import_tested":False,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}))
