# B5 fixed 19 offline candidate

This directory binds the reader delta to the previously reviewed source
bytes. `SOURCE_MANIFEST.json` records each logical release path, its bundle
path, size, and SHA-256. The original 32 source files came from the pinned
source archive; the four local release overrides and original B5 helpers are
separate entries. It is a draft source review unit, **not** a production
release or permission to activate the new batch.

The targeted tests run directly from this directory:

```
python -B test_old_policy_dependency_reader.py -v
python -B test_original_capability_preflight.py -v
python -B test_canonical_prestart_proof.py -v
```

The prestart observation A authenticates the original database pin, enforces
aggregate size and row bounds before returning request bodies to Python, and
uses a monotonic deadline and SQLite progress handler. It returns HOLD before
connecting to a live WAL database because SQLite read markers can modify its
SHM file even in read-only mode. The locked observation B independently reads
the complete bounded set after the worker has exited and the original lock
and database FD have been proven.

The original maintenance caller, deployment identity and permissions, grant,
new batch acknowledgements, 19 bodies, original custody, live WAL coordination,
independent review, and installation are not established by this commit. In
particular the earlier runtime code pin and release manifest cannot be reused
for these changed bytes. A reviewed complete release and external binder must
be generated only from the final exact source and actual commit identity.
