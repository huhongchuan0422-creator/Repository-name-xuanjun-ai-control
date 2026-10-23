#!/usr/bin/env python3
"""Offline read-only V2.7 Owner node evidence preview. No server, secrets or network."""
import argparse
import html
import json
import pathlib
import re
from datetime import datetime, timezone

SAFE_KEYS = ("ARCHITECTURE_VERSION", "CURRENT_STAGE", "CURRENT_BATCH", "CURRENT_TASK", "STATUS")
SECRET = re.compile(r"(?i)(password|token|secret|api.?key|credential|private.?key)")
STATES = {"UNKNOWN", "IN_PROGRESS", "PAUSED_RESOURCE", "WAITING_EXTERNAL", "WAITING_APPROVAL", "SUCCEEDED", "FAILED"}

def read_canonical(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    result = {}
    for line in text.splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key.strip() in SAFE_KEYS:
            result[key.strip()] = value.strip()[:160]
    return result

def cards(path):
    if not path:
        return []
    obj = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, list) or len(obj) > 150:
        raise ValueError("expected <=150 evidence cards")
    clean = []
    for item in obj:
        if not isinstance(item, dict):
            raise ValueError("card must be object")
        status = str(item.get("status", "UNKNOWN"))
        if status not in STATES:
            status = "UNKNOWN"
        ident = str(item.get("node_id", "UNKNOWN"))[:80]
        title = str(item.get("title", "未命名节点"))[:180]
        if any(SECRET.search(v) for v in (ident, title)):
            raise ValueError("sensitive name rejected")
        clean.append({"node_id": ident, "title": title, "status": status})
    return clean

def render(state, entries):
    cell = lambda s: html.escape(str(s), quote=True)
    rows = "".join("<tr><td>"+cell(k)+"</td><td>"+cell(v)+"</td></tr>" for k,v in state.items())
    jobs = "".join("<tr><td>"+cell(x["node_id"])+"</td><td>"+cell(x["title"])+"</td><td>"+cell(x["status"])+"</td></tr>" for x in entries)
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>玄钧云汇 Owner 证据预览（非生产）</title><style>body{font:16px system-ui,sans-serif;max-width:960px;margin:auto;padding:24px;color:#18202b}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #ddd;text-align:left;padding:10px;overflow-wrap:anywhere}h1{font-size:25px}.note{background:#eee;padding:14px;border-radius:8px}</style>
<h1>Owner 工作台 · 只读证据预览</h1><p class="note">仅为离线工程预览，不是生产后台；不支持审批、通知、操作服务器。UNKNOWN 不等于 PASS。</p><h2>权威项目摘要</h2><table>"""+rows+"""</table><h2>节点摘要</h2><table><tr><th>节点</th><th>内容</th><th>状态</th></tr>"""+jobs+"""</table></html>"""

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--canonical", required=True)
    p.add_argument("--cards")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    state = read_canonical(a.canonical)
    output = pathlib.Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(state, cards(a.cards)), encoding="utf-8")
    print("OWNER_PREVIEW=PASS")
    print("PRODUCTION_MUTATION=NO")

if __name__ == "__main__":
    main()
