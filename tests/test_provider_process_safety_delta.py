"""Supplemental process-safety checks; not an end-to-end main/runner test."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from producer_http_contract import REFERENCE_SHA256
from producer_http_provider import ProducerHTTPProvider
from task_supervisor import canonical

CHILD = r'''
import hashlib, os, sys, time
import producer_http_provider as module
from producer_http_contract import REFERENCE_SHA256
intent={'source_sha256':hashlib.sha256(b'source').hexdigest(),'test_reference_sha256':REFERENCE_SHA256}
def runner(source):
    with open(sys.argv[2], 'a') as f:
        f.write('invoked\n'); f.flush(); os.fsync(f.fileno())
    time.sleep(30)
module.run_producer_http_with_artifact=runner
try:
    module.ProducerHTTPProvider(sys.argv[1])(intent,b'source')
except ValueError as e:
    print(str(e),flush=True)
'''

class ProcessSafetyTests(unittest.TestCase):
    def test_interrupted_reservation_and_competing_process_do_not_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=os.path.join(directory,'invocations')
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            cmd=[sys.executable,'-c',CHILD,directory,marker]
            first=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
            try:
                deadline=time.monotonic()+10
                while not os.path.exists(marker) and time.monotonic()<deadline:
                    if first.poll() is not None: self.fail('first process exited before reservation')
                    time.sleep(.05)
                self.assertTrue(os.path.exists(marker))
                second=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=10)
                self.assertEqual(second.returncode,0,second.stderr)
                self.assertIn('EXECUTION_INTENT_ALREADY_RESERVED',second.stdout)
            finally:
                first.kill(); first.communicate(timeout=5)
            third=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=10)
            self.assertEqual(third.returncode,0,third.stderr)
            self.assertIn('EXECUTION_INTENT_ALREADY_RESERVED',third.stdout)
            self.assertEqual(Path(marker).read_text().splitlines(),['invoked'])
            intent={'source_sha256':hashlib.sha256(b'source').hexdigest(),'test_reference_sha256':REFERENCE_SHA256}
            self.assertIsNone(ProducerHTTPProvider(directory).query(intent))

    def test_existing_store_format_reads_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'producer-http.sqlite')
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            intent={'task_id':'format-only'};body=canonical(intent);digest=hashlib.sha256(body.encode()).hexdigest()
            artifact=b'old-format';obs={'intent_sha256':digest,'artifact_sha256':hashlib.sha256(artifact).hexdigest()}
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE observations (digest TEXT PRIMARY KEY, intent TEXT NOT NULL, observation TEXT, artifact BLOB)')
                db.execute('INSERT INTO observations VALUES (?,?,?,?)',(digest,body,canonical(obs),artifact))
            provider=ProducerHTTPProvider(directory)
            self.assertEqual(provider.query(intent),obs);self.assertEqual(provider.artifact(intent),artifact)

    def test_real_filesystem_permissions_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            bad=os.path.join(root,'bad');os.mkdir(bad,0o755);os.chmod(bad,0o755)
            with self.assertRaisesRegex(ValueError,'PRIVATE_PROVIDER_DIRECTORY_REQUIRED'):ProducerHTTPProvider(bad)
            private=os.path.join(root,'private');os.mkdir(private,0o700)
            target=os.path.join(root,'target');Path(target).touch(mode=0o600)
            os.symlink(target,os.path.join(private,'producer-http.sqlite'))
            with self.assertRaises(OSError):ProducerHTTPProvider(private)
            os.unlink(os.path.join(private,'producer-http.sqlite'))
            p=ProducerHTTPProvider(private)
            self.assertEqual(os.stat(p.path).st_mode & 0o777,0o600)
            os.chmod(p.path,0o644)
            with self.assertRaisesRegex(ValueError,'PRIVATE_PROVIDER_STORE_REQUIRED'):ProducerHTTPProvider(private)
