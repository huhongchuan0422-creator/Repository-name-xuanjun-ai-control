# V2.7 node 1.14 offline evaluation baseline

Contract: PR17 comment6135609509, Owner2026-10-13 request to advance one
unassigned independent node. Dots owns these five source/test/document paths.
The existing canonical parent remains
XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1. No new task queue/database,
P2/shared source, host, credential, model provider or runtime admission is added.

## What this implements

A deterministic reader for a fixed versioned structured-output evaluation suite
and already-produced receipts. Eight baseline cases cover missing evidence,
source-versus-UK distinctions, denied delegated-model routes, unauthorized
writes, human-gate continuation, unknown-effect replay, missing receiver ACK and
secret exposure refusal. Each case has an exact expected JSON object.

This is the evidence-checking foundation of node1.14, NOT a model-quality test.
There are no prompts, inference calls, paid APIs, child agents or subprocess
launches in the evaluator. Unit tests synthesize fixture outputs; they do not
prove a model actually answered correctly. Free-text reasoning quality, useful
Chinese responses, factual correctness and adversarial semantic robustness
require separately authorized real outputs and independent review later.

Existing plans/V27_OWNER_OPERATIONS_PRIORITY_20261010.md retain node1.14 and
1.15 runtime dependency gates. Issue18 local embedding remains blocked by loop
acceptance. Neither starts from this source-only delivery.

## Interface and identity

scripts/ai_eval_receipt_gate.py accepts --suite, --receipt and
--expected-binding JSON file paths. It reads bounded regular files without
following symlinks, writes only its result to stdout and never opens the
canonical operational database. Supports Python3.6.8 and standard library only.

Suite schema: xuanjun.ai_eval.suite.v1, suite_id, integer version and1..256 cases.
Each case has unique id, category, integer weight1..100 and expected JSON object.
The current fixtures/ai_eval/v1.json canonical SHA256 is
5dc1552bb89e9fc367b7b317d42da5873a4ede5c0a13a6b1265a800880e3d90a.
Changes require a new reviewed baseline fingerprint; never silently reuse the
old receipt against edited expected answers.

Receipt schema: xuanjun.ai_eval.receipt.v1, suite_sha256, binding and cases.
Each case has case_id, state COMPLETED or NOT_RUN, output, output_sha256 and
execution_ref. COMPLETED requires a full output object, matching canonical hash
and bounded identifier. NOT_RUN requires all three evidence fields null.
Absent cases remain NOT_RUN. Unknown/duplicate cases and extra schema fields
are rejected, not ignored.

Binding fields: source_commit (40 lowercase hex), source_tree (40),
artifact_sha256 (64), environment (LOCAL_FIXTURE/HOSTED_FIXTURE/UK_HOST),
runner_run_id, mode (FIXTURE/RECORDED_OUTPUT), delegated_model_calls (integer0).
Expected binding comes separately from the existing admitted collector/reviewer;
it must exactly match the receipt. A supplied label or matching hash does NOT
prove that collector is authentic. The report therefore always says
NOT_VERIFIED_BY_THIS_TOOL for authenticity and NOT_GRANTED for runtime acceptance.
This component provides no signatures, trusted receipt ingestion, new registry
or replacement for existing independent gates. It cannot detect fabricated data
when both receipt and expected input have been fabricated together.

RECORDED_OUTPUT means checking existing data, never invoking a model. The
zero-delegated-call policy remains enforced by the actual runtime owner. The
receipt's0 field is only a claimed count checked against the expected binding;
it is not an independently measured runtime audit. Native chat quota is UNKNOWN.

## Results and failure behavior

PASS: every mandatory case has completed exact typed JSON output.
FAIL: at least one completed output differs, even if others are NOT_RUN.
NOT_RUN: no failed output, but at least one case lacks completed evidence.
INVALID_INPUT: malformed schema/JSON, wrong hashes/binding or unsafe input file.

Scores use passed case weights divided by ALL configured weights, not merely
executed cases; missing cases cannot inflate the score. All configured cases
are required for PASS. Type identity matters: false is not0, true is not1.
Case report order is deterministic. Raw receipt hash still distinguishes an
input order change. No raw outputs, file paths or private binding values are
printed in reports/error messages; case IDs must be nonsecret manifest IDs.

Exit codes:0 PASS,1 FAIL,2 INVALID_INPUT,3 NOT_RUN. FIXTURE_CHECK_ONLY and
RECORDED_OUTPUT_CHECK_ONLY are always explicit. Semantic review remains
NOT_PERFORMED; release_granted=false and dispatch_performed=false regardless
of score. Untrusted stdout must not itself become release authority.

The parser rejects duplicate JSON keys, NaN/Infinity/exponent overflow, >64-level
nesting, >64-digit integers, oversized strings/items/files and invalid UTF-8.
Normal integers/floats preserve their types. Limits apply before recursive JSON
parsing where necessary. No external shell, network or model command is loaded
from suite/receipt content.

## Acceptance and next integration boundary

Source checks: real local Python3.6.8 unit tests, same tests on hosted Python,
exact-head CI, independent changed-scope review. Historical task23 tests are
not rerun for unrelated evaluator files. Local build/SQLite differs from UK.

Runtime collector/AI semantic evaluation/real UK receipts are NOT_RUN. Later
integration must reuse existing receipt collection and canonical evidence paths,
bind real outputs to reviewed suite/source/artifact/environment, authenticate
origin independently and retain all current P2/Stage1 gates. No installation,
model execution, runtime lease acquisition or overall node1.14 PASS is implied.
