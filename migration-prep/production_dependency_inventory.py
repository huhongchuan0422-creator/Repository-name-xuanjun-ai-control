"""Build private and path-redacted Tokyo Binance production dependency evidence.

This collector is read-only.  It inventories the frozen 95 potential Writer
sources, current process references, readable systemd/cron triggers, static
imports, data-path references and credential *names* (never values).  Absence in
the caller view is recorded as UNKNOWN until Root/Gateway/GitHub administration
coverage is complete.
"""
from __future__ import print_function

import argparse
import ast
import hashlib
import json
import os
import re
import socket
from datetime import datetime, timezone


DATA_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".jsonl", "-wal", "-shm")
CREDENTIAL_NAME = re.compile(
    r"^(?:BINANCE|BITGET|TRADING|FINANCE|OWNER|SECRET|CREDENTIAL|API)[A-Z0-9_]*(?:KEY|SECRET|TOKEN|REF|ID|PATH)?$")
WRITE_MARKERS = (
    "new_order", "create_order", "place_order", "cancel_order", "cancel_all",
    "change_leverage", "change_margin", "/fapi/v1/order", "/fapi/v1/allOpenOrders",
    "STOP_MARKET", "TAKE_PROFIT_MARKET", "reduceOnly", "closePosition")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def read_bytes(path):
    with open(path, "rb") as stream:
        return stream.read()


def safe_text(path):
    try:
        return read_bytes(path).decode("utf-8", "replace")
    except (OSError, IOError):
        return ""


def source_facts(path):
    raw = read_bytes(path)
    text = raw.decode("utf-8", "replace")
    imports, strings = [], []
    syntax = "PASS"
    try:
        tree = ast.parse(text, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(("." * node.level) + (node.module or ""))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.append(node.value)
    except SyntaxError:
        syntax = "FAIL"
    credential_names = sorted(set(
        token for value in strings for token in re.findall(r"[A-Z][A-Z0-9_]{3,}", value)
        if CREDENTIAL_NAME.match(token)))
    data_paths = sorted(set(
        value for value in strings if value.startswith("/") and
        (value.endswith(DATA_SUFFIXES) or "/database/" in value or "/runtime/" in value)))
    return {
        "source_sha256": sha256_bytes(raw),
        "size": len(raw),
        "syntax": syntax,
        "has_main_guard": "if __name__" in text and "__main__" in text,
        "imports": sorted(set(imports)),
        "credential_reference_names": credential_names,
        "data_path_references": data_paths,
        "write_markers": [marker for marker in WRITE_MARKERS if marker in text],
    }


def readable_trigger_sources():
    paths = []
    for root in ("/etc/systemd/system", "/usr/lib/systemd/system", "/etc/cron.d",
                 "/etc/cron.daily", "/etc/cron.hourly", "/etc/cron.weekly",
                 "/etc/cron.monthly"):
        if not os.path.isdir(root):
            continue
        for base, unused_dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(base, name)
                if os.path.islink(path):
                    continue
                paths.append(path)
    return sorted(set(paths))


def process_path_index(roots):
    result = {}
    own = {os.getpid(), os.getppid()}
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) in own:
            continue
        try:
            parts = [part.decode("utf-8", "replace") for part in
                     read_bytes("/proc/{0}/cmdline".format(name)).split(b"\0") if part]
            matches = []
            for part in parts:
                for root in roots:
                    if part.startswith(root):
                        matches.append(part)
            for path in set(matches):
                result.setdefault(path, []).append(int(name))
        except (OSError, IOError):
            continue
    return result


def trigger_index(trigger_paths, source_paths):
    result = {path: [] for path in source_paths}
    entrypoints = []
    for trigger in trigger_paths:
        text = safe_text(trigger)
        for path in source_paths:
            if path in text:
                result[path].append(trigger)
        for match in re.findall(r"/(?:opt/trading-system|home/admin/\.openclaw/workspace/binance-eth-trader)/[^\s;'\"]+\.py", text):
            entrypoints.append({"source_path": match, "trigger_path": trigger})
    return result, sorted(entrypoints, key=lambda item: (item["source_path"], item["trigger_path"]))


