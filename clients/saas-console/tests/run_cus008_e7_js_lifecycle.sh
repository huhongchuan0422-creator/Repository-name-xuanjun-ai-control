#!/bin/sh
set -eu
: "${XJ_PR122_E7_ROOT:?Set XJ_PR122_E7_ROOT to the extracted e7 customer-center root}"
exec node tests/cus008-e7-js-lifecycle.mjs
