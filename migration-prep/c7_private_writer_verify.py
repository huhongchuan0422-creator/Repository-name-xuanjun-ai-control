"""Redacted CLI for owner-controlled private Writer evidence bytes."""
from __future__ import print_function

import json
import os
import sys

from c7_acceptance import load_private_writer_evidence


def main():
    if len(sys.argv) != 3:
        print(json.dumps({"status": "HOLD", "error": "EXACT_PRIVATE_AND_PUBLIC_PATHS_REQUIRED",
                          "production_mutation": False}, sort_keys=True))
        return 2
    try:
        value = load_private_writer_evidence(sys.argv[1], sys.argv[2], os.getuid())
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except BaseException as error:
        print(json.dumps({"status": "HOLD", "error_type": type(error).__name__,
                          "production_mutation": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
