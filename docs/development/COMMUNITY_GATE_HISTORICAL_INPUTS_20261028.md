# Original community Gate: historical test inputs

This change repairs test input/version boundaries only. It is not a production
carrier, a new core10 version, permission to deploy, or a successful preview.
The previous failed runs (40620564681, 40621298623, 40621298575, 40623242791)
remain evidence; no run is deleted, rerun as success, or silently reclassified.

## Fixed original inputs

`tests/test_community_historical_fixtures.py` admits only enumerated original
commit/path/SHA256 triples. Missing or changed inputs fail; they never skip or
fall back to current source. It has no downloader, credentials, network calls,
installer, or server entry. The workflow fetches exact commits before complete regression and the existing dependent
handoff/resume inspection scopes, and reuses its existing fixed artifact downloader.

* `1d639347f404f952998b3b414a95e48f66571c3c`: original A entry, SHA256
  `48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55`.
* `3b6be4aa1ff06d088fe26f44f08b9a505c5b5513`: exact V1 sources. The unchanged
  current builder's frozen guard reproduces the original 111330-byte ZIP,
  `aa8afb5c05240e3c4835680e8cec765fa4199f0b7f230e3adaced8bc489397f9`.
* `4a0d8e2f48077b0254966e0e54947e910c56596f`: previously admitted readonly
  helper composition and its four generated assets. Current-source drift is
  still rejected, not repinned as previously approved source.
* `2853904258ca036a4abcdc2c829278634c45370b`: the original Stage A delivery
  manifest and its 12 declared source/receipt files. This is historical closure,
  not a claim that an old delivery contains current workflow/tests. Other Stage A
  behavior tests still execute the current adapter and builder with fixed original
  public inputs and the existing synthetic image fixture; no real image is loaded.
* Original artifact `12572781194`: existing outer ZIP
  `a9b034ce85734cf26f4b18058f6840f6434aac0c31322b0664fda7e78eb68956`, nested BC ZIP
  `5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4`, manifest
  `e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a`.
  The actual unchanged fixed installer validates every nested member.

The original downloader also retains its already-declared `12586026477` nested
successor fixture and all original hashes for existing handoff tests. Its download
body, token handling, artifact IDs and hashes are unchanged. Inputs becoming
unavailable are a real CI failure, not a reason to invent a replacement archive.

The original post-B successor is separately fixed to commit
`a93c4853b7bbb2a249d49b309c27b98c4082055d`: its nine actual source members
reproduce the existing 63221-byte ZIP
`8556531d52b81ca87f3346f2d098de7aea50cf7838106482aadcc86188c374eb` and manifest
`f7118e9a45c77cf260ae516864635d45af4a9159055da3f9ab983ff4ca95f99e`.
The post-B tests no longer rebuild this frozen successor from mutable current
source. The prior attempt/checkpoint loop stopped after its first case; these two
one-shot checks now run as separate fresh test instances, with both zero-exchange
assertions preserved. No production history or transaction is replayed.

## Tests and boundaries

Six fake clocks now use direct function replacement rather than a Mock callback,
so the existing caller-sensitive fake deadline actually advances. The production
120-second wait, 600-second transaction bound, locks, approvals and all frozen
hashes are unchanged. The isolated loader worker receives the already-verified
original A bytes and checks their digest again.

Permission tests require exactly one top-level block containing only
`contents: read` and `actions: read`. Extra scopes, write permissions, quoted or
job-level overrides are rejected. Workflow permissions themselves are unchanged.

Only the readiness file size/hash in `connection-inputs.json` is synchronized.
The document remains `DRAFT_INPUTS_PINNED_NOT_ENROLLED`: all false/null authority,
registration, recipient and initialization fields and old runtime provenance stay
unchanged. The `files` array describes the current unregistered proposal; the
historical `runtime_source` does not claim these newer bytes were in its old ZIP.
An absent trusted runtime SHA still makes health fail closed; this edit is not
evidence of a working connection or a production enrollment.

Local tests use an isolated writable HOME and fixed original fixture files.
They do not acquire cloud credentials or start the actual service. Full hosted
regression and actual platform acceptance remain separate from local results.
The existing fixed-product preview inputs, exact health gate, appid/base binding,
manual opt-in and no-default-upload conditions are unchanged.
