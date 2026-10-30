#!/usr/bin/env python3
"""Make a network-disabled, single-file review of an existing public tree.

This is a derived review artifact, never a deployment or an authenticated host.
Original inputs are not modified. Navigation is handled by the review shell.
"""
import argparse, base64, hashlib, json, mimetypes, posixpath, re
from pathlib import Path
from urllib.parse import urlsplit


def build(public, delivery, output):
    files = {p.relative_to(public).as_posix(): p.read_bytes()
             for p in public.rglob('*') if p.is_file()}
    def resolve(url, origin):
        u = urlsplit(url)
        if u.scheme or u.netloc or not u.path:
            return None
        return posixpath.normpath(posixpath.join(posixpath.dirname(origin), u.path)) if not u.path.startswith('/') else u.path.lstrip('/')
    assets = {}
    def asset(url, origin):
        name = resolve(url, origin)
        if name not in files:
            return url
        token = 'PR122_ASSET_'+hashlib.sha256(name.encode()).hexdigest()+'__'
        if token in assets:
            return token
        assets[token] = ''
        data = files[name]
        mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        if name.endswith('.js'):
            data = data.decode().replace('location.origin', "'https://review.invalid'").encode()
        if name.endswith('.css'):
            css = data.decode()
            css = re.sub(r'url\([\'\"]?([^\)\'\"]+)[\'\"]?\)', lambda m: 'url("'+asset(m[1], name)+'")', css)
            data = css.encode()
        assets[token] = {'mime': mime, 'data': base64.b64encode(data).decode()}
        return token
    pages = {}
    bridge = '''<script>document.addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;const h=a.getAttribute('href');if(!h||h.startsWith('#'))return;e.preventDefault();parent.postMessage({reviewRoute:h},'*')},true);document.addEventListener('submit',e=>{e.preventDefault();alert('离线审阅：未提交真实资料或订单。')},true);</script>'''
    for name, raw in files.items():
        if not name.endswith('.html'):
            continue
        text = raw.decode('utf-8')
        text = re.sub(r'<meta\b[^>]*http-equiv=[\'\"]Content-Security-Policy[\'\"][^>]*>', '', text, flags=re.I)
        text = re.sub(r'\b(src|poster)="([^"]+)"', lambda m: m[1]+'="'+asset(m[2], name)+'"', text)
        text = re.sub(r'(<link\b[^>]*href=")([^"]+)(")', lambda m: m[1]+asset(m[2], name)+m[3] if resolve(m[2], name) in files and not m[2].split('?')[0].endswith('.html') else m[0], text)
        # Apply the Owner's navigation correction only to the derived preview.
        text = re.sub(r'(<div class="nav-panel">)', lambda m: m[0]+'<a href="'+target+'">'+label+'</a>', text, count=1) if False else text
        text = re.sub(r'(<a href="[^"]*/custom-ai">(?:定制与交付|Custom &amp; Delivery|Custom & Delivery)</a>.*?<div class="nav-panel">)', lambda m:m[0]+'<a href="/delivery/">开发中项目</a><a href="/delivery/cases.html">已完成案例</a>', text, count=1, flags=re.S)
        pages[name] = text.replace('</head>', '<meta http-equiv="Content-Security-Policy" content="default-src data: blob: \'unsafe-inline\' \'unsafe-eval\'; connect-src \'none\'; form-action \'none\'; frame-src data: blob: about:"></head>', 1).replace('</body>', bridge+'</body>')
    pages['delivery/index.html'] = delivery.read_text()
    pages['delivery/cases.html'] = delivery.read_text().replace('</script></body>', 'showList(true);</script></body>')
    payload = json.dumps(pages, ensure_ascii=False).replace('<', '\\u003c')
    shell = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>官网完整离线审阅</title><style>body{margin:0;font:14px system-ui;background:#eef2f8}nav{display:flex;gap:10px;flex-wrap:wrap;padding:12px}button,select{padding:9px;font:inherit}iframe{display:block;border:0;background:white;width:100%;height:calc(100vh - 125px);margin:auto;max-width:100%}p{margin:5px 12px;color:#4b5870}</style><nav><button onclick="back()">← 返回</button><select id="route"><option value="/">官网首页</option><option value="/delivery/">开发中项目与案例</option><option value="/ecosystem/">共创生态</option><option value="/ecosystem/tiers/">生态值档次与折扣</option><option value="/ecosystem/profit-sharing/">共创分成</option><option value="/marketplace/">功能市场</option><option value="/visual/">可视化中心</option></select><button onclick="screen(390)">手机宽度</button><button onclick="screen(0)">桌面宽度</button><span id="path"></span></nav><p>完整静态源码审阅，沿 db93285f + c29e8d27；非生产。禁用网络与真实提交；评论为内存演示，项目全集、权限及交付记录未接通。</p><iframe id="view" sandbox="allow-scripts" title="官网完整页面"></iframe><script>const pages=PAYLOAD,assets=ASSETS,cache={};function resource(t){if(cache[t])return cache[t];const a=assets[t];let data=a.data;if(a.mime==='text/css'){let bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));let css=new TextDecoder().decode(bytes).replace(/PR122_ASSET_[a-f0-9]+__/g,resource);data=btoa(String.fromCharCode(...new TextEncoder().encode(css)))}return cache[t]='data:'+a.mime+';base64,'+data}const frame=document.getElementById('view'),stack=[];let current='/index.html';function navigate(v,record=true){let u;try{u=new URL(v,'https://review.invalid'+current)}catch{return}if(u.origin!=='https://review.invalid'){document.getElementById('path').textContent='外部入口未在离线预览打开：'+u.hostname;return}let key=u.pathname.slice(1)||'index.html';if(!pages[key])key=key.replace(/\/$/,'')+'/index.html';if(!pages[key])key=u.pathname.slice(1)+'.html';if(!pages[key]){document.getElementById('path').textContent='本闭包不含该入口：'+u.pathname;return}if(record)stack.push(current);current='/'+key;frame.srcdoc=pages[key].replace(/PR122_ASSET_[a-f0-9]+__/g,resource);document.getElementById('path').textContent=current}function back(){const v=stack.pop();if(v)navigate(v,false)}function screen(w){frame.style.width=w?w+'px':'100%'}document.getElementById('route').onchange=e=>navigate(e.target.value);addEventListener('message',e=>{if(e.source===frame.contentWindow&&typeof e.data?.reviewRoute==='string')navigate(e.data.reviewRoute)});navigate('/',false);</script></html>'''
    output.write_text(shell.replace('PAYLOAD', payload).replace('ASSETS', json.dumps(assets).replace('<', '\\u003c')))
    return {'pages': len(pages), 'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('public', type=Path)
    p.add_argument('delivery', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    print(json.dumps(build(a.public, a.delivery, a.output)))
