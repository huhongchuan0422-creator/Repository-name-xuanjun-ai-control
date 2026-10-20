"""Build an exact legacy logging candidate in memory; never install or import it."""
import hashlib

SOURCE_SHA256 = "528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006"

OLD_METHOD = '''    def log_message(self, fmt, *args):
        path = urllib.parse.urlsplit(self.path).path
        sys.stderr.write("%s - - [%s] %s\\n" % (
            self.client_address[0],
            self.log_date_time_string(),
            fmt % args if "%s" not in fmt else fmt % tuple("[REDACTED]" for _ in args),
        ))
        sys.stderr.write("path=%s\\n" % path)
'''

NEW_METHOD = '''    def log_message(self, fmt, *args):
        try:
            path = urllib.parse.urlsplit(self.path).path
        except ValueError:
            path = "[INVALID_PATH]"
        safe_args = tuple(
            arg if type(arg) in (int, float) else "[REDACTED]" for arg in args
        )
        try:
            message = fmt % safe_args
        except (TypeError, ValueError, OverflowError):
            message = "[REDACTED]"
        sys.stderr.write("%s - - [%s] %s\\n" % (
            self.client_address[0],
            self.log_date_time_string(),
            message,
        ))
        sys.stderr.write("path=%s\\n" % path)
'''


def build_candidate(source):
    """Require exact server bytes and replace only the known logging method."""
    if not isinstance(source, bytes):
        raise TypeError("SOURCE_BYTES_REQUIRED")
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("SOURCE_SHA256_MISMATCH")
    old, new = OLD_METHOD.encode(), NEW_METHOD.encode()
    if source.count(old) != 1:
        raise ValueError("EXACT_LOG_METHOD_REQUIRED")
    return source.replace(old, new, 1)
