# P2 retained recovery governance mapping

Status: IN_DEVELOPMENT. This mapping does not create a task, queue, lease or install admission.
FEATURE_ID: P2_RETAINED_RECOVERY. This entry remains IN_DEVELOPMENT until complete acceptance evidence exists.

## 1 Functional design

Continue PR17 / PR58 and repair/p2-chatgpt-clean-review-20261013. Recover the retained epoch7 HOLD using a complete, finite, exact-version manual entry. Reuse the canonical ledger, retained TLS certificate and renewal proof, existing activation/fence interfaces and old service isolation. No historical notification replay, old writer restart or second task database.

Components: protected kit loader; snapshot and resource observers; approval reader; retained-state gate; finite phase coordinator; host adapters; bounded subprocess evidence; runtime identity/access adapters; independent failure containment. Inputs are authenticated code and manifests, private exact plan and fresh snapshot, reviewer approval and Owner consent for security effects. Private plan, credential material and raw host inventory are not public deliverables.

Every effect must have exact input bindings, bounded execution and observable terminal evidence. Failure means FENCE_STOP_RETAIN_NO_REPLAY with independently attempted cleanup groups and HOLD on uncertainty. This is limited failure containment, not a promise to reverse all side effects.

## 2 Development order and dependencies

Phase 2 of existing control-plane work; no priority or task change. Runtime source is frozen at 101b465ca3554bf34fef2d53d6006b96d85c4a63; the 107-file manifest is 26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa. Public source/test checkpoint 1238a03f2aef763861447c8f34ca9a4bfcdcce8c is still not the complete recovery release.

1. Finish concrete loader/coordinator/observer/admission composition and local affected tests.
2. Authenticate one complete diagnostic candidate, obtain exact Owner consent where required, collect fresh UK snapshot and narrowly scoped isolated mechanism proof.
3. Freeze complete source, immutable kit, manifests, plan and evidence. Pass Feature Compliance Gate and exact CI. Request one consolidated independent review in PR58, reusing unchanged verified scope.
4. Obtain fresh exact single-attempt approval, revalidate real-time gates, have Owner execute protected recovery, then record health and independent production acceptance separately.

Existing approval6170703284 is consumed. Current production remains HOLD. No dependent production step advances from simulated or local-only tests.

## 3 Acceptance criteria and evidence

- Design/order/acceptance all bind the same FEATURE_ID. Each exact CI result must actually be run and read back; partial gates do not imply the complete kit passed.
- Verify complete source and package manifests, allowed file set, private plan targets/plugins and version bindings independently.
- Test denial of changed files, unknown/expired authority, mismatched snapshot, active writers, partial effects, interruption, timeout, unbounded descendant pipes, failed cleanup and unknown results.
- Test exact Python 3.6.8 compatibility; distinguish fixtures, local process tests, shared CI, UK isolated tests, host preflight and production acceptance. Skips are not PASS.
- Test admitted context binds actual approval ID/body while the preapproval contract is independent of the not-yet-created comment ID.
- Existing tests include evidence/p2-epoch7-access-repair-20261014/preflight-ack/test_service_preflight_ack.py and test_exact_access_plan.py. tests/test_p2_retained_recovery_governance.py executes the existing15 ACL planner cases; it does not claim full recovery-kit coverage.
- Source checkpoint d03e7226 has shared runs38753941972/38753941911/38753941329 SUCCESS; native probe38753938016 SKIPPED. These do not certify all recovery helpers or production.
- Runtime-only checkpoint 1238a03f has independent raw-log readback for runtime CI 38614873783 (74/74,107 source hashes) and Feature Compliance Gate 38614875281 (7 checker cases,COMPLIANCE_PASS). Prior failed runs are retained as history.
- tests/test_p2_full_kit_checkpoint.py invokes the exact-checkout published kit generator, validates Git blob/SHA provenance, builds two identical archives, authenticates extraction, and requires all mandatory offline suites plus separate bootstrap/resume/tool tests without skipped required cases. tests/test_p2_full_kit_wrapper_contract.py checks the wrapper using explicitly synthetic results. The prior frozen helper source 3b87d10b66ae791086cdb05a554ad44ed0f4ad90 passed full-kit CI38644002796:1704 mandatory tests and157 bootstrap tests, zero skips. That result applies only to its exact bytes; the present continuation requires a new exact-commit full-kit result.
- Source profiles cover only the finite reviewed OpenClaw Gateway/relay/native bridge and nginx startup families. Installed source mismatch, unknown children or missing positive capability proof cause HOLD. No business-module or complete vendor-distribution audit is implied.
- Local Node SQLite diagnosis uses builtins and in-memory data only; it does not start OpenClaw or invoke a model. Its result cannot substitute for the required exact UK executable and execution identity proof.
- Full kit, fresh UK proof, consolidated independent approval, actual deployment and production acceptance are not yet complete.

