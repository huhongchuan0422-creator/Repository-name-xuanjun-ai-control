#!/usr/bin/env python3
"""Outside-Runner mechanical timeout watcher. No model/host/lease access."""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

REPO = "huhongchuan0422-creator/Repository-name-xuanjun-ai-control"
TASK = "XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1"
PR = 17
EVENT = re.compile(r"<!-- XJ_GH_TASK_EVENT (\{[^\n]{1,2048}\}) -->")
ALERT = re.compile(r"<!-- XJ_GH_WATCHDOG_ALERT (\{[^\n]{1,2048}\}) -->")
STATES = {"SUBMITTED", "RECEIVED", "STARTED", "PROGRESS", "COMPLETE", "FAIL", "HOLD"}


def parse(comments):
    events, alerted = [], set()
    for c in comments:
        body = c.get("body") or ""
        try:
            stamp = dt.datetime.fromisoformat(c["created_at"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        for m in EVENT.finditer(body):
            try:
                x = json.loads(m.group(1))
                if (x.get("task_id") == TASK and x.get("state") in STATES
                        and x.get("source") == "AUTHORIZED_EXECUTION_RECEIPT"
                        and re.fullmatch(r"[A-Za-z0-9._-]{8,128}", x.get("attempt", ""))):
                    events.append((stamp, x))
            except (TypeError, ValueError):
                continue
        for m in ALERT.finditer(body):
            try:
                x = json.loads(m.group(1))
                if x.get("task_id") == TASK:
                    alerted.add((x.get("attempt"), x.get("kind")))
            except (TypeError, ValueError):
                continue
    return sorted(events, key=lambda x: x[0]), alerted


def detect(events, alerted, now):
    grouped, findings = {}, []
    for stamp, x in events:
        grouped.setdefault(x["attempt"], []).append((stamp, x["state"]))
    for attempt, seq in grouped.items():
        if any(s in ("COMPLETE", "FAIL", "HOLD") for _, s in seq):
            continue
        submitted = next((t for t, s in seq if s == "SUBMITTED"), None)
        if submitted is None:
            continue
        received = next((t for t, s in seq if s == "RECEIVED"), None)
        started = next((t for t, s in seq if s == "STARTED"), None)
        progress = max((t for t, s in seq if s in ("STARTED", "PROGRESS")), default=None)
        kinds = []
        if received is None and (now - submitted).total_seconds() >= 120:
            kinds.append("RECEIVE_TIMEOUT")
        if started is None and (now - submitted).total_seconds() >= 300:
            kinds.append("START_TIMEOUT")
        if started is not None and progress is not None and (now - progress).total_seconds() >= 600:
            kinds.append("STALL_10M")
        for kind in kinds:
            if (attempt, kind) not in alerted:
                findings.append((attempt, kind))
    return findings


def gh(token, suffix, method="GET", body=None):
    url = "https://api.github.com/repos/" + REPO + suffix
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "xuanjun-mechanical-watchdog"}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(
            url, data=data, headers=headers, method=method), timeout=20) as response:
        return json.load(response)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("HOLD_NO_GITHUB_TOKEN")
        return 2
    rows = []
    for page in range(1, 11):
        batch = gh(token, "/issues/%d/comments?per_page=100&page=%d" % (PR, page))
        if not isinstance(batch, list):
            print("HOLD_INVALID_GITHUB_RESPONSE")
            return 2
        rows.extend(batch)
        if len(batch) < 100:
            break
    else:
        print("HOLD_PAGINATION_LIMIT")
        return 2
    events, alerted = parse(rows)
    findings = detect(events, alerted, dt.datetime.now(dt.timezone.utc))
    print(json.dumps({"receipts": len(events), "new_alerts": len(findings),
                      "model_inference_by_this_script": 0}, sort_keys=True))
    for attempt, kind in findings:
        marker = json.dumps({"task_id": TASK, "attempt": attempt, "kind": kind},
                            sort_keys=True, separators=(",", ":"))
        message = ("<!-- XJ_GH_WATCHDOG_ALERT " + marker + " -->\n"
                   "::SKIP_COMPLETION::\n"
                   "Mechanical watchdog: " + kind + " for attempt " + attempt
                   + ". Actual worker outcome UNKNOWN; reconcile before restart. "
                   "No model, writer, lease or production action.")
        gh(token, "/issues/%d/comments" % PR, "POST", {"body": message})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("HOLD_WATCHDOG_ERROR_" + type(e).__name__)
        sys.exit(2)
