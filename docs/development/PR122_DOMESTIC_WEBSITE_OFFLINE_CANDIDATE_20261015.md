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
4. Test prepare, activate, check and rollback against temporary root trees,
   including lock timeout, partial activation and unknown-current fail-closed
   behavior.
5. Publish only the offline candidate commit and bundle receipt. Production
   installation, certificate issuance, Nginx changes, permission changes and
   DNS changes require a separate Release Gate.

## 3 Acceptance

- A status request failure or malformed response never displays connected,
  exposes stale account text, or enables disconnect.
- The source archive remains byte-identical and is referenced by its existing
  SHA-256; the delta bundle has its own deterministic manifest and hash.
- Release preparation rejects unsafe archive members, baseline drift, extra or
  missing files, hash mismatch, timeout and existing release collisions.
- Activation and rollback use exact symlink identity checks. Any partial or
  unknown state stops further writes and emits a non-PASS receipt.
- Apex Nginx/TLS candidates use only the new server name and root namespace;
  `winctl` files and its certificate names are absent from mutation lists.
- Preview pages, controlled APIs, feedback persistence and real dynamic
  backends remain explicitly incomplete and are never reported as deployed.
