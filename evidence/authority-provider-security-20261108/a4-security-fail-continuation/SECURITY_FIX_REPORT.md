# Authority provider Security FAIL continuation

Status: **implementation candidate only**.  The prior QA PASS evidence and all
historical Security FAIL evidence remain unchanged.  This change requires fresh
independent QA, Security, and Release review and is not deployment authorization.

## Source boundary

- Input commit: `2e5b66944b96afc3699b8988c9edd46aaff92638`
- Input tree: `4a65d43fe1deb08b472b58f3147f84c1a99872df`
- No push, deployment, registration, installation, or production mutation.

## Closed gaps and attack observations

1. `formal-primary` now has a source-frozen, non-configurable minimum set of two
   TEST_ONLY ledger paths.  A separately deployment-root-signed policy must bind
   that deployment class and contain every built-in path.  The signed provider
   config may append paths only and must contain every policy path.
2. Valid Ed25519 provider/deployment signatures, a FORMAL-profile ledger, fixed
   replay device/inode, valid private key, and valid token still fail closed for
   an empty forbidden list, a non-empty unrelated replacement, or omission of
   either required TEST_ONLY path.  A symlink alias from a required TEST_ONLY
   path to the proposed FORMAL inode is rejected by inode identity checking.
   Existing profile enforcement separately rejects a TEST_ONLY runtime profile.
3. Recovery records the exact pre-transition state in PREPARED.  Interruption
   after PREPARED, state replacement, canonical receipt write, and COMPLETED was
   injected independently.  Restart plus four concurrent retries returned one
   byte-equivalent receipt, left generation at 3, and did not perform a second
   or reverse exchange.

## Verification

Command:

`python3 -m unittest -v tests.test_authority_security_regressions tests.test_development_authority tests.test_development_authority_operational tests.test_authority_key_file`

Observed: `Ran 26 tests ... OK`.  This includes the retained authority/replay,
ledger alias, signature, key-file, and operational checks plus the new attacks
and four recovery fault boundaries.  Python 3.6 emitted pre-existing
`ResourceWarning` diagnostics from terse test fixtures; no test failed.

`git diff --check` also completed with no diagnostics before freezing.
