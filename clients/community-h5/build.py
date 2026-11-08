"""Compile the five ORIGINAL mini pages into a browser shell, no runtime eval.
Never modifies source pages, workflow, auth state or an installed service.
"""
from pathlib import Path
from html.parser import HTMLParser
import json,re,hashlib
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'dist'
mini=ROOT/'clients/community-mini'
expressions=[]
def value(raw):
 parts=re.split(r'(\{\{.*?\}\})',raw,flags=re.S)
 if len(parts)==3 and not parts[0] and not parts[2]:
  idx=len(expressions);expressions.append(parts[1][2:-2]);return {'expression':idx}
 values=[]
 for p in parts:
  if not p:continue
  if p.startswith('{{') and p.endswith('}}'):
   idx=len(expressions);expressions.append(p[2:-2]);values.append({'expression':idx})
  else:values.append(p)
 return {'parts':values}
class Parse(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.root=[];self.stack=[self.root]
 def handle_starttag(self,tag,attrs):
  n={'tag':tag,'attrs':{k:value(v or '') for k,v in attrs},'children':[]};self.stack[-1].append(n)
  if tag not in ('input','image'):self.stack.append(n['children'])
 def handle_startendtag(self,tag,attrs):
  self.handle_starttag(tag,attrs)
  if tag not in ('input','image'):self.stack.pop()
 def handle_endtag(self,tag):
  if tag not in ('input','image') and len(self.stack)>1:self.stack.pop()
 def handle_data(self,data):
  if data.strip():self.stack[-1].append({'text':value(data)})
def main():
 OUT.mkdir(exist_ok=True)
 pages={};manifest={};css=''
 for n in ('home','profile','checkout','merchant','merchant-join'):
  p=mini/'pages'/n/'index.wxml';parser=Parse();parser.feed(p.read_text());pages[n]=parser.root
 for p in [mini/'app.wxss',*sorted(mini.glob('pages/*/*.wxss'))]:
  s=p.read_text();s=re.sub(r'(-?\d*\.?\d+)rpx',r'calc(\1 * var(--rpx))',s);s=re.sub(r'\bpage\s*\{','body {',s);css+=s+'\n'
 for p in sorted(mini.rglob('*')):
  if p.is_file() and not p.name.endswith('.test.cjs'):manifest[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
 modules=[]
 for p in [*sorted(mini.rglob('*.js')),*sorted(Path(__file__).parent.glob('*.js'))]:
  if p.name in ('runtime.js',):continue
  name=str(p.relative_to(ROOT/'clients'))
  code=p.read_text()
  if name=='community-mini/session.js':code+='\nmodule.exports.getSharedSession=function(wx,config,now,page){if(page)globalThis.H5_SESSION.attachPage(page);return globalThis.H5_SESSION};\nconst miniCustomerError=module.exports.customerError;module.exports.customerError=function(error){return error&&error.message==="RATE_LIMIT"?"操作较频繁，请稍后再试；登录和已保存资料保持不变。":miniCustomerError(error)};\n'
  modules.append(json.dumps(name)+':function(require,module,exports){\n'+code+'\n}')
 expr='['+','.join('function(s){with(s){return ('+x+')}}' for x in expressions)+']'
 bundle='const H5_MODULES={'+','.join(modules)+'};\nconst H5_TEMPLATES='+json.dumps(pages,ensure_ascii=False)+';\nconst H5_EXPRESSIONS='+expr+';\n'+(Path(__file__).parent/'runtime.js').read_text()
 (OUT/'app.js').write_text(bundle)
 (OUT/'app.css').write_text('html{--rpx:min(.133333vw,.64px)}body{margin:0}view,scroll-view,block{display:block}text{white-space:pre-wrap}button{cursor:pointer;border:0}image,img{max-width:100%}input,textarea,select,button{font:inherit}button[disabled]{cursor:default}picker{display:block;position:relative}picker>select{position:absolute;inset:0;width:100%;opacity:0;cursor:pointer}textarea{width:100%;box-sizing:border-box}#login-panel{position:relative;max-width:440px;margin:16px auto;padding:18px;box-sizing:border-box}#h5-message{white-space:pre-wrap;color:#8a3e26;padding:8px 18px;max-width:600px;margin:auto}.h5-login-heading{font-size:22px}'+css)
 (OUT/'index.html').write_text('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>社区服务</title><link rel="stylesheet" href="app.css"></head><body><form id="login-panel" class="card"><div class="h5-login-heading">登录现有账户</div><label>邮箱<input id="email" type="email" autocomplete="username" required></label><label>密码<input id="password" type="password" autocomplete="current-password" required></label><button class="primary" type="submit">登录</button><p>使用已有消费者账户，不新建账号或角色。</p></form><div id="h5-message" role="status"></div><main id="app"></main><aside style="padding:16px 18px 90px"><button type="button" id="h5-privacy">隐私指引（草案待审核）</button><button type="button" id="h5-logout" hidden>退出当前账户</button></aside><script src="app.js" defer></script></body></html>''')
 import shutil
 if (mini/'assets').exists():shutil.copytree(mini/'assets',OUT/'assets',dirs_exist_ok=True)
 (OUT/'privacy-draft.txt').write_text((ROOT/'docs/legal/templates/privacy.md').read_text())
 (OUT/'SOURCE_MANIFEST.json').write_text(json.dumps({'status':'ISOLATED_RECOVERY_NOT_OLD_SOURCE_RESTORED_NOT_DEPLOYED','base':'4a1bbae3e72dea151bfca86b2e46e72076837095','reused_files':manifest,'pages':list(pages),'privacy_draft_sha256':hashlib.sha256((ROOT/'docs/legal/templates/privacy.md').read_bytes()).hexdigest()},indent=2))
 print('BUILT',OUT,'pages',len(pages),'expressions',len(expressions))
if __name__=='__main__':main()