## 4 Governance adoption provenance

Owner instruction Sentinel_f557dd99420481918694d75d61687ced, 2026-10-14. Main232e8a732c45ed2f13eb747f02e883283475b499 contains Feature Compliance Gate. That historical main registry contained only GOVERNANCE_COMPLIANCE_GATE. The repair branch now includes these governance files and P2_RETAINED_RECOVERY; preserve upstream checker/workflow bytes and all concurrent registry entries when updating. Native protected-merge enforcement remains unverified; do not extrapolate from branch metadata.

## 5 Current retained-host compatibility continuation

The runtime107 files remain unchanged. This continuation corrects helper-side observation and composition against actual retained evidence:

- Validate the owned native-sidefile transition using its four exact buffers and journal, preserving the historical ledger-client binding separately from the newly rendered configuration.
- Accept only the exact two-name Python3.6 executable hard-link pair with native/package digest consistency and stable descriptor metadata. Unrelated files keep the single-link requirement; RPM signature authenticity is not asserted.
- Preserve the188-byte existing launcher and its configuration hash. Its fixed versioned dist/entry.js profile is distinct from the root openclaw.mjs profile: initial lexical Node alias, canonical process executable, fixed32-source scope, foreground Gateway main plus bridge, and at most one reviewed warning-adjusted relay child. Unknown aliases or source bytes HOLD.
- Keep pre-permission Node measurements explicitly non-admitting. Owner consent covers only the three named0775→0755 directory narrowings, retaining owner/group/content. Hold locks, validate inactive writers and PREPARED epoch7, and bind descriptor and Node identity before/after. Any partial change or uncertainty is HOLD, with no automatic retry or permission-widening rollback.
- Preserve the old staged kit. The new exact staging sibling is epoch7-recovery-candidate-r2; it does not create a second task, ledger or recovery authorization.

The latest UK receipts establish the native transition, Python pair, five SDK hashes and31 source files. Fresh Node-alias/binary/32nd-source verification, permission effects, new complete observation and isolated execution proof remain separate requirements. Local helper tests do not satisfy them. The three permission changes have not yet been applied at this source checkpoint.

Current validation must include all previous mandatory suites plus the new prerequisite-effect tests. A local run with nine socket-limited skips remains incomplete; hosted exact-commit CI must execute those tests. New byte changes cannot inherit an old install approval. Final package, plan, fresh host evidence and independent approval remain required before recovery.

## 6 Bound Owner diagnostic entry

The separate owner-diagnostic-r2 checkpoint pins the exact reviewed kit source4798cda235b24b31a18b57d3957fbc0d396d634b and immutable archive publication965c0f8bd7e5145dc353a9145388c733e0660ab5. Its dedicated hosted test compares wrapper/test bytes against the actual checkout HEAD blobs, validates all immutable download pins, verifies the real frozen archive and imports/selects the exact UK-only case without executing it, then runs34 mocked/pure boundary cases with zero skips. It never downloads, changes host permissions or starts a service in CI. The unchanged full kit retains its independent1982-case plus170-bootstrap CI receipt38669612327; this small outer checkpoint does not rerun that unchanged kit.

A successful outer CI is only delivery readiness for the explicitly authorized prerequisite and diagnostic command. Real three-directory effects, fresh UK observation and isolated mechanism proof remain separate. Any mismatch or partial effect is HOLD, with no automatic retry and no restoration of broader permissions. Final production recovery still requires its own exact independent approval and live admission.

