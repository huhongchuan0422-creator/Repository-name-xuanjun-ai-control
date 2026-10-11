"""Bounded, non-interactive Codex CLI worker (Python 3.6+).

Authentication is provisioned externally with official `codex login` in the
explicit dedicated HOME/CODEX_HOME. This module never reads credential files.
Raw CLI diagnostics and prompts are never returned or logged. Completion is a
transport result, not acceptance of generated code or permission to deploy it.
"""
import json
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time

MODEL = 'gpt-5.6-sol'
OPENCLAW_MODEL = 'openai/gpt-5.6-sol'
ALLOWED_MODELS = ('gpt-5.6-sol',)
MAX_STREAM_BYTES = 2 * 1024 * 1024
MAX_PROMPT_BYTES = 256 * 1024


def redact(text):
    """Defense in depth for final agent text; do not log raw event streams."""
    text = re.sub(r'(?i)(bearer\s+)[^\s"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{8,}\b', '[REDACTED]', text)
    text = re.sub(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{8,}\b',
                  '[REDACTED]', text)
    text = re.sub(r'(?<!\d)\d{5,15}:[A-Za-z0-9_-]{20,}',
                  '[REDACTED]', text)
    # Include JSON quoted keys and escaped quoted values. Preserve value quotes
    # so that redacting a JSON final message does not corrupt its structure.
    assignments = re.compile(
        r"(?i)((?:[\"'])?(?:api[ _-]?key|access[ _-]?token|"
        r"refresh[ _-]?token|secret|password|bot[ _-]?token|"
        r"telegram[ _-]?(?:bot[ _-]?)?token|github[ _-]?token)"
        r"(?:[\"'])?\s*[=:]\s*)"
        r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;}]+)")

    def replace_assignment(match):
        value = match.group(2)
        quote = value[0] if value[0] in ('"', "'") else ''
        return match.group(1) + quote + '[REDACTED]' + quote

    return assignments.sub(replace_assignment, text)


