# Actual saved R7 evidence: 2026-10-15

This packet is the exact successful saved-data export for observation `8df3b22b3762070f`, nonce `cee45858d9d19863e977e2648bc2196a`. It is 294,949 bytes including LF, SHA-256 `45b832dce9577b49e6ee718f1637862eebd775c6c10f87d9150ed0a87476fdf7`. The JSON line without LF is 294,948 bytes, SHA-256 `66a75e7c6269b5e592835b5b777c2d7ef49a5969bba624d10135369c3d18f475`. Integer values are preserved exactly.

Both Python 3.6.8 and 3.12.14 independently recomputed the same seven subset hashes using the published offline verifier. The strict metadata schema also passed for the full packet and decoded 93,423-byte probe receipt. See `verification.json` for exact hashes and counts.

## Observed evidence

- Eight finite cases: cases 1–5 and 7 recorded PASS; cases 6 and 8 recorded the expected BrokenPipe rejection.
- Nine server records: three SERVER_READY and six PEER_ACCESS_PROOF.
- 129 receipt events, 35 resources, and 40 successful cleanup rows (34 REMOVED and six STOPPED_AND_EMPTY).
- Node SQLite PASS_OBSERVED with OBSERVED cleanup. Failure and incomplete_case are null.
- Saved collector proof covers exactly 11 units and 33 drop-in roots.

## Reproduce offline

Use exact exporter publication `876109b10a3fc95fe6b2a77c1d2d72cbdc281f80` and the immutable R7 archive from artifact publication `ec3f0c3ceb1842fc5c0cb5e2f2a5c37792494eac`. From a checkout of the former, with this packet available locally:

```sh
python3 -I -B -S evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7/verify_exported_evidence.py packet.json evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz 45b832dce9577b49e6ee718f1637862eebd775c6c10f87d9150ed0a87476fdf7
```

The last argument is the separately measured digest of the exact received packet bytes. Do not take it from an untrusted packet. The verifier binds the archive and exporter, validates exact packet fields, and recomputes only the exported subset. It performs no network access or host action.

## Limits

The whole private observation remains unavailable: raw file and normalized hashes are authenticated/exporter-reported bindings, not independently reconstructed evidence. The saved inventory does not provide fresh directory-authority stamps. Future final-plan preparation and its fresh-versus-saved comparison require separate implementation and review. The unsigned expected-review body is a proposal for independent review, not an approval. This packet supplies no production admission or resume authority. Earlier failed observations remain HOLD and are not explained retroactively by this successful attempt. No additional collection, probe or installation was performed for this export or offline verification.

The public packet contains only metadata accepted by the fixed strict schema, including finite unit/resource paths, numeric IDs, namespace and capability metadata, file modes/timestamps/hashes, and known event/status labels. It includes the fixed hostname, public PATH value, allowlisted service/group fields, and fixed probe ExecStart metadata. It excludes the complete observation, secret or arbitrary configuration bodies, arbitrary environment values, and raw command output.
