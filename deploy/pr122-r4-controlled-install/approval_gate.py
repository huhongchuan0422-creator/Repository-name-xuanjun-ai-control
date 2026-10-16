"""I1 admission: Owner-pinned independent receipt + canonical GitHub facts.

GitHub developer/reviewer share an account/App. Provenance alone cannot prove
independence: a separate Owner-root pin of the independently received body hash
is mandatory. This module never creates that trust anchor or an approval.
"""
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import time
import urllib.request

REPO = "huhongchuan0422-creator/Repository-name-xuanjun-ai-control"
HOST = "iZ6wee8q9z4t03hvqumwfhZ"
AUTHOR_ID = 332398908
APP_ID = 1144995
INSTALLER_PATH = "deploy/pr122-r4-controlled-install/controlled_install.py"
BINDING_PATH = "deploy/pr122-r4-controlled-install/REVIEW_BINDING.json"
SOURCE_SHA = "d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0"
CANDIDATE_SHA = "57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1"
HELPER_SHA = "0e61a4cab72a18e94ed8b97c81e035ee023dfe0969c871c50651cf75792cbcbe"
BEGIN = "<!-- PR122_R4_ACTION_APPROVAL_V1\n"
END = "\nPR122_R4_ACTION_APPROVAL_V1 -->"
EFFECTS = {
    "install": ["backup_single_source", "write_single_source", "restart_portal_once", "empty_negative_post_4"],
    "rollback-offline": ["stop_portal", "restore_single_source_offline", "keep_portal_stopped"],
}
_SEAL = object()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("NONFINITE_JSON")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def root_file(path, mode, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != mode):
            raise ValueError("ROOT_ADMISSION_FILE_IDENTITY")
        data = handle.read(limit + 1)
        if len(data) > limit:
            raise ValueError("ADMISSION_SIZE_LIMIT")
        return data


def root_parent(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("ROOT_ADMISSION_PARENT_IDENTITY")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("GITHUB_REDIRECT_REJECTED")


def github_json(path):
    if not path.startswith("/repos/" + REPO + "/") or ".." in path:
        raise ValueError("CANONICAL_GITHUB_PATH_REQUIRED")
    url = "https://api.github.com" + path
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "PR122-R4-Admission-V1", "Accept": "application/vnd.github+json"})
    with opener.open(request, timeout=10) as response:
        if response.geturl() != url or response.status != 200:
            raise ValueError("CANONICAL_GITHUB_RESPONSE_REQUIRED")
        data = response.read(262145)
    if len(data) > 262144:
        raise ValueError("GITHUB_RESPONSE_SIZE_LIMIT")
    return strict_json(data)


def integer(value, minimum=1):
    return type(value) is int and value >= minimum


