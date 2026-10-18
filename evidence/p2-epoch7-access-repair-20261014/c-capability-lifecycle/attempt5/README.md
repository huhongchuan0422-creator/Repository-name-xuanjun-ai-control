# Attempt5 versioned offline candidate

Owner transferred the sole development Writer to Work after window1 STOPPED.
Base b88aab7e, recovered originals imported unchanged by cc397828. Exact ZIP
SHA256 3d8f6adc6c2eca87c44d3a113af8f67cb51e540c824872d1f44ecb94cac39d1f.
Original 29 tests and SOURCE_HASHES.json remain unchanged. The old Bridge is
historical source, not the production continuation entry; its SKIP adapter is
never used by native_recovery.NativeRecovery.

The new API uses a separately versioned five-attempt grant, persistent local
Ledger and service-side AuthorityStore. It never calls old resume_once again.
First native admission uses original capability preparation and exact once-only
Claim; continuation uses the native OuterJournal CAS and actual Driver dispatch,
before/after guards, protected inner receipt and bounded failure containment.
No caller can send a phase SKIP. Recovery requires independently authenticated
whole-phase COMMITTED or NO_WRITE proof; unresolved partial effects stay HOLD.
The new journal retains failed intent digest and recovery proof. A phase already
committed is independently read back, not executed again. Cross-process service
consumption, lease generations/fence, restart quota and terminal success persist
in SQLite; the service must be singular/shared, not cloned per client.

ReceiptProvider verifies an explicitly pinned RSA-2048+ SHA256 signature, exact
request digest, new nonce, issuer and <=60s response validity. No verified=True
flag or default transport is accepted. The issuer's trusted host readback and
signing/transport deployment are external dependencies, not supplied facts.
AuthorityStore registration is administrative after independent grant validation;
calling register is not itself approval or production authority. Database loss
never implicitly recreates history. Existing grants/claims/expiry are not revived.

The new Kit has a separate root, strict cached import scope and full Attempt5 manifest. Its legacy/ subtree
retains every original Kit byte including its original manifest and entry. New
modules live outside that subtree so original strict inventory stays intact.
The legacy fixed-host production entry is not rewritten or called. Production
activation of the new API still requires an independently reviewed trusted
composition and exact host/provider binding. Kit production_ready=false.

## Test boundaries

29 original + 19 real SQLite/multiprocess + 10 real RSA/nonce + 22 native
admission/CAS/recovery + 7 issuer service + 6 actual Kit + 7 new authority tests extend the 775
complete versioned tests to 875 per Python environment. Native tests
reuse the unchanged transaction Rig: real gate, capability, native journals,
control loop and signing verification, with explicit synthetic private approval,
predecessor/host facts and phase effects. They are not a production Provider,
UK installation, proof of real host Writer exclusivity or production acceptance.
The old R1-R4 workflow/assertions/Kit remain unchanged and historical failures
are never reclassified. Both full current and retained historical groups run.

## Minimum external read-only evidence, one pack

Through the original trusted channel only, administrators/host authority provide:

1. Exact approved new grant/version/source Commit/Tree/Kit/Manifest, host,
   execution identity, UTC window, five-attempt budget and recovery entry; old
   consumed/expired single-use permits remain closed.
2. Authenticated issuer public-key fingerprint/provenance and channel identities,
   actual single shared AuthorityStore path, history retention/backups and no
   missing/cloned/deleted quota history. Never provide private keys/tokens.
3. Current Writer identity, epoch, lease/fence generation and expiry; complete
   conflicting/inflight Attempt, Run/Job/InvokeId history and terminal outcomes.
4. Protected native outer/inner/phase transaction receipts and independent
   actual file/service/DB readback binding exact phase effects, failed intent,
   command/log hashes, backup and recovery checkpoint identities.
5. Reconstructed native Driver/control/host-readback composition on exact code,
   preserving existing masks, backups, activation and bounded containment.

No new UK collection command is authorized by this list. Missing evidence stays
UNKNOWN; no UK Root, Prepare, install, activate or rollback is run. Offline code
and tests do not issue a permit. P2_RELEASE=HOLD; INSTALL_PERMIT=NOT_ISSUED.

Native checkpoints also persist the finite component state: actual control cursor,
gate target/generation/identity observations, original review provenance, native
authority binding, diagnostic ordinal, Core activation/staged-parent and runtime/
legacy/acceptance data. No plan, policy, callback or code is restored from data.
A whole-phase return is durably recorded as pending component state before
independent commit readback; only a matching signed proof promotes it through
native CAS. Missing partial component state stays HOLD. The actual native
ClaimAuthority receipt guard also rechecks the new grant/lease during effect IO.
Concrete production composition is required by default; TEST_ONLY fixtures cannot
authorize the UK host. No obsolete single-use admission is re-opened.

Production NativeRecovery additionally requires a fresh PR58 review ID. The
new authorization module reuses the unchanged bounded HTTPS transport and checks
independent account 18598789888 / 95597695, PR58 destination, exact raw body SHA,
new five-attempt decision/marker, full grant and issuer RSA public-key fingerprint.
No injected fetcher exists on the production path. Old single-use bodies and
developer-authored comments cannot authorize it. No such permit is issued here.

The exact new approval body explicitly states the fixed no-replay retry policy
and inherited 107-payload/16-phase/no-TLS-issuance effect scope. Production grants
must name `native_recovery.NativeRecovery` as the recovery entry; legacy entries
cannot be substituted. One approval binds all five attempts and the issuer key.


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
