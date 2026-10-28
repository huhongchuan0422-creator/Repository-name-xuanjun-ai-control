"""Local build of the exact original App /customer/center/ecosystem/ asset subtree.
No server calls, deployment, grants, index overwrite or backend startup.
"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'src'
def build(asset_root):
 out=Path(asset_root)/'ecosystem';out.mkdir(parents=True,exist_ok=True)
 for source,target in (('api.js','api.mjs'),('ecosystem-view.mjs','ecosystem-view.mjs'),('ecosystem-bootstrap.mjs','bootstrap.mjs')):
  (out/target).write_bytes((SOURCE/source).read_bytes())
 (out/'index.html').write_text('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>原控制台 · 模块待审核登记</title><link rel="stylesheet" href="./style.css"></head><body><main><a href="/customer/center/">返回原控制台</a><h1>SaaS 模块登记</h1><p id="entry-status" role="status">正在读取原登录权限</p><label for="project-picker">当前授权项目</label><select id="project-picker" disabled></select><section id="pending-content"></section></main><script type="module" src="./bootstrap.mjs"></script></body></html>''',encoding='utf-8')
 (out/'style.css').write_text('''body{font-family:system-ui,sans-serif;color:#e5edf7;background:#111827;margin:0}main{max-width:960px;margin:auto;padding:24px}button,input,select{font:inherit;min-height:44px;padding:8px;margin:6px;max-width:100%;box-sizing:border-box}p{overflow-wrap:anywhere}a{color:#9cc9ff}button:disabled{opacity:.5}section{padding:16px;border:1px solid #475569;border-radius:12px;margin-top:16px}@media(max-width:480px){main{padding:12px}button,input,select{display:block;width:100%;margin:8px 0}}''',encoding='utf-8')
 return out
if __name__=='__main__':
 import sys
 if len(sys.argv)!=2:raise SystemExit('One local original-assets build destination required; no deployment implied')
 print(build(sys.argv[1]))
