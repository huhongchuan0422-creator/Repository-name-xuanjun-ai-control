"""Read-only supplement for the 17 exact dracut links in the frozen Root receipt.

This does not alter the collector allowlist.  It binds the original failed
subject hashes to target bytes, parent permissions and RPM ownership so an
auditor can decide the precise exception without trusting arbitrary links.
"""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys


EXPECTED_SUBJECTS = frozenset((
    "04039393f881d30c7c95d5e133e09ff6376a477d08212caf4414bd5c267e0d9a",
    "11e3784000ac863863ecc9ba9738fe6d9b7b2a250316af1a25b86519dc65040d",
    "2128077c18c39c5803b5dcb54a730cffb7add68fc991c2bc590d2f00dfdde31f",
    "2670e60322b3681c694edc7918f65407921a9f5e73d346dddae67de1036c62ef",
    "2ae0c8f56729ee967096ee6f31d8380ed219696e8e03baa8dcc7873407ad2523",
    "3ed5b395193305e171bb3018db8d46909cece33c09b889fa46770969edda5255",
    "45419098b87bf448f8eff050fb205b503f25bdfb2911cac7f89c36f5f2f2f24b",
    "7f811c767dd0dce063c54b64bbc091eb719a3a6a7b7ab3c1729b76934a0ddbea",
    "878209d9639a2679cf77433bd25747cd7091366df8f54b9d9116f9ae016ee833",
    "99bdae100b1779151afb2da24978e1c78ef6c2cb173876f4584cac59776ee49c",
    "b21b92e000bff3328d1249c5dab0c500607be05003aa17e8d05747b84f9e1e19",
    "b28eafe6a6f0e05bbd61d2f3c5281323c9f3e0f8ccddf162fe93209e5c63bc5d",
    "c5c89f886e210b092aab5a5e030709fb686954752524272994ea44c30535a1fd",
    "dd543ccb2640ff9f0a924bda916fd4dffd0210ad682f8e620e9f1d13f0a282b4",
    "dfa65f67437f3e7bee5b07eedfa1cc9266f69df5f2ff35befa8d0f05e2a50d52",
    "f55130f1a067fce0642185d390d88165700f9e472488b342542229285b27c209",
    "fd92ad59b638f1ff9f9e9935ea6e3ee09539cd473dd6cf4a432e2ecf8c474523",
))
TARGET_ROOT = "/usr/lib/dracut/modules.d/98dracut-systemd"
SEARCH_ROOTS = ("/etc/systemd/system", "/usr/lib/systemd/system")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _identity(path, follow=True):
    value = os.stat(path) if follow else os.lstat(path)
    return {
        "uid": value.st_uid,
        "gid": value.st_gid,
        "mode": stat.S_IMODE(value.st_mode),
        "size": value.st_size,
        "mtime_ns": getattr(value, "st_mtime_ns", int(value.st_mtime * 1000000000)),
    }


def _parents(path):
    rows = []
    current = os.path.dirname(path)
    while current.startswith("/usr/lib/dracut"):
        rows.append({"path": current, "identity": _identity(current)})
        if current == "/usr/lib/dracut":
            break
        current = os.path.dirname(current)
    return rows


def _rpm_source(path):
    result = subprocess.run(
        ["/usr/bin/rpm", "-qf", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{ARCH}\n", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout.decode("utf-8", "replace").strip(),
        "stderr": result.stderr.decode("utf-8", "replace").strip(),
    }


def collect(host):
    rows = []
    for root in SEARCH_ROOTS:
        for base, directories, files in os.walk(root, followlinks=False):
            for name in directories + files:
                path = os.path.join(base, name)
                if not os.path.islink(path):
                    continue
                target = os.path.realpath(path)
                if target != TARGET_ROOT and not target.startswith(TARGET_ROOT + os.sep):
                    continue
                raw = open(target, "rb").read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = None
                rows.append({
                    "subject_sha256": _sha(path.encode("utf-8")),
                    "link_path": path,
                    "link_text": os.readlink(path),
                    "link_identity": _identity(path, follow=False),
                    "resolved_target": target,
                    "target_identity": _identity(target),
                    "target_content_sha256": _sha(raw),
                    "target_content_utf8": text,
                    "target_parent_chain": _parents(target),
                    "target_package": _rpm_source(target),
                })
    rows.sort(key=lambda item: item["link_path"])
    observed = frozenset(item["subject_sha256"] for item in rows)
    blockers = []
    if len(rows) != 17:
        blockers.append("EXACT_LINK_COUNT_MISMATCH")
    if observed != EXPECTED_SUBJECTS:
        blockers.append("ORIGINAL_FAILED_SUBJECT_SET_MISMATCH")
    if any(item["target_package"]["exit_code"] != 0 for item in rows):
        blockers.append("PACKAGE_SOURCE_UNVERIFIED")
    return {
        "schema_version": 1,
        "host": host,
        "collector_original_status": "HOLD_INCOMPLETE",
        "collector_original_exit": 2,
        "original_link_failure_count": 17,
        "walk_complete_diagnostic": {
            "classification": "ROOT_WALK_FINISHED_BUT_ENTRY_VALIDATION_INCOMPLETE",
            "collector_behavior": "failed_items includes root outcome WALK_COMPLETE when root status is HOLD_INCOMPLETE",
            "host_failure": False,
            "collector_pass_changed": False,
        },
        "links": rows,
        "blockers": blockers,
        "status": "SUPPLEMENT_COMPLETE_ORIGINAL_HOLD_RETAINED" if not blockers else "HOLD_INCOMPLETE",
        "production_mutation": False,
        "allowlist_widened": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    args = parser.parse_args(argv)
    value = collect(args.host)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if not value["blockers"] else 2


if __name__ == "__main__":
    sys.exit(main())
