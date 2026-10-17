"""Independent read-only development observer; never executes application code."""
import datetime as dt
import json
import os
import pathlib
import urllib.request

REPO = os.environ['GITHUB_REPOSITORY']
BRANCH = 'feature/chatgpt-community-wechat-sp-offline-20261017'
ROOT = pathlib.Path('docs/development/community-progress')

def api(path):
    req = urllib.request.Request('https://api.github.com/repos/' + REPO + path,
        headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'User-Agent': 'community-development-observer'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

def application(path):
    return (path.startswith(('scripts/community_', 'demos/community-stage/', 'clients/community-', 'migrations/community'))
            and not path.endswith(('.md', '.json')) and 'development_watch' not in path)

def main():
    from urllib.parse import quote
    head = api('/commits/' + quote(BRANCH, safe=''))
    latest = None
    for page in range(1, 11):
        commits = api('/commits?sha=' + quote(BRANCH, safe='') + '&per_page=100&page=' + str(page))
        for commit in commits:
            detail = api('/commits/' + commit['sha'])
            if any(application(f['filename']) and f.get('changes', 0) > 0 for f in detail.get('files', [])):
                latest = detail
                break
        if latest or not commits:
            break
    now = dt.datetime.now(dt.timezone.utc)
    ledger = json.loads((ROOT / 'scope.json').read_text())
    last_at = latest['commit']['committer']['date'] if latest else None
    age = (now - dt.datetime.fromisoformat(last_at.replace('Z', '+00:00'))).total_seconds() if last_at else None
    runs = api('/actions/runs?branch=' + quote(BRANCH, safe='') + '&per_page=30')['workflow_runs']
    current_runs = [{'id': r['id'], 'name': r['name'], 'status': r['status'], 'conclusion': r['conclusion'],
                     'url': r['html_url']} for r in runs if latest is not None and r['head_sha'] == latest['sha']]
    tasks = ledger['tasks']
    phases = {str(p): {'completed': sum(t['phase'] == p and t['state'] == 'IMPLEMENTED' for t in tasks),
                       'remaining': sum(t['phase'] == p and t['state'] != 'IMPLEMENTED' for t in tasks)} for p in (1, 2)}
    result = {'checked_at': now.isoformat(), 'branch': BRANCH, 'head_sha': head['sha'],
        'current_module': ledger['current_module'], 'phases': phases,
        'last_code_sha': latest['sha'] if latest else None, 'last_code_at': last_at,
        'status': 'UNKNOWN' if age is None else '无提交进展' if age >= 1200 else '最近20分钟有代码提交',
        'ci': current_runs, 'ci_status': 'NOT_RUN_OR_NOT_FOUND' if not current_runs else 'SEE_RUN_RESULTS', 'blockers': ledger['blockers'],
        'counts_basis': 'Explicit scope ledger, implementation claims only; not independent acceptance.',
        'schedule_note': 'GitHub scheduled runs may be delayed; check checked_at.'}
    (ROOT / 'status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    lines = ['# 社区分账开发监督', '', result['status'], '', '检查时间：' + result['checked_at'],
        '当前模块：' + result['current_module'], '最后真实代码提交：' + str(result['last_code_sha']),
        '最后真实提交时间：' + str(last_at), '', '|阶段|已实现|剩余|', '|---|---:|---:|']
    lines += [f'|{p}|{v["completed"]}|{v["remaining"]}|' for p, v in phases.items()]
    lines += ['', '数量为源码范围登记，不代表验收通过。', '', 'CI：' + json.dumps(current_runs, ensure_ascii=False),
              '', '阻塞：' + '；'.join(result['blockers'])]
    (ROOT / 'README.md').write_text('\n\n'.join(lines) + '\n')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        pathlib.Path(summary).write_text((ROOT / 'README.md').read_text())

if __name__ == '__main__':
    main()
