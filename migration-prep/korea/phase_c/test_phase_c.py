"""Synthetic-only adapter tests. No provider, production DB, systemd or nft action."""
import copy
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import tarfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import urlsplit

from gate_common import canonical_bytes, GateError
from korea.get_only_policy import ControlledHttpsTransport
from korea.phase_c import broker, credentials, network, runtime, security, snapshots
from korea.phase_c import artifact, prepare
from korea.phase_c.resources import CombinedResourceSampler
from readonly_reconciliation_adapter import TABLE_SPECS

NOW = 1792140000000
FEATURE = "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1"


def policy():
    return dict(schema_version=1, table="xj_pr99_c_fixture", broker_uid=986, worker_uid=1986,
                pinned_ips=["8.8.8.8", "2001:4860:4860::8888"],
                issued_at_ms=NOW-1000, expires_at_ms=NOW+120000)


def create_database(path, now=NOW):
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    created = set()
    for table, columns in TABLE_SPECS.values():
        if table in created:
            continue
        created.add(table)
        definitions = ['"%s" %s' % (column, "INTEGER PRIMARY KEY" if column == "id" else "TEXT")
                       for column in columns]
        connection.execute("CREATE TABLE %s (%s)" % (table, ",".join(definitions)))
    connection.execute("INSERT INTO account_snapshots VALUES(1,?,?,?,?)",
                       ("snapshot-a", "account-a", str(now), json.dumps({"raw": {"assets": []}})))
    connection.execute("INSERT INTO account_capabilities VALUES(1,?,?,?,?,?)",
                       ("account-a", "PRODUCTION", "HEDGE", "ACTIVE", str(now)))
    connection.execute("INSERT INTO kill_switch_state VALUES(1,'global','1','fixture')")
    connection.commit()
    return connection  # Keep WAL live; tests must not accidentally rely on checkpoint on close.


class FakeGET(ControlledHttpsTransport):
    timeout_seconds = 10
    def __init__(self):
        self.calls = []
    def get(self, url, headers=None, timeout_seconds=None):
        path = urlsplit(url).path
        self.calls.append((url, headers))
        if path == "/fapi/v1/time":
            value = {"serverTime": NOW}
        elif path == "/fapi/v3/account":
            value = {"assets": []}
        elif path == "/fapi/v1/positionSide/dual":
            value = {"dualSidePosition": True}
        else:
            value = []
        raw = canonical_bytes(value)
        return raw, {"method": "GET", "path": path, "body_sha256": security.digest(raw),
                     "status": 200, "proxy_used": False, "redirect_followed": False}


