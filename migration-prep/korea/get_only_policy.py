"""Single controlled HTTPS GET transport for the Korea candidate.

It uses raw sockets (therefore no environment proxy), pins DNS results to a
root-supplied IP allowlist, performs normal hostname/certificate verification,
and never follows redirects.  Root-controlled egress remains a separate gate.
"""
from __future__ import print_function

import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit


ALLOWED_HOSTS = frozenset(("fapi.binance.com",))
ALLOWED_PATHS = frozenset((
    "/fapi/v1/time", "/fapi/v3/account", "/fapi/v3/balance",
    "/fapi/v1/positionSide/dual", "/fapi/v3/positionRisk",
    "/fapi/v1/openOrders", "/fapi/v1/openAlgoOrders",
    "/fapi/v1/allOrders", "/fapi/v1/userTrades"
))
REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class PolicyDenied(Exception):
    pass


def validate_request(method, url):
    if type(method) is not str or method != "GET":
        raise PolicyDenied("NON_GET_FORBIDDEN")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise PolicyDenied("HTTPS_HOST_NOT_ALLOWLISTED")
    if parsed.path not in ALLOWED_PATHS:
        raise PolicyDenied("PATH_NOT_ALLOWLISTED")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise PolicyDenied("URL_AUTH_OR_PORT_FORBIDDEN")
    if parsed.fragment:
        raise PolicyDenied("URL_FRAGMENT_FORBIDDEN")
    return {"method": method, "host": parsed.hostname, "path": parsed.path,
            "query_present": bool(parsed.query), "decision": "ALLOW_GET_ONLY"}


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, pinned_ip, port, timeout, context):
        self._pinned_ip = pinned_ip
        http.client.HTTPSConnection.__init__(self, host, port=port, timeout=timeout,
                                             context=context)

    def connect(self):
        raw = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class ControlledHttpsTransport(object):
    """The only candidate transport; its public API exposes GET only."""
    def __init__(self, host, allowed_ip_addresses, timeout_seconds=10):
        if host not in ALLOWED_HOSTS:
            raise PolicyDenied("TRANSPORT_HOST_NOT_ALLOWLISTED")
        if type(timeout_seconds) is not int or not 0 < timeout_seconds <= 30:
            raise PolicyDenied("TRANSPORT_TIMEOUT_INVALID")
        if not isinstance(allowed_ip_addresses, (list, tuple, set, frozenset)) or not allowed_ip_addresses:
            raise PolicyDenied("DNS_IP_ALLOWLIST_REQUIRED")
        try:
            self.allowed_ips = frozenset(str(ipaddress.ip_address(value))
                                         for value in allowed_ip_addresses)
        except ValueError:
            raise PolicyDenied("DNS_IP_ALLOWLIST_INVALID")
        self.host, self.timeout_seconds, self.receipts = host, timeout_seconds, []
        self.proxy_policy = "ENVIRONMENT_PROXY_BYPASSED_RAW_SOCKET"
        self.redirect_policy = "DENY_ALL_REDIRECTS"
        self.tls_policy = "SYSTEM_CA_HOSTNAME_VERIFICATION_REQUIRED"

    def _select_pinned_ip(self, resolved_addresses):
        try:
            observed = frozenset(str(ipaddress.ip_address(value)) for value in resolved_addresses)
        except ValueError:
            raise PolicyDenied("DNS_RESULT_INVALID")
        if not observed or not observed.issubset(self.allowed_ips):
            raise PolicyDenied("DNS_RESULT_NOT_PINNED")
        return sorted(observed)[0], sorted(observed)

    def _resolve(self):
        records = socket.getaddrinfo(self.host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return self._select_pinned_ip([record[4][0] for record in records])

    @staticmethod
    def _validate_status(status):
        if type(status) is not int:
            raise PolicyDenied("HTTP_STATUS_INVALID")
        if status in REDIRECT_STATUSES:
            raise PolicyDenied("HTTP_REDIRECT_FORBIDDEN")
        if not 200 <= status < 300:
            raise PolicyDenied("HTTP_NON_SUCCESS_FORBIDDEN")

    def get(self, url, headers=None, timeout_seconds=None):
        decision = validate_request("GET", url)
        if decision["host"] != self.host:
            raise PolicyDenied("TRANSPORT_HOST_MISMATCH")
        safe_headers = dict(headers or {})
        if any(str(name).lower() in ("host", "connection", "proxy-authorization")
               for name in safe_headers):
            raise PolicyDenied("CALLER_TRANSPORT_HEADER_FORBIDDEN")
        pinned_ip, resolved = self._resolve()
        context = ssl.create_default_context()
        if hasattr(context, "minimum_version") and hasattr(ssl, "TLSVersion"):
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        parsed = urlsplit(url)
        request_target = parsed.path + (("?" + parsed.query) if parsed.query else "")
        effective_timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        if not isinstance(effective_timeout, (int, float)) or not 0 < effective_timeout <= self.timeout_seconds:
            raise PolicyDenied("TRANSPORT_REQUEST_TIMEOUT_INVALID")
        started_monotonic = time.monotonic()
        connection = PinnedHTTPSConnection(self.host, pinned_ip, 443,
                                           effective_timeout, context)
        try:
            connection.request("GET", request_target, headers=safe_headers)
            response = connection.getresponse()
            self._validate_status(response.status)
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise PolicyDenied("HTTP_RESPONSE_TOO_LARGE")
            certificate = connection.sock.getpeercert(binary_form=True)
            if not certificate:
                raise PolicyDenied("TLS_PEER_CERTIFICATE_REQUIRED")
            finished_monotonic = time.monotonic()
            if finished_monotonic - started_monotonic > effective_timeout:
                raise PolicyDenied("HTTP_REQUEST_DEADLINE_EXCEEDED")
            receipt = {"method": "GET", "host": self.host, "path": parsed.path,
                       "status": response.status, "resolved_ip_sha256":
                           hashlib.sha256(pinned_ip.encode("ascii")).hexdigest(),
                       "resolved_set_sha256": hashlib.sha256(
                           "\n".join(resolved).encode("ascii")).hexdigest(),
                       "tls_peer_certificate_sha256": hashlib.sha256(certificate).hexdigest(),
                       "proxy_used": False, "redirect_followed": False,
                       "root_egress_isolation_proven": False,
                       "request_timeout_seconds": effective_timeout,
                       "elapsed_ms": int((finished_monotonic - started_monotonic) * 1000),
                       "body_sha256": hashlib.sha256(body).hexdigest()}
            self.receipts.append(receipt)
            return body, receipt
        finally:
            connection.close()
