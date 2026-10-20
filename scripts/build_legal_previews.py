"""Build escaped, non-signing static contract previews from versioned legal drafts."""
import argparse
import hashlib
import html
import json
from pathlib import Path

STYLE='body{font:16px/1.8 system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px;color:#20304b}nav a{margin-right:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.notice{border:2px solid #b77700;background:#fff7dd;padding:16px}li{margin:12px 0}a{color:#174c9e}'

# Existing static wrapper shape; new brand-only draft bytes require fresh review. No signing capability.
REVIEWED_STATIC = {'custom-development': {'prefix': '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>软件与AI定制开发电子合同（唯一签署文件）</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.notice{padding:16px;border:2px solid #b77700}</style></head><body><a href="index.html">协议与合同中心</a><h1>软件与AI定制开发电子合同（唯一签署文件）</h1><p class="notice">草案不可签署，不开放真实收款。</p><p>版本：2026-10-17-draft.5-brand-20261019 | SHA256：5d7a5bc9afdf7aad5e46ef91fa35c7e5595b113aaf9932d31d9e1a2e799c2db5</p>', 'suffix': '</body></html>\n', 'version': '2026-10-17-draft.5-brand-20261019', 'sha256': '5d7a5bc9afdf7aad5e46ef91fa35c7e5595b113aaf9932d31d9e1a2e799c2db5', 'title': '软件与AI定制开发电子合同（唯一签署文件）'}, 'custom-sow': {'prefix': '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>内部需求与报价字段定义（不单独签署）</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.notice{padding:16px;border:2px solid #b77700}</style></head><body><a href="index.html">协议与合同中心</a><h1>内部需求与报价字段定义（不单独签署）</h1><p class="notice">内部字段定义，不供客户签署。</p><p>版本：2026-10-17-internal.2 | SHA256：9474bebe5d8b24a837f6b7d710587c1ef295b00e15eb33c321cd0a96611887df</p>', 'suffix': '</body></html>\n', 'version': '2026-10-17-internal.2', 'sha256': '9474bebe5d8b24a837f6b7d710587c1ef295b00e15eb33c321cd0a96611887df', 'title': '内部需求与报价字段定义（不单独签署）'}}

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
        internal = entry['status'] == 'INTERNAL_ONLY'
        if entry['signature_enabled'] is not False or entry['status'] not in ('DRAFT_NOT_FOR_SIGNATURE', 'INTERNAL_ONLY'):raise ValueError('SIGNATURE_NOT_AUTHORIZED')
        if internal and (key != 'custom-sow' or entry.get('preview') is not None or entry.get('planned_route') is not None):raise ValueError('INTERNAL_DOCUMENT_MUST_NOT_BE_PUBLIC')
        if key == 'custom-sow' and not internal:raise ValueError('CUSTOM_SOW_MUST_BE_INTERNAL')
        source=(root/entry['source']).resolve()
        if not source.is_relative_to(root/'docs/legal/templates') or not source.is_file():raise ValueError('INVALID_TEMPLATE_PATH')
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=entry['source_sha256']:raise ValueError('TEMPLATE_HASH_MISMATCH')
        title=html.escape(entry['title']);version=html.escape(entry['version']);sha=entry['source_sha256']
        page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+title+' · 草案预览</title><style>'+STYLE+'</style></head><body><nav><a href="index.html">协议与合同中心</a></nav><main><h1>'+title+'</h1><p class="notice">草案预览 · 尚未生效 · 不开放真实签署或收款。主体、业务参数及法律审核完成后，另经发布门禁启用。</p><p>版本：'+version+'<br>原文 SHA-256：'+sha+'</p><pre>'+html.escape(data.decode())+'</pre></main></body></html>\n'
        if key in REVIEWED_STATIC:
            fixed = REVIEWED_STATIC[key]
            if (entry['version'], sha, entry['title']) != (fixed['version'], fixed['sha256'], fixed['title']):raise ValueError('REVIEWED_STATIC_VERSION_MISMATCH')
            page = fixed['prefix'] + '<pre>' + html.escape(data.decode('utf-8')) + '</pre>' + fixed['suffix']
        (dest/(key+'.html')).write_text(page, encoding='utf-8')
        if internal:continue
        links.append('<li><a href="'+key+'.html">'+title+'</a> — '+html.escape('、'.join(entry['audience']))+'</li>')
    index='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>玄钧AI新 · 协议与合同中心（草案）</title><style>'+STYLE+'</style></head><body><main><h1>玄钧AI新协议与合同中心</h1><p class="notice">'+str(len(links))+'份对客草案供阅读与审查，不构成已生效合同或已上线业务。请勿在演示页面提交真实证件、签名或客户秘密。</p><ul>'+''.join(links)+'</ul><p>定制开发使用一份完整合同草案，项目范围、报价与验收内容整合在同一文件中；内部需求与报价字段定义不作为客户签署文件。正式签署与条款接受记录尚未接线。</p></main></body></html>\n'
    (dest/'index.html').write_text(index)
    return len(seen)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='.');args=parser.parse_args();print('DRAFT_PREVIEWS_BUILT='+str(build(args.root)))
