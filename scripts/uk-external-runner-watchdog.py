#!/usr/bin/env python3
"""Bounded, event-started UK Runner receipt monitor; no model or host access."""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request

REPO = "huhongchuan0422-creator/Repository-name-xuanjun-ai-control"
OWNER = "huhongchuan0422-creator"
TASK = "XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1"
PR = 17
EVENT = re.compile(r"<!-- XJ_GH_TASK_EVENT (\{[^\n]{1,2048}\}) -->")
ALERT = re.compile(r"<!-- XJ_GH_WATCHDOG_ALERT (\{[^\n]{1,2048}\}) -->")
STATES = {"SUBMITTED", "RECEIVED", "STARTED", "PROGRESS", "COMPLETE", "FAIL", "HOLD"}
TERMINAL = {"COMPLETE", "FAIL", "HOLD"}
TRUSTED_RECEIPT_LOGINS = {OWNER, "github-actions[bot]"}
POLL_SECONDS = 20
MAX_MONITOR_SECONDS = 3600


def _stamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse(comments):
    events, alerted = [], set()
    for c in comments:
        body = c.get("body") or ""
        login = ((c.get("user") or {}).get("login") or "")
        try:
            stamp = _stamp(c["created_at"])
        except (ValueError, KeyError, AttributeError):
            continue
        if login in TRUSTED_RECEIPT_LOGINS:
            for m in EVENT.finditer(body):
                try:
                    x = json.loads(m.group(1))
                    if (x.get("task_id") == TASK and x.get("state") in STATES
                            and x.get("source") == "AUTHORIZED_EXECUTION_RECEIPT"
                            and re.fullmatch(r"[A-Za-z0-9._-]{8,128}", x.get("attempt", ""))):
                        events.append((stamp, x))
                except (TypeError, ValueError):
                    continue
        for m in ALERT.finditer(body) if login in TRUSTED_RECEIPT_LOGINS else []:
            try:
                x = json.loads(m.group(1))
                if x.get("task_id") == TASK:
                    alerted.add((x.get("attempt"), x.get("kind")))
            except (TypeError, ValueError):
                continue
    return sorted(events, key=lambda x: x[0]), alerted


def submitted_attempt(event):
    """Accept only an Owner-created PR17 SUBMITTED event as the monitor anchor."""
    if (event.get("action") != "created" or
            (event.get("issue") or {}).get("number") != PR or
            (event.get("sender") or {}).get("login") != OWNER or
            ((event.get("comment") or {}).get("user") or {}).get("login") != OWNER):
        return None
    body = (event.get("comment") or {}).get("body") or ""
    for match in EVENT.finditer(body):
        try:
            item = json.loads(match.group(1))
        except (TypeError, ValueError):
            continue
        if (item.get("task_id") == TASK and item.get("state") == "SUBMITTED" and
                item.get("source") == "AUTHORIZED_EXECUTION_RECEIPT" and
                re.fullmatch(r"[A-Za-z0-9._-]{8,128}", item.get("attempt", ""))):
            return item["attempt"]
    return None


def detect(events, alerted, now, only_attempt=None):
    grouped, findings = {}, []
    for stamp, item in events:
        grouped.setdefault(item["attempt"], []).append((stamp, item["state"]))
    for attempt, seq in grouped.items():
        if only_attempt is not None and attempt != only_attempt:
            continue
        if any(state in TERMINAL for _, state in seq):
            continue
        submitted = next((stamp for stamp, state in seq if state == "SUBMITTED"), None)
        if submitted is None:
            continue
        received = next((stamp for stamp, state in seq if state == "RECEIVED"), None)
        started = next((stamp for stamp, state in seq if state == "STARTED"), None)
        progress = max((stamp for stamp, state in seq if state in ("STARTED", "PROGRESS")),
                       default=None)
        kinds = []
        if received is None and (now - submitted).total_seconds() >= 120:
            kinds.append("RECEIVE_TIMEOUT_2M")
        if started is None and (now - submitted).total_seconds() >= 300:
            kinds.append("START_TIMEOUT_5M")
        if started is not None and progress is not None and (now - progress).total_seconds() >= 600:
            kinds.append("PROGRESS_TIMEOUT_10M")
        if (now - submitted).total_seconds() >= MAX_MONITOR_SECONDS:
            kinds.append("TERMINAL_TIMEOUT_60M")
        for kind in kinds:
            if (attempt, kind) not in alerted:
                findings.append((attempt, kind))
    return findings


def is_terminal(events, attempt):
    return any(item["attempt"] == attempt and item["state"] in TERMINAL
               for _, item in events)


def gh(token, suffix, method="GET", body=None):
    url = "https://api.github.com/repos/" + REPO + suffix
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "xuanjun-mechanical-watchdog"}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def fetch_comments(token):
    rows = []
    for page in range(1, 11):
        batch = gh(token, "/issues/%d/comments?per_page=100&page=%d" % (PR, page))
        if not isinstance(batch, list):
            raise ValueError("INVALID_GITHUB_RESPONSE")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise ValueError("PAGINATION_LIMIT")


def post_alert(token, attempt, kind):
    marker = json.dumps({"task_id": TASK, "attempt": attempt, "kind": kind},
                        sort_keys=True, separators=(",", ":"))
    message = ("<!-- XJ_GH_WATCHDOG_ALERT " + marker + " -->\n"
               "::SKIP_COMPLETION::\n"
               "Mechanical Runner receipt SLA: " + kind + " for attempt " + attempt +
               ". Actual worker outcome is UNKNOWN; reconcile before restart. "
               "This receipt used no model and performed no writer, lease, host, or production action.")
    gh(token, "/issues/%d/comments" % PR, "POST", {"body": message})


def monitor(token, attempt, sleep=time.sleep, now=lambda: dt.datetime.now(dt.timezone.utc)):
    """One bounded monitor born from SUBMITTED; exits on terminal or at 60 minutes."""
    while True:
        events, alerted = parse(fetch_comments(token))
        if is_terminal(events, attempt):
            print(json.dumps({"attempt": attempt, "status": "TERMINAL_RECEIPT_OBSERVED",
                              "model_inference_by_this_script": 0}, sort_keys=True))
            return 0
        findings = detect(events, alerted, now(), only_attempt=attempt)
        for _, kind in findings:
            post_alert(token, attempt, kind)
        if (any(kind == "TERMINAL_TIMEOUT_60M" for _, kind in findings)
                or (attempt, "TERMINAL_TIMEOUT_60M") in alerted):
            return 4
        sleep(POLL_SECONDS)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("HOLD_NO_GITHUB_TOKEN")
        return 2
    if not args.event_path:
        print("HOLD_NO_EVENT_PATH")
        return 2
    try:
        with open(args.event_path, "r", encoding="utf-8") as handle:
            attempt = submitted_attempt(json.load(handle))
    except (OSError, ValueError, TypeError):
        print("HOLD_INVALID_EVENT")
        return 2
    if attempt is None:
        print("SKIP_NON_SUBMITTED_EVENT")
        return 0
    return monitor(token, attempt)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("HOLD_WATCHDOG_ERROR_" + type(error).__name__)
        sys.exit(2)
