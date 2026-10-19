"""Exact window-one + window-two real-chain acceptance. No mock effect adapter."""
import hashlib, io, json, os, signal, stat, sys, tarfile, tempfile, time, unittest
from pathlib import Path
from production.p2_install.coordinator import Coordinator
from production import p2_artifacts, p2_runtime

ARTIFACTS_COMMIT="ea31dbbec2a8710b964efb38fa2975684bbd9739"
RUNTIME_COMMIT="499bcc43f4c992b21035c22446ccc4d915873fb1"
CHAIN_VERSION=hashlib.sha256((ARTIFACTS_COMMIT+"\n"+RUNTIME_COMMIT).encode()).hexdigest()
SERVICE="""#!{python}
import os,socket,sys,threading
path=sys.argv[1]
try: os.unlink(path)
except FileNotFoundError: pass
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.bind(path); s.listen(16)
def h(c):
    try: c.recv(128); c.sendall(b"PONG\\n")
    finally: c.close()
while True:
    c,_=s.accept(); threading.Thread(target=h,args=(c,),daemon=True).start()
"""

class ArtifactAdapter:
    execute=staticmethod(p2_artifacts.execute); inspect=staticmethod(p2_artifacts.inspect); recover=staticmethod(p2_artifacts.recover)
class RuntimeAdapter:
    execute=staticmethod(p2_runtime.execute); inspect=staticmethod(p2_runtime.inspect); recover=staticmethod(p2_runtime.recover)

def sha(b): return hashlib.sha256(b).hexdigest()

