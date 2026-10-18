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

29 original + 19 real SQLite/multiprocess + 10 real RSA/nonce + 21 native
admission/CAS/recovery + 7 issuer service + 6 actual Kit + 7 new authority tests extend the 775
complete versioned tests to 874 per Python environment. Native tests
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
