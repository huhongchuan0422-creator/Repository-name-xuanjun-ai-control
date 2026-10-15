# PR122 Domestic Website Offline Candidate

## 1 Design

Build a delta-only candidate on top of the immutable Tokyo source archive. The
candidate changes only `public/assets/tiktok-integration.js`, adds an isolated
Domestic apex Nginx/TLS design, and provides fail-closed release tooling. The
private control base remains below `/home/openclaw_ops` with mode `0700`; the
public static release lives below `/var/www/wenwenwenyiyiyi.work` and is owned
by root. Existing `winctl` server blocks, certificates, services and routes are
not replaced or included in this package.

The source archive is pinned by SHA-256 and is not repacked. The delta bundle
contains an overlay, the complete expected post-overlay file manifest, exact
configuration candidates, and release tooling. Dynamic integrations and
protected routes remain fail-closed until their independent backends and
authorization contracts are accepted.

## 2 Development Sequence

1. Verify the pinned source archive hash and the original TikTok asset hash.
2. Build the overlay and expected final manifest without rebuilding the source
   archive or recollecting routes.
3. Test network failure, invalid JSON, explicit disconnection, disconnect
   failure and successful connection UI states.
4. Test W1—W5 as one release transaction: worker readability and immutability;
   receipt-bound artifact identity; namespace/link/owner/mode constraints;
   durable intent, reconciliation and exact rollback; one real hard deadline
   across lock and I/O. Include negative cases for A-receipt/B-bundle, content,
   mode, traversal, wrong IDs, link substitution, write failure, interruption,
   ambiguous state, NaN/Inf and actual timeout.
5. Test W6 as one cutover contract: generated CSP hashes in real Chromium,
   Tokyo-only ACME challenge forwarding while DNS remains unchanged, exact
   existing Domestic certbot path/version, dynamic-route cutover HOLD, and a
   non-executable cross-object backup/rollback contract that protects winctl.
6. Publish only the offline candidate commit and bundle receipt. Production
   installation, certificate issuance, Nginx changes, permission changes and
   DNS changes require a separate Release Gate.

## 3 Acceptance

- A status request failure or malformed response never displays connected,
  exposes stale account text, or enables disconnect.
- The source archive remains byte-identical and is referenced by its existing
  SHA-256; the delta bundle has its own deterministic manifest and hash.
- Release preparation rejects unsafe archive members, baseline drift, extra or
  missing files, hash mismatch, timeout and existing release collisions.
- Activation writes old state and intent durably before pointer replacement;
  interrupted states use bounded reconciliation, not automatic retry.
- Final releases are root owned, directory 0755/file 0644, and proven readable
  but not writable by a real non-root worker identity.
- Activate/check consume the receipt-embedded trusted manifest and reject a
  substituted bundle, release, mode, owner, pointer, lock or transaction.
- Every command shares a finite process deadline; NaN, Inf, non-positive and
  excessive limits fail before side effects.
- Inline script/style compatibility uses exact generated hashes and is tested
  in real Chromium; no unsafe-inline exception is added.
- Apex certificate issuance uses the proven Domestic
  /usr/local/bin/certbot 5.8.0 and a separately gated Tokyo ACME-only forward,
  never an early DNS switch.
- Any unresolved dynamic route forces cutover HOLD. The cross-object contract
  remains NOT_AUTHORIZED and intentionally provides no installer/sudo entry.
- Apex Nginx/TLS candidates use only the new server name and root namespace;
  `winctl` files and its certificate names are absent from mutation lists.
- Preview pages, controlled APIs, feedback persistence and real dynamic
  backends remain explicitly incomplete and are never reported as deployed.
