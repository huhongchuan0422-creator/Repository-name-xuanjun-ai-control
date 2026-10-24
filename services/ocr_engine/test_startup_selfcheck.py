import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet
from services.ocr_engine.startup_selfcheck import check_environment

class StartupSelfcheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.models = {}
        for name in ("det", "rec", "cls"):
            path = self.root / (name + ".onnx")
            path.write_bytes(("synthetic-model-" + name).encode())
            self.models[name] = path
        self.expected = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in self.models.items()}
        self.manifest = self.root / "model_manifest.json"
        self.manifest.write_text(json.dumps({"model_set":{"files":{name:{"sha256":digest} for name,digest in self.expected.items()}}}))
        self.db = self.root / "data" / "ocr.sqlite3"
        self.db.parent.mkdir(mode=0o700)
        self.env = {
            "OCR_SQLITE_PATH":str(self.db),
            "OCR_ENCRYPTION_KEY":Fernet.generate_key().decode("ascii"),
            "OCR_DET_MODEL_PATH":str(self.models["det"]),
            "OCR_REC_MODEL_PATH":str(self.models["rec"]),
            "OCR_CLS_MODEL_PATH":str(self.models["cls"]),
            "OCR_MODEL_SHA256":json.dumps(self.expected),
        }
    def tearDown(self):
        self.tmp.cleanup()
    def check(self):
        return check_environment(self.env, self.manifest)
    def test_valid_prestaged_assets_pass_without_creating_database(self):
        result=self.check()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["production_callbacks"], "NOT_CONNECTED")
        self.assertEqual(result["production_start"], "HOLD")
        self.assertFalse(self.db.exists())
    def test_missing_external_key_fails_without_generating_one(self):
        self.env.pop("OCR_ENCRYPTION_KEY")
        result=self.check()
        self.assertFalse(result["ok"])
        self.assertIn("MISSING_REQUIRED_SETTINGS:OCR_SQLITE_PATH,OCR_ENCRYPTION_KEY,OCR_DET_MODEL_PATH,OCR_REC_MODEL_PATH,OCR_CLS_MODEL_PATH,OCR_MODEL_SHA256", result["errors"])
        self.assertFalse(self.db.exists())
    def test_model_hash_mismatch_fails(self):
        self.env["OCR_MODEL_SHA256"]=json.dumps({**self.expected,"det":"0"*64})
        result=self.check()
        self.assertFalse(result["ok"])
        self.assertIn("OCR_MODEL_PIN_MISMATCH:det",result["errors"])
    def test_model_byte_change_fails(self):
        self.models["rec"].write_bytes(b"changed")
        result=self.check()
        self.assertFalse(result["ok"])
        self.assertIn("OCR_MODEL_SHA256_MISMATCH:rec",result["errors"])
    def test_symlink_model_is_rejected(self):
        target=self.root/"det-link-target.onnx"; target.write_bytes(b"target")
        link=self.root/"det-link.onnx"; link.symlink_to(target)
        self.env["OCR_DET_MODEL_PATH"]=str(link)
        result=self.check()
        self.assertFalse(result["ok"])
        self.assertIn("OCR_MODEL_FILE_UNAVAILABLE:det",result["errors"])
    def test_existing_database_with_broad_permissions_fails(self):
        self.db.write_bytes(b"")
        self.db.chmod(0o644)
        result=self.check()
        self.assertFalse(result["ok"])
        self.assertIn("OCR_DB_PERMISSIONS_UNSAFE",result["errors"])
