# Consolidated B1 repair for PR58 review6165869434

The independent review identified a real fail-closed cleanup ordering defect:
first stopped-state observation could raise before all restart-inhibition work.

Repair: initial observation, boot restoration, Owner mask restoration, legacy
mask restoration, final stopped-state observation, and final legacy observation
are six independently attempted operations. Any error remains UNKNOWN/HOLD even
when a later observation succeeds. A typed exception carries bounded evidence
for every operation into the original single-attempt durable receipt; no error
messages or private data are recorded. No automatic retry, no legacy restart.

New targeted tests cover initial/both/final stopped observation failure, each
cleanup group failure, final legacy measurement failure, multiple errors including
interruption, and preservation of detailed UNKNOWN state in the actual temp-file
journal. Existing original160 and final34 Owner UK evidence retained.

Local Python3.6.8 full177/177 PASS. Packaged affected suite39/39 PASS. UK amended
39/39 and full verify-only PASS per Owner original receipt, SHA256
3efeca693481d0b1d79d5490b9a17cc4b9d64a7d1d7a9135b3daf3b8a9313484;
not installation approval.

Final replacement kit archive SHA256:
7e3228b293d0737d27a3f3fca57385f5b6c5628cfddf6488ce1c17c1017d619f
Kit manifest:1e13f9e1b6c2fddc135c314fbfb4c6f2b687466ef01208321116a9de10a3c71c
Entry:5c494fe7b5c8737a972d6e012e76a74d17b005a978462a6b3ab9b3cb8daa2848
Runtime and private plan unchanged. Two archive builds byte-identical.

The previous independent reviewer explicitly did not complete binary/19-helper/
102-runtime independent verification. That remains part of the requested complete
review, not something source-owner tests can self-approve. The amended review
request must cover this entire candidate and the same finite failure contract,
not merely mark B1 closed and infer production acceptance.
