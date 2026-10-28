# Original community preview: fixed f131 product, separate control revision

Status: LOCAL_CANDIDATE_PENDING_INDEPENDENT_REVIEW. No push, workflow dispatch, upload, release, server action or live credential read is included.

## Original task and source identity

This only repairs the existing Issue76 preview workflow. It creates no new app, runner, upload channel, credential or identity system.

- Control baseline: bf8c482b3bd7bc58c75995713cc87e58a0e3aab6.
- Latest observed branch successor: df810b52ae68da3d4b356995a939d8fa0de77c47, an original bot documentation-only observation on 2026-10-28T01:57:49Z. No candidate path changed.
- The original branch guard remains feature/chatgpt-community-wechat-sp-offline-20261017.
- GITHUB_SHA always remains the actual control workflow commit. No global or subprocess GITHUB_SHA substitution.
- The product is ONLY f13155ed63a3137d41766ee587d9b4b96a81477f, tree c31a9b1df006eeacd78ae3f9921073f3fe77d2c3.
- Product push Run40058542631/test120766815688; fixed original step must be completed/success, not skipped.
- Product source Artifact12546258346; API binding, size 992283, expiry and outer SHA256 21c15e3bb8ff1bb2b54ba3f7d950eea5b96cc62df98d94ee2155d4fff146b0ec are mandatory.
- Source ZIP SHA256 125ec8633e173d582d5ca5cd3dccc21d2d97104723fb61a136911c48e12d47d1.
- Original full manifest SHA256 5dc52185ab0b7cb9eecaea59da6e57de20dcad051547361530bf6ee75405f9e8; 427 files plus manifest. No arbitrary artifact/ref/product parameter exists.

## Existing platform inputs after reviewed source publication

Use the existing workflow path .github/workflows/chatgpt-community-wechat-sp-offline.yml and original feature branch. The existing input names are retained, so default-branch registration needs no new input.

- preview_enabled: true ONLY for the separately authorized actual preview.
- preview_source_sha: actual published CONTROL branch HEAD (not f131, not the older local baseline).
- preview_target: uk-path-candidate.
- preview_evidence_run_id: 40058542631 exactly.
- backend_image_enabled: false; no backend image build/deploy is requested.

The product SHA is fixed inside the reviewed control contract; it is not an editable dispatch input. Concurrent source drift requires re-reading the current branch and reviewing changes, not resetting it. Do not use a [mini-preview] commit marker to trigger an automatic preview while publishing this source. The focused test marker is [fixed-product-preview-scope].

## Admission and identity chain

1. Current control checkout validates the actual event/ref/control input and fixed product run/job/artifact metadata.
2. Existing repository actions-read token only downloads that fixed GitHub artifact. It is not a WeChat secret. Authorization is sent only to api.github.com; the signed artifact-storage request is clean, HTTPS and allowlisted. No redirect/proxy chain is accepted.
3. Actual outer bytes, inner ZIP, manifest set, regular file types, path safety, every hash, original AppID and fixed endpoint are verified before any product input is handed to the domestic job.
4. The original domestic runner identity and same-run control-source manifest gates remain. Product source is staged in a separate private, run/attempt-bound directory. Existing outputs, symlinks, stale/foreign contexts and source edits fail closed.
5. Current reviewed control scripts read that admitted product tree; the original 27 client source files remain f131. prepare-mini only injects the original fixed base URL/commerce setting. Both the generated tree and the final upload source must also equal the frozen product manifest projection (including pinned connected app.js SHA256 07eaedb76bc73f278eeab7235cf2f921cee0c875f890fdc26c82fb4e4699b42e); editing a self-reported prepared manifest cannot bypass this. Its one-line per-child copy also retains the already reviewed Node24 compatibility without replacing the source tree.
6. The explicit product identity is passed to health/prepare/preview. Receipts record frontend/product SHA=f131 and control_source_sha=actual GITHUB_SHA separately.
7. Existing Node20, SDK2.1.31, runner name/user, original WeChat secret references and private-key handling remain. No secret is sent to the Python identity subprocess; only an explicit environment allowlist is passed.
8. The original preview call remains ci.preview, not ci.upload/release. UNKNOWN is not retried and old output is not reused.

## Readiness and business boundaries

The original anonymous exact URL is https://uk.wenwenwenyiyiyi.work/community-preview/community/health.

Require HTTP200, JSON, exact URL, bounded response, status READY, scope PROCESS_AND_DATABASE_CONNECTIVITY, production_acceptance=false, runtime_source_sha=f131, version_source=IMAGE_BUILD_STAMP and integer observed_at no older than600 seconds/no more than30 seconds ahead. The produced readiness receipt additionally binds the actual control SHA, fixed profile/base/origin, frontend=f131/backend=f131 and fresh local observation. The upload script rechecks freshness, control binding, prepared source manifest, AppID and base before reading the existing upload key.

AppID stays wx1d5f8873eaea5392. Entry is pages/home/index, scene=null, query empty, payments=false. No request-domain/IP allowlist/account permission modification, real login, merchant admission, payment or customer acceptance is inferred. Health alone is not product acceptance.

## Offline verification and limits

The local acceptance fixture used the actual downloaded artifact bytes; metadata/HTTP positive and negative unit fixtures are explicitly synthetic and never contact GitHub, health, WeChat or the host. Test-only health proofs live in temporary directories and are removed, not offered as runtime readiness.

Current local results: 48 Python tests +6 original Node endpoint tests, all passed/no skips with the exact product fixture. This covers the new fixed-product gate, original endpoint/evidence contracts, original preparation safety, source mutation/symlink/replay denial, redirect credential isolation and exact source/control health binding. YAML, all46 original/new shell run blocks, Python/Node syntax pass. Added-code registry coverage2/2 passes; full repository feature governance and actual Hosted/platform execution remain to be verified in the original repository, not claimed from the partial local fixture.

This record is an execution contract/candidate, not platform execution or independent review approval.

