import hashlib, importlib.util, io, json, math, os, signal, subprocess, sys, tarfile, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("release",ROOT/"scripts/pr122_website_release.py")
release=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(release)
def sha(data): return hashlib.sha256(data).hexdigest()

class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.bundle=self.root/"bundle"
        (self.bundle/"overlay/public/assets").mkdir(parents=True)
        self.original=b"old\n"; self.updated=b"new\n"
        (self.bundle/"overlay/public/assets/tiktok-integration.js").write_bytes(self.updated)
        self.source=self.root/"source.tar.gz"
        with tarfile.open(self.source,"w:gz") as archive:
            for name in ("package","package/public","package/public/assets"):
                item=tarfile.TarInfo(name); item.type=tarfile.DIRTYPE; archive.addfile(item)
            item=tarfile.TarInfo("package/public/assets/tiktok-integration.js"); item.size=len(self.original); archive.addfile(item,io.BytesIO(self.original))
        self.pin={"source_archive_size":self.source.stat().st_size,"source_archive_sha256":release.digest(self.source),
                  "overlay_baselines":{"assets/tiktok-integration.js":sha(self.original)}}
        self.manifest={"schema_version":2,"files":[{"path":"assets/tiktok-integration.js","size":len(self.updated),"sha256":sha(self.updated)}]}
        self.write_bundle(); self.base=self.root/"webroot"
    def tearDown(self): self.temp.cleanup()
    def write_bundle(self):
        (self.bundle/"source-pin.json").write_text(json.dumps(self.pin))
        (self.bundle/"candidate-manifest.json").write_text(json.dumps(self.manifest))
        files=[]
        for name in ("source-pin.json","candidate-manifest.json"):
            path=self.bundle/name; files.append({"path":name,"size":path.stat().st_size,"sha256":release.digest(path)})
        (self.bundle/"PACKAGE_MANIFEST.json").write_text(json.dumps({"schema_version":2,"files":files}))
    def args(self,**kw):
        values=dict(bundle=self.bundle,source_archive=self.source,webroot_base=self.base,transaction_id="tx-1",
                    release_id="release-1",deadline_seconds=5,lock_wait_seconds=1,allow_non_root_test=True)
        values.update(kw); return SimpleNamespace(**values)
    def prepared(self): return release.prepare(self.args())

    def test_w1_sealed_release_is_worker_readable_and_not_worker_writable(self):
        self.prepared(); tree=self.base/"releases/release-1"
        self.assertEqual(tree.stat().st_mode&0o777,0o755)
        self.assertEqual((tree/"public/assets/tiktok-integration.js").stat().st_mode&0o777,0o644)
        self.assertEqual((tree/"public/assets").stat().st_mode&0o777,0o755)
        nobody=65534 if os.geteuid()==0 else os.geteuid()
        code="import os,sys; os.setgid(int(sys.argv[1])); os.setuid(int(sys.argv[1])); p=sys.argv[2]; assert open(p,'rb').read()==b'new\\n';\ntry: open(p,'ab')\nexcept PermissionError: pass\nelse: raise SystemExit(2)"
        if os.geteuid()==0: subprocess.run([sys.executable,"-c",code,str(nobody),str(tree/"public/assets/tiktok-integration.js")],check=True)

    def test_w2_tamper_before_activate_is_rejected(self):
        self.prepared(); (self.base/"releases/release-1/public/assets/tiktok-integration.js").write_bytes(b"bad")
        with self.assertRaisesRegex(release.Hold,"RELEASE_CONTENT_MISMATCH"): release.activate(self.args())
    def test_w2_check_rejects_other_bundle(self):
        self.prepared(); release.activate(self.args()); other=self.root/"other"; other.mkdir()
        (other/"candidate-manifest.json").write_text(json.dumps({"files":[]}))
        with self.assertRaisesRegex(release.Hold,"CALLER_BUNDLE"): release.check(self.args(bundle=other))
    def test_w2_mode_drift_is_rejected(self):
        self.prepared(); os.chmod(self.base/"releases/release-1/public/assets",0o777)
        with self.assertRaisesRegex(release.Hold,"RELEASE_MODE_MISMATCH"): release.activate(self.args())
    def test_w2_receipt_binds_all_artifact_ids(self):
        r=self.prepared()
        for key in ("candidate_manifest_sha256","source_pin_sha256","package_manifest_sha256","source_archive_sha256","trusted_manifest"): self.assertIn(key,r)

    def test_w3_traversal_and_absolute_ids_have_no_side_effect(self):
        for bad in ("../../outside","/absolute","a/b"):
            with self.assertRaisesRegex(release.Hold,"INVALID_RELEASE_ID"): release.prepare(self.args(release_id=bad))
        self.assertFalse(self.base.exists()); self.assertFalse((self.root/"outside").exists())
    def test_w3_bad_transaction_has_no_side_effect(self):
        with self.assertRaisesRegex(release.Hold,"INVALID_TRANSACTION_ID"): release.prepare(self.args(transaction_id="../tx"))
        self.assertFalse(self.base.exists())
    def test_w3_symlink_base_rejected_without_target_change(self):
        target=self.root/"target"; target.mkdir(); self.base.symlink_to(target)
        with self.assertRaisesRegex(release.Hold,"UNSAFE_WEBROOT_BASE|TRUSTED_DIRECTORY_LINK"): release.prepare(self.args())
        self.assertEqual(list(target.iterdir()),[])
    def test_w3_rollback_requires_exact_release(self):
        self.prepared(); release.activate(self.args())
        with self.assertRaisesRegex(release.Hold,"RECEIPT_IDENTITY_MISMATCH"): release.rollback(self.args(release_id="wrong"))
        self.assertTrue((self.base/"current").is_symlink())
    def test_w3_lock_replacement_or_mode_drift_rejected(self):
        self.base.mkdir(mode=0o755); lock=self.base/".release.lock"; lock.write_text(""); os.chmod(lock,0o666)
        with self.assertRaisesRegex(release.Hold,"LOCK_IDENTITY_MISMATCH"):
            with release.lock(self.base,1,uid=os.geteuid()): pass

    def test_w4_normal_activate_check_rollback_absent(self):
        self.prepared(); self.assertEqual(release.activate(self.args())["state"],"ACTIVATED")
        self.assertEqual(release.check(self.args())["state"],"PASS")
        self.assertEqual(release.rollback(self.args())["state"],"ROLLED_BACK"); self.assertFalse((self.base/"current").exists())
    def test_w4_failed_check_can_rollback_without_deleting_tampered_release(self):
        self.prepared(); release.activate(self.args()); target=self.base/"releases/release-1/public/assets/tiktok-integration.js"
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(release.Hold,"RELEASE_CONTENT_MISMATCH"): release.check(self.args())
        self.assertEqual(release.rollback(self.args())["state"],"ROLLED_BACK")
        self.assertTrue(target.exists()); self.assertFalse((self.base/"current").exists())
    def test_w4_existing_release_restored_with_content_proof(self):
        old=self.base/"releases/old/public"; old.mkdir(parents=True); (old/"index.html").write_text("old")
        for p in (self.base,self.base/"releases",self.base/"releases/old",old): os.chmod(p,0o755)
        os.chmod(old/"index.html",0o644); (self.base/"current").symlink_to(self.base/"releases/old")
        self.prepared(); release.activate(self.args()); release.rollback(self.args())
        self.assertEqual((self.base/"current").resolve(),(self.base/"releases/old").resolve())
        self.assertEqual((self.base/"current/public/index.html").read_text(),"old")
    def test_w4_commit_write_failure_is_reconcilable(self):
        self.prepared(); real=release.atomic_json; calls=0
        def fail_commit(path,value):
            nonlocal calls; calls+=1
            if value.get("state")=="ACTIVATED": raise OSError("injected")
            return real(path,value)
        with mock.patch.object(release,"atomic_json",side_effect=fail_commit):
            with self.assertRaisesRegex(OSError,"injected"): release.activate(self.args())
        disk=json.loads((self.base/"transactions/tx-1.json").read_text()); self.assertEqual(disk["state"],"ACTIVATION_INTENT")
        self.assertEqual(release.reconcile(self.args())["state"],"ACTIVATED")
    def test_w4_ambiguous_reconcile_never_deletes_unknown(self):
        self.prepared(); path=self.base/"transactions/tx-1.json"; r=json.loads(path.read_text())
        r.update(state="ACTIVATION_INTENT",previous_current=None); path.write_text(json.dumps(r))
        unknown=self.base/"releases/unknown"; (unknown/"public").mkdir(parents=True); (self.base/"current").symlink_to(unknown)
        with self.assertRaisesRegex(release.Hold,"RECONCILIATION_AMBIGUOUS"): release.reconcile(self.args())
        self.assertTrue(unknown.exists())
    def test_w4_partial_receipt_lists_residual(self):
        self.pin["overlay_baselines"]["assets/tiktok-integration.js"]="0"*64; self.write_bundle()
        with self.assertRaisesRegex(release.Hold,"OVERLAY_BASELINE_DRIFT"): self.prepared()
        r=json.loads((self.base/"transactions/tx-1.json").read_text()); self.assertEqual(r["state"],"HOLD_PARTIAL"); self.assertTrue(r["residuals"])

    def test_w5_rejects_nan_inf_zero_and_excessive(self):
        for value in (math.nan,math.inf,0,-1,901):
            with self.assertRaisesRegex(release.Hold,"INVALID_DEADLINE_SECONDS"): release.prepare(self.args(deadline_seconds=value))
        self.assertFalse(self.base.exists())
    def test_w5_real_hard_deadline_interrupts_blocked_digest(self):
        with release.Deadline(.05):
            with self.assertRaisesRegex(release.Hold,"OVERALL_DEADLINE_EXCEEDED"): time.sleep(.2)
    def test_w5_lock_timeout(self):
        self.base.mkdir(mode=0o755); path=self.base/".release.lock"; path.write_text(""); os.chmod(path,0o600)
        p=subprocess.Popen([sys.executable,"-c","import fcntl,sys,time; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); print('R',flush=True); time.sleep(2)",str(path)],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(p.stdout.readline().strip(),"R")
            with self.assertRaisesRegex(release.Hold,"LOCK_TIMEOUT"):
                with release.lock(self.base,.05,uid=os.geteuid()): pass
        finally: p.terminate(); p.wait(); p.stdout.close()
    def test_w5_signal_interrupt_leaves_durable_intent(self):
        self.prepared(); path=self.base/"transactions/tx-1.json"; real=release.atomic_json
        def interrupt(p,v):
            real(p,v)
            if v.get("state")=="ACTIVATION_INTENT": raise KeyboardInterrupt()
        with mock.patch.object(release,"atomic_json",side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): release.activate(self.args())
        self.assertEqual(json.loads(path.read_text())["state"],"ACTIVATION_INTENT")

    def test_unsafe_archive_member_is_rejected(self):
        with tarfile.open(self.source,"w:gz") as a:
            x=tarfile.TarInfo("package/public/../../escape"); x.size=1; a.addfile(x,io.BytesIO(b"x"))
        self.pin.update(source_archive_size=self.source.stat().st_size,source_archive_sha256=release.digest(self.source)); self.write_bundle()
        with self.assertRaisesRegex(release.Hold,"UNSAFE_ARCHIVE_MEMBER_PATH"): self.prepared()

class CandidateContractTest(unittest.TestCase):
    base=ROOT/"deploy/pr122-domestic-website"
    def test_w6_csp_uses_generated_hashes_not_unsafe_inline(self):
        text=(self.base/"nginx/xuanjun-apex-https.conf").read_text()
        self.assertIn("current/release-metadata/inline-csp.conf",text); self.assertNotIn("'unsafe-inline'",text)
    def test_w6_inline_event_or_style_attributes_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); public=root/"public"; public.mkdir(); (public/"index.html").write_text("<button onclick='x()'>x</button>")
            with release.Deadline(1) as deadline:
                with self.assertRaisesRegex(release.Hold,"INLINE_ATTRIBUTE_REQUIRES_EXPLICIT_REMEDIATION"):
                    release.write_csp_metadata(public,root,deadline)
    def test_w6_acme_uses_exact_existing_binary_and_forward_contract(self):
        issue=(self.base/"tls/issue-apex-certificate.sh").read_text()
        self.assertIn("/usr/local/bin/certbot",issue); self.assertTrue((self.base/"nginx/tokyo-apex-acme-forward.locations.conf").is_file())
    def test_w6_unresolved_routes_force_cutover_hold(self):
        gate=json.loads((self.base/"cutover-gate.json").read_text())
        self.assertEqual(gate["cutover_state"],"HOLD")
        self.assertTrue(any(x["state"]!="ACCEPTED" for x in gate["dynamic_routes"]))
    def test_w6_cross_object_contract_is_non_executable(self):
        contract=json.loads((self.base/"production-action-contract.json").read_text())
        self.assertEqual(contract["execution_state"],"NOT_AUTHORIZED")
        self.assertIn("winctl",json.dumps(contract)); self.assertTrue((self.base/"PRODUCTION_EXECUTION.lock").is_file())
    def test_existing_winctl_is_not_mutation_target(self):
        for path in list((self.base/"nginx").glob("*"))+list((self.base/"tls").glob("*")):
            self.assertNotIn("server_name winctl.wenwenwenyiyiyi.work",path.read_text())
    def test_package_manifest_matches_every_managed_file(self):
        manifest=json.loads((self.base/"PACKAGE_MANIFEST.json").read_text())
        for item in manifest["files"]:
            path=ROOT/"scripts/pr122_website_release.py" if item["path"]=="bin/pr122_website_release.py" else self.base/item["path"]
            self.assertEqual(path.stat().st_size,item["size"],item["path"]); self.assertEqual(release.digest(path),item["sha256"],item["path"])

if __name__=="__main__": unittest.main()