The first r2 Owner diagnostic verified extraction but stopped at the UK fixture import stage before permission changes. Its historical disabled-suite mapping omitted the existing authenticated test_snapshot dependency. The outer-only correction adds exactly that SHA-bound alias; it neither rewrites the frozen kit/manifest nor changes production helpers. Hosted CI must now exercise this real cached-import/case-selection path while leaving the UID-specific case execution to the authorized UK diagnostic.

## 7. Typed unit properties and r3 successor

Owner's complete read-only diagnostic established two stable rounds of19 inactive units with no reload request. On the observed systemd interface the three fixed timers omit MainPID, ControlPID and ControlGroup; the three fixed sockets omit MainPID. The shared exact-unit contract preserves these absent observations, while requiring all applicable service/socket properties and validating any supplied optional PID as zero and timer ControlGroup as empty. Independent associated-service, recursive cgroup, process, descriptor, mask and scheduler checks remain mandatory. Unknown unit types, malformed values, changed field presence or unexplained runtime state fail closed.

Tests cover the recorded19-unit selected-property projection (not original CLI stdout), pure contract failures, parser/live/transition/compiler seams and full107-file plan composition with synthetic host facts. Runtime107 remains unchanged. New helper staging uses only epoch7-recovery-candidate-r3, preserving the installed r2 generation. Earlier r2 test results are historical and cannot certify these changed helper bytes. The fresh collector observed the Node identity and fixed32nd source successfully, but the approved directory changes remain unapplied; new complete prerequisite/observation/probe and final review are still required.

## 8. Bound r3 diagnostic delivery gate

The r3 helper source460a53e0f702fb416811e785a6ef8d6c39b2d003 passed exact full-kit CI38757450098:2012 mandatory cases plus173 bootstrap cases, zero skips. Its immutable archive is published at02822b674a7c8a0c9c395cbf5664b3d24bff2516, SHA256 c56a11e78914d567f91a94118d676d49f65775161b3c46b16583ece1403c1d85,1015797 bytes. Binary GitHub readback matches. This evidence does not grant installation admission.

The separate owner-diagnostic-r3 wrapper binds that source/tree/archive/manifest/extractor/entry and only the existing approved prerequisite, observation and scoped isolated probe. tests/test_p2_owner_diagnostic_r3.py requires the actual archived cached import closure and exact UK case selection without executing that case in hosted CI, plus36 mocked boundaries and exact checkout/blob verification. The historical r2 gate remains executable against its explicitly preserved extractor. No historical approval or old staged directory is reused for new code. Fresh actual Owner output, private plan binding and consolidated independent review remain required.

## 9. R4 continuation after completed Owner prerequisites

Owner's r3 receipt4d85a064583ca92079f0df489838aa76cfb21f530a3725217689f33356fcbe91 records successful completion of the three authorized0775→0755 directory narrowings and one disposable UK UID/ACL fixture. The subsequent core observation remained HOLD; its exact private hash is2192823493290c4829bfda8a4f6397e94d1ae053266075c1f0da9f63d319e0c9. Neither permissions nor that fixture may be blindly repeated.

The next fixed r4 generation preserves r3. Its distinct continuation validates the exact prior receipt/observation and their source/manifest linkage, verifies the same current0755 directory metadata without mutation, and invokes one existing observe/probe operation. It has no permission-repair or UID-fixture execution path. New publication pins and exact CI remain required; local tests cannot enable delivery on their own.

Actual bounded metadata established that all20 original-plan directory tuples match live UID/GID/mode. The collector excluded the exact declared /var/lib/xuanjun-development root because it only accepted a trailing-slash prefix. R4 adds only exact-root equality while retaining all declared metadata checks. The fixed /home/xuanjun_dev/.config is root:root0755, without ACL/capability; its openclaw child is absent. R4 permits only that exact root-owned profile in addition to the existing developer-owned profile. No other home-directory authority rule is generalized. Missing-parent proofs recheck held ancestors/root and independently close all descriptors; no nonexistent file/directory pin is fabricated.

