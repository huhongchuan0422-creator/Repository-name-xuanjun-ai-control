# Fixed account creation candidate — local authoring only

Status: reviewable executable candidate; NOT executed on any host. Deployment,
GitHub writes, root probes, account changes and credentials reads were not done.
36 mocked tests pass. Target compatibility and production execution remain
unverified; a reviewed exact STS/SWAS one-shot workflow binding is still required.

## Files and execution scope

- account_candidate.py: fixtureable one-shot operation core and offline HOLD plan.
- account_os.py: actual OS adapter, exact --apply entrypoint, fixed host/root guard.
- tests/test_account_candidate.py: wholly mocked account/syscall/subprocess tests.
- TEST_RESULTS.log and FILE_HASHES.json: local verification.

Only host `iZvt5t8tlrm8oiZ`, real/effective root, and account/group
`xuanjun-customer`. System UID/GID must be nonzero in verified system ranges.
Home field `/nonexistent`, no home creation, shell `/usr/sbin/nologin`, locked
password, no supplementary groups, no mail spool or subordinate-ID allocation.
No runtime/data/service/DNS/credential/sudo-policy/wrapper changes. No repair,
delete, or blind retry. Unknown results consume the attempt.

Fixed proposed command:

`/usr/sbin/useradd -r -U -M -d /nonexistent -s /usr/sbin/nologin --password '!' xuanjun-customer`

No command, account, path, or environment overrides are available on the CLI.
No real invocation was made. --apply is only for a separately reviewed caller.

## Canonical transaction integration

Original source context provided by parent:
`a1d5a6dee3135df2d3332e96c722091e2f2fd9d9`.
Available local files are baselines, not a verified checkout of that commit.
Examined customer_release.py, customer_channel_binding.py and
customer_channel_upgrade.py in website-runtime-prep/baseline and
website-release-prep/scripts. Existing install/upgrade permissions are not
reinterpreted as account permission; wrapper operations stay unchanged.
Historical metadata only established account/group absence and nologin metadata.

Parent-supplied current bindings used exactly:
- Lock existing root-owned inode: /var/lib/xuanjun-customer-channel/channel.py
- Exclusive account receipt: /var/lib/xuanjun-customer-channel/account-preparation-20261017

No new general ledger. Original grant, wrapper, install and upgrade state remain
untouched. Lock uses no-follow existing open, inode identity check and EX|NB flock.
Fresh account/group/path checks run twice. Receipt creation and intent are durable
before the single useradd call. Any failure leaves the consumed evidence intact.

## Privilege checks and limitations

Existing sudo/doas/polkit policy files do not block account creation merely by
existing. This script makes no changes to any privilege policy.

After creation it runs only the fixed read-only query:
`/usr/bin/sudo -n -l -U xuanjun-customer`, with LANG=C and LC_ALL=C.
Root-owned, non-writable, regular sudo/passwd binaries may carry their normal
setuid-root bit. Foreign ownership, setgid, writable or symlink binaries fail.
Raw stdout/stderr is captured, never printed or written to receipts.

Sudo rc=0 (any allowed command) fails postcheck. Only rc=1 with the exact known
English denial naming the fixed account and host passes. Unexpected output,
password prompts, unknown user, plugin error or other return codes remain UNKNOWN.
Password lock is a boolean derived from fixed passwd -S output; no shadow hash
is read or disclosed. Supplementary group enumeration must be empty.

Global polkit/doas policy is NOT audited and is not claimed verified. Success
reports explicitly include polkit_global_policy=NOT_AUDITED and
privilege_policy_changes=false. No generic assertion of globally absent elevated
privileges is made.

## Remaining review and target gates

The exact caller/payload/workflow identity and receipt binding must be reviewed
before execution. Target useradd defaults and semantics are not yet verified.
Platform checks require supported useradd flags, fixed system account defaults,
empty recognized account-hook directories and positive system UID/GID ranges.
There is no local man-page requirement or files-only NSS requirement. Fresh named
NSS lookups are repeated; exceptions remain UNKNOWN. The explicit password value
`!` is a disabled marker, not a secret. Password status is verified afterward.

Official shadow documentation confirms -r leaves subuid/subgid unchanged unless
-F is explicitly passed; this candidate never passes -F. Advertising -F in help
is not a blocker. Source: https://github.com/shadow-maint/shadow/blob/master/man/useradd.8.xml
Target binary ownership, supported flags and final postconditions still require
fresh validation. Global polkit/doas permissions are not audited.

No automatic rollback is attempted after partial useradd or postcheck failure;
such failure returns HOLD and requires explicit investigation. Tests do not prove
live OS compatibility, read isolation against concurrent root administrators, or
complete platform-hook discovery.

Run only the local tests for verification:
`python -B -m unittest discover -s account-preparation-candidate/tests -v`

Mail suppression uses -r directly: official shadow src/useradd.c calls create_mail only for non-system users. No possibly unsupported -K CREATE_MAIL_SPOOL override is used. Source: https://raw.githubusercontent.com/shadow-maint/shadow/master/src/useradd.c

Standalone payload: account_prepare.py combines the core and OS adapter, without local imports or the old core main guard. Compatible with /usr/bin/python3 -I -B <payload> --apply. Only compiled/imported under mocked no-host/no-process tests; never run with --apply. Offline --plan is deliberately unsupported; no-args refuses.

Final preflight: both fixed /usr/bin/passwd and /usr/bin/sudo are checked before receipt reservation or useradd, and rechecked immediately before use. Only root:root regular single-link files with mode exactly 0755 or 04755 pass. No arbitrary setuid-tool exception exists. The redundant named_nss_lookups_complete platform assertion was removed: the core relies only on its actual two fresh named account/group observations, with lookup errors UNKNOWN. This does not claim NSS enumeration completeness or isolation from other root administrators.
