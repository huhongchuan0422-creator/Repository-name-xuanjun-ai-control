"""Host-owned durable observations for the fixed offline producer runner.

A reserved invocation remains UNKNOWN after interruption; it is never replayed.
This store records runner observations, not task authority or attestations.
"""
import hashlib
import json
import os
import sqlite3
import stat

from producer_http_contract import REFERENCE_SHA256
from producer_http_runner import run_producer_http_with_artifact
from task_supervisor import canonical


class ProducerHTTPProvider:
    def __init__(self, directory):
        directory = os.path.abspath(directory)
        st = os.lstat(directory)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            raise ValueError('PRIVATE_PROVIDER_DIRECTORY_REQUIRED')
        self.path = os.path.join(directory, 'producer-http.sqlite')
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
                raise ValueError('PRIVATE_PROVIDER_STORE_REQUIRED')
        finally:
            os.close(fd)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS observations (digest TEXT PRIMARY KEY, intent TEXT NOT NULL, observation TEXT, artifact BLOB)')

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def _identity(intent):
        body = canonical(intent)
        return body, hashlib.sha256(body.encode()).hexdigest()

    def __call__(self, intent, source):
        body, digest = self._identity(intent)
        if (type(source) is not bytes or hashlib.sha256(source).hexdigest() != intent.get('source_sha256')
                or intent.get('test_reference_sha256') != REFERENCE_SHA256):
            raise ValueError('PRODUCER_INPUT_BINDING_MISMATCH')
        with self._connect() as db:
            try:
                db.execute('INSERT INTO observations(digest,intent) VALUES (?,?)', (digest, body))
            except sqlite3.IntegrityError:
                raise ValueError('EXECUTION_INTENT_ALREADY_RESERVED')
        observation, artifact = run_producer_http_with_artifact(source)
        if (observation.get('source_sha256') != intent['source_sha256'] or
                observation.get('test_reference_sha256') != REFERENCE_SHA256 or
                observation.get('artifact_sha256') != hashlib.sha256(artifact).hexdigest()):
            raise ValueError('PRODUCER_OBSERVATION_BINDING_MISMATCH')
        observation = dict(observation, intent_sha256=digest)
        with self._connect() as db:
            db.execute('UPDATE observations SET observation=?,artifact=? WHERE digest=? AND intent=?',
                       (canonical(observation), artifact, digest, body))
        return observation

    def _read(self, intent):
        body, digest = self._identity(intent)
        with self._connect() as db:
            row = db.execute('SELECT intent,observation,artifact FROM observations WHERE digest=?', (digest,)).fetchone()
        if row is None or row[1] is None:
            return None
        if row[0] != body:
            raise ValueError('EXECUTION_INTENT_BINDING_CONFLICT')
        observation = json.loads(row[1])
        if observation['intent_sha256'] != digest or hashlib.sha256(row[2]).hexdigest() != observation['artifact_sha256']:
            raise ValueError('PRODUCER_STORED_OBSERVATION_MISMATCH')
        return observation, row[2]

    def query(self, intent):
        result = self._read(intent)
        return None if result is None else result[0]

    def artifact(self, intent):
        result = self._read(intent)
        return None if result is None else result[1]
