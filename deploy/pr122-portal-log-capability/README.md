# Persistent Owner authority, first fixed Tokyo adapter

Owner explicitly requested standing authority on 2026-10-16 for Domestic and
Tokyo website/server migrations, deployment, maintenance, backup and rollback.
This authorization has no expiry and can be revoked. It does not bypass existing
DNS, business-write or Tokyo-retirement release gates. UK/P2, PR99 and Finance
remain outside this execution adapter.

## Registered operations and exact scope

This first adapter implements ONLY Tokyo PR122 legacy Portal logging correction
approved in PR122#6204793589 (ce211a606e82845bfe4d7a6e3d511f3872d53147).
It does not yet implement Domestic deployment or general server migration.
Future reviewed adapters can use the same standing Owner authorization; they
still require technical implementation and evidence, not a claim of generic root.

The root-owned, SHA256-bound helper accepts exactly one fixed argument:

| Command | Effect |
| --- | --- |
| status | Reads its private grant and bounded execution receipt |
| apply | Once only: exact old source, private backup, exact candidate, atomic replacement, one Portal restart, four real GET/HEAD health checks |
| rollback | Once only after apply: exact candidate and old backup required, restore old source, one restart and check the original behavior |
| revoke | Removes only its exact matching sudoers rule, preserving the grant and evidence |

No user-supplied paths, scripts, environment overrides, unit names, arbitrary
commands, credential reads, DNS changes or additional keys are accepted.
`apply`/`rollback` are once per this adapter grant, even on partial failure.
Unknown outcomes preserve evidence and require inspection, never blind retry.
The original URL-path logging behavior remains unchanged.

## One-time installation on Tokyo

The Owner admin terminal downloads `install_grant.py` at an immutable commit,
checks its separately provided SHA256 and runs it with Python isolated mode.
The installer embeds the exact helper bytes, checks host/Runner/source identity,
root directory ownership, existing sudoers validity and the four-command rule.
It refuses existing destinations and does not clean up unknown partial states.
The rule is published last, root:root 0440, with the helper's SHA256 digest.
It verifies the resulting access by running `status` as githubrunner.
Installation does not apply the patch or restart a service.

Paths: `/usr/local/sbin/xuanjun-pr122-portal-logfix-v1`,
`/etc/sudoers.d/xuanjun-pr122-portal-logfix`,
`/var/lib/xuanjun-pr122-portal-logfix-capability` (root 0700).
The grant record is root 0600; backup source is root 0400.
Owner can revoke with `sudo -n /usr/local/sbin/xuanjun-pr122-portal-logfix-v1 revoke`.

## Validation and limits

20 filesystem/receipt lifecycle tests run locally against the actual original
source and also a synthetic fixture. Local container ownership mapping required
a test-module-only UID fallback; production SOURCE_UID remains1000.
The hosted CI uses root only inside an ephemeral GitHub-hosted runner, a synthetic
class fixture, mocked restart and mocked live checks. It verifies rule syntax with
real visudo and checks embedded payload bytes. It does not claim Tokyo root
execution, real service restart, service-file custody or production acceptance.
The approved patch's real-source Tokyo 16-test evidence is inherited unchanged.

Independent patch approval covers the logging correction, not automatically this
new installation/execution mechanism. Its new code and tests are supplemental
review material. Work website/current and the approved312efdd3 config package
are unchanged. W06 production correction remains NOT_EXECUTED until real receipt.
