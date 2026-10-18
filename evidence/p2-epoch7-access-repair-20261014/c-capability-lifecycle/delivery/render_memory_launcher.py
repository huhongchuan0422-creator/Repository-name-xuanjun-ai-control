#!/usr/bin/env python3
"""Render a reviewable, hash-pinned in-memory launcher; never execute it.

No bootstrap file is placed in the one-file preparation directory or kit.
The exact publication commit and private expiry must be supplied for review.
Rendering is not permission to run the resulting command on any host.
"""
import argparse
import datetime
import hashlib
import pathlib
import re
import sys

def render(commit, expiry, raw):
    if not re.fullmatch('[0-9a-f]{40}', commit): raise ValueError('COMMIT')
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', expiry):
        raise ValueError('EXPIRY')
    datetime.datetime.strptime(expiry, '%Y-%m-%dT%H:%M:%SZ')
    url=('https://raw.githubusercontent.com/huhongchuan0422-creator/'
         'Repository-name-xuanjun-ai-control/'+commit+
         '/evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/'
         'delivery/epoch7_prepare_successor_delivery.py')
    body="""import hashlib,sys,urllib.request
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise ValueError('DELIVERY_REDIRECT')
url=%r
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
with opener.open(urllib.request.Request(url,headers={'Accept-Encoding':'identity'}),timeout=10) as response:
    if response.status!=200 or response.geturl()!=url or response.headers.get('Content-Encoding','identity')!='identity':raise ValueError('DELIVERY_RESPONSE')
    raw=response.read(%d)
if len(raw)!=%d or hashlib.sha256(raw).hexdigest()!=%r:raise ValueError('DELIVERY_PIN')
scope={'__name__':'verified_delivery','__file__':'<verified-preparation-delivery>'}
exec(compile(raw,scope['__file__'],'exec'),scope)
sys.exit(scope['entrypoint'](['--operation','prepare','--admission-expires-at-utc',%r]))
""" % (url,len(raw)+1,len(raw),hashlib.sha256(raw).hexdigest(),expiry)
    return ("/usr/bin/python3 -I -S -B <<'P2_VERIFIED_MEMORY_DELIVERY'\n"+body+
            'P2_VERIFIED_MEMORY_DELIVERY\n').encode('ascii')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery-commit',required=True)
    parser.add_argument('--admission-expires-at-utc',required=True)
    args=parser.parse_args()
    command=render(args.delivery_commit,args.admission_expires_at_utc,
                   pathlib.Path(__file__).with_name('epoch7_prepare_successor_delivery.py').read_bytes())
    sys.stdout.buffer.write(command)
    sys.stderr.write('COMMAND_SHA256='+hashlib.sha256(command).hexdigest()+'\n')
    return 0

if __name__=='__main__':sys.exit(main())
