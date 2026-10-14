"""Bounded stdio Codex worker with native model/account evidence (Python 3.6+).

Uses only an already provisioned dedicated ChatGPT login. No login, token copy,
API key, channel delivery, automatic task replay or deployment is performed.
The supervisor must enforce per-job OS containment and protect HOME/CODEX_HOME
from model tools. A protocol fixture is always simulated, never live evidence.
Protocol: https://learn.chatgpt.com/docs/app-server
"""
import json
import hashlib
import math
import os
import re
import selectors
import signal
import subprocess
import threading
import time

from codex_worker import CodexWorker, MAX_PROMPT_BYTES, MAX_STREAM_BYTES


class ProtocolFailure(Exception):
    def __init__(self, code):
        self.code = code


class CodexAppServerWorker(CodexWorker):
    def __init__(self, *args, **kwargs):
        self.isolation_prefix = kwargs.pop('isolation_prefix', ())
        super(CodexAppServerWorker, self).__init__(*args, **kwargs)
        if any(os.path.realpath(path) != path for path in
               (self.home, self.codex_home, self.workdir)):
            raise ValueError('canonical paths required')
        for path in (self.home, self.codex_home):
            if (os.path.commonpath([path, self.workdir]) == self.workdir
                    or os.path.commonpath([path, self.workdir]) == path):
                raise ValueError('authentication home and snapshot must be disjoint')
        self._proc = self._selector = None
        self._run_lock = threading.Lock()
        if self.isolation_prefix and not self._valid_isolation_prefix(self.isolation_prefix):
            raise ValueError('unapproved per-task isolation wrapper')
        self.requires_boundary_proof = bool(self.isolation_prefix)
        self._pending_result = None

    def _result(self, *args, **kwargs):
        result = super(CodexAppServerWorker, self)._result(*args, **kwargs)
        self._pending_result = result
        return result

    def _valid_isolation_prefix(self, prefix):
        values = list(prefix)
        if (len(values) not in (10, 11) or values[-1:] != ['--']
                or not isinstance(values[0], str) or not values[0].startswith('/')
                or os.path.realpath(values[0]) != values[0]
                or values[2] != '--operation=launch'):
            return False
        expected_names = ('--socket=', '--operation=', '--task-id=', '--fence=',
                          '--generation=', '--epoch=', '--instance=', '--role=')
        if any(not values[index + 1].startswith(name)
               for index, name in enumerate(expected_names)):
            return False
        socket_path = values[1][len('--socket='):]
        task_id = values[3][len('--task-id='):]
        fence = values[4][len('--fence='):]
        generation = values[5][len('--generation='):]
        epoch = values[6][len('--epoch='):]
        instance = values[7][len('--instance='):]
        role = values[8][len('--role='):]
        if (not socket_path.startswith('/') or os.path.realpath(socket_path) != socket_path
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', task_id)
                or any(not re.fullmatch(r'[1-9][0-9]*', item)
                       for item in (fence, generation, epoch))
                or not re.fullmatch(
                    r'[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',
                    instance)):
            return False
        task_key = hashlib.sha256(task_id.encode('utf-8')).hexdigest()[:24]
        main_root = os.path.join(os.path.dirname(self.workdir), task_key)
        if role == 'DEVELOPMENT':
            if len(values) != 10 or self.workdir != main_root:
                return False
        elif role == 'QA':
            if len(values) != 11 or not values[9].startswith('--artifact-sha='):
                return False
            artifact = values[9][len('--artifact-sha='):]
            if not re.fullmatch(r'[0-9a-f]{40}', artifact) or self.workdir != main_root + '-qa-' + artifact:
                return False
        else:
            return False
        return True

    @staticmethod
    def _stop(proc):
        # Give the privileged helper enough time to stop the transient unit and
        # prove it inactive before a final kill. Failure remains an unknown
        # effect and the pipeline quarantines the task.
        try: os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait()
        return proc.poll() is not None and proc.returncode == 0

    def build_argv(self):
        return list(self.isolation_prefix) + [self.codex_bin, '-c', 'model_provider="openai"',
                '-c', 'approval_policy="never"', '-c', 'features.multi_agent=false',
                'app-server', '--listen', 'stdio://']

    def _guard(self):
        now = time.monotonic()
        if now >= self._deadline:
            raise ProtocolFailure('TIMEOUT')
        if self._lease is not None and not self._lease():
            raise ProtocolFailure('LEASE_LOST')
        if self._heartbeat is not None and now >= self._next_heartbeat:
            self._heartbeat()
            self._next_heartbeat = now + self._heartbeat_seconds

    def _send(self, value):
        self._guard()
        packed = (json.dumps(value, separators=(',', ':'),
                             ensure_ascii=False) + '\n').encode('utf-8')
        # Nonblocking input avoids deadlock when an unresponsive server stops
        # reading a large prompt. The same deadline/fence applies while writing.
        position = 0
        while position < len(packed):
            self._guard()
            try:
                written = os.write(self._proc.stdin.fileno(), packed[position:])
                if written <= 0:
                    raise ProtocolFailure('TRANSPORT_CLOSED')
                position += written
            except BlockingIOError:
                self._drain(0.02)

    def _drain(self, timeout=0.1):
        for key, _ in self._selector.select(timeout=timeout):
            chunk = os.read(key.fd, 65536)
            if not chunk:
                raise ProtocolFailure('TRANSPORT_CLOSED')
            self._bytes += len(chunk)
            if self._bytes > MAX_STREAM_BYTES:
                raise ProtocolFailure('OUTPUT_LIMIT')
            self._buffer.extend(chunk)

    def _event(self):
        while True:
            self._guard()
            if b'\n' in self._buffer:
                raw, _, rest = self._buffer.partition(b'\n')
                self._buffer = bytearray(rest)
                try:
                    value = json.loads(raw.decode('utf-8'))
                    if not isinstance(value, dict):
                        raise ValueError('invalid object')
                except (ValueError, UnicodeError):
                    raise ProtocolFailure('INVALID_JSON')
                return value
            self._drain(min(0.1, max(0, self._deadline - time.monotonic())))

    def _notification(self, event):
        # Reject server requests rather than granting approvals, credentials,
        # elicitation, dynamic tools or attestations. Never echo their payload.
        if 'id' in event and 'method' in event:
            self._send({'id': event['id'], 'error': {
                'code': -32601, 'message': 'Unattended request not authorized'}})
            raise ProtocolFailure('HUMAN_INPUT_REQUIRED')
        method, params = event.get('method'), event.get('params', {})
        if method == 'account/updated' and params.get('authMode') != 'chatgpt':
            raise ProtocolFailure('OAUTH_ROUTE_CHANGED')
        if method in ('model/rerouted', 'model/safetyBuffering/updated'):
            # No implicit reroute, including a service-selected faster model.
            raise ProtocolFailure('MODEL_ROUTE_CHANGED')
        if method == 'error':
            raise ProtocolFailure('TURN_FAILED')
        if method in ('item/started', 'item/completed'):
            item = params.get('item', {})
            if item.get('type') in ('collabToolCall', 'mcpToolCall', 'dynamicToolCall'):
                raise ProtocolFailure('TOOL_ROUTE_NOT_AUTHORIZED')
        return method, params

    def _rpc(self, method, params):
        self._sequence += 1
        identifier = self._sequence
        self._send({'id': identifier, 'method': method, 'params': params})
        while True:
            event = self._event()
            if 'id' in event and 'method' not in event:
                if event['id'] != identifier or 'error' in event:
                    raise ProtocolFailure('RPC_REJECTED')
                result = event.get('result')
                if not isinstance(result, dict):
                    raise ProtocolFailure('INVALID_RPC_RESULT')
                return result
            method_name, _ = self._notification(event)
            # Inference events arriving before acknowledged turn identity must
            # not be discarded and later misrepresented as a complete turn.
            if method_name in ('item/completed', 'turn/completed'):
                raise ProtocolFailure('TURN_ORDER_UNCONFIRMED')

    def _sandbox_policy(self):
        access = {'type': 'restricted', 'includePlatformDefaults': True,
                  'readableRoots': [self.workdir, '/usr', '/bin', '/lib', '/lib64']}
        if self.sandbox == 'read-only':
            return {'type': 'readOnly', 'access': access}
        return {'type': 'workspaceWrite', 'writableRoots': [self.workdir],
                'readOnlyAccess': access, 'networkAccess': False}

    def run(self, prompt, timeout_seconds=900, heartbeat=None,
            lease_check=None, heartbeat_seconds=5):
        raise RuntimeError('delegated model dispatch prohibited by owner policy')
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('nonempty prompt required')
        if len(prompt.encode('utf-8')) > MAX_PROMPT_BYTES:
            raise ValueError('prompt too large')
        for timing in (timeout_seconds, heartbeat_seconds):
            if (isinstance(timing, bool) or not isinstance(timing, (int, float))
                    or not math.isfinite(timing) or timing <= 0):
                raise ValueError('positive finite timing required')
        if not self._run_lock.acquire(False):
            return self._result('WORKER_BUSY')
        self._pending_result = None
        self._lease, self._heartbeat = lease_check, heartbeat
        self._heartbeat_seconds = heartbeat_seconds
        self._deadline = time.monotonic() + timeout_seconds
        self._next_heartbeat = 0
        self._buffer, self._bytes, self._sequence = bytearray(), 0, 0
        self._selector = selectors.DefaultSelector()
        try:
            self._guard()
            factory = self.runner or subprocess.Popen
            self._proc = factory(self.build_argv(), cwd=self.workdir,
                                 env=self.build_env(), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 start_new_session=True, bufsize=0)
            os.set_blocking(self._proc.stdin.fileno(), False)
            self._selector.register(self._proc.stdout, selectors.EVENT_READ)
            self._rpc('initialize', {'clientInfo': {
                'name': 'xuanjun_development_worker', 'title': 'Xuanjun Worker',
                'version': '1.0.0'}})
            self._send({'method': 'initialized', 'params': {}})
            auth = self._rpc('account/read', {'refreshToken': False})
            account = auth.get('account')
            if (not isinstance(account, dict) or account.get('type') != 'chatgpt'
                    or auth.get('requiresOpenaiAuth') is not True):
                raise ProtocolFailure('OAUTH_ROUTE_UNCONFIRMED')
            started = self._rpc('thread/start', {
                'model': self.model, 'modelProvider': 'openai', 'cwd': self.workdir,
                'approvalPolicy': 'never',
                'sandbox': 'readOnly' if self.sandbox == 'read-only' else 'workspaceWrite'})
            thread = started.get('thread', {})
            thread_id = thread.get('id')
            if not isinstance(thread_id, str) or not thread_id:
                raise ProtocolFailure('THREAD_IDENTITY_UNCONFIRMED')
            if (started.get('model') != self.model
                    or started.get('modelProvider') != 'openai'
                    or thread.get('modelProvider') not in (None, 'openai')):
                raise ProtocolFailure('MODEL_EVIDENCE_NOT_VERIFIED')
            initial = self._rpc('turn/start', {
                'threadId': thread_id, 'input': [{'type': 'text', 'text': prompt}],
                'cwd': self.workdir, 'approvalPolicy': 'never', 'model': self.model,
                'sandboxPolicy': self._sandbox_policy()})
            turn = initial.get('turn', {})
            turn_id = turn.get('id')
            if (not isinstance(turn_id, str) or not turn_id
                    or turn.get('status') != 'inProgress'):
                raise ProtocolFailure('TURN_IDENTITY_UNCONFIRMED')
            messages, seen = [], set()
            while True:
                event = self._event()
                if 'id' in event and 'method' not in event:
                    raise ProtocolFailure('UNEXPECTED_RPC_RESULT')
                method, params = self._notification(event)
                if method in ('item/started', 'item/completed', 'turn/completed'):
                    if params.get('threadId') != thread_id:
                        raise ProtocolFailure('THREAD_IDENTITY_UNCONFIRMED')
                    identity = (params.get('turn', {}).get('id') if method == 'turn/completed'
                                else params.get('turnId'))
                    if identity != turn_id:
                        raise ProtocolFailure('TURN_IDENTITY_UNCONFIRMED')
                if method == 'item/completed':
                    item = params.get('item', {})
                    if item.get('type') == 'agentMessage':
                        item_id, text = item.get('id'), item.get('text')
                        if not isinstance(item_id, str) or item_id in seen:
                            raise ProtocolFailure('ITEM_IDENTITY_UNCONFIRMED')
                        seen.add(item_id)
                        if isinstance(text, str) and text.strip():
                            messages.append(text)
                if method == 'turn/completed':
                    final = params['turn']
                    if final.get('status') != 'completed' or final.get('error') is not None:
                        raise ProtocolFailure('TURN_FAILED')
                    if not messages:
                        raise ProtocolFailure('EMPTY_OUTPUT')
                    self._guard()
                    result = self._result('COMPLETED', '\n'.join(messages), True)
                    result.update({'model': self.model, 'provider': 'openai',
                                   'openclaw_model': 'openai/' + self.model,
                                   'model_verified': True, 'auth_type': 'chatgpt',
                                   'model_evidence_source': 'APP_SERVER_THREAD_AND_TURN',
                                   'thread_id': thread_id, 'turn_id': turn_id})
                    return result
        except ProtocolFailure as error:
            return self._result(error.code)
        except (OSError, ValueError, UnicodeError, TypeError, AttributeError):
            return self._result('TRANSPORT_ERROR')
        except Exception:
            return self._result('CALLBACK_ERROR')
        finally:
            stopped = False
            try:
                self._selector.close()
                if self._proc is not None:
                    stopped = self._stop(self._proc)
                    self._proc.stdin.close()
                    self._proc.stdout.close()
                    self._proc = None
            finally:
                if self._pending_result is not None:
                    self._pending_result['worker_boundary_stopped'] = stopped
                self._run_lock.release()