Failure classification remains explicit. The unchanged approval worker's short local timeout exhausted cleanup during one aggregate run; it failed closed, and the exact-byte isolated75-case rerun passed. The unchanged diagnostics fixture also produced a scheduling-sensitive success instead of its expected timeout; its exact-byte39-case rerun passed. Those reruns do not erase the original failures. Independent deterministic analysis additionally found an actual terminal-EOF deadline-check omission in the diagnostics helper. The candidate now rechecks the absolute deadline after selector/event processing and around the terminal poll. Nine deterministic regressions cover late/exact-boundary completion, first-failure precedence and no signalling of reaped identities; all39 existing tests remain unchanged. The48-case diagnostics suite passes both Python versions, while exact final full-kit CI is still required. No deadline or required assertion is weakened to manufacture PASS.

## 10. Bound r4 continuation delivery gate

Final sourcec86a4d6402859b628a7e604c36fa1ea4d8111b41 passed complete CI38682242057:2052 mandatory tests and176 bootstrap tests, zero skips, exact provenance and reproducible archive verification. Artifact publication04fcd6eeb61d1cf1c5d88547dbb2d8f32f8d679b contains the1021728-byte archive SHA2562b1885a9b1cec024abf657a82c790d420f1e5b4fe8ce1776d9cba4616b4b97b9, whose complete GitHub binary readback matches. Prior local failures remain recorded separately.

The distinct r4 continuation entry must pass its dedicated exact-checkout gate tests/test_p2_owner_diagnostic_r4.py with61 mocked/local-boundary tests and actual249-member archive/cache imports. It must never select or execute the prior UK fixture, invoke a chmod helper, or treat the prior diagnostic as production approval. It validates authenticated completion and current directory identities, then performs a single fresh observation and optional scoped probe through the existing VerifiedKit.observe boundary. Any new snapshot failure blocks the probe; missing or uncertain evidence stays HOLD. Private plan binding, formal exact independent approval, protected recovery and real production acceptance remain subsequent separate gates.

## 11. Epoch7 r5 writer-observation comparison correction

FEATURE_ID remains `P2_RETAINED_RECOVERY`; the canonical task remains PR17 with independent Release review in PR58. This is a recovery-preparation correction, not a new product or queue.

The exact UK diagnostic at source `df748d8f1cefe9668894d69f1f6fa115324291dc` observed two individually validated writer samples whose only difference was total system FD count, 567 versus 568. The process identity digest, background SSH evidence, manager, 19 unit/cgroup rows, masks, scheduler and 22 control files were unchanged. The changing descriptor/process is not attributed. The exact report JSON line SHA256 is `b5be98085982b749f971d1dcb2ca9ed87e2c67657a941fd27a03925e413df481`; the locally stored file with appended LF hashes `315a5b818df808d5a84395737ddbe44a893b869f42a53479918ad526ceb94610`.

Design: preserve all concrete per-scan descriptor/UID/PID-race and protected DB-holder checks. Compare every complete writer-safety field across samples, excluding only the bounded aggregate `processes.fd_count` telemetry. Preserve both counts, both raw-sample hashes and the exact safety projection hash in a mandatory, validated transient evidence sibling. Keep this transient comparison outside the immutable retained-resource digest. Existing raw after-writer and manager/background bindings remain unchanged. Missing or tampered comparison records must reject at downstream preflight.

Execution order: source and consumer fixes; mandatory dual-version negative and integration tests; exact-source Hosted CI; immutable r5 kit and artifact readback; receipt-bound continuation reusing the already completed three-directory 0755 proof without chmod or fixture replay; fresh complete UK observation/probe and private plan binding; consolidated independent exact-version review; then separately authorized controlled recovery and production acceptance. Existing r4 remains immutable and historical approval must not be reused.

Acceptance: count-only drift may complete unchanged retained-resource checks; PID/starttime/UID identity, manager/unit/cgroup/mask/scheduler/control-file/background changes still HOLD; database FD holders, in-scan races and forbidden writer accounts still reject; forged/missing/type-invalid comparison records reject; unchanged retained-resource fingerprints remain stable across fresh count-only telemetry differences. The new `test_writer_comparison` module belongs to the existing mandatory snapshot suite, not an optional skipped gate. Local and Hosted tests must be distinguished from UK observation, production and customer acceptance. This section does not declare any pending stage PASS.

