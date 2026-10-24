#!/bin/sh
set -eu
: "${XJ_PR122_E7_ROOT:?Set XJ_PR122_E7_ROOT to the extracted e7 customer-center artifact root}"
exec python3 clients/saas-console/tests/real_python_backend_integration.py
