# Epoch7 access repair preparation

Status: LOCAL_TESTED_PREPARATION_ONLY. Production remains HOLD; approval 6170703284 is consumed. This is a source checkpoint, not a review request or an install package.

These two Python 3.6-compatible files implement and test a pure ACL delta planner. It never changes permissions, starts processes, or accesses a production host. It allows only the proposed ancestor traversal and exact binding-file read purposes, preserves the existing mask and unrelated entries, and rejects ambiguous/default ACLs and malformed IDs.

Local Python 3.6.8: 15 tests passed. Actual UK ACL application, systemd access, full recovery integration and independent review remain NOT_VERIFIED. The caller must still authenticate exact path/inode/owner/mode, fresh state and a new precise approval before applying any future permission delta. No apply function is included.

Run from this directory: python3 -B -m unittest test_exact_access_plan -v

Frozen epoch5 v4 source, package, manifest and production entrypoint are unchanged. Other epoch7 repairs are still being integrated and will be submitted together for independent review.
