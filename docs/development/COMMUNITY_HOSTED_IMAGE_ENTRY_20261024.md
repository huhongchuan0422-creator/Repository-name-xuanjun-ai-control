# Original Hosted image build entry — prepared, NOT_EXECUTED

Accepted baseline: 1e86fcd1779adeb7937a50c784b618d755f1664a offline release-plan
scope PASS,12 tests. Business/OCR31d3 scope PASS,48 Python+19 Node and original
assets reused. No runtime, OCR lock, Dockerfile or build commands change here.

## Existing path, smallest added inputs

Original workflow .github/workflows/chatgpt-community-wechat-sp-offline.yml,
original branch feature/chatgpt-community-wechat-sp-offline-20261017.
community-backend-image remains needs:test, ubuntu-latest,12 minutes. Workflow
permissions remain contents:read. No job/global permission, secret, environment,
new workflow, cloud or SSH execution is added. Old real push [community-image]
behavior remains restricted to the original branch. No dummy push is needed.

New workflow_dispatch inputs:

| Input | Default / exact meaning |
| --- | --- |
| backend_image_enabled | boolean false; only later approved invocation sets true |
| backend_image_source_sha | empty; must equal selected original branch HEAD and run github.sha |
| backend_image_evidence_run_id | empty; successful completed original push evidence for that exact SHA |
| preview_enabled | original false; must stay false for image build |

The delivery manifest supplies this new source SHA/Tree and its actual push Run.
Do NOT substitute the old1e86/31d3 Run for a new SHA. Recheck branch HEAD and
artifact expiry at the later approved invocation. The test gate validates repo,
original branch, lowercase40hex exact source, one explicit mode and canonical
evidence Run ID BEFORE evidence requests. Image inputs never fall back to
preview source/Run inputs. Both enabled or malformed mode flags fail closed.

## Actual execution boundary

For approved image-only dispatch, the original test job reuses its existing
strict push evidence validator: exact repo/head-repo/branch/path/event/head_sha,
completed successful test job and exact accepted scope step, unique unexpired
source artifact, digest/size/repository IDs. Its original checks and accepted
names are unchanged. It rebuilds the deterministic source ZIP from the exact
checkout, with the new run's source_package SHA output. It does not claim that
prior artifact bytes were downloaded or that rebuilding itself re-executes the
old business regression. Image dispatch skips complete old regression/browser
installation; it does not delete or weaken those tests or bypass the evidence.

Only test + community-backend-image may run. SDK, preview and both runtime jobs
are not selected; the manual preview branch excludes image mode explicitly.
Runtime jobs now explicitly require push, retaining their old normal push
behavior. Conflicting preview+image cannot start either optional branch. The
Hosted image job contains no Secrets/self-hosted/server/SSH/docker push/load.
Local Docker build/save is the existing Hosted artifact production, not a cloud
deployment or a WeChat upload. This preparation does not invoke that job.

Root must review this exact candidate before authorizing the normal explicit
Hosted build. Defaults remain off. Do not run old2330 updater, dispatch preview,
enable OCR, alter grants/credentials, or install any server/runtime dependency.

## Exact artifact/source-stamp acceptance after a future build

1. Actual workflow Run must be completed/success on the exact reviewed source
   SHA and original branch; test evidence gate must pass, not merely be skipped.
   community-backend-image must actually succeed. Other optional jobs must be
   SKIPPED. A failed/cancelled/incomplete build with an always-uploaded partial
   artifact is not successful image evidence.
2. Source job deterministic community-stage-source.zip SHA output must equal
   the downloaded SAME RUN input ZIP. Existing bounded extraction checks all
   member paths/types/manifest file hashes before constructing an empty context.
   Verify current Git input bytes independently; keep source ZIP digest separate
   from its outer artifact archive digest.
3. Existing verify/release Docker targets use SOURCE_SHA=actual GITHUB_SHA.
   Dockerfile writes protected /app/COMMUNITY_SOURCE_SHA, sets
   COMMUNITY_SOURCE_SHA and OCI org.opencontainers.image.revision to that SHA.
   Existing compatibility/nonroot import tests and pinned vendor wheel checks
   must pass. No OCR production dependency or permission is enabled by the image.
4. Original community-backend-image-candidate must contain the complete existing
   community-image-tests.log, community-image-id.txt,
   community-backend-image.tar.gz and community-backend-image.sha256. Verify
   outer artifact bytes/SHA separately, hash the actual inner tar.gz and compare
   the sha256 file, and bind community-image-id.txt to the saved image config
   digest. Check archive/config label+environment+stamp content from that actual
   image with an independently reviewed inspection; never infer the running
   server's SHA from a label or locally supplied GITHUB_SHA. RepoDigest can be
   absent for a local image; do not fabricate one or confuse it with image ID.
5. Retain run/job/step results, exact source/Tree/OCR lock, source/input/archive
   digests, image ID/OCI and actual artifact IDs/expiry in a fixed receipt. Root
   reviews these bytes/metadata before any separate UK transaction authorization.

The current image build status is NOT_EXECUTED; image ID, RepoDigest, image tar
SHA and image artifact ID are null. New normal source CI tests this entry only,
not an image build. The current UK observed OCI remains
2330dd55c07f58d7f45a7c4510a97610dd4735d6, runtimeSHA/freshness unknown, preview
HOLD. The accepted offline update/rollback plan and existing private data/account
configuration/history are unchanged. Image build permission never implies
server deployment, official preview upload, real login or production acceptance.
