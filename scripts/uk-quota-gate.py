#!/usr/bin/env python3
"""CLI wrapper for the inference-free quota admission policy."""
from __future__ import print_function
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE1 = os.path.join(ROOT, 'stage1')
if STAGE1 not in sys.path:
    sys.path.insert(0, STAGE1)

from uk_quota_policy import main  # noqa: E402


if __name__ == '__main__':
    sys.exit(main())
