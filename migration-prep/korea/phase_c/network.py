"""Compile a dedicated inet egress table, without invoking nft or changing rules."""
import ipaddress
import time

from gate_common import require
from korea.get_only_policy import ControlledHttpsTransport
from korea.phase_c.security import hash_value, identifier


def validate_policy(policy, now_ms=None):
    require(set(policy) == {"schema_version", "table", "broker_uid", "worker_uid",
                            "pinned_ips", "issued_at_ms", "expires_at_ms"}, "C_NETWORK_FIELDS")
    require(policy["schema_version"] == 1, "C_NETWORK_SCHEMA")
    identifier(policy["table"])
    require(policy["table"].startswith("xj_pr99_c_") and
            all(c.isalnum() or c == "_" for c in policy["table"]), "C_NETWORK_TABLE")
    require(type(policy["broker_uid"]) is int and policy["broker_uid"] == 986 and
            type(policy["worker_uid"]) is int and 1 <= policy["worker_uid"] <= 60000 and
            policy["worker_uid"] not in (986, 1000, 1001), "C_DISTINCT_UIDS_REQUIRED")
    now = int(time.time() * 1000) if now_ms is None else now_ms
    require(type(policy["issued_at_ms"]) is int and type(policy["expires_at_ms"]) is int and
            policy["issued_at_ms"] <= now < policy["expires_at_ms"] and
            0 < policy["expires_at_ms"] - policy["issued_at_ms"] <= 7 * 86400000,
            "C_NETWORK_EXPIRED")
    require(isinstance(policy["pinned_ips"], list) and 1 <= len(policy["pinned_ips"]) <= 32,
            "C_IP_ALLOWLIST_REQUIRED")
    pins = []
    for value in policy["pinned_ips"]:
        address = ipaddress.ip_address(value)
        require(address.is_global and str(address) == value, "C_IP_PUBLIC_CANONICAL_REQUIRED")
        pins.append(value)
    require(len(set(pins)) == len(pins), "C_DUPLICATE_IP")
    return policy


def compile_rules(policy, now_ms=None):
    validate_policy(policy, now_ms)
    table = policy["table"]
    lines = ["create table inet " + table,
             "create chain inet %s output { type filter hook output priority 0; policy accept; }" % table]
    for address in sorted(policy["pinned_ips"]):
        family = "ip6" if ipaddress.ip_address(address).version == 6 else "ip"
        lines.append("add rule inet %s output meta skuid %d %s daddr %s tcp dport 443 counter accept" %
                     (table, policy["broker_uid"], family, address))
    # Worker has only AF_UNIX in its unit; nft also rejects both IP families.
    for uid in (policy["broker_uid"], policy["worker_uid"]):
        lines.append("add rule inet %s output meta skuid %d counter drop" % (table, uid))
    return "\n".join(lines) + "\n"


class ApprovedPinnedTransport(ControlledHttpsTransport):
    """No DNS exemption: connect only to the immutable, expiring approved pin set."""
    def __init__(self, policy, clock_ms=None):
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        validate_policy(policy, self.clock_ms())
        self.policy = dict(policy, pinned_ips=list(policy["pinned_ips"]))
        self.policy_sha256 = hash_value(self.policy)
        super().__init__("fapi.binance.com", self.policy["pinned_ips"])

    def _resolve(self):
        validate_policy(self.policy, self.clock_ms())
        return sorted(self.allowed_ips)[0], sorted(self.allowed_ips)
