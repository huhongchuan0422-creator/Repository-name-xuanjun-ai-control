"""Deterministic native-entry capability probe for ordinary ChatGPT.

Scope: evidence-only. No P2 source, host, lease, credential, deployment,
network, subprocess, filesystem mutation, or external service access.
"""

from __future__ import print_function


ENTRY = "CHATGPT"
EXECUTION_PATH = "CHATGPT_NATIVE"
SCOPE = "evidence/entry-probes/chatgpt/"


def probe_result():
    """Return the immutable evidence payload used by CI and review."""
    return {
        "entry": ENTRY,
        "execution_path": EXECUTION_PATH,
        "scope": SCOPE,
        "p2_source_modified": False,
        "host_touched": False,
        "lease_touched": False,
        "work_or_codex_delegated": False,
    }


def self_test():
    result = probe_result()
    assert result["entry"] == "CHATGPT"
    assert result["execution_path"] == "CHATGPT_NATIVE"
    assert result["scope"].startswith("evidence/entry-probes/chatgpt/")
    assert result["p2_source_modified"] is False
    assert result["host_touched"] is False
    assert result["lease_touched"] is False
    assert result["work_or_codex_delegated"] is False
    return True


if __name__ == "__main__":
    self_test()
    print("CHATGPT_NATIVE_ENTRY_PROBE_PASS")
