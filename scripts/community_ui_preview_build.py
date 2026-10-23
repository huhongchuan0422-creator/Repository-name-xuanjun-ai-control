"""Build isolated UI/navigation projection from original community fields.
Never imports application code or accesses configuration, identities or data stores.
"""
from html.parser import HTMLParser
from html import escape
from pathlib import Path
import json,re,hashlib,base64
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'demos/community-stage'
class Node:
    def __init__(self,tag='',attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[]
    def text(self):return ''.join(c.text() if isinstance(c,Node) else c for c in self.children)
    def find(self,tag):
        return [n for c in self.children if isinstance(c,Node) for n in ([c] if c.tag==tag else [])+c.find(tag)]
    def html(self):
        attrs={k:v for k,v in self.attrs.items() if not k.startswith('on') and k not in ('action','formaction','src','href','hidden','disabled')}
        if self.tag in ('script','style','link'):return ''
        a=''.join(' '+k+'="'+escape(v or '',quote=True)+'"' for k,v in attrs.items())
        body=''.join(c.html() if isinstance(c,Node) else escape(c) for c in self.children)
        return '<'+self.tag+a+'>'+body+('' if self.tag in ('input','br','hr','img','meta') else '</'+self.tag+'>')
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.root=Node('root');self.stack=[self.root]
    def handle_starttag(self,t,a):
        n=Node(t,a);self.stack[-1].children.append(n)
        if t not in ('input','br','hr','img','meta','link'):self.stack.append(n)
    def handle_endtag(self,t):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==t:self.stack=self.stack[:i];break
    def handle_data(self,d):self.stack[-1].children.append(d)
def load(name):
    p=Parser();p.feed((BASE/name).read_text());return p.root

def build():
    pages=[];sources={}
    platform={'平台审核','平台运营查询','平台商家管理','平台配置社区分账接收关系'}
    for name,role in [('workbench.html','merchant'),('communities.html','community')]:
        raw=(BASE/name).read_bytes();sources[name]=hashlib.sha256(raw).hexdigest()
        for i,section in enumerate(load(name).find('section')):
            heading=section.find('h2')
            if not heading:continue
            title=heading[0].text();parts=[];part=[];sub=title
            for child in section.children:
                if isinstance(child,Node) and child.tag=='h3':
                    if part:parts.append((sub,part))
                    sub=child.text();part=[]
                elif isinstance(child,Node) and child.tag!='h2':part.append(child)
            if part:parts.append((sub,part))
            for j,(subtitle,children) in enumerate(parts):
                owner='platform' if role=='community' and (title in platform or subtitle in platform) else role
                if title=='查询结果':continue
                forms=[n for c in children for n in ([c] if c.tag=='form' else c.find('form'))]
                # A form is its own edit screen, never a long folded screen.
                chunks=[]
                for form in forms:
                    fields=form.find('label')
                    if len(fields)>8:
                        for k in range(0,len(fields),8):chunks.append(('表单 '+str(k//8+1),''.join(x.html() for x in fields[k:k+8])))
                    else:chunks.append(((form.find('button')[0].text() if form.find('button') else '编辑') if len(forms)>1 else '',form.html()))
                if not chunks:chunks=[('', ''.join(c.html() for c in children if c.tag not in ('pre','div','table')))]
                for k,(suffix,body) in enumerate(chunks):
                    pages.append({'id':owner+'-'+str(i)+'-'+str(j)+'-'+str(k),'role':owner,'title':subtitle+(' · '+suffix if suffix else ''),'source':name,'source_heading':title,'html':body,'kind':'module','editable':bool(forms),'actions':[{'id':b.attrs.get('id',''), 'title':b.text()} for c in children for b in ([c] if c.tag=='button' else c.find('button'))]})
    # Keep the original backoffice modules as source evidence, not the mini menu.
    for page in pages:
        if page['role']=='merchant':page['legacyOnly']=True
    native='clients/community-mini/pages/merchant/index.wxml'
    native_specs=[('orders','订单与收款记录','<label>订单编号<input id="merchant-reference" maxlength="64"></label>',False),
        ('summary','收款统计','<p>订单总额、微信已核收款及退款观察按原接口分别读取；无真实核验时不显示到账。</p>',False),
        ('profile','门店资料','<label>门店名称<input id="merchant-name" maxlength="120"></label><label>简介<textarea id="merchant-description" maxlength="2048"></textarea></label><label>联系方式<input id="merchant-contact" maxlength="120"></label>',True),
        ('catalog','商品与服务','<p>沿原目录查看商品；原商品、定价库存和退款后台源码保留。本候选手机端不冒充已覆盖全部维护操作。</p>',False),
        ('detail','订单详情与退款状态','<label>原订单编号<input id="merchant-order-reference" maxlength="64"></label><p>订单、退款与分账状态分别展示，不以预览流水冒充真实执行。</p>',False),
        ('collection','收款码与保存手机','<p>仅原微信认证、签约、JSAPI及门店资格核验通过后，服务端才取得正式版小程序收款入口码。</p><button disabled>取得正式收款码（隔离预览不调用微信）</button><button disabled>保存手机相册（未取得正式图片）</button>',False)]
    for key,title,body,editable in native_specs:
        pages.append(dict(id='merchant-native-'+key,role='merchant',title=title,html=body,source=native,kind='mini',editable=editable,actions=[]))
    on=load('onboarding.html');profile=next(x for x in on.find('form') if x.attrs.get('id')=='profile')
    labels=[label for label in profile.find('label') if not any(n.attrs.get('id') in ('legal_name','contact','identity_type','delegated') for n in label.find('input')+label.find('select'))]
    for n in range(0,len(labels),6):pages.append({'id':'admission-basic-'+str(n//6),'role':'admission','title':'经营信息 '+str(n//6+1),'html':''.join(x.html() for x in labels[n:n+6]),'source':'onboarding.html','kind':'step'})
    js=(BASE/'onboarding.js').read_text()
    defs=re.findall(r"\['([a-z_]+(?:\.[a-z_]+)+)','([^']+)'\]",js[js.index('const definitions='):js.index('for(const [scene,title]')])
    groups=[('contact_info.','管理员'),('subject_info.business_license_info.','经营主体'),('subject_info.identity_info.id_card_info.','法人身份证'),('subject_info.identity_info.id_doc_info.','其他法人证件'),('business_info.','经营场景'),('settlement_info.','结算规则'),('bank_account_info.','结算账户')]
    required_fields={'contact_info.contact_type','contact_info.contact_name','contact_info.mobile_phone','contact_info.contact_email','subject_info.business_license_info.license_number','subject_info.business_license_info.merchant_name','subject_info.business_license_info.legal_person','subject_info.identity_info.id_doc_type','subject_info.identity_info.id_card_info.id_card_name','subject_info.identity_info.id_card_info.id_card_number','subject_info.identity_info.id_card_info.card_period_begin','subject_info.identity_info.id_card_info.card_period_end','subject_info.identity_info.id_card_info.id_card_address','subject_info.identity_info.id_doc_info.id_doc_name','subject_info.identity_info.id_doc_info.id_doc_number','subject_info.identity_info.id_doc_info.doc_period_begin','subject_info.identity_info.id_doc_info.doc_period_end','subject_info.identity_info.id_doc_info.id_doc_address','business_info.merchant_shortname','business_info.service_phone','business_info.sales_info.mini_program_info.mini_program_appid','settlement_info.settlement_id','settlement_info.qualification_type','bank_account_info.bank_account_type','bank_account_info.account_name','bank_account_info.account_bank','bank_account_info.account_number'}
    def field_attrs(key):
        return ' required aria-required="true"' if key in required_fields or key.startswith('subject_info.ubo_info_list.') else ''
    # Original official enum text stays descriptive; preview does not invent validation.
    for prefix,title in groups:
        fields=[(key,label) for key,label in defs if key.startswith(prefix)]
        if title=='法人身份证':fields.insert(0,('subject_info.identity_info.id_doc_type','法人证件类型'))
        if title=='经营场景':fields.extend([('business_info.sales_info.biz_store_info.'+f,t) for f,t in [('biz_store_name','线下门店名称'),('biz_address_code','线下门店地区代码'),('biz_store_address','线下门店详细地址')]])
        body=''.join('<label>'+escape(label)+'<input data-path="'+key+'" maxlength="512" autocomplete="off"'+field_attrs(key)+'></label>' for key,label in fields)
        pages.append({'id':'admission-'+prefix.replace('.','-'),'role':'admission','title':title,'html':body,'source':'onboarding.js','kind':'step'})
    body='<p>按官方适用条件填写完整受益人名单，含适用法人；只有明确符合条件时才可省略名单。</p>'+''.join('<label>'+title+'<input data-path="subject_info.ubo_info_list.{index}.'+field+'" maxlength="512" required aria-required="true"></label>' for field,title in [('ubo_id_doc_type','证件类型'),('ubo_id_doc_name','姓名'),('ubo_id_doc_number','证件号'),('ubo_id_doc_address','住址'),('ubo_period_begin','有效期开始'),('ubo_period_end','有效期结束或长期')])
    pages.append({'id':'admission-beneficiary','role':'admission','title':'最终受益人资料','html':body,'source':'onboarding.js','kind':'step'})
    pages.insert(next(i for i,p in enumerate(pages) if p['role']=='admission')+1,{'id':'admission-materials','role':'admission','title':'资料清单与版本','html':'','source':'onboarding.html','kind':'materials'})
    pages.append({'id':'admission-result','role':'admission','title':'申请状态与补件','html':'','source':'onboarding.html','kind':'result'})
    # Four primary stages, with applicable field editors as subordinate views.
    # This is one shared application draft, not a second platform collection.
    for page in pages:
        if page['role']!='admission' or page['id']=='admission-result':continue
        page['kind']='admission-field'
        page['stage']='admission-start' if page['id'].startswith('admission-basic') or 'business_license' in page['id'] or 'identity_info' in page['id'] or page['id']=='admission-beneficiary' else 'admission-settlement' if 'bank_account' in page['id'] or 'settlement_info' in page['id'] or page['id']=='admission-materials' else 'admission-business'
    pages.extend([{'id':key,'role':'admission','title':title,'html':'','source':'onboarding.html/onboarding.js','kind':'stage'} for key,title in [('admission-start','主体与门店'),('admission-business','办理人与经营场景'),('admission-settlement','结算与资料')]])
    next(p for p in pages if p['id']=='admission-result')['kind']='stage'
    pages.append({'id':'platform-admission','role':'platform','title':'商家入驻审核','html':'','source':'onboarding.html','kind':'review'})
    consumer_specs=[('home','首页与我的服务',[]),('stores','门店与服务',[]),('orders','我的订单',[]),('profile','个人资料',['昵称','联系方式']),('communities','社区与归属',['社区编号','社区推广码']),('referrals','推荐关系',['推荐码']),('notices','我的通知',[]),('basket','商品篮子',['商品数量']),('refunds','退款申请',['退款申请编号','申请退款金额（分）','退款原因']),('payment','支付与订单恢复',['订单编号'])]
    for key,title,fields in consumer_specs:
        body=''.join('<label>'+x+'<input id="consumer-'+key+'-'+str(i)+'" maxlength="120"></label>' for i,x in enumerate(fields))
        source='clients/community-mini/pages/'+('home' if key=='home' else 'profile' if key=='profile' else 'checkout')+'/index.wxml'
        pages.append({'id':'consumer-'+key,'role':'consumer','title':title,'html':body,'source':source,'kind':'consumer','editable':bool(fields)})
    for f in ['onboarding.html','onboarding.js']:
        sources[f]=hashlib.sha256((BASE/f).read_bytes()).hexdigest()
    document_types={x.attrs['value']:x.text() for select in on.find('select') if select.attrs.get('id')=='identity_type' for x in select.find('option')}
    for f in ('app.json','session.js','merchant-form.js','merchant-fields.json','pages/merchant/index.js','pages/merchant/index.wxml','pages/merchant-join/index.js','pages/merchant-join/index.wxml'):
        sources['clients/community-mini/'+f]=hashlib.sha256((ROOT/'clients/community-mini'/f).read_bytes()).hexdigest()
    return {'documentTypes':document_types,'schema':1,'isolated':True,'sources':sources,'roles':{'merchant':'商家小程序','community':'社区管理','platform':'平台管理','admission':'商家入驻（同一小程序）','consumer':'用户小程序'},'pages':pages}
def main():
    data=build();out=BASE/'ui-preview'
    (out/'original.css').write_bytes((BASE/'onboarding.css').read_bytes())
    (out/'sources.js').write_text('window.COMMUNITY_UI_PREVIEW='+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+';\n')
    lines=['# 社区逐页UI预览清单','', '仅示例状态；无真实登录、API调用、业务写入或资金动作。消费者为原小程序界面投影，不是新增H5业务端。','', '|角色|页面|点击路径|原字段来源|','|---|---|---|---|']
    for p in data['pages']:
        if p['role']=='admission':
            route='`#/admission/'+p['id']+'/edit` → 演示保存返回 `'+(p.get('stage') or p['id'])+'`；仅适用分支可见'
        else:route='`#/'+p['role']+'/'+p['id']+'/list` → `detail` → `edit` → '+('演示保存返回列表' if p.get('editable') else '只读操作说明后返回列表，不新增业务记录')
        if p.get('legacyOnly'):route='原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明'
        lines.append('|'+data['roles'][p['role']]+'|'+p['title']+'|'+route+'|'+p['source']+'|')
    (ROOT/'docs/development/COMMUNITY_UI_PREVIEW_PAGE_MAP_20261022.md').write_text('\n'.join(lines)+'\n')
def bundle(target):
    out=BASE/'ui-preview';html=(out/'index.html').read_text()
    scripts=[(out/name).read_text() for name in ('sources.js','preview.js')]
    styles=[(out/name).read_text() for name in ('original.css','preview.css')]
    def digest(value):return "'sha256-"+base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()+"'"
    html=html.replace("script-src 'self'",'script-src '+' '.join(digest(s) for s in scripts)).replace("style-src 'self'",'style-src '+' '.join(digest(s) for s in styles))
    for name,value in zip(('original.css','preview.css'),styles):html=html.replace('<link rel="stylesheet" href="'+name+'">','<style>'+value+'</style>')
    # Inline scripts execute after the parsed original DOM, preserving defer semantics.
    for name in ('sources.js','preview.js'):html=html.replace('<script src="'+name+'" defer></script>','')
    html=html.replace('</body>',''.join('<script>'+s+'</script>' for s in scripts)+'</body>')
    Path(target).write_text(html)
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--bundle');args=parser.parse_args()
    bundle(args.bundle) if args.bundle else main()
