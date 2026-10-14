# Read-only independent review aid, not a new recovery candidate

Frozen recovery source07e81116edb0dcf851259f6a292a8a25e735cca7 and evidence3e473efc282c2955191411497e4b86b7a1aba937 remain unchanged.
This supplemental aid reads bytes only. It does not import or execute any packaged code, extract to disk, connect to a server, or grant release approval.
Reviewer should inspect it or write their own equivalent verifier, then execute in their own local/sandbox code tool.

Inputs:
1. Original epoch3-recovery-kit.tar.gz (SHA2567e3228b293d0737d27a3f3fca57385f5b6c5628cfddf6488ce1c17c1017d619f), or independently fetched epoch3-recovery-kit.base64.txt with --base64.
2. Independently fetch GitHub tree JSON from https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/git/trees/552839cc0f55660ffe3d982c571e2c37b83763cd?recursive=1 and save as repository-tree.json. Must be nontruncated with that exact tree SHA. Do not substitute a source-owner file inventory.
3. original-runtime-manifest.review-reference.json: original approved102-file manifest; require SHA2569bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3. Compare to the original independently approved artifact11865804223 record when reusing that approval.

Run in reviewer's own environment, not UK:
python3 -I -B verify_frozen_kit_offline.py epoch3-recovery-kit.tar.gz --repository-tree repository-tree.json --old-runtime-manifest original-runtime-manifest.review-reference.json

The tool independently calculates archive SHA256, bounds decompression, rejects unsafe tar paths/duplicates/links/modes/owners/extra/missing inventory, verifies entry and manifest, all19 helpers/17 tests/102 runtime files, provenance and freezer. It computes Git blob SHA1 directly from each packaged helper/test/entry bytes and compares the independently retrieved immutable repository tree. It compares unchanged100 runtime hashes plus exactly2 pinned repairs to the old manifest.

Important source mapping: runtime is a built/frozen artifact, not a repository checkout where every stage1 path exists at the repo root. Validate100 unchanged files against old approved manifest/artifact; inspect2 repairs and freezer/provenance source. Do not invent one-to-one repository paths for generated outputs.

Scope limits: cryptographic consistency is not semantic source review; private plan/re-rendered24 still require original protected plan inputs and review of the compiler/renderer. Tool reports private_plan_and_rendered24=NOT_RUN, production_effects=NOT_RUN, release_approval=NOT_GRANTED. Source-owner local output is only a demonstration; reviewer must run their own check before claiming independent PASS. If no Python/code execution tool is available, report that exact capability blocker rather than infer success from size/magic or request changes to frozen production code.