## 12. Separate complete preparation packet (candidate; not admission)

FEATURE_ID remains `P2_RETAINED_RECOVERY`. Reuse the exact frozen kit generation (historical r5, or corrected r6 under section13), current107 runtime, existing private observation/probe receipts, four exact historical v4 pure helper sources and the original102/v4-102 packages. No old entry is executed; exact v4 plan5938dad8 must be independently reproduced from original planec1d6178, then current24 bindings compiled. A standalone bounded preparation wrapper gathers the six exact retained buffers and derives all service/access/resource checkpoints through existing builders. Owner must not invent checkpoint JSON.

A complete independent audit can produce two mechanically linked receipts without circular hashes: an exact topology-only acceptance binds observed mechanisms and preparation source evidence first, then deterministic plan compilation includes that real receipt identity/hash, and the existing final machine acceptance binds the final plan. Neither receipt may be fabricated or inferred from a marker string; existing bounded authenticated GitHub verification is required. This is one complete audit scope, not permission to return unrelated issues one at a time.

Preparation must require complete namespace/readpath/case/peer/SDK/syscall evidence and explicit retained-renewal-timer scope. Exact socket drop-in evidence is separately gathered and bound by the topology receipt without rewriting the observation. Missing proof, nonempty unsupported drop-ins, stale inputs, forged approval, unknown cleanup or output races HOLD. Propose mode writes no output. Prepare mode exclusively creates only bounded root0600 private seed/plan/review-packet files, with full input and output-set revalidation; creation is not approval. No probe, service action, assembly/resume or production data change is permitted in this helper.

Public CI includes only public-source and synthetic fixtures. Real original-plan/private-buffer reproduction is separately classified local/Owner evidence; private input bytes are excluded from publication. All new source, interface, exception, deadline, cleanup and output-transaction paths require consolidated independent review. Actual UK proof, genuine topology review, final exact approval, controlled recovery and production acceptance remain distinct pending stages.

## 13. Epoch7 r6 Python3.6 inherited-socket correction and partial evidence

Keep FEATURE_ID P2_RETAINED_RECOVERY and original PR17/PR58. The actual r5 finite probe reached Node SQLite PASS but failed its first cold native connection. Its retained ledger error was650 bytes with SHA2564d24f655028fe71357e4f338beca7cb27d7a282e1e43f992352a1e9016a958d8. Frozen helper bytes and a real AF_UNIX descriptor under Python3.6.8 reproduce that exact traceback: socket.socket(fileno=3) reports default AF_INET, causing EXACT_INHERITED_LISTENER before SERVER_READY. No new host read was needed to identify this failure.

Design: explicitly construct the inherited Unix stream wrapper, then independently verify kernel socket domain/type/listening state, inherited LISTEN_PID/FDS and exact socket pathname. Do not rely on supplied Python family/type attributes as kernel proof. Preserve the eight-connection limit, UID/peer/namespace/SDK checks, finite deadlines and cleanup scope. The other three implicit constructors in unchanged107 runtime use unnamed clients and discard address metadata; no current-flow failure was established. They are exercised in the Hosted compatibility fixture, not silently rewritten.

Retain one bounded private incomplete-case result before post-result stop/budget checks; mark completion false, preserve failure and cleanup evidence, and never count it as a completed case. Failed durable CASE_OBSERVED publication must roll back the in-memory event and not append a completed case. Capture pre-ready server failure only as bounded static exception code/class and output hash/length; keep clean four-key output-capture schema unchanged. Entry and whole-attempt proof validation reject non-None incomplete_case in either result or authenticated creation receipt; legacy missing remains compatible. No partial result grants admission.

Execution order: exact-source local reproduction; helper/driver and all evidence-consumer fixes in one scoped candidate; dual-version tests; immutable sibling r6 source/index with unchanged runtime; exact Hosted whole-kit gate; immutable artifact verification; receipt-bound observation and finite-probe attempt; then complete independent review and separate controlled recovery. Preserve prior r5 artifacts and receipts and do not replay completed permissions or UID fixture.

