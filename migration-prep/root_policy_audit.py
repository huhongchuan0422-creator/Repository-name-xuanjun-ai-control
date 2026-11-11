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

def protected_digest(path, owner_uid=0):
    """Walk pinned directory descriptors; never follow a replaced symlink."""
    components = path.split("/")[1:]
    if not path.startswith("/") or not components or any(x in ("", ".", "..") for x in components):
        raise ValueError("INVALID_PATH")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, component in enumerate(components):
            parent = os.fstat(directory)
            if parent.st_uid != owner_uid or parent.st_mode & 0o022:
                raise ValueError("UNPROTECTED_PARENT")
            last = index == len(components) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if not last:
                flags |= os.O_DIRECTORY
            opened = os.open(component, flags, dir_fd=directory)
            if not last:
                os.close(directory)
                directory = opened
                continue
            try:
                before = os.fstat(opened)
                if not stat.S_ISREG(before.st_mode) or before.st_uid != owner_uid or before.st_mode & 0o022:
                    raise ValueError("UNPROTECTED_FILE")
                digest = hashlib.sha256()
                while True:
                    block = os.read(opened, 65536)
                    if not block:
                        break
                    digest.update(block)
                after = os.fstat(opened)
                identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns, x.st_uid, x.st_mode)
                if identity(before) != identity(after):
                    raise ValueError("FILE_CHANGED_DURING_READ")
                return digest.hexdigest()
            finally:
                os.close(opened)
    finally:
        os.close(directory)

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
            before[path] = protected_digest(path)
        if protected_digest(HELPER) != EXPECTED:
            raise ValueError("HELPER_HASH_MISMATCH")
        grant = effective_policy(run(["/usr/bin/sudo", "-n", "-l", "-U", "githubrunner"]))
        for path, digest in before.items():
            if protected_digest(path) != digest:
                raise ValueError("POLICY_CHANGED_DURING_AUDIT")
        print(json.dumps({"host": host, "sudoers_sources_checked": len(paths),
                          "observed_source_integrity": "PASS", "grant_shape_check": grant,
                          "source_closure": "NOT_VERIFIED", "effective_policy_semantics": "NOT_VERIFIED",
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