class Gate:
    def __init__(self, action, self_path, *, anchor=None, registry=None,
                 fetch=github_json, clock=time.time):
        if action not in EFFECTS:
            raise ValueError("UNREGISTERED_ACTION")
        self.action, self.self_path = action, Path(self_path)
        self.anchor = Path(anchor) if anchor else Path("/etc/xuanjun-pr122-release/" + action + "-admission.json")
        self.registry = Path(registry) if registry else Path("/var/lib/xuanjun-pr122-authorizations")
        self.fetch, self.clock = fetch, clock

    def get(self, suffix):
        if self.clock() - self.started > 60:
            raise ValueError("APPROVAL_VALIDATION_DEADLINE")
        return self.fetch("/repos/" + REPO + suffix)

    def validate(self):
        self.started = self.clock()
        if os.geteuid() != 0 or os.uname().nodename != HOST:
            raise ValueError("ROOT_ON_APPROVED_HOST_REQUIRED")
        root_parent(self.anchor.parent)
        anchor_data = root_file(self.anchor, 0o600, 16384)
        pin = strict_json(anchor_data)
        expected_pin_keys = {"schema_version", "action", "approval_comment_id", "approval_body_sha256", "owner_attests_independent_review", "owner_confirms_backend_outage"}
        if (set(pin) != expected_pin_keys or type(pin["schema_version"]) is not int or pin["schema_version"] != 1
                or pin["action"] != self.action or pin["owner_attests_independent_review"] is not True
                or pin["owner_confirms_backend_outage"] is not (self.action == "rollback-offline")
                or not integer(pin["approval_comment_id"])
                or not re.fullmatch(r"[0-9a-f]{64}", str(pin["approval_body_sha256"]))):
            raise ValueError("OWNER_PIN_REQUIRED")
        identifier = pin["approval_comment_id"]
        marker = self.registry / ("approval-" + str(identifier) + ".consumed.json")
        if os.path.lexists(marker):
            raise ValueError("APPROVAL_ALREADY_CONSUMED")
        comment = self.get("/issues/comments/" + str(identifier))
        if (comment.get("id") != identifier
                or comment.get("issue_url") != "https://api.github.com/repos/" + REPO + "/issues/122"
                or comment.get("user", {}).get("id") != AUTHOR_ID
                or (comment.get("performed_via_github_app") or {}).get("id") != APP_ID):
            raise ValueError("APPROVAL_PROVENANCE_MISMATCH")
        body = comment.get("body", "")
        if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != pin["approval_body_sha256"]:
            raise ValueError("PINNED_APPROVAL_BODY_MISMATCH")
        if body.count(BEGIN) != 1 or body.count(END) != 1:
            raise ValueError("EXPLICIT_ACTION_APPROVAL_REQUIRED")
        value = strict_json(body.split(BEGIN)[1].split(END)[0])
        keys = {"schema_version", "kind", "decision", "reviewer_role", "repository", "pr_number", "host", "action", "max_attempts", "source_commit", "source_tree", "installer_sha256", "binding_sha256", "artifact_id", "artifact_zip_sha256", "artifact_tar_sha256", "expected_source_sha256", "result_source_sha256", "helper_sha256", "allowed_effects", "negative_post_requests_max", "issued_at", "expires_at", "approval_nonce"}
        if (set(value) != keys or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["kind"] != "PR122_R4_ACTION_APPROVAL"
                or value["decision"] != "APPROVED_EXACT_ONE_ATTEMPT"
                or value["reviewer_role"] != "INDEPENDENT_AUDITOR"
                or value["repository"] != REPO or value["pr_number"] != 122
                or value["host"] != HOST or value["action"] != self.action
                or type(value["max_attempts"]) is not int or value["max_attempts"] != 1
                or value["allowed_effects"] != EFFECTS[self.action]
                or type(value["negative_post_requests_max"]) is not int
                or value["negative_post_requests_max"] != (4 if self.action == "install" else 0)):
            raise ValueError("EXACT_APPROVAL_SCOPE_REQUIRED")
        for key in ("source_commit", "source_tree"):
            if not re.fullmatch(r"[0-9a-f]{40}", str(value[key])):
                raise ValueError("APPROVAL_COMMIT_TREE_FORMAT")
        for key in ("installer_sha256", "binding_sha256", "artifact_zip_sha256", "artifact_tar_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(value[key])):
                raise ValueError("APPROVAL_DIGEST_FORMAT")
        old, new = (SOURCE_SHA, CANDIDATE_SHA) if self.action == "install" else (CANDIDATE_SHA, SOURCE_SHA)
        if (value["expected_source_sha256"] != old or value["result_source_sha256"] != new
                or value["helper_sha256"] != HELPER_SHA
                or not re.fullmatch(r"[0-9a-f]{32}", str(value["approval_nonce"]))):
            raise ValueError("SOURCE_OR_ACTION_BINDING_MISMATCH")
        now = self.clock()
        created = datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00")).timestamp()
        if (not integer(value["issued_at"], 0) or not integer(value["expires_at"], 0)
                or abs(value["issued_at"] - created) > 60 or now < value["issued_at"]
                or now >= value["expires_at"] or not 0 < value["expires_at"] - value["issued_at"] <= 86400):
            raise ValueError("APPROVAL_EXPIRED_OR_NOT_CURRENT")
        own = root_file(self.self_path, 0o400, 200000)
        if hashlib.sha256(own).hexdigest() != value["installer_sha256"]:
            raise ValueError("INSTALLER_HASH_NOT_APPROVED")
        commit = self.get("/git/commits/" + value["source_commit"])
        if commit.get("sha") != value["source_commit"] or commit.get("tree", {}).get("sha") != value["source_tree"]:
            raise ValueError("APPROVED_COMMIT_TREE_MISMATCH")
        def content(path):
            entry = self.get("/contents/" + path + "?ref=" + value["source_commit"])
            if entry.get("type") != "file" or entry.get("path") != path or entry.get("encoding") != "base64":
                raise ValueError("APPROVED_FILE_BINDING_MISMATCH")
            return base64.b64decode("".join(entry["content"].split()), validate=True)
        if content(INSTALLER_PATH) != own:
            raise ValueError("INSTALLER_COMMIT_BYTES_MISMATCH")
        binding_data = content(BINDING_PATH)
        binding = strict_json(binding_data)
        if (hashlib.sha256(binding_data).hexdigest() != value["binding_sha256"]
                or binding.get("files", {}).get(INSTALLER_PATH) != value["installer_sha256"]):
            raise ValueError("APPROVAL_MANIFEST_MISMATCH")
        if not integer(value["artifact_id"]):
            raise ValueError("APPROVAL_ARTIFACT_ID")
        artifact = self.get("/actions/artifacts/" + str(value["artifact_id"]))
        run = artifact.get("workflow_run", {})
        if (artifact.get("id") != value["artifact_id"] or artifact.get("expired") is not False
                or artifact.get("digest") != "sha256:" + value["artifact_zip_sha256"]
                or run.get("head_sha") != value["source_commit"]
                or run.get("repository_id") != 1413132159 or run.get("head_repository_id") != 1413132159):
            raise ValueError("APPROVED_ARTIFACT_MISMATCH")
        if self.clock() >= value["expires_at"] or self.clock() - self.started > 30:
            raise ValueError("APPROVAL_VALIDATION_NOT_CURRENT")
        # TAR bytes are independently reviewed and pinned by the exact Owner body
        # hash. Anonymous GitHub metadata verifies the actual ZIP digest/run; do
        # not claim this runtime downloads/rehashes an authenticated artifact.
        proof = dict(value, approval_comment_id=identifier,
            approval_body_sha256=pin["approval_body_sha256"],
            trust_boundary="OWNER_ROOT_PIN_SHARED_GITHUB_IDENTITY_NOT_CRYPTOGRAPHIC_REVIEWER_SEPARATION")
        return VerifiedTicket(_SEAL, self, proof, hashlib.sha256(anchor_data).hexdigest(), marker, self.started)


class VerifiedTicket:
    def __init__(self, seal, gate, proof, anchor_hash, marker, validated_at):
        if seal is not _SEAL:
            raise ValueError("UNVERIFIED_APPROVAL_TICKET")
        self._seal, self._gate, self._proof = seal, gate, json.dumps(proof, sort_keys=True)
        self._anchor_hash, self._marker, self._validated_at = anchor_hash, marker, validated_at
        self._consumed = False

    def snapshot(self):
        return strict_json(self._proof)

    def check(self, action):
        proof = self.snapshot()
        now = self._gate.clock()
        if (self._consumed or os.path.lexists(self._marker) or proof["action"] != action
                or now >= proof["expires_at"] or not 0 <= now - self._validated_at <= 30):
            raise ValueError("APPROVAL_TICKET_NOT_CURRENT_OR_CONSUMED")
        current = root_file(self._gate.anchor, 0o600, 16384)
        if hashlib.sha256(current).hexdigest() != self._anchor_hash:
            raise ValueError("OWNER_PIN_CHANGED")
        if hashlib.sha256(root_file(self._gate.self_path, 0o400, 200000)).hexdigest() != proof["installer_sha256"]:
            raise ValueError("INSTALLER_DRIFT_AFTER_APPROVAL")
        comment = self._gate.get("/issues/comments/" + str(proof["approval_comment_id"]))
        body = comment.get("body", "")
        if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != proof["approval_body_sha256"]:
            raise ValueError("APPROVAL_CHANGED_BEFORE_CONSUMPTION")
        if self._gate.clock() >= proof["expires_at"] or self._gate.clock() - self._validated_at > 30:
            raise ValueError("APPROVAL_EXPIRED_BEFORE_CONSUMPTION")

    def consume(self):
        self.check(self.snapshot()["action"])
        directory = self._gate.registry
        if not os.path.lexists(directory):
            directory.mkdir(mode=0o700)
        root_parent(directory)
        fd = os.open(self._marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self._consumed = True
        with os.fdopen(fd, "wb") as handle:
            handle.write((self._proof + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        for path in (directory, directory.parent):
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def require_ticket(ticket, action):
    if type(ticket) is not VerifiedTicket or ticket._seal is not _SEAL:
        raise ValueError("EXACT_INDEPENDENT_APPROVAL_REQUIRED")
    ticket.check(action)
    return ticket