class CodexWorker(object):
    def __init__(self, codex_bin, workdir, home, codex_home, path,
                 sandbox='read-only', runner=None, model=MODEL):
        for value in (codex_bin, workdir, home, codex_home):
            if not isinstance(value, str) or not os.path.isabs(value):
                raise ValueError('explicit absolute paths required')
        if not isinstance(path, str) or not path or any(
                not os.path.isabs(p) for p in path.split(os.pathsep)):
            raise ValueError('explicit absolute PATH entries required')
        if sandbox not in ('read-only', 'workspace-write'):
            raise ValueError('unsupported sandbox')
        if model not in ALLOWED_MODELS:
            raise ValueError('model outside Owner allowlist')
        self.codex_bin, self.workdir = codex_bin, workdir
        self.home, self.codex_home, self.path = home, codex_home, path
        self.sandbox, self.runner = sandbox, runner
        self.model = model

    def build_argv(self):
        return [self.codex_bin, '-c', 'model_provider="openai"',
                '-c', 'approval_policy="never"', 'exec', '--json',
                '--model', self.model, '--sandbox', self.sandbox,
                '--cd', self.workdir, '-']

    def build_env(self):
        # Deliberately do not copy os.environ, API keys, proxies or production
        # variables. HOME and CODEX_HOME must belong to the dedicated worker.
        return {'PATH': self.path, 'HOME': self.home,
                'CODEX_HOME': self.codex_home, 'LANG': 'C.UTF-8'}

    def _result(self, status, output='', completed=False, exit_code=None):
        simulated = self.runner is not None
        return {'status': status, 'output': redact(output),
                'turn_completed': completed, 'exit_code': exit_code,
                'requested_model': self.model,
                'requested_openclaw_model': 'openai/' + self.model,
                # CLI selection is not authoritative returned-model evidence.
                # Agent text must never be parsed as provider attestation.
                'model': 'UNKNOWN', 'provider': 'UNKNOWN',
                'model_verified': False, 'openclaw_model': 'UNKNOWN',
                'simulated': simulated,
                'real_execution': not simulated and status == 'COMPLETED',
                'production_pass': False}

    @staticmethod
    def _stop(proc):
        # The session created by Popen includes descendants. Always reap the
        # direct process, including if it exited before group termination.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()

    def run(self, prompt, timeout_seconds=900, heartbeat=None,
            lease_check=None, heartbeat_seconds=5):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('nonempty prompt required')
        encoded = prompt.encode('utf-8')
        if len(encoded) > MAX_PROMPT_BYTES:
            raise ValueError('prompt too large')
        if timeout_seconds <= 0 or heartbeat_seconds <= 0:
            raise ValueError('positive timing required')
        proc = None
        selector = selectors.DefaultSelector()
        try:
            if lease_check is not None and not lease_check():
                return self._result('LEASE_LOST')
            with tempfile.TemporaryFile() as source:
                source.write(encoded)
                source.seek(0)
                factory = self.runner or subprocess.Popen
                proc = factory(self.build_argv(), cwd=self.workdir,
                               env=self.build_env(), stdin=source,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               start_new_session=True)
                selector.register(proc.stdout, selectors.EVENT_READ)
                started = time.monotonic()
                next_heartbeat = started
                stream = bytearray()
                eof = False
                while True:
                    now = time.monotonic()
                    if now - started >= timeout_seconds:
                        self._stop(proc)
                        return self._result('TIMEOUT')
                    if lease_check is not None and not lease_check():
                        self._stop(proc)
                        return self._result('LEASE_LOST')
                    if heartbeat is not None and now >= next_heartbeat:
                        heartbeat()
                        next_heartbeat = now + heartbeat_seconds
                    events = selector.select(timeout=min(0.2, timeout_seconds))
                    if events:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk:
                            eof = True
                            selector.unregister(proc.stdout)
                        stream.extend(chunk)
                        if len(stream) > MAX_STREAM_BYTES:
                            self._stop(proc)
                            return self._result('OUTPUT_LIMIT')
                    if eof and proc.poll() is not None:
                        break
                remaining = timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    self._stop(proc)
                    return self._result('TIMEOUT')
                try:
                    code = proc.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    self._stop(proc)
                    return self._result('TIMEOUT')
                if lease_check is not None and not lease_check():
                    self._stop(proc)
                    return self._result('LEASE_LOST')
                # End the job boundary for any descendants left behind.
                self._stop(proc)
                return self._parse(stream, code)
        except (OSError, ValueError, UnicodeError):
            if proc is not None:
                self._stop(proc)
            return self._result('CLI_ERROR')
        except Exception:
            # Callback exceptions fail closed. Exception text may include
            # secrets; it must never become a result/log message.
            if proc is not None:
                self._stop(proc)
            return self._result('CALLBACK_ERROR')
        finally:
            selector.close()
            if proc is not None and proc.stdout is not None:
                proc.stdout.close()

    def _parse(self, stream, code):
        completed, failed, messages = False, False, []
        try:
            lines = bytes(stream).decode('utf-8').splitlines()
            for line in lines:
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError('invalid event')
                kind = event.get('type')
                if kind == 'turn.completed':
                    completed = True
                elif kind in ('turn.failed', 'error'):
                    failed = True
                elif kind == 'item.completed':
                    item = event.get('item')
                    if isinstance(item, dict) and item.get('type') == 'agent_message':
                        message = item.get('text')
                        if isinstance(message, str) and message.strip():
                            messages.append(message)
        except (ValueError, UnicodeError):
            return self._result('INVALID_JSON', exit_code=code)
        if code != 0 or failed:
            return self._result('FAILED', exit_code=code)
        if not completed:
            return self._result('INCOMPLETE', exit_code=code)
        if not messages:
            return self._result('EMPTY_OUTPUT', completed=True, exit_code=code)
        return self._result('COMPLETED', '\n'.join(messages), True, code)
