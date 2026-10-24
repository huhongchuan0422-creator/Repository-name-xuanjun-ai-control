#!/bin/sh
set -eu
: "${XJ_PR122_BACKEND_ROOT:?Set XJ_PR122_BACKEND_ROOT to a local checkout of 1b48e5fe8015afd9035ff269f9b432d9a68223b2}"
exec python3 clients/saas-console/tests/real_python_backend_integration.py
