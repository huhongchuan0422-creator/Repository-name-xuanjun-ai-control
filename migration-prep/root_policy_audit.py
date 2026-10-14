"""Read-only root audit; emit bounded results, never sudo policy text."""
import hashlib
import json
import os
import re
import stat
import subprocess
import sys

HOSTS = ("iZ6wee8q9z4t03hvqumwfhZ", "iZmj7a5kwr75qc1tul4kf9Z")
HELPER = "/usr/local/sbin/xuanjun-migration-inspect-v1"
EXPECTED = "61bed97a32e970dd868f2d223c68ab41c012c484d314cb714c768629aac263c2"

def protected_path(path, regular=True):
    if not os.path.isabs(path):
        raise ValueError("PATH_NOT_ABSOLUTE")
    current = "/"
    for component in path.split("/")[1:]:
        if not component or component in (".", ".."):
            raise ValueError("INVALID_COMPONENT")
        current = os.path.join(current, component)
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("UNPROTECTED_PATH")
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("INVALID_PARENT")
    if regular and not stat.S_ISREG(info.st_mode):
        raise ValueError("NOT_REGULAR")
    return info

def parsed_sources(text):
    paths = []
    for line in text.splitlines():
        match = re.fullmatch(r"(/[^\r\n]+): parsed OK", line.strip())
        if not match:
            raise ValueError("UNRECOGNIZED_VISUDO_OUTPUT")
        paths.append(match.group(1))
    if "/etc/sudoers" not in paths or len(paths) != len(set(paths)):
        raise ValueError("INCOMPLETE_SOURCE_LIST")
    return paths

def effective_policy(text):
    # Only accept the exact fixed no-argument root grant; no broad privileges.
    grants = [line.strip() for line in text.splitlines()
              if line.lstrip().startswith("(")]
    normalized = [line.replace('\\\"', '"') for line in grants]
    expected = '(root) NOPASSWD: ' + HELPER + ' ""'
    if normalized != [expected]:
        raise ValueError("UNEXPECTED_RUNNER_GRANTS")
    if not re.search(r"(?<![!\w])env_reset(?:[,\s]|$)", text):
        raise ValueError("ENV_RESET_NOT_PROVEN")
    if re.search(r"(?:^|[,\s])!?SETENV(?=[:\s,]|$)", text):
        raise ValueError("ENV_OVERRIDE_NOT_PROVEN_SAFE")
    if re.search(r"\b(?:BASH_ENV|ENV|SHELLOPTS|BASHOPTS|LD_PRELOAD|LD_LIBRARY_PATH)\b", text):
        raise ValueError("DANGEROUS_ENV_RULE")
    return "FIXED_HELPER_ONLY"

def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, timeout=20,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    if result.returncode:
        raise ValueError("COMMAND_FAILED")
    return result.stdout + result.stderr

def main():
    try:
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise ValueError("ROOT_ZERO_ARGUMENTS_REQUIRED")
        host = run(["/usr/bin/hostname", "-s"]).strip()
        if host not in HOSTS:
            raise ValueError("HOST_MISMATCH")
        paths = parsed_sources(run(["/usr/sbin/visudo", "-c"]))
        before = {}
        for path in paths:
            protected_path(path)
            with open(path, "rb") as stream:
                before[path] = hashlib.sha256(stream.read()).hexdigest()
        protected_path(HELPER)
        with open(HELPER, "rb") as stream:
            if hashlib.sha256(stream.read()).hexdigest() != EXPECTED:
                raise ValueError("HELPER_HASH_MISMATCH")
        grant = effective_policy(run(["/usr/bin/sudo", "-n", "-l", "-U", "githubrunner"]))
        for path, digest in before.items():
            protected_path(path)
            with open(path, "rb") as stream:
                if hashlib.sha256(stream.read()).hexdigest() != digest:
                    raise ValueError("POLICY_CHANGED_DURING_AUDIT")
        print(json.dumps({"host": host, "sudoers_sources_checked": len(paths),
                          "source_integrity": "PASS", "effective_runner_grant": grant,
                          "helper_hash": EXPECTED, "production_mutation": False,
                          "global_runner_policy": "NOT_VERIFIED",
                          "full_sudoers_semantic_audit": "NOT_VERIFIED"}, sort_keys=True))
    except Exception as error:
        # Exception text could carry source content; only emit its type.
        print(json.dumps({"audit": "HOLD", "error_type": type(error).__name__,
                          "production_mutation": False}))
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
