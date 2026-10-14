"""Fresh PR58 exact-version approval. Old consumed decisions never match.

GitHub account provenance authenticates the repository account used by the
independent reviewer; human/agent independence still requires the review process.
"""
import hashlib,json,re,urllib.request
import math
import os
import selectors
import signal
import subprocess
import time
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
TX='c529c379-9341-4510-8384-fc6be1e412e5'
MARKER='CHATGPT_NATIVE_TASK5_EXACT_EPOCH7_RECOVERY_ACCEPTANCE\n'
DECISION='APPROVED_ONE_EXACT_EPOCH7_RESUME_WITH_FENCED_RETAIN_ON_FAILURE'
CONSUMED=frozenset((6160188919,6161965867,6167552232,6170703284))
SHA=re.compile(r'^[0-9a-f]{64}$')

def need(value,label):
 if not value:raise ValueError(label)
def unique(pairs):
 result={}
 for key,value in pairs:
  need(key not in result,'APPROVAL_DUPLICATE_JSON_KEY');result[key]=value
 return result
def decode(raw):
 return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('APPROVAL_NONFINITE')))
def expected(plan_sha,kit_sha,manifest_sha,snapshot_sha):
 for value in (plan_sha,kit_sha,manifest_sha,snapshot_sha):
  need(isinstance(value,str) and SHA.fullmatch(value),'APPROVAL_HASH_FORMAT')
 return {'schema':1,'reviewer':'CHATGPT_NATIVE_TASK5','decision':DECISION,'transaction_id':TX,
         'recovery_plan_sha256':plan_sha,'recovery_kit_manifest_sha256':kit_sha,
         'runtime_manifest_sha256':manifest_sha,'snapshot_sha256':snapshot_sha,
         'expected_epoch':7,'proposed_prepared_epoch':8,'authorized_attempts':1,
         'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY','legacy_restart':False,
         'historical_notification_replay':False,'production_acceptance':'PENDING'}
def validate(raw,review_id,wanted):
 need(type(review_id) is int and review_id>0 and review_id not in CONSUMED,'APPROVAL_FRESH_ID_REQUIRED')
 need(isinstance(raw,bytes) and len(raw)<=65536,'APPROVAL_RESPONSE_BOUND')
 value=decode(raw.decode('utf-8','strict'))
 need(isinstance(value,dict) and isinstance(value.get('user'),dict),'APPROVAL_RESPONSE_SCHEMA')
 need(type(value.get('id')) is int and value['id']==review_id and
      value.get('user',{}).get('id')==332398908 and
      value.get('user',{}).get('login')=='huhongchuan0422-creator','APPROVAL_AUTHOR')
 need(value.get('issue_url')=='https://api.github.com/repos/'+REPO+'/issues/58','APPROVAL_DESTINATION')
 body=value.get('body');need(isinstance(body,str) and body.startswith(MARKER),'APPROVAL_MARKER')
 parsed=decode(body[len(MARKER):])
 # Canonical JSON distinguishes bool from int, unlike Python dict equality.
 canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
 need(canon(parsed)==canon(wanted),'APPROVAL_EXACT_BINDING')
 return {'review_id':review_id,'body_sha256':hashlib.sha256(body.encode()).hexdigest(),'approval':parsed}
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('APPROVAL_REDIRECT_REFUSED')
# Linux/POSIX production contract: the loader must authenticate this entire
# module, including the inline worker, before using fetch. Never resolve Python
# through PATH, inherit proxy/Python configuration, or import a helper from cwd.
TRUSTED_PYTHON = '/usr/bin/python3'
MAX_RESPONSE_BYTES = 65536
FETCH_TIMEOUT_SECONDS = 20.0
FETCH_CLEANUP_SECONDS = 1.0
_FETCH_WORKER = r"""
import os
import sys
import urllib.request

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('APPROVAL_REDIRECT_REFUSED')

try:
    url = sys.argv[1]
    request = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'xuanjun-exact-epoch7-recovery'})
    # The parent enforces the total deadline, including DNS/TLS and drip reads.
    # This socket timeout is only a secondary bound. No environment proxy is used.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=20) as response:
        if response.geturl() != url or response.getcode() != 200:
            raise ValueError('APPROVAL_RESPONSE_ORIGIN')
        raw = response.read(65537)
    # Send at most limit + 1, so the parent detects rather than truncates oversize.
    while raw:
        count = os.write(1, raw)
        if count <= 0:
            raise ValueError('APPROVAL_WRITE_FAILED')
        raw = raw[count:]
except BaseException:
    # No exception text, credentials, HTTP body, or traceback goes to the parent.
    os._exit(2)
os._exit(0)
"""


