"""Read-only GitHub issue intake with durable local ledger. Python 3.6 compatible.

This stage deliberately DOES NOT dispatch shell commands, alter production jobs,
or mark issues completed. A separate policy-gated scheduler will consume INTAKE_READY.
"""
import argparse
import json
import os
import sqlite3
import time
import urllib.request

SCHEMA = """CREATE TABLE IF NOT EXISTS github_issue_intake (
 repo TEXT NOT NULL, issue_number INTEGER NOT NULL, title TEXT NOT NULL,
 state TEXT NOT NULL, source_updated_at TEXT NOT NULL, seen_at REAL NOT NULL,
 intake_state TEXT NOT NULL DEFAULT 'INTAKE_READY',
 PRIMARY KEY(repo, issue_number)
)"""

def collect(payload):
    if not isinstance(payload, list):
        raise ValueError('expected issues array')
    result = []
    for x in payload:
        if not isinstance(x, dict) or 'pull_request' in x:
            continue
        n = x.get('number')
        title = x.get('title')
        state = x.get('state')
        updated = x.get('updated_at')
        if type(n) is not int or n < 1 or not isinstance(title, str) or not isinstance(updated, str):
            continue
        if state != 'open':
            continue
        result.append((n, title[:240], state, updated))
    return result

def ingest(dbpath, repository, issues, now=None):
    if not repository or '/' not in repository:
        raise ValueError('invalid repository')
    stamp = time.time() if now is None else now
    db = sqlite3.connect(dbpath, timeout=10)
    try:
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute(SCHEMA)
        db.execute('BEGIN IMMEDIATE')
        inserted = 0
        for n, title, state, updated in collect(issues):
            present = db.execute('SELECT 1 FROM github_issue_intake WHERE repo=? AND issue_number=?',
                                 (repository,n)).fetchone()
            if not present:
                db.execute('INSERT INTO github_issue_intake(repo,issue_number,title,state,source_updated_at,seen_at) VALUES(?,?,?,?,?,?)',
                           (repository,n,title,state,updated,stamp))
                inserted += 1
            else:
                db.execute('UPDATE github_issue_intake SET title=?,state=?,source_updated_at=?,seen_at=? WHERE repo=? AND issue_number=?',
                           (title,state,updated,stamp,repository,n))
        db.commit()
        return inserted
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

def fetch(repository, token, timeout=12):
    if repository.count('/') != 1 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./' for c in repository):
        raise ValueError('invalid repo')
    req = urllib.request.Request('https://api.github.com/repos/'+repository+'/issues?state=open&per_page=100',
        headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+token,
                 'User-Agent':'xuanjun-stage1-issue-intake'})
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        return json.loads(resp.read(2000000).decode('utf-8'))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--db',required=True)
    ap.add_argument('--repo',required=True)
    ap.add_argument('--input-json',help='offline issue JSON; no network or auth')
    ap.add_argument('--token-file',help='protected GitHub token file; never printed')
    args=ap.parse_args()
    if args.input_json:
        with open(args.input_json,encoding='utf-8') as f: issues=json.load(f)
    elif args.token_file:
        if os.stat(args.token_file).st_mode & 0o077:
            raise SystemExit('STOP_TOKEN_FILE_PERMISSIONS')
        with open(args.token_file,encoding='utf-8') as f: token=f.read().strip()
        if not token: raise SystemExit('STOP_EMPTY_TOKEN')
        issues=fetch(args.repo,token)
    else:
        raise SystemExit('STOP_AUTH_OR_OFFLINE_INPUT_REQUIRED')
    count=ingest(args.db,args.repo,issues)
    print('GITHUB_INTAKE_NEW='+str(count))
    print('GITHUB_INTAKE_DISPATCH=DISABLED_UNTIL_POLICY_GATE')
if __name__=='__main__':main()