Evidence boundaries: local3.6 and3.12 real AF_UNIX socketpair construction/kernel negatives execute; local fresh-listener creation is EPERM-blocked and must be recorded as skipped, never PASS. Hosted real listener/unnamed-client accept/send/receive/SO_PEERCRED regression is mandatory and cannot skip. Hosted3.11 does not prove full positive3.6 listening; that remains an actual UK probe requirement. Required suites, errors, skipped tests and original failed receipts must remain visible. No production approval is implied by this correction.

## 14. Owner installation-attempt policy (2026-10-18)

Canonical cross-project rule: [开发执行与反馈强制规则：安装器默认最多5次受控尝试](../DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md).

Future installers, versioned installation plans and newly reviewed grants default to at most five controlled attempts within the exact approved scope. Each attempt has a unique ID, durable ordinal and complete log. Only a proven no-write failure or independently verified safe recovery checkpoint can permit a next attempt under the grant's retry conditions; completed steps are skipped using retained checkpoints and fingerprints. Success or exhaustion ends the grant. Partial writes, UNKNOWN, concurrent ownership/fence conflicts or an unproven recovery point require HOLD and reconciliation, never blind redispatch.

Development windows implement and test the mechanism. Work independently verifies actual implementation, including restart accounting, the five-attempt ceiling, no replay of successful steps, safety stops and evidence retention. One review binds version/Kit/Manifest, host, executor, UTC validity, attempt budget, retry predicates and recovery entrypoint. Unchanged approved evidence is inherited; changed code/scope receives affected-scope review.

Existing one-attempt installers require real code and recovery/state migration plus incremental review; changing grant wording or an integer is insufficient. Consumed/expired/sealed grants stay closed and platform/production controls remain mandatory.

P2 task remains PR17; independent review remains PR58. The original Epoch7 frozen single-successor implementation, UK files and old grants are preserved. This documentation does not change the current R1-R4 candidate's execution policy or authorize an installation.

P2_INSTALL_RETRY_POLICY=ONE_ATTEMPT_FROZEN
FIVE_ATTEMPT_DEFAULT_POLICY=RECORDED
FIVE_ATTEMPT_IMPLEMENTATION=NOT_IMPLEMENTED
WORK_INDEPENDENT_VERIFICATION=NOT_RUN
P2_RELEASE=HOLD


## Attempt5 Work sole-writer handoff — 2026-10-18

Window1 STOPPED; Work continues PR17 from b88aab7e. Original recovered six
source/test files were byte-preserved and imported by cc397828. New code is
versioned under c-capability-lifecycle/attempt5; README lists the exact runtime
entry, Ledger/AuthorityStore/issuer-service/receipt-provider composition, native
CAS recovery and minimum external read-only proof pack. The original single-use
successor, existing frozen Kit, Prepare and 16-stage business bytes remain intact.

New full-ci-attempt5 gate binds current exact Commit/Tree and all source inputs,
runs all 775 inherited complete tests plus 100 Attempt5 tests, and rebuilds the
separate Kit/manifest deterministically. Test Providers, keys, Run/Job/Invoke IDs
and host effects are explicit isolated fixtures, never production proof.
Hosted and independent review terminal evidence must be reported from actual
runs; this source document does not predeclare PASS. Production Writer/Fence,
real host transaction/backup/readback composition and exact new permit remain
external admission dependencies. INSTALL_PERMIT=NOT_ISSUED; P2_RELEASE=HOLD.


## Owner最终规则：ONE_PERMIT_MAX_5_ATTEMPTS（2026-10-18）

适用于玄钧云汇今后所有新安装器、安装方案和执行许可。一次独立审核签发一份许可；同一Grant最多5次受控Attempt，不得拆成5份许可，不得逐次要求Dots新审核。首次批准必须绑定准确Source Commit/Tree、Kit/Manifest及SHA、目标主机、执行身份、UTC有效期、持久额度规则、诊断与配置范围、安全恢复入口、检查点和幂等条件、Writer及Lease/Fence、UNKNOWN/部分写入停止条件以及成功/耗尽/下一轮规则。