def build(private_map, gateway_total, gateway_visible, gateway_scope,
          protected_secret_store_count):
    roots = private_map["roots"]
    source_paths = [item["source_path"] for item in private_map["records"]]
    processes = process_path_index(roots)
    triggers, triggered_entries = trigger_index(readable_trigger_sources(), source_paths)
    records = []
    for source in private_map["records"]:
        path = source["source_path"]
        exists = os.path.isfile(path)
        facts = source_facts(path) if exists else {
            "source_sha256": None, "size": None, "syntax": "NOT_READABLE",
            "has_main_guard": False, "imports": [], "credential_reference_names": [],
            "data_path_references": [], "write_markers": []}
        runtime_pids = sorted(processes.get(path, []))
        trigger_paths = sorted(triggers.get(path, []))
        if runtime_pids:
            disposition = "PRODUCTION_REQUIRED_OBSERVED_RUNTIME"
        elif trigger_paths:
            disposition = "CONDITIONAL_DEPENDENCY_OBSERVED_TRIGGER"
        else:
            disposition = "NOT_CONFIRMED_PRODUCTION_DEPENDENCY_GLOBAL_COVERAGE_UNKNOWN"
        records.append({
            "path_id": source["path_id"], "source_path": path,
            "source_path_sha256": sha256_bytes(path.encode("utf-8")),
            "path_class": source["path_class"], "static_role": source["static_role"],
            "exists_and_readable": exists, "current_source_sha256": facts["source_sha256"],
            "frozen_source_sha256": source["source_sha256"],
            "frozen_bytes_match": facts["source_sha256"] == source["source_sha256"],
            "size": facts["size"], "syntax": facts["syntax"],
            "has_main_guard": facts["has_main_guard"], "imports": facts["imports"],
            "data_path_references": facts["data_path_references"],
            "credential_reference_names": facts["credential_reference_names"],
            "write_markers": facts["write_markers"], "runtime_pids": runtime_pids,
            "readable_trigger_paths": trigger_paths,
            "runtime_reachability": ("OBSERVED_ACTIVE_CURRENT_USER_SCOPE" if runtime_pids else
                                     "NOT_OBSERVED_CURRENT_USER_SCOPE_GLOBAL_UNKNOWN"),
            "scheduler_reachability": ("OBSERVED_READABLE_TRIGGER" if trigger_paths else
                                       "NOT_OBSERVED_READABLE_SCOPE_ROOT_GATEWAY_UNKNOWN"),
            "credential_reachability": ("REFERENCE_NAMES_FOUND_ACCESS_NOT_PROVEN" if
                                        facts["credential_reference_names"] else
                                        "NO_REFERENCE_NAME_FOUND_STATIC_ONLY"),
            "migration_disposition": disposition,
            "candidate_enforcement": "DENY_UNTIL_COMPLETE_DEPENDENCY_AND_TRIGGER_CLOSURE",
        })
    inventory = {
        "schema_version": 1,
        "task_id": "TOKYO_KOREA_COMPLETE_MIGRATION_REVIEW_PACKAGE_6171881293",
        "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "host": socket.gethostname(), "writer_count": len(records),
        "writer_records": records, "observed_systemd_entrypoints": triggered_entries,
        "gateway_inventory": {"reported_total": gateway_total, "visible": gateway_visible,
                              "scope": gateway_scope,
                              "complete": gateway_scope == "global" and gateway_total == gateway_visible},
        "protected_secret_store_metadata_count": protected_secret_store_count,
        "root_cron_complete": False, "github_runner_admin_complete": False,
        "production_dependency_closure": False,
        "production_execution_authorized": False,
        "limitations": [
            "ROOT_CRON_SYSTEMD_SUDOERS_COMPLETE_EXPORT_REQUIRED",
            "GATEWAY_GLOBAL_TRIGGER_COMPLETE_PAGINATION_REQUIRED",
            "GITHUB_RUNNER_ADMIN_POLICY_EXPORT_REQUIRED",
            "CREDENTIAL_REFERENCE_REACHABILITY_REQUIRES_ADMIN_METADATA",
            "ZERO_OBSERVED_ACTIVE_WRITER_DOES_NOT_PROVE_ABSENCE"],
    }
    unsigned = dict(inventory)
    inventory["inventory_sha256"] = sha256_bytes(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return inventory


def public_view(inventory):
    rows = []
    for item in inventory["writer_records"]:
        rows.append({
            "path_id": item["path_id"], "source_path_sha256": item["source_path_sha256"],
            "path_class": item["path_class"], "static_role": item["static_role"],
            "exists_and_readable": item["exists_and_readable"],
            "current_source_sha256": item["current_source_sha256"],
            "frozen_source_sha256": item["frozen_source_sha256"],
            "frozen_bytes_match": item["frozen_bytes_match"], "syntax": item["syntax"],
            "has_main_guard": item["has_main_guard"],
            "import_name_sha256": [sha256_bytes(value.encode("utf-8")) for value in item["imports"]],
            "data_path_sha256": [sha256_bytes(value.encode("utf-8")) for value in item["data_path_references"]],
            "credential_reference_name_sha256": [sha256_bytes(value.encode("utf-8")) for value in item["credential_reference_names"]],
            "write_markers": item["write_markers"],
            "runtime_observed_pid_count": len(item["runtime_pids"]),
            "readable_trigger_count": len(item["readable_trigger_paths"]),
            "runtime_reachability": item["runtime_reachability"],
            "scheduler_reachability": item["scheduler_reachability"],
            "credential_reachability": item["credential_reachability"],
            "migration_disposition": item["migration_disposition"],
            "candidate_enforcement": item["candidate_enforcement"],
        })
    value = {key: inventory[key] for key in (
        "schema_version", "task_id", "observed_at_utc", "host", "writer_count",
        "gateway_inventory", "protected_secret_store_metadata_count",
        "root_cron_complete", "github_runner_admin_complete",
        "production_dependency_closure", "production_execution_authorized", "limitations")}
    value["writer_records"] = rows
    value["private_inventory_sha256"] = inventory["inventory_sha256"]
    value["source_paths_redacted"] = True
    return value


def write_json(path, value):
    with open(path, "w") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def render_private_markdown(inventory):
    lines = [
        "# Tokyo Binance actual production dependency register",
        "",
        "- Task: `{0}`".format(inventory["task_id"]),
        "- Host: `{0}`".format(inventory["host"]),
        "- Observed UTC: `{0}`".format(inventory["observed_at_utc"]),
        "- Frozen potential Writer coverage: `{0}/95`".format(inventory["writer_count"]),
        "- Production dependency closure: `{0}`".format(
            str(inventory["production_dependency_closure"]).upper()),
        "- Gateway: reported `{0}`, caller-visible `{1}`, scope `{2}`".format(
            inventory["gateway_inventory"]["reported_total"],
            inventory["gateway_inventory"]["visible"],
            inventory["gateway_inventory"]["scope"]),
        "- Protected Secret Store metadata entries visible: `{0}`".format(
            inventory["protected_secret_store_metadata_count"]),
        "",
        "`NOT_OBSERVED` is not absence. Root cron/systemd/sudoers, Gateway global",
        "trigger, GitHub Runner administration and credential reachability remain",
        "UNKNOWN until their named administrators return complete receipts.",
        "",
        "## Readable systemd entrypoints under the two source roots",
        ""]
    for item in inventory["observed_systemd_entrypoints"]:
        lines.append("- `{0}` <- `{1}`".format(
            item["source_path"], item["trigger_path"]))
    lines.extend(["", "## All 95 potential Writer sources", ""])
    for item in inventory["writer_records"]:
        lines.extend([
            "### {0}".format(item["path_id"]),
            "- Actual path: `{0}`".format(item["source_path"]),
            "- Class / static role: `{0}` / `{1}`".format(
                item["path_class"], item["static_role"]),
            "- Bytes: current `{0}`; frozen `{1}`; match `{2}`".format(
                item["current_source_sha256"], item["frozen_source_sha256"],
                str(item["frozen_bytes_match"]).upper()),
            "- Entrypoint: main guard `{0}`; runtime `{1}`; scheduler `{2}`".format(
                str(item["has_main_guard"]).upper(), item["runtime_reachability"],
                item["scheduler_reachability"]),
            "- Runtime PIDs: `{0}`".format(item["runtime_pids"] or "NONE_OBSERVED"),
            "- Readable triggers: `{0}`".format(
                item["readable_trigger_paths"] or "NONE_OBSERVED"),
            "- Imports/dependencies: `{0}`".format(item["imports"] or "NONE_STATIC"),
            "- Data references: `{0}`".format(
                item["data_path_references"] or "NONE_STATIC"),
            "- Credential reference names only: `{0}`".format(
                item["credential_reference_names"] or "NONE_STATIC"),
            "- Write markers: `{0}`".format(item["write_markers"] or "NONE_STATIC"),
            "- Current disposition: `{0}`".format(item["migration_disposition"]),
            "- Enforcement: `{0}`".format(item["candidate_enforcement"]),
            ""])
    lines.extend(["## Unclosed evidence", ""])
    lines.extend("- `{0}`".format(value) for value in inventory["limitations"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("private_map")
    parser.add_argument("private_output")
    parser.add_argument("public_output")
    parser.add_argument("--gateway-total", required=True, type=int)
    parser.add_argument("--gateway-visible", required=True, type=int)
    parser.add_argument("--gateway-scope", required=True)
    parser.add_argument("--protected-secret-store-count", required=True, type=int)
    parser.add_argument("--private-markdown-output")
    args = parser.parse_args()
    with open(args.private_map, "r") as stream:
        private_map = json.load(stream)
    value = build(private_map, args.gateway_total, args.gateway_visible,
                  args.gateway_scope, args.protected_secret_store_count)
    if value["writer_count"] != 95:
        raise SystemExit("WRITER_COUNT_NOT_95")
    write_json(args.private_output, value)
    write_json(args.public_output, public_view(value))
    if args.private_markdown_output:
        with open(args.private_markdown_output, "w") as stream:
            stream.write(render_private_markdown(value))


if __name__ == "__main__":
    main()