@unittest.skipUnless(os.geteuid() == 0, "Root-owned synthetic fixtures require hosted sudo/container root")
class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir="/root", prefix="pr99-c-tests-")
        cls.root = Path(cls.temp.name)
        cls.private = cls.root/"test-only-private.pem"
        cls.public = cls.root/"test-only-public.pem"
        subprocess.run(["/usr/bin/openssl", "genrsa", "-out", str(cls.private), "2048"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        subprocess.run(["/usr/bin/openssl", "rsa", "-in", str(cls.private), "-pubout", "-out", str(cls.public)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        cls.private.chmod(0o600); cls.public.chmod(0o644)
        cls.public_hash = security.digest(cls.public.read_bytes())
        cls.signer = security.DetachedRSA(cls.public, cls.public_hash, private_key=cls.private)
        cls.verifier = security.DetachedRSA(cls.public, cls.public_hash)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()  # Only synthetic test fixtures, never production evidence.
    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.root))
        self.generations = self.case/"generations"; self.generations.mkdir(); self.generations.chmod(0o711)
        self.evidence = self.case/"evidence"; self.evidence.mkdir(mode=0o700)
        self.source = self.case/"source.sqlite"
        self.db = create_database(self.source)
        self.config = dict(feature_id=FEATURE, account_id="account-a", snapshot_max_age_ms=30000,
            capture_timeout_ms=30000, runtime_manifest_sha256="a"*64,
            snapshot_publisher_identity_sha256=self.public_hash, snapshot_reader_uid=0,
            snapshot_root=str(self.generations), business_database=str(self.generations/"unused.sqlite"),
            evidence_root=str(self.evidence), credential_role="BINANCE_ACCOUNT_READONLY",
            verifier_sha256="b"*64, snapshot_refresh_protocol=snapshots.PROTOCOL,
            network_policy=policy(), writer_enabled=False, scheduler_enabled=False)
    def tearDown(self):
        self.db.close()
    def publish(self, name="gen-a", at=NOW):
        result = snapshots.collect_generation(self.source, self.generations, name, self.config, self.signer, at)
        snapshots.publish_pointer(self.generations, name, self.config, self.verifier, at)
        return result
    def client(self, fake=None, packet_mutator=None):
        fake = fake or FakeGET()
        server = broker.ReadonlyBroker(policy(), "account-a", b"synthetic-key", b"synthetic-secret",
                                      self.signer, "window-a", NOW+90000, transport=fake, clock_ms=lambda: NOW)
        def exchange(request):
            packet = server.handle(request, 1986)
            if packet_mutator:
                packet_mutator(packet)
            return packet
        return broker.VerifiedBrokerClient("/unused", 986, self.verifier, policy(), "account-a",
                    "window-a", "run-a", exchange=exchange, clock_ms=lambda: NOW), fake, server
    def test_real_signature_valid_and_mutated_payload_rejected(self):
        signed = self.signer.sign({"value": 1})
        self.assertTrue(self.verifier.verify({"value": 1}, signed))
        self.assertFalse(self.verifier.verify({"value": 2}, signed))
        self.assertFalse(self.verifier.verify({"value": 1}, "garbage"))
    def test_wrong_public_key_pin_rejected(self):
        with self.assertRaises(GateError): security.DetachedRSA(self.public, "0"*64)
    def test_symlink_and_hardlink_and_broad_file_rejected(self):
        p=self.case/"private"; security.write_once(p, b"fixture")
        for change in (lambda: os.symlink(p, self.case/"link"),):
            change()
        with self.assertRaises(OSError): security.read_file(self.case/"link")
        os.link(p, self.case/"hard")
        with self.assertRaises(GateError): security.read_file(p)
        (self.case/"hard").unlink(); p.chmod(0o644)
        with self.assertRaises(GateError): security.read_file(p)
    def test_parent_permissions_not_required_0700(self):
        self.case.chmod(0o755)
        self.assertEqual(security.trusted_directory(self.case), self.case)
        self.case.chmod(0o777)
        with self.assertRaises(GateError): security.trusted_directory(self.case)
    def test_duplicate_json_rejected(self):
        with self.assertRaises(GateError): security.strict_json(b'{"a":1,"a":2}')
    def test_atomic_rename_rejects_even_empty_existing_directory(self):
        a=self.case/"a"; b=self.case/"b"; a.mkdir(); b.mkdir()
        with self.assertRaises(FileExistsError): security.rename_new(a,b)
        self.assertTrue(a.exists() and b.exists())
    def test_wal_commit_survives_closed_authenticated_generation(self):
        self.assertTrue(Path(str(self.source)+"-wal").stat().st_size>0)
        self.publish()
        pinned, receipt, held=snapshots.pin_current(self.generations,self.config,self.verifier,NOW)
        self.assertEqual(receipt["snapshot_generation_id"],"gen-a")
        copy=held.materialize(str(self.evidence)); held.close()
        connection=sqlite3.connect(copy["path"])
        self.assertEqual(connection.execute("SELECT snapshot_id FROM account_snapshots").fetchone()[0],"snapshot-a")
        connection.close()
        self.assertFalse(Path(copy["path"]+"-wal").exists())
    def test_pointer_switch_before_reader_pin_selects_whole_new_generation(self):
        self.publish("gen-a"); self.publish("gen-b")
        _,r,h=snapshots.pin_current(self.generations,self.config,self.verifier,NOW)
        self.assertEqual(r["snapshot_generation_id"],"gen-b"); h.close()
    def test_pointer_switch_during_receipt_read_keeps_whole_old_generation(self):
        self.publish("gen-a")
        snapshots.collect_generation(self.source,self.generations,"gen-b",self.config,self.signer,NOW)
        original=snapshots.read_file
        switched=[]
        def racing(path,*args,**kwargs):
            raw=original(path,*args,**kwargs)
            if str(path).endswith("gen-a/receipt.json") and not switched:
                switched.append(True)
                snapshots.publish_pointer(self.generations,"gen-b",self.config,self.verifier,NOW)
            return raw
        with mock.patch.object(snapshots,"read_file",side_effect=racing):
            _,r,h=snapshots.pin_current(self.generations,self.config,self.verifier,NOW)
            self.assertEqual(r["snapshot_generation_id"],"gen-a"); h.close()
        self.assertEqual(json.loads((self.generations/"current.json").read_text())["generation_id"],"gen-b")
    def test_database_tamper_rejected_before_any_get(self):
        self.publish(); p=self.generations/"gen-a/business-snapshot.sqlite"
        p.chmod(0o600); p.write_bytes(p.read_bytes()+b"tamper")
        client,fake,_=self.client()
        result=runtime.run_cycle(self.config,self.verifier,lambda _:client,NOW,lambda:NOW)
        self.assertEqual(result["status"],"HOLD"); self.assertEqual(fake.calls,[])
    def test_forged_receipt_even_with_matching_local_db_hash_rejected(self):
        self.publish(); p=self.generations/"gen-a/receipt.json"
        value=json.loads(p.read_text()); value["account_id"]="attacker"
        p.chmod(0o600); p.write_bytes(canonical_bytes(value)); p.chmod(0o400)
        with self.assertRaises(GateError): snapshots.pin_current(self.generations,self.config,self.verifier,NOW)
    def test_snapshot_stale_and_cross_account_rejected(self):
        self.publish()
        with self.assertRaises(GateError): snapshots.pin_current(self.generations,self.config,self.verifier,NOW+30001)
        cfg=dict(self.config,account_id="wrong")
        with self.assertRaises(GateError): snapshots.pin_current(self.generations,cfg,self.verifier,NOW)
    def test_sidecar_and_extra_file_rejected(self):
        self.publish(); security.write_once(self.generations/"gen-a/extra",b"fixture")
        with self.assertRaises(GateError): snapshots.pin_current(self.generations,self.config,self.verifier,NOW)
    def test_incomplete_generation_never_changes_pointer(self):
        self.publish(); before=(self.generations/"current.json").read_bytes()
        with mock.patch.object(snapshots,"write_once",side_effect=OSError("synthetic interruption")):
            with self.assertRaises(OSError): snapshots.collect_generation(self.source,self.generations,"gen-failed",self.config,self.signer,NOW)
        self.assertEqual((self.generations/"current.json").read_bytes(),before)
        self.assertTrue((self.generations/".pending-gen-failed").exists())
    def test_concurrent_same_generation_only_one_capture_commits(self):
        outcomes=[]
        def run():
            try:
                snapshots.collect_generation(self.source,self.generations,"gen-race",self.config,self.signer,NOW)
                outcomes.append("commit")
            except (OSError,GateError): outcomes.append("hold")
        threads=[threading.Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sorted(outcomes),["commit","hold"])
    def test_signed_broker_result_verifies_once_and_contains_no_credentials(self):
        client,fake,_=self.client()
        response,receipt=client("server_time",None,None,"account-a","snapshot-a")
        self.assertTrue(client.verify_receipt(receipt,response))
        self.assertFalse(client.verify_receipt(receipt,response))
        self.assertNotIn("synthetic-secret",json.dumps(receipt))
        self.assertNotIn("synthetic-key",json.dumps(receipt))
        self.assertEqual(len(fake.calls),1)
    def test_broker_response_or_receipt_or_context_forgery_rejected(self):
        mutators=[lambda p:p["response"].update(items={"serverTime":1}),
                  lambda p:p["receipt"].update(account_id="wrong"),
                  lambda p:p["attestation"].update(window_id="other"),
                  lambda p:p.update(signature="garbage")]
        for mutate in mutators:
            client,_,_=self.client(packet_mutator=mutate)
            with self.subTest(mutate=repr(mutate)),self.assertRaises(GateError):
                client("server_time",None,None,"account-a","snapshot-a")
    def test_broker_rejects_wrong_uid_method_url_and_account_before_get(self):
        client,fake,server=self.client()
        request=dict(surface="server_time",symbol=None,cursor=None,account_id="account-a",
                     snapshot_id="snapshot-a",run_id="run-a",nonce="n-a")
        changes=[(request,0),(dict(request,method="POST"),1986),(dict(request,url="https://evil"),1986),
                 (dict(request,account_id="other"),1986),(dict(request,symbol="BAD"),1986)]
        for value,uid in changes:
            with self.assertRaises(GateError):server.handle(value,uid)
        self.assertEqual(fake.calls,[])
    def test_broker_replay_not_reissued_and_unknown_sign_failure_preserved(self):
        _,fake,server=self.client()
        request=dict(surface="server_time",symbol=None,cursor=None,account_id="account-a",
                     snapshot_id="snapshot-a",run_id="run-a",nonce="n-a")
        with mock.patch.object(server.signer,"sign",side_effect=OSError("fixture failure")):
            with self.assertRaises(OSError):server.handle(request,1986)
        with self.assertRaises(GateError):server.handle(request,1986)
        self.assertEqual(len(fake.calls),1)
    def test_expired_policy_blocks_broker_before_network(self):
        _,fake,server=self.client(); server.clock=lambda:NOW+120000
        with self.assertRaises(GateError):server.handle({},1986)
        self.assertEqual(fake.calls,[])
    def test_complete_authenticated_synthetic_cycle_uses_existing_reconciliation(self):
        self.publish(); client,fake,_=self.client()
        result=runtime.run_cycle(self.config,self.verifier,lambda _:client,NOW,lambda:NOW)
        self.assertEqual(result["status"],"PASS_READONLY_SHADOW_CYCLE",result)
        self.assertEqual(result["snapshot_generation_id"],"gen-a")
        self.assertGreater(len(fake.calls),10)
        self.assertFalse(result["production_authorized"])
    def test_socket_framing_and_truncation(self):
        a,b=socket.socketpair()
        with a,b:
            broker._send(a,{"fixture":"ok"})
            self.assertEqual(broker._receive(b,1000),{"fixture":"ok"})
            a.sendall(b"\x00\x00\x00\x05xx");a.shutdown(socket.SHUT_WR)
            with self.assertRaises(GateError):broker._receive(b,1000)
    def test_unix_peer_uid_is_observed_not_caller_supplied(self):
        path=str(self.case/"broker.sock")
        try:
            listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        except PermissionError:
            self.skipTest("Local sandbox denies new AF_UNIX listener; hosted CI must exercise it")
        listener.bind(path);listener.listen(1)
        _,fake,server=self.client()
        thread=threading.Thread(target=server.serve_one,args=(listener,));thread.start()
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
            conn.connect(path);broker._send(conn,{"peer_uid":1986})
            self.assertEqual(broker._receive(conn,1000),{"status":"HOLD_BROKER_REJECTED"})
        thread.join(timeout=5);listener.close();self.assertFalse(thread.is_alive());self.assertEqual(fake.calls,[])
    def test_key_permission_owner_enforcement_on_multi_uid_host(self):
        path=self.case/"uid-fixture";security.write_once(path,b"fixture")
        try:os.chown(path,986,986)
        except OSError as error:
            if error.errno==22:self.skipTest("Local user namespace maps UID0 only; hosted CI must exercise actual UID986")
            raise
        with self.assertRaises(GateError):security.read_file(path,owner=1986)
        self.assertEqual(security.read_file(path,owner=986),b"fixture")

    def attestation(self):
        return dict(account_id="account-a",role=credentials.ROLE,secret_ref="SecretRef:READONLY_FIXTURE",
                    read_only_verified=True,trading_enabled=False,withdrawal_enabled=False,expires_at_ms=NOW+90000,
                    pair_sha256=credentials.pair_digest(b"synthetic-key",b"synthetic-secret"))

    def test_credential_refusal_before_secret_files_or_pointer(self):
        root=self.case/"credentials";root.mkdir();root.chmod(0o711)
        expected={k:self.attestation()[k] for k in ("account_id","role","secret_ref")}
        bad=self.attestation();bad["trading_enabled"]=True
        with self.assertRaises(GateError):
            credentials.deliver_pair(root,"bad",986,986,expected,lambda _:(b"key",b"secret",bad),lambda _:True,NOW)
        self.assertTrue((root/".pending-bad").exists());self.assertFalse((root/"bad").exists())
        self.assertFalse(any(x.name=="api_key" for x in (root/".pending-bad").iterdir()))

    def test_unverified_or_expired_readonly_attestation_refused(self):
        expected={k:self.attestation()[k] for k in ("account_id","role","secret_ref")}
        for change in ({"read_only_verified":False},{"withdrawal_enabled":True},{"role":"BINANCE_TRADING"},
                       {"account_id":"other"},{"expires_at_ms":NOW}):
            with self.subTest(change=change),self.assertRaises(GateError):
                credentials.validate_attestation(dict(self.attestation(),**change),expected,NOW)

    def test_pair_delivery_partial_write_preserves_private_pending(self):
        root=self.case/"credentials";root.mkdir();root.chmod(0o711)
        expected={k:self.attestation()[k] for k in ("account_id","role","secret_ref")}
        def interrupted(path,data,**kwargs):
            if path.name=="api_secret":raise OSError("synthetic failure between pair members")
            security.write_once(path,data,mode=kwargs["mode"])
        # Simulates fchown only: this local namespace cannot map UID986. Actual
        # uid/mode and worker denial are exercised separately in hosted CI.
        with mock.patch.object(credentials,"write_once",side_effect=interrupted):
            with self.assertRaises(OSError):credentials.deliver_pair(root,"partial",986,986,expected,
                lambda _:(b"synthetic-key",b"synthetic-secret",self.attestation()),lambda _:True,NOW)
        self.assertFalse((root/"partial").exists())
        self.assertEqual((root/".pending-partial").stat().st_mode&0o777,0o700)
        with self.assertRaises(FileExistsError):credentials.deliver_pair(root,"partial",986,986,expected,
                lambda _:self.fail("must not reread SecretRef"),lambda _:True,NOW)

    def test_actual_pair_delivery_uid986_and_worker_cannot_read(self):
        probe=self.case/"uidprobe";security.write_once(probe,b"fixture")
        try:os.chown(probe,986,986)
        except OSError as error:
            if error.errno==22:self.skipTest("UID986 unavailable locally; actual custody tested on hosted root")
            raise
        root=self.case/"credentials";root.mkdir();root.chmod(0o711)
        expected={k:self.attestation()[k] for k in ("account_id","role","secret_ref")}
        credentials.deliver_pair(root,"pair",986,986,expected,
                lambda _:(b"synthetic-key",b"synthetic-secret",self.attestation()),lambda _:True,NOW)
        pair=root/"pair"
        self.assertEqual(credentials.load_pair(pair,expected,lambda _:True,NOW),(b"synthetic-key",b"synthetic-secret"))
        self.assertEqual((pair/"api_key").stat().st_uid,986)
        self.assertEqual((pair/"api_secret").stat().st_mode&0o777,0o400)
        # Permit pathname traversal; the deny must come from actual file owner/mode.
        self.root.chmod(0o711);self.case.chmod(0o711)
        code="import os,sys;os.setgid(1986);os.setuid(1986);open(sys.argv[1],'rb').read()"
        r=subprocess.run([sys.executable,"-I","-B","-c",code,str(pair/"api_key")],capture_output=True)
        self.assertNotEqual(r.returncode,0);self.assertIn(b"PermissionError",r.stderr)
        self.root.chmod(0o700)

    def test_receive_forged_transfer_leaves_current_unchanged(self):
        self.publish();before=(self.generations/"current.json").read_bytes()
        rows={p.name:p.read_bytes() for p in (self.generations/"gen-a").iterdir()}
        rows["business-snapshot.sqlite"]+=b"forged"
        with self.assertRaises(GateError):snapshots.receive_generation(self.generations,"gen-new",rows,self.config,self.verifier,NOW)
        self.assertEqual((self.generations/"current.json").read_bytes(),before)

    def test_receive_signed_generation_and_duplicate_unknown_ack(self):
        # Simulates the authenticated transport's binary input; destination path is
        # signed by source before transfer. No business export/network is performed.
        self.publish("gen-a")
        rows={p.name:p.read_bytes() for p in (self.generations/"gen-a").iterdir()}
        receipt=json.loads(rows["receipt.json"])
        receipt.update(snapshot_generation_id="gen-transfer",database_path=str(self.generations/"gen-transfer/business-snapshot.sqlite"))
        rows["receipt.json"]=canonical_bytes(receipt)
        rows["signature.json"]=canonical_bytes({"signature":self.signer.sign(receipt)})
        result=snapshots.receive_generation(self.generations,"gen-transfer",rows,self.config,self.verifier,NOW)
        self.assertEqual(result["status"],"GENERATION_COMMITTED")
        with self.assertRaises(GateError):snapshots.receive_generation(self.generations,"gen-transfer",rows,self.config,self.verifier,NOW)

    def acceptance(self):
        p=Path(__file__).parents[1]/"shadow-acceptance.template.json"
        a=json.loads(p.read_text());a.update(owner_approved=True,owner_approval_id="synthetic-only",
            window_id="window-a",duration_seconds=60,sample_interval_seconds=30,minimum_samples=2,
            max_sample_gap_seconds=60)
        return a

    def admission(self,config,acceptance):
        return dict(schema_version=1,action="PR99_PHASE_C_READONLY_SHADOW_V1",host="iZmj7a5kwr75qc1tul4kf9Z",
            window_id=acceptance["window_id"],config_sha256=security.hash_value(config),
            acceptance_sha256=security.hash_value(acceptance),issued_at_ms=NOW-1000,expires_at_ms=NOW+100000,
            approval_comment_id=999999,max_attempts=1,network_enforcement_verified=True,
            credential_readonly_verified=True,source_identity_verified=True)

    def test_exact_external_admission_binding_and_expiry(self):
        cfg=dict(self.config,snapshot_reader_uid=1986);a=self.acceptance();ad=self.admission(cfg,a)
        signature=self.signer.sign(ad)
        runtime.verify_admission(ad,signature,self.verifier,cfg,a,NOW,ad["host"])
        for key,value in (("action","OLD_PHASE_B"),("window_id","old-window"),("max_attempts",2),
                          ("network_enforcement_verified",False),("credential_readonly_verified",False),
                          ("source_identity_verified",False),("config_sha256","0"*64)):
            bad=dict(ad,**{key:value})
            with self.subTest(key=key),self.assertRaises(GateError):
                runtime.verify_admission(bad,self.signer.sign(bad),self.verifier,cfg,a,NOW,ad["host"])
        with self.assertRaises(GateError):runtime.verify_admission(ad,signature,self.verifier,cfg,a,NOW+100000,ad["host"])
        with self.assertRaises(GateError):runtime.verify_admission(ad,"forged",self.verifier,cfg,a,NOW,ad["host"])

    def resource(self):
        return dict(rss_mib=10,mem_available_mib=1024,swap_used_mib=0,cgroup_memory_peak_mib=12,
                    cgroup_oom=0,cgroup_version="v1",cgroup_oom_semantics="fixture-v1",
                    cgroup_evidence_complete=True)

    def test_window_complete_two_fresh_generations_with_original_ledger(self):
        self.publish("gen-a");cfg=dict(self.config,snapshot_reader_uid=1986)
        a=self.acceptance();ad=self.admission(cfg,a);clock=[NOW];captured=[]
        def pin(*args):
            name="gen-"+str(len(captured))
            class Held:
                def close(self):pass
            return {},{"snapshot_generation_id":name},Held()
        def cycle(*args,**kwargs):
            captured.append(kwargs["now_ms"])
            return dict(status="PASS_READONLY_SHADOW_CYCLE",snapshot_generation_id="gen-"+str(len(captured)),
                        observation_run_id="fixture",authoritative_business_snapshot_id="snapshot-a")
        with mock.patch.object(runtime.os,"geteuid",return_value=1986),mock.patch.object(runtime,"pin_current",side_effect=pin),mock.patch.object(runtime,"run_cycle",side_effect=cycle):
            result=runtime.run_window(cfg,a,ad,self.signer.sign(ad),self.verifier,self.verifier,None,
                clock_ms=lambda:clock[0],sleep_fn=lambda sec:clock.__setitem__(0,clock[0]+int(sec*1000)),
                resource_sampler=self.resource,host=ad["host"])
        self.assertEqual(result["status"],"PASS_SHADOW_WINDOW",result)
        self.assertEqual(len(result["samples"]),2)
        # This is a clock/resource/UID model, not real elapsed window or live process isolation.
        with mock.patch.object(runtime.os,"geteuid",return_value=1986),self.assertRaises(FileExistsError):
            runtime.run_window(cfg,a,ad,self.signer.sign(ad),self.verifier,self.verifier,None,
                clock_ms=lambda:NOW,resource_sampler=self.resource,host=ad["host"])

    def test_duplicate_generation_holds_before_second_get(self):
        cfg=dict(self.config,snapshot_reader_uid=1986);a=self.acceptance();ad=self.admission(cfg,a);clock=[NOW]
        class Held:
            def close(self):pass
        with mock.patch.object(runtime.os,"geteuid",return_value=1986),mock.patch.object(runtime,"pin_current",return_value=({}, {"snapshot_generation_id":"same"},Held())),mock.patch.object(runtime,"run_cycle",return_value=dict(status="PASS_READONLY_SHADOW_CYCLE",snapshot_generation_id="same")) as runner:
            with self.assertRaises(GateError):runtime.run_window(cfg,a,ad,self.signer.sign(ad),self.verifier,self.verifier,None,
                clock_ms=lambda:clock[0],sleep_fn=lambda sec:clock.__setitem__(0,clock[0]+int(sec*1000)),
                resource_sampler=self.resource,host=ad["host"])
            self.assertEqual(runner.call_count,1)
        ledger=json.loads((self.evidence/"shadow-window-window-a.json").read_text())
        self.assertEqual(ledger["status"],"HOLD_INTERRUPTED")

    def test_missing_real_cgroup_evidence_never_becomes_zero(self):
        from korea.shadow_acceptance import run_continuous
        with self.assertRaises(GateError):run_continuous(self.config,self.acceptance(),clock_ms=lambda:NOW,
            resource_sampler=lambda:{"rss_mib":1,"swap_used_mib":0,"mem_available_mib":1000})

    def test_reproducible_bound_package_and_runtime_tamper_rejection(self):
        source=Path(__file__).resolve().parents[3]
        first=self.case/"a.tar.gz";second=self.case/"b.tar.gz"
        receipt=artifact.build(source,"a"*40,first);artifact.build(source,"a"*40,second)
        self.assertEqual(first.read_bytes(),second.read_bytes())
        extracted=self.case/"extracted";extracted.mkdir(mode=0o700)
        with tarfile.open(first) as archive:
            rows={}
            for member in archive.getmembers():
                self.assertTrue(member.isfile());self.assertNotIn("..",Path(member.name).parts)
                self.assertNotIn(member.name,rows)
                rows[member.name]=archive.extractfile(member).read()
                target=extracted/member.name;target.parent.mkdir(parents=True,exist_ok=True)
                security.write_once(target,rows[member.name],mode=0o400)
        binding=json.loads(rows["REVIEW_BINDING.json"])
        self.assertEqual(set(rows),set(binding["files"])|{"REVIEW_BINDING.json"})
        for name,expected in binding["files"].items():self.assertEqual(security.digest(rows[name]),expected)
        artifact.verify_runtime(extracted,receipt["runtime_manifest_sha256"])
        changed=extracted/"migration-prep/korea/phase_c/network.py"
        changed.chmod(0o600);changed.write_bytes(changed.read_bytes()+b"\n#tampered\n")
        with self.assertRaises(GateError):artifact.verify_runtime(extracted,receipt["runtime_manifest_sha256"])

    def test_candidate_unit_render_rejects_injection_and_old_release(self):
        values=dict(C_RELEASE="/opt/xuanjun-binance-phase-c/releases/"+"a"*64,
                    PYTHON="/usr/bin/python3.11",C_CONFIG="/etc/xuanjun-binance-phase-c/runtime.json",
                    C_CONFIG_ROOT="/etc/xuanjun-binance-phase-c",C_CREDENTIAL_ROOT="/run/xuanjun-phase-c-credentials",
                    C_KEY_ROOT="/etc/xuanjun-binance-phase-c/keys",C_PRIVATE_KEY_ROOT="/run/xuanjun-phase-c-private-keys",
                    C_SNAPSHOT_ROOT="/var/lib/xuanjun-binance-phase-c/snapshots",
                    C_EVIDENCE_ROOT="/var/lib/xuanjun-binance-phase-c/evidence",RUNTIME_SECONDS=120)
        units=prepare.render_units(values)
        self.assertIn("PrivateNetwork=yes",units["worker.service"])
        self.assertIn("RestrictAddressFamilies=AF_UNIX\n",units["worker.service"])
        self.assertIn("Restart=no",units["broker.service"])
        self.assertIn('WatchdogSec=45s',units['controller.service'])
        self.assertIn('from korea.phase_c.stop_guard import main',units['controller.service'])
        self.assertIn('BindsTo=xuanjun-binance-phase-c-controller.service',units['worker.service'])
        self.assertIn('RuntimeMaxSec=240',units['controller.service'])
        self.assertNotIn("LoadCredential",json.dumps(units))
        self.assertNotIn("IPAddressDeny",json.dumps(units))
        for change in ({"C_RELEASE":"/opt/xuanjun-binance/current"},{"C_CONFIG":"/tmp/x';import os"},
                       {"RUNTIME_SECONDS":0},{"C_EVIDENCE_ROOT":"/var/lib/shared"}):
            with self.subTest(change=change),self.assertRaises(GateError):prepare.render_units(dict(values,**change))

    def test_cgroup_v1_paths_missing_or_positive_oom_not_fabricated(self):
        from korea.shadow_acceptance import sample_resources
        proc=self.case/"proc";(proc/"self").mkdir(parents=True)
        (proc/"self/status").write_text("VmRSS: 1024 kB\n")
        (proc/"meminfo").write_text("MemAvailable: 1048576 kB\nSwapTotal: 1024 kB\nSwapFree: 1024 kB\n")
        (proc/"self/cgroup").write_text("5:memory:/candidate\n")
        cg=self.case/"cgroup";(cg/"memory/candidate").mkdir(parents=True)
        with self.assertRaises(FileNotFoundError):sample_resources(str(proc),str(cg))
        (cg/"memory/candidate/memory.max_usage_in_bytes").write_text("2097152")
        (cg/"memory/candidate/memory.failcnt").write_text("3")
        (cg/"memory/candidate/memory.oom_control").write_text("under_oom 1\noom_kill_disable 0\n")
        result=sample_resources(str(proc),str(cg))
        self.assertEqual(result["cgroup_oom"],4);self.assertEqual(result["cgroup_version"],"v1")

    def test_broker_credential_expiry_independent_of_network_expiry(self):
        _,fake,server=self.client();server.clock=lambda:NOW+90000
        with self.assertRaises(GateError):server.handle({},1986)
        self.assertEqual(fake.calls,[])

    def test_combined_resources_include_broker_peak_oom_and_pid_identity(self):
        proc=self.case/"combined-proc";cg=self.case/"combined-cgroup"
        for name in ("self","123"):(proc/name).mkdir(parents=True)
        (proc/"self/cgroup").write_text("5:memory:/worker\n")
        (proc/"123/cgroup").write_text("5:memory:/broker\n")
        fields=["S"]+["0"]*18+["42"]
        (proc/"123/stat").write_text("123 (fixture) "+" ".join(fields))
        (proc/"123/status").write_text("Uid: 986 986 986 986\nVmRSS: 2048 kB\n")
        mem=cg/"memory/broker";mem.mkdir(parents=True)
        (mem/"memory.max_usage_in_bytes").write_text("3145728")
        (mem/"memory.failcnt").write_text("2")
        (mem/"memory.oom_control").write_text("under_oom 1\n")
        sampler=CombinedResourceSampler(123,proc,cg,worker_sampler=self.resource)
        result=sampler()
        self.assertEqual(result["rss_mib"],12);self.assertEqual(result["cgroup_memory_peak_mib"],15)
        self.assertEqual(result["cgroup_oom"],3)
        fields[-1]="43";(proc/"123/stat").write_text("123 (fixture) "+" ".join(fields))
        with self.assertRaises(GateError):sampler()

    def test_combined_resources_reject_same_cgroup_or_missing_oom(self):
        proc=self.case/"combined-proc";cg=self.case/"combined-cgroup"
        for name in ("self","123"):(proc/name).mkdir(parents=True)
        (proc/"self/cgroup").write_text("5:memory:/same\n")
        (proc/"123/cgroup").write_text("5:memory:/same\n")
        (proc/"123/stat").write_text("123 (fixture) "+" ".join(["S"]+["0"]*18+["42"]))
        with self.assertRaises(GateError):CombinedResourceSampler(123,proc,cg,worker_sampler=self.resource)

    def test_combined_resources_include_root_controller_separate_cgroup(self):
        proc=self.case/'three-proc';cg=self.case/'three-cgroup'
        (proc/'self').mkdir(parents=True);(proc/'self/cgroup').write_text('5:memory:/worker\n')
        for pid,uid,name,rss,peak,oom in ((123,986,'broker',2048,3145728,0),(124,0,'controller',1024,4194304,1)):
            p=proc/str(pid);p.mkdir();(p/'cgroup').write_text('5:memory:/'+name+'\n')
            (p/'stat').write_text(str(pid)+' (synthetic) '+' '.join(['S']+['0']*18+['42']))
            (p/'status').write_text('Uid: '+' '.join([str(uid)]*4)+'\nVmRSS: '+str(rss)+' kB\n')
            m=cg/('memory/'+name);m.mkdir(parents=True)
            (m/'memory.max_usage_in_bytes').write_text(str(peak))
            (m/'memory.failcnt').write_text(str(oom));(m/'memory.oom_control').write_text('under_oom 0\n')
        broker_sample=CombinedResourceSampler(123,proc,cg,worker_sampler=self.resource)
        all_sample=CombinedResourceSampler(124,proc,cg,worker_sampler=broker_sample,peer_uid=0)
        result=all_sample();self.assertEqual(result['rss_mib'],13)
        self.assertEqual(result['cgroup_memory_peak_mib'],19);self.assertEqual(result['cgroup_oom'],1)

    def test_templates_require_external_admission_and_root_owned_manifest(self):
        from korea.phase_c.entry import load_config
        template=self.case/"placeholder.json";security.write_once(template,b'{"schema_version":1}',mode=0o644)
        with self.assertRaises(GateError):load_config(template)
        with self.assertRaises(FileNotFoundError):artifact.verify_runtime(self.case,"0"*64)


class NetworkTests(unittest.TestCase):
    def test_rules_only_create_own_inet_output_and_two_uid_drops(self):
        rules=network.compile_rules(policy(),NOW)
        self.assertIn("create table inet xj_pr99_c_fixture",rules)
        self.assertIn("meta skuid 986 ip daddr 8.8.8.8 tcp dport 443",rules)
        self.assertIn("meta skuid 986 ip6 daddr 2001:4860:4860::8888 tcp dport 443",rules)
        self.assertIn("meta skuid 1986 counter drop",rules)
        for forbidden in ("flush", " input ", " forward ", "IPAddressDeny", "udp dport"):
            self.assertNotIn(forbidden,rules)
    def test_private_duplicate_injected_ip_and_table_rejected(self):
        for key,value in (("pinned_ips",["127.0.0.1"]),("pinned_ips",["8.8.8.8","8.8.8.8"]),
                          ("pinned_ips",["8.8.8.8; flush ruleset"]),("table","xj_pr99_c_a;drop"),
                          ("worker_uid",986),("worker_uid",0)):
            with self.subTest(key=key,value=value),self.assertRaises((GateError,ValueError)):
                network.compile_rules(dict(policy(),**{key:value}),NOW)
    def test_pinned_transport_never_calls_dns_and_checks_expiry(self):
        clock=[NOW]; transport=network.ApprovedPinnedTransport(policy(),lambda:clock[0])
        with mock.patch("socket.getaddrinfo",side_effect=AssertionError("DNS forbidden")):
            chosen,pins=transport._resolve();self.assertIn(chosen,pins)
        clock[0]=NOW+120000
        with self.assertRaises(GateError):transport._resolve()


if __name__=="__main__":unittest.main()