失败自动进入可信诊断、事务对账、已批准配置调整、原生CAS恢复和幂等续接；满足原许可条件才继续下一次。成功立即终止，剩余额度失效；5次失败停止并保留集中失败报告。HOLD不自动废除许可，但UNKNOWN、未确认部分写入、事务回执不一致、Writer/Fence冲突、无法确认检查点、过期或错版本时禁止继续。原许可允许的可信对账证明安全后，可使用同一许可剩余额度，不需要重新签发。

源码变化停止原周期；保留日志和检查点，修复并测试后，仅审核受影响变化，再签发下一轮新许可。不得在旧许可下修改生产源码并安装未经审核的新版本。已消费或过期的旧许可不恢复，旧单次Successor许可不自动解释为五次。

### P2本次实际实现与边界

`attempt5/runtime/permit_cycle.py`提供自动循环入口（接收构造真实NativeRecovery的factory），同一review ID/批准正文SHA和Grant贯穿全周期；原Ledger与AuthorityStore持久消费最多5次。失败必须取得签名诊断及真实事务证明，调用原NativeRecovery/CAS恢复，不重跑整个安装命令、不SKIP已成功阶段。私有Ledger目录保留内容寻址的完整终态/失败报告。

首次批准正文现包含完整permit_cycle策略；AuthorityStore由受信管理员在独立认证后register_cycle，服务按策略SHA、review ID、批准正文SHA核验每个周期请求。IssuerService对代码身份变化持久停止原周期，普通UNKNOWN保持可对账HOLD。`approved_config.py`仅执行管理员预映射的、首次许可逐项批准的专用JSON配置CAS，校验before/after/payload/checkpoint SHA，O_EXCL保留原始备份和意图、fsync、Fence、写后校验；不接收任意路径/命令，不允许源代码调整。部分输出保留，需先可信对账，不能盲重试。

生产集成需原受信通道提供真实Writer身份、Lease/Fence和事务/备份/检查点回执；测试中的TEST_ONLY host facts和签名钥匙仅为隔离测试，绝不作为英国生产验收。未修改英国冻结文件，未运行旧Prepare、安装、激活或回滚。原R1–R4、未变16阶段及257文件旧Kit继承原结果。INSTALL_PERMIT=NOT_ISSUED；P2_RELEASE=HOLD。


### Dots恢复缺陷闭环（PR58 #6247637376）

c527原版本已正确复用同一人工Grant；逐次签名服务回执不是新的人工许可。本次修改补齐自动周期及首次批准配置范围，并处理独审A1/A2/B1/B2恢复窗口：

- 原生ADMITTED或COMPLETE已落盘但本地Ledger未收敛时，认证原生绑定、逐阶段可信读回，恢复持久组件检查点，原子补回已验证checkpoint回执，最后以独立证明收敛原Attempt；不清空PARTIAL_WRITE、不重建Claim、不SKIP、不重跑成功阶段。
- AuthorityStore在同一个SQLite提交中保存完整语义结果/证明/原始host回执与事务结果，再执行签名和签名审计；相同证明可幂等返回，冲突证明拒绝。`read_committed_outcome`仅允许同一已认证主机/身份/Grant读取已提交结果，重新签署当前request digest与新nonce。
- SUCCESS后取回终态不获取或续租执行Lease，不消费额度，不执行任何阶段。原生16阶段全部完成后的局部Ledger/checkpoint异常，可以同Attempt认证收敛SUCCESS；普通UNKNOWN且未得到可信证明仍HOLD。
- 隔离故障注入覆盖native COMPLETE提交后中断、本地checkpoint写失败、服务结果提交后签名失败、签名审计失败、丢失响应、服务重启、新nonce取回和冲突证明拒绝；完整测试包含原875项。

这些均是离线实现和Hosted验证；真实英国Writer、共享数据库、Lease/Fence、签名发行方、可信通道以及Run/Job/InvokeId、实际副作用和备份checkpoint仍需原受信只读取证。未实施生产操作，未签发安装许可。
