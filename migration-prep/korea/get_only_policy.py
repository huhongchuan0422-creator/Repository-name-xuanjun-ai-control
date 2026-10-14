"""Application-layer HTTPS request policy for Korea shadow runtime."""
from __future__ import print_function

from urllib.parse import urlsplit


ALLOWED_HOSTS = frozenset(("fapi.binance.com",))
ALLOWED_PATHS = frozenset((
    "/fapi/v1/time", "/fapi/v3/account", "/fapi/v3/balance",
    "/fapi/v1/positionSide/dual", "/fapi/v3/positionRisk",
    "/fapi/v1/openOrders", "/fapi/v1/openAlgoOrders",
    "/fapi/v1/allOrders", "/fapi/v1/userTrades"
))


class PolicyDenied(Exception):
    pass


def validate_request(method, url):
    if method != "GET":
        raise PolicyDenied("NON_GET_FORBIDDEN")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise PolicyDenied("HTTPS_HOST_NOT_ALLOWLISTED")
    if parsed.path not in ALLOWED_PATHS:
        raise PolicyDenied("PATH_NOT_ALLOWLISTED")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise PolicyDenied("URL_AUTH_OR_PORT_FORBIDDEN")
    return {"method": method, "host": parsed.hostname, "path": parsed.path,
            "query_present": bool(parsed.query), "decision": "ALLOW_GET_ONLY"}
