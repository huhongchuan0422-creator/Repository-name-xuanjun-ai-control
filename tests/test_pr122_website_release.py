import hashlib, importlib.util, io, json, math, os, pwd, signal, stat, subprocess, sys, tarfile, tempfile, time, unittest
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
        os.chmod(self.root,0o755)
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
        package=self.bundle/"PACKAGE_MANIFEST.json"; package.write_text(json.dumps({"schema_version":2,"files":files}))
        self.package_hash=release.digest(package)
    def args(self,**kw):
        values=dict(bundle=self.bundle,source_archive=self.source,webroot_base=self.base,transaction_id="tx-1",
                    release_id="release-1",deadline_seconds=5,lock_wait_seconds=1,allow_non_root_test=True,
                    approved_package_manifest_sha256=self.package_hash)
        values.update(kw); return SimpleNamespace(**values)
    def prepared(self): return release.prepare(self.args())
    def existing_old(self,with_metadata=False):
        old=self.base/"releases/old"; public=old/"public"; public.mkdir(parents=True); (public/"index.html").write_text("old")
        if with_metadata:
            metadata=old/"release-metadata"; metadata.mkdir()
            policy="default-src 'self'"
            (metadata/"inline-csp.json").write_text(json.dumps({"schema_version":1,"html_count":1,"script_hashes":[],"style_hashes":[],"policy":policy}))
            (metadata/"inline-csp.conf").write_text('add_header Content-Security-Policy "'+policy+'" always;\n')
        for path in [self.base,self.base/"releases",old,*[p for p in old.rglob("*") if p.is_dir()]]: os.chmod(path,0o755)
        for path in [p for p in old.rglob("*") if p.is_file()]: os.chmod(path,0o644)
        (self.base/"current").symlink_to(old)
        return old
    def rollback_with_failed_final_receipt(self):
        real=release.atomic_json
        with mock.patch.object(release,"atomic_json",side_effect=lambda p,v: (_ for _ in ()).throw(OSError("injected")) if v.get("state")=="ROLLED_BACK" else real(p,v)):
            with self.assertRaisesRegex(OSError,"injected"): release.rollback(self.args())

    def run_cli(self,command,transaction="tx-1",release_id="release-1",bundle=True,source=False):
        args=[sys.executable,str(ROOT/"scripts/pr122_website_release.py"),command,
              "--webroot-base",str(self.base),"--transaction-id",transaction,
              "--release-id",release_id,"--deadline-seconds","5","--lock-wait-seconds","1",
              "--allow-non-root-test"]
        if bundle:
            args.extend(["--bundle",str(self.bundle),"--approved-package-manifest-sha256",self.package_hash])
        if source: args.extend(["--source-archive",str(self.source)])
        return subprocess.run(args,capture_output=True,text=True,preexec_fn=lambda: os.umask(0o077))

    def test_umask_077_real_subprocess_canary_and_stage_lifecycle(self):
        sequence=[("prepare","canary-tx","canary-release",True),
                  ("activate","canary-tx","canary-release",False),
                  ("check","canary-tx","canary-release",False),
                  ("rollback","canary-tx","canary-release",False),
                  ("prepare","stage-tx","stage-release",True),
                  ("activate","stage-tx","stage-release",False),
                  ("check","stage-tx","stage-release",False)]
        for command,transaction,release_id,needs_source in sequence:
            result=self.run_cli(command,transaction,release_id,source=needs_source)
            self.assertEqual(result.returncode,0,(command,result.stdout,result.stderr))
        self.assertEqual((self.base.stat().st_mode&0o777),0o755)
        self.assertEqual((self.base/"releases").stat().st_mode&0o777,0o755)
        self.assertEqual((self.base/"transactions").stat().st_mode&0o777,0o700)
        self.assertEqual(json.loads((self.base/"transactions/canary-tx.json").read_text())["state"],"ROLLED_BACK")
        self.assertEqual(json.loads((self.base/"transactions/stage-tx.json").read_text())["state"],"CHECKED")
        self.assertEqual((self.base/"current").resolve(),(self.base/"releases/stage-release").resolve())

    def test_umask_077_preexisting_bad_directory_is_rejected_unchanged(self):
        self.base.mkdir(mode=0o700); os.chmod(self.base,0o700)
        before=self.base.stat(follow_symlinks=False)
        result=self.run_cli("prepare",source=True)
        after=self.base.stat(follow_symlinks=False)
        self.assertEqual(result.returncode,1,(result.stdout,result.stderr))
        self.assertIn("TRUSTED_DIRECTORY_IDENTITY_MISMATCH",result.stderr)
        self.assertEqual((before.st_dev,before.st_ino,stat.S_IMODE(before.st_mode)),
                         (after.st_dev,after.st_ino,stat.S_IMODE(after.st_mode)))
        self.assertEqual(list(self.base.iterdir()),[])

    def test_umask_077_partial_failure_preserves_receipt_and_staging(self):
        (self.bundle/"overlay/public/assets/tiktok-integration.js").unlink()
        result=self.run_cli("prepare",source=True)
        self.assertEqual(result.returncode,1,(result.stdout,result.stderr))
        receipt=json.loads((self.base/"transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"],"HOLD_PARTIAL")
        self.assertIn("OVERLAY_MISSING",receipt["failure"])
        self.assertTrue((self.base/".staging-tx-1").is_dir())

    def test_umask_077_sigterm_preserves_unknown_failure_evidence(self):
        code="""import importlib.util,sys,time
spec=importlib.util.spec_from_file_location('release',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.extract_source=lambda *_: time.sleep(30)
sys.argv=[sys.argv[1],*sys.argv[2:]]
raise SystemExit(m.main())
"""
        args=[sys.executable,"-c",code,str(ROOT/"scripts/pr122_website_release.py"),"prepare",
              "--webroot-base",str(self.base),"--bundle",str(self.bundle),"--source-archive",str(self.source),
              "--transaction-id","signal-tx","--release-id","signal-release",
              "--approved-package-manifest-sha256",self.package_hash,"--deadline-seconds","5",
              "--lock-wait-seconds","1","--allow-non-root-test"]
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                                 preexec_fn=lambda: os.umask(0o077))
        receipt=self.base/"transactions/signal-tx.json"
        until=time.time()+3
        while time.time()<until and not receipt.exists(): time.sleep(.01)
        self.assertTrue(receipt.exists(),"subprocess did not reach durable PREPARE_INTENT")
        process.terminate(); stdout,stderr=process.communicate(timeout=3)
        self.assertEqual(process.returncode,2,(stdout,stderr))
        self.assertIn("PROCESS_INTERRUPTED_SIGTERM",stderr)
        saved=json.loads(receipt.read_text())
        self.assertEqual(saved["state"],"HOLD_PARTIAL")
        self.assertIn("PROCESS_INTERRUPTED_SIGTERM",saved["failure"])
        self.assertTrue((self.base/".staging-signal-tx").is_dir())

    def test_w1_sealed_release_is_worker_readable_and_not_worker_writable(self):
        self.prepared(); tree=self.base/"releases/release-1"
        self.assertEqual(tree.stat().st_mode&0o777,0o755)
        self.assertEqual((tree/"public/assets/tiktok-integration.js").stat().st_mode&0o777,0o644)
        self.assertEqual((tree/"public/assets").stat().st_mode&0o777,0o755)
        if os.geteuid()==0:
            nobody=pwd.getpwnam("nobody")
            code="import os,sys; os.setgroups([]); os.setgid(int(sys.argv[1])); os.setuid(int(sys.argv[2])); p=sys.argv[3]; assert open(p,'rb').read()==b'new\\n';\ntry: open(p,'ab')\nexcept PermissionError: pass\nelse: raise SystemExit(2)"
            result=subprocess.run([sys.executable,"-c",code,str(nobody.pw_gid),str(nobody.pw_uid),str(tree/"public/assets/tiktok-integration.js")],capture_output=True,text=True)
            if result.returncode and "Invalid argument" in result.stderr: self.skipTest("real non-root worker identity unavailable in this user namespace")
            self.assertEqual(result.returncode,0,result.stderr)
        else:
            code="import sys; p=sys.argv[1]; assert open(p,'rb').read()==b'new\\n';\ntry: open(p,'ab')\nexcept PermissionError: pass\nelse: raise SystemExit(2)"
            result=subprocess.run(["sudo","-n","-u","nobody","--",sys.executable,"-c",code,str(tree/"public/assets/tiktok-integration.js")],capture_output=True,text=True)
            if result.returncode and ("password" in result.stderr.lower() or "not permitted" in result.stderr.lower()):
                self.skipTest("sudo non-root worker proof unavailable; mode assertions completed")
            self.assertEqual(result.returncode,0,result.stderr)

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
    def test_rw1_csp_conf_tamper_is_rejected(self):
        self.prepared(); (self.base/"releases/release-1/release-metadata/inline-csp.conf").write_text("bad\n")
        with self.assertRaisesRegex(release.Hold,"RELEASE_ENVELOPE_DRIFT|CSP_JSON_CONF_MISMATCH"): release.activate(self.args())
    def test_rw1_csp_json_link_substitution_is_rejected(self):
        self.prepared(); path=self.base/"releases/release-1/release-metadata/inline-csp.json"; copy=self.root/"csp.json"
        copy.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(copy)
        with self.assertRaisesRegex(release.Hold,"RELEASE_ENVELOPE_LINK"): release.activate(self.args())
    def test_rw1_release_root_and_parent_mode_drift_are_rejected(self):
        self.prepared(); release_root=self.base/"releases/release-1"; os.chmod(release_root,0o777)
        with self.assertRaisesRegex(release.Hold,"RELEASE_ENVELOPE_IDENTITY"): release.activate(self.args())
        os.chmod(release_root,0o755); os.chmod(self.base/"releases",0o777)
        with self.assertRaisesRegex(release.Hold,"RELEASE_ENVELOPE_IDENTITY"): release.activate(self.args())
    def test_rw2_all_consumed_manifest_files_must_be_immutable(self):
        for name in ("candidate-manifest.json","source-pin.json","PACKAGE_MANIFEST.json"):
            with self.subTest(name=name):
                path=self.bundle/name; old=path.stat().st_mode&0o777; os.chmod(path,0o666)
                try:
                    with self.assertRaisesRegex(release.Hold,"TRUSTED_INPUT_(FILE_IDENTITY|PATH_WRITABLE)"): release.prepare(self.args())
                finally: os.chmod(path,old)
    def test_rw2_overlay_and_parent_must_be_immutable(self):
        overlay=self.bundle/"overlay/public/assets/tiktok-integration.js"; os.chmod(overlay,0o666)
        with self.assertRaisesRegex(release.Hold,"TRUSTED_INPUT_(FILE_IDENTITY|PATH_WRITABLE)"): release.prepare(self.args())
        os.chmod(overlay,0o644); os.chmod(self.bundle,0o775)
        with self.assertRaisesRegex(release.Hold,"TRUSTED_INPUT_PATH_WRITABLE|TRUSTED_INPUT_DIRECTORY_IDENTITY"): release.prepare(self.args())
    def test_rw2_external_package_hash_rejects_self_consistent_replacement(self):
        self.manifest["files"][0]["sha256"]="0"*64; self.write_bundle(); approved=self.package_hash
        self.manifest["files"][0]["sha256"]="1"*64; self.write_bundle()
        with self.assertRaisesRegex(release.Hold,"APPROVED_PACKAGE_MANIFEST_IDENTITY_MISMATCH"):
            release.prepare(self.args(approved_package_manifest_sha256=approved))
    def test_rw2_open_descriptor_detects_path_replacement(self):
        path=self.bundle/"candidate-manifest.json"; replacement=self.root/"replacement.json"; replacement.write_bytes(path.read_bytes())
        with self.assertRaisesRegex(release.Hold,"TRUSTED_INPUT_FILE_REPLACED"):
            with release.open_trusted_file(path,os.geteuid()) as (_fd,_info): os.replace(replacement,path)
    def test_rw2_non_root_owned_input_is_rejected(self):
        path=self.bundle/"candidate-manifest.json"; unauthorized_expected_uid=os.geteuid()+1
        with self.assertRaisesRegex(release.Hold,"TRUSTED_INPUT_PATH_OWNER|TRUSTED_INPUT_FILE_IDENTITY"):
            with release.open_trusted_file(path,unauthorized_expected_uid): pass

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
    def test_rw3_check_is_repeatable_and_detects_later_drift(self):
        self.prepared(); release.activate(self.args()); self.assertEqual(release.check(self.args())["state"],"PASS")
        self.assertEqual(release.check(self.args())["state"],"PASS")
        (self.base/"releases/release-1/release-metadata/inline-csp.conf").write_text("bad\n")
        with self.assertRaisesRegex(release.Hold,"RELEASE_ENVELOPE_DRIFT|CSP_JSON_CONF_MISMATCH"): release.check(self.args())
    def test_rw3_csp_drift_is_detected_but_safe_rollback_remains_available(self):
        self.prepared(); release.activate(self.args()); (self.base/"releases/release-1/release-metadata/inline-csp.conf").write_text("bad\n")
        with self.assertRaisesRegex(release.Hold,"RELEASE_ENVELOPE_DRIFT|CSP_JSON_CONF_MISMATCH"): release.check(self.args())
        result=release.rollback(self.args()); self.assertEqual(result["state"],"ROLLED_BACK")
        self.assertRegex(result["target_envelope_failure"],"RELEASE_ENVELOPE_DRIFT|CSP_JSON_CONF_MISMATCH"); self.assertFalse((self.base/"current").exists())
    def test_rw3_interrupted_absent_rollback_reconciles_final_state(self):
        self.prepared(); release.activate(self.args()); real=release.atomic_json
        def fail_commit(path,value):
            if value.get("state")=="ROLLED_BACK": raise OSError("injected")
            return real(path,value)
        with mock.patch.object(release,"atomic_json",side_effect=fail_commit):
            with self.assertRaisesRegex(OSError,"injected"): release.rollback(self.args())
        self.assertFalse((self.base/"current").exists())
        self.assertEqual(release.reconcile(self.args())["state"],"ROLLED_BACK")
    def test_rw3_interrupted_previous_rollback_reconciles_final_state(self):
        self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        self.assertEqual(release.reconcile(self.args())["state"],"ROLLED_BACK")
        self.assertEqual((self.base/"current").resolve(),(self.base/"releases/old").resolve())
    def test_rw3_relative_direct_previous_pointer_rolls_back_and_reconciles(self):
        old=self.existing_old(); current=self.base/"current"; current.unlink(); current.symlink_to("releases/old")
        self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        self.assertEqual(release.reconcile(self.args())["state"],"ROLLED_BACK")
        self.assertEqual(os.readlink(current),"releases/old"); self.assertEqual(current.resolve(),old.resolve())
    def test_rw3_absolute_intermediate_alias_is_rejected_before_activation_intent(self):
        old=self.existing_old(); current=self.base/"current"; alias=self.base/"old-alias"
        alias.symlink_to(old); current.unlink(); current.symlink_to(alias)
        self.prepared()
        with self.assertRaisesRegex(release.Hold,"PREVIOUS_POINTER_NOT_DIRECT_RELEASE"): release.activate(self.args())
        receipt=json.loads((self.base/"transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"],"PREPARED"); self.assertEqual(current.resolve(),old.resolve())
    def test_rw3_relative_and_multilayer_aliases_are_rejected_before_activation_intent(self):
        old=self.existing_old(); current=self.base/"current"; alias1=self.base/"old-alias"; alias2=self.base/"old-alias-2"
        alias2.symlink_to("releases/old"); alias1.symlink_to("old-alias-2"); current.unlink(); current.symlink_to("old-alias")
        self.prepared()
        with self.assertRaisesRegex(release.Hold,"PREVIOUS_POINTER_NOT_DIRECT_RELEASE"): release.activate(self.args())
        receipt=json.loads((self.base/"transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"],"PREPARED"); self.assertEqual(current.resolve(),old.resolve())
    def test_rw3_relative_path_jump_is_rejected_before_activation_intent(self):
        old=self.existing_old(); current=self.base/"current"; (self.base/"releases/jump").mkdir()
        current.unlink(); current.symlink_to("releases/jump/../old")
        self.prepared()
        with self.assertRaisesRegex(release.Hold,"PREVIOUS_POINTER_NOT_DIRECT_RELEASE"): release.activate(self.args())
        receipt=json.loads((self.base/"transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"],"PREPARED"); self.assertEqual(current.resolve(),old.resolve())
    def test_rw3_legacy_alias_receipt_after_final_write_failure_cannot_report_complete(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        current=self.base/"current"; alias=self.base/"old-alias"; wrong=self.base/"releases/wrong"
        (wrong/"public").mkdir(parents=True); alias.symlink_to(old); current.unlink(); current.symlink_to(alias)
        path=self.base/"transactions/tx-1.json"; receipt=json.loads(path.read_text())
        receipt["previous_current"]["link"]=str(alias)
        receipt["rollback_pointer_identity"]=release.symlink_identity(current,os.geteuid())
        path.write_text(json.dumps(receipt)); alias.unlink(); alias.symlink_to(wrong)
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:PREVIOUS_POINTER_NOT_DIRECT_RELEASE"):
            release.reconcile(self.args())
        self.assertEqual(current.resolve(),wrong.resolve()); self.assertTrue(old.is_dir())
    def test_rw3_reconcile_rejects_damaged_restored_previous_content(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        (old/"public/index.html").write_text("damaged")
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:RELEASE_CONTENT_MISMATCH"):
            release.reconcile(self.args())
        receipt=json.loads((self.base/"transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"],"UNKNOWN_AFTER_ROLLBACK"); self.assertTrue((self.base/"current").is_symlink())
    def test_rw3_reconcile_rejects_missing_restored_previous_release(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        moved=self.root/"old-moved"; old.rename(moved)
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:PREVIOUS_RELEASE_MISSING"):
            release.reconcile(self.args())
        self.assertTrue((self.base/"current").is_symlink()); self.assertTrue(moved.is_dir())
    def test_rw3_reconcile_allows_damaged_retired_target_when_previous_is_proved(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        target=self.base/"releases/release-1/public/assets/tiktok-integration.js"; target.write_text("damaged")
        result=release.reconcile(self.args())
        self.assertEqual(result["state"],"ROLLED_BACK"); self.assertIn("RELEASE_CONTENT_MISMATCH",result["target_residual_failure"])
        self.assertTrue(target.exists()); self.assertEqual((self.base/"current").resolve(),old.resolve())
    def test_rw3_rollback_rejects_previous_damage_before_pointer_change(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); (old/"public/index.html").write_text("damaged")
        with self.assertRaisesRegex(release.Hold,"RELEASE_CONTENT_MISMATCH"): release.rollback(self.args())
        self.assertEqual(os.readlink(self.base/"current"),str(self.base/"releases/release-1"))
    def test_rw3_reconcile_rejects_previous_root_identity_drift(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt(); os.chmod(old,0o777)
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:PREVIOUS_RELEASE_ENVELOPE_DRIFT"):
            release.reconcile(self.args())
    def test_rw3_reconcile_rejects_previous_public_identity_drift(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt(); os.chmod(old/"public",0o777)
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:PREVIOUS_RELEASE_ENVELOPE_DRIFT"):
            release.reconcile(self.args())
    def test_rw3_reconcile_rejects_previous_csp_drift(self):
        old=self.existing_old(with_metadata=True); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        (old/"release-metadata/inline-csp.conf").write_text("bad\n")
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:PREVIOUS_RELEASE_ENVELOPE_DRIFT"):
            release.reconcile(self.args())
    def test_rw3_reconcile_rejects_same_text_current_pointer_replacement(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); self.rollback_with_failed_final_receipt()
        current=self.base/"current"; current.unlink(); current.symlink_to(old)
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:ROLLBACK_POINTER_IDENTITY_DRIFT"):
            release.reconcile(self.args())
        self.assertTrue(current.is_symlink()); self.assertEqual(os.readlink(current),str(old))
    def test_rw3_post_switch_identity_receipt_failure_stays_unknown(self):
        old=self.existing_old(); self.prepared(); release.activate(self.args()); real=release.atomic_json
        def fail_post_switch(path,value):
            if value.get("last_stage")=="ROLLBACK_POINTER_SWITCHED": raise OSError("injected-post-switch")
            return real(path,value)
        with mock.patch.object(release,"atomic_json",side_effect=fail_post_switch):
            with self.assertRaisesRegex(OSError,"injected-post-switch"): release.rollback(self.args())
        self.assertEqual((self.base/"current").resolve(),old.resolve())
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_FINAL_STATE_UNPROVEN:ROLLBACK_POINTER_IDENTITY_DRIFT"):
            release.reconcile(self.args())
        receipt=json.loads((self.base/"transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"],"UNKNOWN_AFTER_ROLLBACK"); self.assertTrue(old.exists())
    def test_rw3_unknown_rollback_temp_is_preserved(self):
        self.existing_old(); self.prepared(); release.activate(self.args()); path=self.base/"transactions/tx-1.json"; r=json.loads(path.read_text())
        tmp=self.base/".rollback-tx-1"; r.update(state="ROLLBACK_INTENT",rollback_temp=str(tmp)); path.write_text(json.dumps(r))
        unknown=self.base/"releases/unknown"; unknown.mkdir(); tmp.symlink_to(unknown)
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_RECONCILIATION_AMBIGUOUS"): release.reconcile(self.args())
        self.assertTrue(tmp.is_symlink()); self.assertEqual(tmp.resolve(),unknown.resolve())
    def test_rw3_owned_activation_temp_is_cleaned_without_switch(self):
        self.prepared(); path=self.base/"transactions/tx-1.json"; r=json.loads(path.read_text()); target=self.base/"releases/release-1"
        tmp=self.base/".current-tx-1"; r.update(state="ACTIVATION_INTENT",previous_current=None,activation_temp=str(tmp)); path.write_text(json.dumps(r)); tmp.symlink_to(target)
        result=release.reconcile(self.args()); self.assertEqual(result["state"],"PREPARED"); self.assertFalse(tmp.exists())
    def test_rw3_rollback_not_applied_reconciles_pending_then_finishes_explicitly(self):
        self.prepared(); release.activate(self.args()); path=self.base/"transactions/tx-1.json"; r=json.loads(path.read_text())
        r.update(state="ROLLBACK_INTENT",rollback_temp=str(self.base/".rollback-tx-1")); path.write_text(json.dumps(r))
        self.assertEqual(release.reconcile(self.args())["state"],"ROLLBACK_PENDING")
        self.assertEqual(release.rollback(self.args())["state"],"ROLLED_BACK"); self.assertFalse((self.base/"current").exists())
    def test_rw3_unknown_rollback_pointer_is_preserved(self):
        self.prepared(); release.activate(self.args()); path=self.base/"transactions/tx-1.json"; r=json.loads(path.read_text())
        r.update(state="ROLLBACK_INTENT",rollback_temp=str(self.base/".rollback-tx-1")); path.write_text(json.dumps(r))
        unknown=self.base/"releases/unknown"; (unknown/"public").mkdir(parents=True); (self.base/"current").unlink(); (self.base/"current").symlink_to(unknown)
        with self.assertRaisesRegex(release.Hold,"ROLLBACK_RECONCILIATION_AMBIGUOUS"): release.reconcile(self.args())
        self.assertTrue((self.base/"current").is_symlink()); self.assertEqual((self.base/"current").resolve(),unknown.resolve())

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
    def test_rw4_failure_receipt_block_is_bounded_and_unknown(self):
        real=release.atomic_json
        def receipt_write(path,value):
            if value.get("state")=="HOLD_PARTIAL": time.sleep(5)
            return real(path,value)
        started=time.monotonic()
        with mock.patch.object(release,"extract_source",side_effect=lambda *_: time.sleep(.2)), mock.patch.object(release,"atomic_json",side_effect=receipt_write):
            with self.assertRaisesRegex(release.Unknown,"FAILURE_RECEIPT_UNAVAILABLE"): release.prepare(self.args(deadline_seconds=.05))
        self.assertLess(time.monotonic()-started,.4)

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
        serialized=json.dumps(contract); self.assertIn("winctl",serialized); self.assertTrue((self.base/"PRODUCTION_EXECUTION.lock").is_file())
        for required in ("/usr/local/libexec/pr122_website_release.py","pr122-dynamic-hold.locations.conf","xuanjun-apex-http-redirect.conf","inline-csp"):
            self.assertIn(required,serialized)
    def test_existing_winctl_is_not_mutation_target(self):
        for path in list((self.base/"nginx").glob("*"))+list((self.base/"tls").glob("*")):
            self.assertNotIn("server_name winctl.wenwenwenyiyiyi.work",path.read_text())
    def test_package_manifest_matches_every_managed_file(self):
        manifest=json.loads((self.base/"PACKAGE_MANIFEST.json").read_text())
        for item in manifest["files"]:
            path=ROOT/"scripts/pr122_website_release.py" if item["path"]=="bin/pr122_website_release.py" else self.base/item["path"]
            self.assertEqual(path.stat().st_size,item["size"],item["path"]); self.assertEqual(release.digest(path),item["sha256"],item["path"])


class NginxInventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        spec=importlib.util.spec_from_file_location('pr122_inventory',ROOT/'scripts/pr122_domestic_channel_inventory.py')
        self.inventory=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.inventory)

    def scan(self,body):
        path=self.root/'nginx.conf';path.write_text(body)
        return self.inventory.nginx_inventory(path,permitted_roots=[self.root])

    def test_exact_domain_excludes_wecom(self):
        result=self.scan('http { server {server_name wecom.wenwenwenyiyiyi.work;} server {server_name wenwenwenyiyiyi.work; location / {try_files $uri /index.html;}}}')
        self.assertEqual(len(result['apex_servers']),1)
        self.assertEqual(result['apex_servers'][0]['locations'][0]['match'],'/')

    def test_includes_expanded_and_provenance_bound(self):
        (self.root/'locations.conf').write_text('location /p/ {proxy_pass http://127.0.0.1:18080;}')
        r=self.scan('http {server {server_name wenwenwenyiyiyi.work;include locations.conf;}}')
        self.assertEqual(len(r['files']),2)
        target=r['apex_servers'][0]['locations'][0]['proxy_pass'][0]
        self.assertEqual(target['port'],18080)

    def test_auth_headers_and_webhook_secrets_not_exported(self):
        r=self.scan('http {server {server_name wenwenwenyiyiyi.work; location /telegram-webhook/synthetic-private-token { auth_basic "private realm";proxy_set_header Authorization "Bearer synthetic-secret";proxy_pass https://u:p@127.0.0.1:18080/private-key;}}}')
        text=json.dumps(r)
        for secret in ['synthetic-private-token','synthetic-secret','private realm','private-key','u:p']:
            self.assertNotIn(secret,text)
        self.assertIn('credentials_present',text)
        self.assertIn('REDACTED',text)

    def test_inherited_access_controls_are_retained(self):
        r=self.scan('http {deny all;server {server_name wenwenwenyiyiyi.work;auth_basic "private";location /p/ {allow 127.0.0.1;deny all;}}}')
        b=r['apex_servers'][0]
        self.assertEqual(b['http_security'][0]['directive'],'deny')
        self.assertEqual(b['server_security'][0]['directive'],'auth_basic')
        self.assertEqual(len(b['locations'][0]['security']),2)

    def test_quoted_braces_and_comments(self):
        tree=self.inventory.nginx_parse('http { # comment\n server {auth_basic "realm # { text";}}')
        self.assertEqual(tree[0]['children'][0]['children'][0]['args'],['realm # { text'])

    def test_unbalanced_config_rejected(self):
        for text in ['http {','http {server {','http { x','}']:
            with self.assertRaises(ValueError):self.inventory.nginx_parse(text)

    def test_include_cycle_rejected(self):
        with self.assertRaisesRegex(ValueError,'CYCLE'):
            self.scan('include nginx.conf;')

    def test_private_include_outside_root_rejected(self):
        with self.assertRaisesRegex(ValueError,'OUTSIDE'):
            self.scan('include /etc/passwd;')

    def test_host_mismatch_never_reads_config(self):
        with mock.patch.object(self.inventory.os,'uname',return_value=SimpleNamespace(nodename='wrong')),mock.patch.object(self.inventory,'nginx_inventory') as call:
            with self.assertRaises(SystemExit):self.inventory.nginx_readonly_main()
            call.assert_not_called()

    def test_inventory_never_invokes_subprocess(self):
        with mock.patch.object(self.inventory,'command',side_effect=AssertionError('command forbidden')):
            result=self.scan('http {server {server_name wenwenwenyiyiyi.work;}}')
        self.assertFalse(result['production_mutation'])
        self.assertFalse(result['private_keys_read'])


class MinimalCutoverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'deploy/pr122-minimal-cutover'
        cls.routes=json.loads((cls.base/'route-responsibility.json').read_text())

    def test_all_75_locations_mapped_without_broad_submit_proxy(self):
        self.assertEqual(self.routes['location_count'],75)
        self.assertEqual(self.routes['dynamic_count'],11)
        matches=[r['candidate_match'] for r in self.routes['routes']]
        self.assertEqual(len(matches),len(set(matches)))
        self.assertIn('= /privacy/',matches)
        self.assertIn('= /tiktok-review/privacy/',matches)
        self.assertNotIn('^~ /submit/',matches)
        self.assertFalse(self.routes['approval'])

    def test_proxy_security_and_no_dns_recursion(self):
        text=(self.base/'tokyo-proxy-settings.conf').read_text()
        for directive in ['proxy_pass https://47.245.53.152;',
            'proxy_ssl_verify on;','proxy_ssl_name wenwenwenyiyiyi.work;',
            'proxy_next_upstream off;','proxy_cache off;',
            'proxy_request_buffering off;','proxy_buffering off;']:
            self.assertIn(directive,text)
        self.assertNotIn('proxy_pass https://wenwenwenyiyiyi.work',text)
        self.assertNotIn('proxy_set_header Authorization',text)
        self.assertNotIn('proxy_set_header X-Telegram',text)

    def test_csp_only_static_and_secret_safe_logs(self):
        server=(self.base/'apex-https.conf').read_text()
        self.assertNotIn('inline-csp',server)
        self.assertIn('inline-csp.conf',(self.base/'static-security.conf').read_text())
        log=(self.base/'http-support.conf').read_text()
        for variable in ['$request_uri','$args','$request_body','$http_authorization','$http_cookie','$remote_addr']:
            self.assertNotIn(variable,log)


class MinimalNginxIntegrationTest(unittest.TestCase):
    """Real Nginx + fake TLS upstream; no real hosts/providers are contacted."""
    @classmethod
    def setUpClass(cls):
        import shutil
        if not shutil.which('nginx') and os.environ.get('GITHUB_ACTIONS')=='true':
            raise RuntimeError('required CI Nginx integration dependency missing')
        if not shutil.which('nginx'):
            raise unittest.SkipTest('nginx not installed locally; required hosted CI installs nginx')
        cls.nginx=shutil.which('nginx')
        cls.base=ROOT/'deploy/pr122-minimal-cutover'
        cls.shared=tempfile.TemporaryDirectory();cls.shared_root=Path(cls.shared.name)
        cls.cert=cls.shared_root/'cert.pem';cls.key=cls.shared_root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-keyout',str(cls.key),'-out',str(cls.cert),'-subj','/CN=wenwenwenyiyiyi.work',
            '-addext','subjectAltName=DNS:wenwenwenyiyiyi.work'],check=True,capture_output=True,timeout=20)
        cls.key.chmod(0o600)

    @classmethod
    def tearDownClass(cls):cls.shared.cleanup()

    def setUp(self):
        import socket,ssl,threading,http.server
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.hits=[];hits=self.hits
        class Backend(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.respond()
            def do_POST(self):self.respond()
            def respond(self):
                size=int(self.headers.get('Content-Length','0'))
                body=self.rfile.read(size).decode()
                record={'path':self.path,'method':self.command,'body':body,
                    'host':self.headers.get('Host'),'origin':self.headers.get('Origin'),
                    'authorization':self.headers.get('Authorization'),'cookie':self.headers.get('Cookie'),
                    'telegram':self.headers.get('X-Telegram-Bot-Api-Secret-Token')}
                hits.append(record)
                if body=='synthetic-slow':time.sleep(2)
                data=json.dumps(record).encode()
                try:
                    self.send_response(200);self.send_header('Content-Type','application/json')
                    self.send_header('Content-Security-Policy','default-src https:')
                    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
        self.backend=http.server.ThreadingHTTPServer(('127.0.0.1',0),Backend)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(self.cert,self.key)
        self.sni=[];ctx.set_servername_callback(lambda sock,name,context:self.sni.append(name))
        self.backend.socket=ctx.wrap_socket(self.backend.socket,server_side=True)
        self.thread=threading.Thread(target=self.backend.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_backend)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.public=self.root/'public';self.public.mkdir()
        self.routes=json.loads((self.base/'route-responsibility.json').read_text())['routes']
        self.static_cases=[]
        for route in self.routes:
            if route['handler']!='DOMESTIC_IMMUTABLE_STATIC':continue
            match=route['candidate_match'];uri=match.split()[-1];tries=route['try_files']
            if '$uri' in tries:
                uri=uri+'synthetic-item'+('.txt' if tries==['$uri','=404'] else '')
                target=uri if tries==['$uri','=404'] else uri+'.html'
            else:target=tries[0]
            file=self.public/target.lstrip('/');file.parent.mkdir(parents=True,exist_ok=True)
            content='synthetic-static:'+target;file.write_text(content)
            self.static_cases.append((uri,content))
        self.csp=self.root/'inline-csp.conf';self.csp.write_text('add_header Content-Security-Policy "default-src self" always;\n')
        self.proc=None
        self.addCleanup(self.close_nginx)

    def close_backend(self):
        self.backend.shutdown();self.backend.server_close();self.thread.join(timeout=5)

    def close_nginx(self):
        if self.proc and self.proc.poll() is None:
            os.killpg(self.proc.pid,signal.SIGTERM)
            try:self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid,signal.SIGKILL);self.proc.wait(timeout=5)
        if hasattr(self,'output'):self.output.close()

    def start(self,wrong_sni=False):
        import socket
        self.config=self.root/'config';self.config.mkdir()
        for path in self.base.glob('*.conf'):
            text=path.read_text().replace('/etc/nginx/pr122-minimal-cutover/',str(self.config)+'/')
            text=text.replace('/var/www/wenwenwenyiyiyi.work/current/public',str(self.public))
            text=text.replace('/var/www/wenwenwenyiyiyi.work/current/release-metadata/inline-csp.conf',str(self.csp))
            text=text.replace('/var/log/nginx/pr122-minimal-status.log',str(self.root/'status.log'))
            text=text.replace('listen 443 ssl;','listen 127.0.0.1:'+str(self.port)+';')
            text=text.replace('listen [::]:443 ssl;','').replace('    http2 on;','')
            # Test HTTP frontend only; upstream remains real TLS with verify ON.
            text='\n'.join(l for l in text.splitlines() if not l.strip().startswith(('ssl_certificate ','ssl_certificate_key ')))+'\n'
            text=text.replace('__HOST_CA_BUNDLE__',str(self.cert))
            text=text.replace('https://47.245.53.152','https://127.0.0.1:'+str(self.backend.server_port))
            text=text.replace('proxy_read_timeout 30s;','proxy_read_timeout 1s;')
            if wrong_sni:text=text.replace('proxy_ssl_name wenwenwenyiyiyi.work;','proxy_ssl_name wrong.invalid;')
            (self.config/path.name).write_text(text)
        main=self.root/'nginx.conf'
        main.write_text('worker_processes 1;error_log stderr;pid '+str(self.root/'nginx.pid')+';\nevents {worker_connections 128;}\nhttp {include /etc/nginx/mime.types;include '+str(self.config/'http-support.conf')+';include '+str(self.config/'apex-https.conf')+';}\n')
        check=subprocess.run([self.nginx,'-p',str(self.root)+'/', '-c',str(main),'-t'],capture_output=True,text=True,timeout=10)
        self.assertEqual(check.returncode,0,check.stderr)
        self.output=(self.root/'process.log').open('wb')
        self.proc=subprocess.Popen([self.nginx,'-p',str(self.root)+'/', '-c',str(main),'-g','daemon off;'],stdout=self.output,stderr=self.output,start_new_session=True)
        for _ in range(50):
            self.assertIsNone(self.proc.poll())
            try:
                with socket.create_connection(('127.0.0.1',self.port),timeout=.1):return
            except OSError:time.sleep(.05)
        self.fail('test Nginx startup timeout')

    def request(self,method,path,body=None,headers=None):
        import http.client
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        try:
            connection.request(method,path,body,{'Host':'wenwenwenyiyiyi.work',**(headers or {})})
            response=connection.getresponse();return response.status,response.getheader('Content-Security-Policy'),response.read().decode()
        finally:connection.close()

    def test_all_62_static_alias_samples_and_default_deny(self):
        self.start();self.assertEqual(len(self.static_cases),62)
        for uri,expected in self.static_cases:
            with self.subTest(uri=uri):
                status,csp,body=self.request('GET',uri)
                self.assertEqual(status,200);self.assertEqual(body,expected);self.assertEqual(csp,'default-src self')
        self.assertEqual(self.request('GET','/nonexistent-private-route')[0],404)
        self.assertEqual(self.request('POST','/submit/binance')[0],404)

    def test_verified_tls_and_exact_request_forwarding(self):
        self.start()
        status,csp,body=self.request('POST','/submit/tiktok?synthetic=query','synthetic-body',{
            'Origin':'https://wenwenwenyiyiyi.work','Authorization':'Bearer synthetic-auth',
            'Cookie':'synthetic-cookie','X-Telegram-Bot-Api-Secret-Token':'synthetic-header'})
        self.assertEqual(status,200);self.assertEqual(csp,'default-src https:')
        record=json.loads(body)
        self.assertEqual(record['path'],'/submit/tiktok?synthetic=query')
        self.assertEqual(record['body'],'synthetic-body')
        self.assertEqual(record['authorization'],'Bearer synthetic-auth')
        self.assertEqual(record['cookie'],'synthetic-cookie')
        self.assertEqual(record['telegram'],'synthetic-header')
        self.assertEqual(record['origin'],'https://wenwenwenyiyiyi.work')
        self.assertIn('wenwenwenyiyiyi.work',self.sni)
        log=(self.root/'status.log').read_text()
        for secret in ['synthetic=query','synthetic-body','synthetic-auth','synthetic-cookie','synthetic-header']:
            self.assertNotIn(secret,log)

    def test_all_11_dynamic_routes_forward_to_same_fake_tls_backend(self):
        self.start()
        for route in self.routes:
            if route['handler']!='TOKYO_HTTPS_EXISTING_BACKEND':continue
            uri=route['candidate_match'].split()[-1]
            if uri.endswith('/'):uri+='synthetic'
            self.assertEqual(self.request('GET',uri)[0],200,uri)
        self.assertEqual(len(self.hits),11)

    def test_wrong_upstream_tls_name_fails_closed(self):
        self.start(wrong_sni=True)
        self.assertEqual(self.request('GET','/p/synthetic')[0],502)
        self.assertEqual(self.hits,[])

    def test_sensitive_post_timeout_is_not_retried_or_success(self):
        self.start()
        status,_,_=self.request('POST','/integrations/tiktok/disconnect','synthetic-slow')
        self.assertEqual(status,504)
        self.assertEqual(len(self.hits),1)
        self.assertEqual(self.hits[0]['method'],'POST')

if __name__=="__main__": unittest.main()