class ExactComponentChain(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); base=Path(self.tmp.name)
        self.coord=base/"coordinator"; self.artifacts=base/"artifacts"; self.runtime=base/"runtime"; self.later=base/"later"; self.inputs=base/"inputs"
        for p in (self.coord,self.artifacts,self.runtime,self.later,self.inputs): p.mkdir(mode=0o700)
        self.plan={"schema":1,"release":CHAIN_VERSION,"batches":["artifact","service","later"]}
        service=SERVICE.format(python=sys.executable).encode()
        self.archive=self.inputs/"service.tar"
        with tarfile.open(self.archive,"w") as t:
            m=tarfile.TarInfo("bin/service"); m.size=len(service); t.addfile(m,io.BytesIO(service))
        self.artifact_req={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"chain-i1","batch_id":"artifact","attempt_id":"artifact-a1","root":str(self.artifacts),"version":CHAIN_VERSION,"deadline_utc":int(time.time())+60,
          "inputs":{"operation":"install","archive":str(self.archive),"archive_sha256":sha(self.archive.read_bytes()),"files":{"bin/service":sha(service)},"modes":{"bin/service":448}}}
        self.program=self.artifacts/"versions/chain-i1--artifact/bin/service"; self.socket=self.runtime/"service.sock"
        self.runtime_req={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"chain-i1","batch_id":"service","attempt_id":"service-a1","root":str(self.runtime),"version":CHAIN_VERSION,"deadline_utc":int(time.time())+60,
          "inputs":{"operation":"start","argv":[str(self.program),str(self.socket)],"cwd":str(self.runtime),"env":{},"health":{"type":"unix_socket","path":str(self.socket),"request":"PING\n","expect":"PONG\n","connect_timeout":0.1,"read_timeout":0.1,"total_timeout":3.0,"max_response":64},"timeout":3.0}}
        bad=b"later-node-failure"; self.bad_archive=self.inputs/"later.tar"
        with tarfile.open(self.bad_archive,"w") as t:
            m=tarfile.TarInfo("fault.bin"); m.size=len(bad); t.addfile(m,io.BytesIO(bad))
        self.later_req={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"chain-i1","batch_id":"later","attempt_id":"later-a1","root":str(self.later),"version":CHAIN_VERSION,"deadline_utc":int(time.time())+60,
          "inputs":{"operation":"install","archive":str(self.bad_archive),"archive_sha256":sha(self.bad_archive.read_bytes()),"files":{"fault.bin":"0"*64},"modes":{"fault.bin":384}}}

    def tearDown(self):
        j=self.runtime/"batch-service.json"
        if j.exists():
            try:
                e=json.loads(j.read_text())
                if e.get("pgid"):
                    try: os.killpg(e["pgid"],signal.SIGKILL)
                    except ProcessLookupError: pass
                if e.get("collector"):
                    try: os.kill(e["collector"]["pid"],signal.SIGKILL)
                    except ProcessLookupError: pass
            except Exception: pass
        self.tmp.cleanup()

    def adapters(self): return {"artifact":ArtifactAdapter(),"service":RuntimeAdapter(),"later":ArtifactAdapter()}
    def roots(self): return {"artifact":str(self.artifacts),"service":str(self.runtime),"later":str(self.later)}

    def test_real_chain_restart_recovery_preserves_prior_commits(self):
        with Coordinator(str(self.coord),self.plan,self.adapters(),component_roots=self.roots()) as c:
            artifact=c.execute(self.artifact_req); self.assertEqual(artifact["status"],"COMMITTED",artifact)
            self.assertTrue(self.program.is_file()); self.assertEqual(stat.S_IMODE(os.lstat(self.program).st_mode),0o700)
            service=c.execute(self.runtime_req); self.assertEqual(service["status"],"COMMITTED",service); self.assertTrue(self.socket.exists())
            self.assertEqual(c.inspect(self.artifact_req)["status"],"COMMITTED")
            self.assertEqual(c.inspect(self.runtime_req)["status"],"COMMITTED")
            self.assertEqual(p2_artifacts.inspect(self.artifact_req)["status"],"COMMITTED")
            self.assertEqual(p2_runtime.inspect(self.runtime_req)["status"],"COMMITTED")
            later=c.execute(self.later_req); self.assertEqual(later["status"],"HOLD",later)

        ap=Path(artifact["receipt"]["path"]); ar=ap.read_bytes(); rp=Path(service["receipt"]["path"]); rr=rp.read_bytes()
        before=(self.program.read_bytes(),os.lstat(self.program).st_ino,os.lstat(self.program).st_mtime_ns,stat.S_IMODE(os.lstat(self.program).st_mode))
        e1=json.loads((self.runtime/"batch-service.json").read_text()); self.assertEqual(p2_runtime.workload_state(e1)[0],"LIVE")
        self.assertEqual(e1["commit_receipt"],service["receipt"])

        with Coordinator(str(self.coord),self.plan,self.adapters(),component_roots=self.roots()) as c:
            recovered=c.recover(self.later_req); self.assertEqual(recovered["status"],"HOLD",recovered)
            self.assertEqual(c.inspect(self.artifact_req)["status"],"COMMITTED")
            self.assertEqual(c.inspect(self.runtime_req)["status"],"COMMITTED")

        self.assertEqual((self.program.read_bytes(),os.lstat(self.program).st_ino,os.lstat(self.program).st_mtime_ns,stat.S_IMODE(os.lstat(self.program).st_mode)),before)
        e2=json.loads((self.runtime/"batch-service.json").read_text())
        self.assertEqual((e2["pid"],e2["start"],e2["pgid"],e2["session"]),(e1["pid"],e1["start"],e1["pgid"],e1["session"]))
        self.assertEqual(p2_runtime.workload_state(e2)[0],"LIVE")
        self.assertEqual(ap.read_bytes(),ar); self.assertEqual(rp.read_bytes(),rr)
        self.assertEqual(p2_artifacts.inspect(self.artifact_req)["status"],"COMMITTED")
        self.assertEqual(p2_runtime.inspect(self.runtime_req)["status"],"COMMITTED")
        self.assertFalse((self.later/".p2_artifacts/receipts/chain-i1--later.json").exists())
        self.assertTrue((self.later/".p2_artifacts/snapshots/chain-i1--later--later-a1.tar").exists())
        self.assertTrue(list((self.later/".p2_artifacts/errors").glob("chain-i1--later--*.json")))

if __name__=="__main__": unittest.main()
