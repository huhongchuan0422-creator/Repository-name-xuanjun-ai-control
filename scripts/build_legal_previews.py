"""Build escaped, non-signing static contract previews from versioned legal drafts."""
import argparse
import hashlib
import html
import json
from pathlib import Path

STYLE='body{font:16px/1.8 system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px;color:#20304b}nav a{margin-right:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.notice{border:2px solid #b77700;background:#fff7dd;padding:16px}li{margin:12px 0}a{color:#174c9e}'
def build(root):
    root=Path(root).resolve()
    registry=json.loads((root/'docs/legal/registry.json').read_text())
    if registry.get('production_enabled') is not False:raise ValueError('DRAFT_ONLY_REQUIRED')
    dest=root/'demos/legal';dest.mkdir(parents=True,exist_ok=True)
    links=[];seen=set()
    for entry in registry['documents']:
        key=entry['id']
        if key in seen or not key or any(c not in 'abcdefghijklmnopqrstuvwxyz-' for c in key):raise ValueError('INVALID_DOCUMENT_ID')
        seen.add(key)
        if entry['status']!='DRAFT_NOT_FOR_SIGNATURE' or entry['signature_enabled'] is not False:raise ValueError('SIGNATURE_NOT_AUTHORIZED')
        source=(root/entry['source']).resolve()
        if not source.is_relative_to(root/'docs/legal/templates') or not source.is_file():raise ValueError('INVALID_TEMPLATE_PATH')
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=entry['source_sha256']:raise ValueError('TEMPLATE_HASH_MISMATCH')
        title=html.escape(entry['title']);version=html.escape(entry['version']);sha=entry['source_sha256']
        page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+title+' · 草案预览</title><style>'+STYLE+'</style></head><body><nav><a href="index.html">协议与合同中心</a></nav><main><h1>'+title+'</h1><p class="notice">草案预览 · 尚未生效 · 不开放真实签署或收款。主体、业务参数及法律审核完成后，另经发布门禁启用。</p><p>版本：'+version+'<br>原文 SHA-256：'+sha+'</p><pre>'+html.escape(data.decode())+'</pre></main></body></html>\n'
        (dest/(key+'.html')).write_text(page)
        links.append('<li><a href="'+key+'.html">'+title+'</a> — '+html.escape('、'.join(entry['audience']))+'</li>')
    index='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>玄钧云汇 · 协议与合同中心（草案）</title><style>'+STYLE+'</style></head><body><main><h1>玄钧云汇协议与合同中心</h1><p class="notice">22份草案供阅读与审查，不构成已生效合同或已上线业务。请勿在演示页面提交真实证件、签名或客户秘密。</p><ul>'+''.join(links)+'</ul><p>定制客户采用主合同＋需求报价任务书＋数据/保密附件＋变更及验收单；正式签署与条款接受记录尚未接线。</p></main></body></html>\n'
    (dest/'index.html').write_text(index)
    return len(seen)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='.');args=parser.parse_args();print('DRAFT_PREVIEWS_BUILT='+str(build(args.root)))