def _cleanup_worker(process, deadline):
    """Kill the unreaped worker's session, close the pipe, and bound reaping.

    We do not poll()/wait() before killpg: the unreaped leader pins its PID, so
    cleanup cannot accidentally target a newly reused process-group ID. waitid
    with WNOWAIT below observes exit without releasing that pin. No communicate
    or blocking pipe drain occurs, even when a descendant inherited stdout.
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    finally:
        try:
            process.stdout.close()
        finally:
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise ValueError('APPROVAL_WORKER_CLEANUP_FAILED')


def _run_worker(command, timeout=FETCH_TIMEOUT_SECONDS,
                cleanup_seconds=FETCH_CLEANUP_SECONDS):
    """Bound startup + network + output + exit + cleanup within one budget.

    The final cleanup_seconds is reserved inside timeout, not added to it. This
    bounds normal OS scheduling and interruptible processes, not an indefinitely
    stuck kernel, a stalled filesystem during exec, or suspension of this parent.
    Such OS failures cannot be made a hard real-time guarantee in Python.
    """
    need(type(timeout) in (int, float) and math.isfinite(timeout) and
         type(cleanup_seconds) in (int, float) and math.isfinite(cleanup_seconds) and
         0 < cleanup_seconds < timeout, 'APPROVAL_TIMEOUT_CONTRACT')
    deadline = time.monotonic() + timeout
    need(os.name == 'posix' and all(hasattr(os, name) for name in
         ('waitid', 'P_PID', 'WEXITED', 'WNOHANG', 'WNOWAIT', 'set_blocking')),
         'APPROVAL_WORKER_PLATFORM')
    work_deadline = deadline - cleanup_seconds
    process = None
    selector = None
    raw = bytearray()
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
            close_fds=True, start_new_session=True, cwd='/',
            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
        # The deadline was set before Popen; startup time is charged to it too.
        need(time.monotonic() < work_deadline, 'APPROVAL_FETCH_TIMEOUT')
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        eof = False
        while True:
            remaining = work_deadline - time.monotonic()
            need(remaining > 0, 'APPROVAL_FETCH_TIMEOUT')
            if eof:
                # EOF alone does not prove the worker terminated successfully.
                exited = os.waitid(os.P_PID, process.pid,
                                  os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if exited is not None:
                    break
                time.sleep(min(remaining, 0.01))
                continue
            if not selector.select(remaining):
                continue
            try:
                chunk = os.read(process.stdout.fileno(),
                                min(8192, MAX_RESPONSE_BYTES + 1 - len(raw)))
            except BlockingIOError:
                continue
            if not chunk:
                eof = True
            else:
                raw.extend(chunk)
                need(len(raw) <= MAX_RESPONSE_BYTES, 'APPROVAL_RESPONSE_BOUND')
    finally:
        # Always close/reap, including decoder-independent IO errors and Ctrl-C.
        try:
            if selector is not None:
                selector.close()
        finally:
            if process is not None:
                _cleanup_worker(process, deadline)
    need(time.monotonic() <= deadline, 'APPROVAL_FETCH_TIMEOUT')
    need(process.returncode == 0, 'APPROVAL_FETCH_FAILED')
    return bytes(raw)


def fetch(review_id, wanted):
    need(type(review_id) is int and review_id > 0 and review_id not in CONSUMED,
         'APPROVAL_FRESH_ID_REQUIRED')
    url = 'https://api.github.com/repos/' + REPO + '/issues/comments/' + str(review_id)
    command = [TRUSTED_PYTHON, '-I', '-B', '-S', '-c', _FETCH_WORKER, url]
    raw = _run_worker(command)
    # Authentication/provenance and exact body binding remain in the parent.
    return validate(raw, review_id, wanted)
