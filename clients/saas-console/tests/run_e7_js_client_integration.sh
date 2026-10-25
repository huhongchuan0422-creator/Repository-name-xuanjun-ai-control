#!/bin/sh
set -eu
: "${XJ_PR122_E7_ROOT:?Set XJ_PR122_E7_ROOT to the extracted e7 customer-center artifact root}"
exec node tests/e7-js-client-integration.mjs
