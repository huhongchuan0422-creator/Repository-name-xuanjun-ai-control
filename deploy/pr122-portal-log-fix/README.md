# PR122 legacy Portal logging correction candidate

The live Tokyo Portal has only GET and POST handlers. Unsupported methods should
produce the standard 501 response. Its existing error logger instead replaces
the integer status argument with a string and raises TypeError for `%d`, so Nginx
receives a disconnected upstream and returns 502. This is an existing backend
error path, reproduced independently of the Domestic proxy.

This candidate changes only `PortalHandler.log_message`: preserve exact built-in
numeric arguments, redact all other arguments, fall back to a redacted message
for malformed formatting, and tolerate an invalid URL while logging an error.
The existing path-only log is retained; query and request-line values are not
added. Existing route-path privacy limitations are not claimed fixed.

The audited replacement OAuth candidate is not the live Portal. Installing that
runtime would change sessions, storage and credentials, so it is not reused to
fix this single logging function. The existing backend and website remain the
authority. No runtime wrapper, additional daemon, queue or database is introduced.

`scripts/pr122_legacy_portal_log_fix.py` only constructs bytes in memory. It has
no installer or CLI and requires the exact server-source SHA256 below. A source
mismatch stops before replacement. `portal-log-message.patch` is a review diff,
not authorization to apply with fuzzy matching.

- Source SHA256: `528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006`
- Corrected SHA256: `d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0`
- Source: Owner-uploaded exact entry; also independently read on Tokyo Runner.
- Regression: 16 tests, including actual isolated HTTP disconnect versus 501,
  HEAD/OPTIONS/DELETE/PATCH/TRACE/CONNECT, GET preservation, argument redaction,
  malformed formats, invalid URL logging, exact-byte guard and AST preservation.
- Test server: temporary loopback address with OS-selected port; no Portal DB,
  production imports, credentials or real business requests.

Run only against the pinned readable source, without production imports:

```sh
PR122_PORTAL_SOURCE=/opt/trading-system/scripts/secure_secrets_portal_server.py \
python3 -B -m unittest discover -s tests -p test_legacy_portal_logging_regression.py -v
```

The tests extract only the logger AST into a local fake server. They do not run
the actual application, verify live authorization, install the correction, or
restart the production service. The builder and generated source are not
executed as an application.

Production remains HOLD. Before installation, independent review must accept
this exact candidate, the existing approved release path must bind original and
replacement bytes plus a protected backup, and a permitted root channel must be
available. After a separately approved atomic source replacement and service
restart, targeted live GET/HEAD and rollback checks are still required. This
candidate does not approve DNS changes, client-IP audit differences, live
OAuth/credential/message/payment/trading requests, or Tokyo retirement.
