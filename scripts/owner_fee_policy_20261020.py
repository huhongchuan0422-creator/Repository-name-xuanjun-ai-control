#!/usr/bin/env python3
"""Apply Owner's 2026-10-20 current fee policy; never execute business jobs.

Fixed domestic/Tokyo paths only. Does not activate timers, migrate databases,
send invoices, call Binance, edit credentials, or claim Korea acceptance.
"""
import argparse
import ast
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap

POLICY_ID = 'OWNER_FEE_POLICY_20261020_20_0_70_V1'
RULE = '带单合作按独立高水位规则收取交易利润的20%服务费；跟单利润分成永久全免，平台分文不取；跟单手续费返佣按实际到账金额收取70%。'
SCHEDULE = '财务返佣采集不进行每日例行扫描。每周一北京时间08:00用带单Trading API采集交易利润快照；每周一15:00用账户只读API查询当天08:00至15:00实际到账的跟单手续费返佣，完成对账后生成账单；采集或对账失败则暂停出账。收款核销任务与返佣采集分别管理。'
DOMESTIC = 'iZvt5t8tlrm8oiZ'
TOKYO = 'iZ6wee8q9z4t03hvqumwfhZ'
DOMESTIC_BASE = Path('/home/openclaw_ops/v8-domestic-operations')
DOMESTIC_APP = DOMESTIC_BASE / 'releases/domestic-real-ai-runtime-20261008-dual-channel-referral-r11/app'
TOKYO_APP = Path('/opt/trading-system')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def once(src, before, after):
    if src.count(before) != 1:
        raise ValueError('SOURCE_SHAPE_MISMATCH: ' + before[:90])
    return src.replace(before, after, 1)

def replace_def(src, name, code, cls=None):
    scope = ast.parse(src).body
    if cls:
        classes = [n for n in scope if isinstance(n, ast.ClassDef) and n.name == cls]
        if len(classes) != 1:
            raise ValueError('CLASS_SHAPE: ' + cls)
        scope = classes[0].body
    nodes = [n for n in scope if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError('FUNCTION_SHAPE: ' + name)
    n = nodes[0]
    block = textwrap.indent(textwrap.dedent(code).strip() + '\n', ' ' * n.col_offset)
    lines = src.splitlines(True)
    return ''.join(lines[:n.lineno-1] + [block] + lines[n.end_lineno:])

def constant(src, name, expression):
    nodes = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    if len(nodes) != 1:
        raise ValueError('CONSTANT_SHAPE: ' + name)
    n = nodes[0]
    lines = src.splitlines(True)
    return ''.join(lines[:n.lineno-1] + [name + ' = ' + expression + '\n'] + lines[n.end_lineno:])

def policy_config(data):
    data = json.loads(json.dumps(data))
    for k in ('lead_trading_service_fees', 'copy_trading_profit_share', 'trading_fee_rebate', 'customer_messaging'):
        if not isinstance(data.get(k), dict):
            raise ValueError('CONFIG_SECTION_MISSING: ' + k)
    lead = data['lead_trading_service_fees']
    old_rule = lead.get('rule_zh', '')
    lead.update(trading_profit_service_fee_rate=.2,
        follow_profit_share_service_fee_rate=0., follow_profit_share_permanently_waived=True,
        follow_profit_share_promotion_months=0, follow_profit_share_promotion_effective_rate=0.,
        fee_rebate_service_fee_rate=.7,
        rule_zh='带单用户需要提供带单 Trading API 和账户只读 API；' + RULE)
    profit = data['copy_trading_profit_share']
    profit.update(standard_rate=0., lead_trading_follow_profit_share_service_fee_rate=0.,
        permanent_waiver=True, promotion_policy_id='PERMANENT_PROFIT_SHARE_WAIVER',
        new_lead_promotion_months=0, promotion_effective_rate=0., promotion_per_customer=False,
        waiver_reason='PERMANENT_WAIVER', fee_due_during_promotion=0,
        fee_due_reason_during_promotion='PERMANENT_WAIVER',
        semantic_hierarchy='COPY_FOLLOW customers pay only Binance platform/system fees. LEAD_TRADING profit-share service fee is permanently zero. Zero service fee is not zero underlying income. Unknown source amounts remain unknown.')
    profit['required_customer_fields'] = [x for x in profit.get('required_customer_fields', [])
        if x not in ('promotion_start_at','promotion_end_at','promotion_months')]
    data['trading_fee_rebate'].update(standard_rate=.7, promotion_applied=False,
        rule='LEAD_TRADING service fee is 70% of verified copy-trading fee rebates. COPY_FOLLOW customers pay no extra Xuanjun service fee.')
    msg = data['customer_messaging']
    msg['required_phrase_zh'] = RULE
    msg['lead_trading_required_phrase_zh'] = lead['rule_zh']
    points = [x for x in msg.get('allowed_points_zh', []) if not
        (('跟单用户分成' in x and ('40%' in x or '6个月' in x)) or ('手续费返佣' in x and '40%' in x))]
    for x in ('跟单利润分成永久全免，平台分文不取', '带单合作的跟单手续费返佣按实际到账金额收取70%'):
        if x not in points:
            points.append(x)
    msg['allowed_points_zh'] = points
    data['finance_collection_policy'] = schedule_policy()
    data['fee_policy_id'] = POLICY_ID
    data['updated_at'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    return data, old_rule

def schedule_policy():
    return {'timezone':'Asia/Shanghai', 'weekday':'MONDAY', 'daily_readonly_rebate_scan_enabled':False,
        'monday_08_00':{'source':'BINANCE_TRADING','purpose':'TRADING_PROFIT_SNAPSHOT_HWM','rate':.2},
        'monday_15_00':{'source':'BINANCE_ACCOUNT_READONLY','purpose':'ACTUALLY_CREDITED_COPY_TRADING_FEE_REBATE',
            'start':'MONDAY 08:00','end_exclusive':'MONDAY 15:00','rate':.7},
        'invoice_rule':'COLLECT_THEN_RECONCILE_THEN_GENERATE; FAILURE_HOLD',
        'payment_reconciliation_is_separate':True,
        'scheduler_activation':'NOT_VERIFIED','rule_zh':SCHEDULE}

def patch_foundation(src):
    values = {'COPY_TRADING_COMMERCIAL_REVENUE_SHARE_RATE':'0.70',
        'COPY_TRADING_COMMERCIAL_REVENUE_SHARE_SYNC_TIME_LOCAL':'time(15, 0)',
        'COPY_TRADING_PROFIT_SHARE_SERVICE_FEE_STANDARD_RATE':'0.0',
        'COPY_TRADING_PROFIT_SHARE_PROMOTION_MONTHS':'0',
        'COPY_TRADING_PROFIT_SHARE_PROMOTION_WAIVER_REASON':repr('PERMANENT_WAIVER'),
        'COPY_TRADING_PROFIT_SHARE_FEE_DUE_REASON_DURING_PROMOTION':repr('PERMANENT_WAIVER'),
        'TRADING_FEE_REBATE_SERVICE_FEE_RATE':'0.70',
        'FINAL_WEEKLY_INVOICE_RECONCILIATION_TIME_LOCAL':'time(15, 0)'}
    for name, val in values.items():
        src = constant(src, name, val)
    src = once(src, '"promotion_end_at": self.promotion_end_at.isoformat(),',
        '"promotion_end_at": self.promotion_end_at.isoformat() if self.promotion_end_at is not None else None,')
    src = replace_def(src, 'build_copy_trading_profit_share_promotion_policy', '''
def build_copy_trading_profit_share_promotion_policy(promotion_start_at, as_of, activity_extended=None, config=None):
    return ProfitSharePromotionPolicy(promotion_start_at=promotion_start_at, promotion_end_at=None,
        promotion_months=0, standard_rate=0.0, effective_rate=0.0, promotion_status="PERMANENT_WAIVER",
        fee_waiver_reason="PERMANENT_WAIVER", activity_extension_supported=False,
        activity_extended=False, fee_due_reason="PERMANENT_WAIVER",
        promotion_policy_id="PERMANENT_PROFIT_SHARE_WAIVER")
''')
    src = replace_def(src, 'calculate_copy_trading_profit_share_service_fee', '''
def calculate_copy_trading_profit_share_service_fee(confirmed_copy_trading_profit_share_total,
    promotion_policy=None, data_source_status=PROFIT_SHARE_DATA_AVAILABLE, config=None):
    known = data_source_status == PROFIT_SHARE_DATA_AVAILABLE and confirmed_copy_trading_profit_share_total is not None
    amount = float(confirmed_copy_trading_profit_share_total) if known else None
    return {"fee_stream":COPY_TRADING_PROFIT_SHARE_SERVICE_FEE,
        "source":COPY_TRADING_COMMERCIAL_REVENUE_SHARE_SOURCE,"source_type":COPY_TRADING_PROFIT_SHARE,
        "profit_share_amount":amount,"profit_share_amount_status":"KNOWN" if known else PROFIT_SHARE_DATA_NOT_AVAILABLE,
        "data_source_status":data_source_status,"standard_rate":0.0,"effective_rate":0.0,"amount_due":0.0,
        "status":"PERMANENT_WAIVER","fee_due_reason":"PERMANENT_WAIVER","fee_waiver_reason":"PERMANENT_WAIVER",
        "promotion_policy":None,"unknown_profit_share_recorded_as_zero":False,
        "prohibited_fee_due_reason":COPY_TRADING_PROFIT_SHARE_PROHIBITED_FEE_DUE_REASON}
''')
    # Preserve aggregate source-data shape for existing DB schemas and callers.
    src = once(src, '"rate": standard_rate,\n        "amount_due": amount_due,\n        "profit_share_service_fee": profit_share_fee,',
        '"rate": None,\n        "component_rates": {"profit_share": 0.0, "fee_rebate": fee_rebate_fee["effective_rate"]},\n        "amount_due": amount_due,\n        "profit_share_service_fee": profit_share_fee,')
    src = once(src, '"rate": COPY_TRADING_COMMERCIAL_REVENUE_SHARE_RATE,', '"rate": None,')
    src = once(src, '**COPY_TRADING_COMMERCIAL_REVENUE_SHARE_RULE.to_dict(),',
        '**COPY_TRADING_COMMERCIAL_REVENUE_SHARE_RULE.to_dict(),\n                    "rate": None,\n                    "component_rates": {"profit_share": 0.0, "fee_rebate": 0.70},')
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == 'single_business_truth')
    vals = [v for n in ast.walk(fn) if isinstance(n,ast.Dict) for k,v in zip(n.keys,n.values)
            if isinstance(k,ast.Constant) and k.value == 'weekly_invoice_plan']
    if len(vals) != 1:
        raise ValueError('WEEKLY_PLAN_SHAPE')
    v = vals[0]; ls = src.splitlines(True)
    value = repr(schedule_policy())
    src = ''.join(ls[:v.lineno-1] + [ls[v.lineno-1][:v.col_offset]+value+ls[v.end_lineno-1][v.end_col_offset:]] + ls[v.end_lineno:])
    return src

def patch_preview(src):
    return once(src, '"service_fee_rate": COPY_TRADING_COMMERCIAL_REVENUE_SHARE_RATE,',
                '"service_fee_rate": 0.0,')

def patch_assistant(src):
    src = once(src, 'None if profit_share is None else profit_share * 0.40', 'None if profit_share is None else 0.0')
    src = once(src, 'None if fee_rebate is None else fee_rebate * 0.40', 'None if fee_rebate is None else fee_rebate * 0.70')
    before = '''                "跟单分润服务费标准为 40%，新加入带单客户前 6 个月该项全免；"
                f"优惠期内本项为 {profit_share_fee_during_promo:.2f} USDT，"
                "6 个月后需先确认活动是否继续；活动结束且分润金额可靠可审计时，"
                f"按示例分润计算为 {profit_share_fee_after_promo:.2f} USDT。"'''
    src = once(src, before, '                "跟单利润分成永久全免，平台分文不取；本项服务费为0.00 USDT。"')
    src = once(src, '"手续费返佣服务费为 40%，不参加 6 个月跟单分润优惠；"', '"带单合作的跟单手续费返佣服务费为70%；"')
    return once(src, '"fee_rebate_service_fee_40pct": fee_rebate_service_fee,',
        '"fee_rebate_service_fee_70pct": fee_rebate_service_fee,')

def patch_core(src):
    return replace_def(src, '_authoritative_promotion_reply', '''
def _authoritative_promotion_reply(authority_state, is_en=False):
    config = (authority_state or {}).get("referral") or {}
    fees = config.get("lead_trading_service_fees") or {}
    if fees.get("follow_profit_share_permanently_waived") is True:
        text = ("Profit-share service fee is permanently zero, with no expiry. Trading-profit service fee is 20% under HWM; verified copy-trading fee-rebate service fee is 70%." if is_en else "跟单利润分成永久全免，平台分文不取，不再设置六个月期限；带单交易利润服务费按高水位规则为20%，跟单手续费返佣服务费为70%。")
    else:
        text = "Current fee policy is unavailable." if is_en else "当前收费规则未能核实，不能确认优惠条款。"
    return _authority_result("PROMOTION_AUTHORITY_READY", text, authority_state)
''')

def patch_semantic(src):
    for a,b in [('"standard_rate_percent": 40,','"standard_rate_percent": 0,'),
        ('"rate_percent": 40,','"rate_percent": 70,'),
        ('"NEW_LEAD_FIRST_6_MONTHS_WAIVED"','"PERMANENT_WAIVER_NO_EXPIRY"'),
        ('"CONTINUE_WAIVER_IF_ACTIVITY_EXTENDED_OTHERWISE_STANDARD_RATE"','"PERMANENT_ZERO_SERVICE_FEE_NO_RENEWAL_REQUIRED"')]:
        src = once(src,a,b)
    return src

def patch_knowledge(src):
    code = '''
def _apply_customer_referral_config(self):
    from trading_execution.business_fee_foundation import load_customer_referral_config
    config = load_customer_referral_config()
    referral = config.get("referral", {})
    rule = (config.get("customer_messaging") or {}).get("lead_trading_required_phrase_zh") or RULE_TEXT
    schedule = (config.get("finance_collection_policy") or {}).get("rule_zh") or SCHEDULE_TEXT
    for topic in ("fees_and_operations", "copy_trading_advantages"):
        if topic in self.topics:
            prefix = "挂单限价通常有助于降低手续费和减少滑点，但不保证收益。" if topic == "copy_trading_advantages" else ""
            self.topics[topic]["answer"] = prefix + rule + schedule + "原始分润未知时保留UNKNOWN，免服务费不代表没有分润。"
            self.topics[topic]["source"] = config.get("source_path")
    url = referral.get("registration_url")
    if "onboarding" in self.topics and url:
        if url not in self.topics["onboarding"]["answer"]:
            self.topics["onboarding"]["answer"] += " Binance 注册入口：" + url + "；邀请码：" + str(referral.get("invitation_code") or "") + "。"
        self.topics["onboarding"]["source"] = config.get("source_path")
'''.replace('RULE_TEXT', repr(RULE)).replace('SCHEDULE_TEXT', repr(SCHEDULE))
    return replace_def(src, '_apply_customer_referral_config', code, 'KnowledgeService')

def atomic_write(path, raw, reference=None):
    st = (path if path.exists() else reference).stat()
    fd,tmp = tempfile.mkstemp(prefix='.fee-policy-',dir=str(path.parent))
    try:
        os.fchmod(fd,stat.S_IMODE(st.st_mode)); os.fchown(fd,st.st_uid,st.st_gid)
        with os.fdopen(fd,'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,str(path))
        dfd=os.open(str(path.parent),os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def prepare(root,config,domestic):
    candidates={}; originals={}
    def read(p):
        if not p.is_file() or p.is_symlink(): raise ValueError('FILE_MISSING_OR_SYMLINK: '+str(p))
        originals[p]=p.read_bytes()
        return originals[p].decode()
    data,old_rule=policy_config(json.loads(read(config)))
    candidates[config]=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    transforms={'trading_execution/business_fee_foundation.py':patch_foundation}
    if domestic:
        transforms.update({'ai_service/customer_assistant.py':patch_assistant,
            'ai_service/customer_context_core.py':patch_core,
            'ai_service/semantic_conversation_brain.py':patch_semantic,'knowledge/service.py':patch_knowledge})
    else:
        transforms['trading_execution/billing_preview.py']=patch_preview
    for name,fn in transforms.items():
        p=root/name; candidates[p]=fn(read(p))
    knowledge=root/'knowledge/data/production_knowledge_v1.json'
    if domestic:
        d=json.loads(read(knowledge))
        for name in ('fees_and_operations','copy_trading_advantages'):
            if name in d.get('topics',{}):
                d['topics'][name].update(answer=RULE+SCHEDULE+'原始分润未知时保留UNKNOWN；不承诺收益。',source=str(config),last_verified=data['updated_at'])
        d['version']=str(d.get('version',''))+'-'+POLICY_ID
        candidates[knowledge]=json.dumps(d,ensure_ascii=False,indent=2)+'\n'
    # Update existing current text documents only by the exact observed old rule.
    # Evidence, historical billing rows, releases, archives, .env and credentials are excluded.
    for docs in (root/'docs',config.parent):
        if not docs.is_dir(): continue
        count=0
        for p in sorted(docs.rglob('*.md')):
            if any(x.lower() in ('evidence','archive','archives','backup','backups') for x in p.relative_to(docs).parts): continue
            if p.is_symlink() or p.stat().st_size>300000: continue
            text=p.read_text()
            if old_rule and old_rule in text:
                read(p); candidates[p]=text.replace(old_rule,data['lead_trading_service_fees']['rule_zh'])
                count+=1
                if count>100: raise ValueError('DOCUMENT_BOUND')
    doc=config.parent/'CURRENT_BILLING_RULES.md'
    if doc.exists(): read(doc)
    candidates[doc]='# 当前收费与财务采集规则\n\n'+POLICY_ID+'\n\n'+RULE+'\n\n'+SCHEDULE+'\n\n历史账单、已结算流水、原始分润和高水位证据不覆盖。\n\n生效范围：本次清单中实际更新的文件。韩国财务部署、实际API采集窗口和执行器迁移尚未验收。\n'
    for p,text in candidates.items():
        if p.suffix=='.py': compile(text,str(p),'exec')
        elif p.suffix=='.json': json.loads(text)
    return {p:t.encode() for p,t in candidates.items()},originals

LIVE_TEST = r'''
import json,sys
from datetime import datetime,timezone
from trading_execution.business_fee_foundation import *
c=json.load(open(sys.argv[1]))
assert calculate_trading_profit_service_fee(11000,10000)['amount_due']==200
assert calculate_trading_profit_service_fee(9000,10000)['amount_due']==0
assert PAYMENT_DUE_HOURS_FROM_ACTUAL_INVOICE_SENT_AT==24
for amount in (None,0,200):
    p=calculate_copy_trading_profit_share_service_fee(amount,config=c)
    assert p['amount_due']==0 and p['profit_share_amount']==amount
    assert p['fee_due_reason']=='PERMANENT_WAIVER'
assert calculate_trading_fee_rebate_service_fee(100,config=c)['amount_due']==70
p=build_copy_trading_profit_share_promotion_policy(datetime(2020,1,1,tzinfo=timezone.utc),datetime(2026,10,26,tzinfo=timezone.utc),activity_extended=False,config=c)
assert p.effective_rate==0 and p.to_dict()['promotion_end_at'] is None
for amount in (None,200):
    i=build_final_weekly_invoice('test','test','test',11000,10000,amount,100,customer_referral_config=c)
    assert i['TOTAL_AMOUNT_DUE']==270 and i['SECTION_B']['rate'] is None
assert single_business_truth()['weekly_invoice_plan']['daily_readonly_rebate_scan_enabled'] is False
if sys.argv[2]=='domestic':
    from knowledge.service import KnowledgeService
    k=KnowledgeService()
    for key in ('fees_and_operations','copy_trading_advantages'):
        if key in k.topics:
            text=k.topics[key]['answer']
            assert '永久' in text and '70%' in text and '恢复标准' not in text
    from ai_service.customer_assistant import CustomerAssistantGateway
    g=CustomerAssistantGateway.__new__(CustomerAssistantGateway)
    r=g._try_copy_trading_benefit_estimate('请计算带单交易利润1000，跟单分润200，手续费返佣100的服务费')
    v=r['calculation']
    assert v['trading_profit_service_fee_20pct']==200
    assert v['profit_share_fee_after_promotion']==0
    assert v['fee_rebate_service_fee_70pct']==70
else:
    from trading_execution.billing_preview import ServiceFeeCalculationEngine
    e=ServiceFeeCalculationEngine().calculate(200,100,{'service_fee_rate':0,'rebate_share_rate':.7})
    assert e['amount']==70
print('OFFLINE_CURRENT_RUNTIME_CHECKS_PASS; NO_API_OR_DATABASE_CALLS')
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    host=os.uname().nodename.split('.')[0]
    if os.geteuid()!=0 or host not in (DOMESTIC,TOKYO): raise ValueError('FIXED_HOST_ROOT_REQUIRED')
    os.umask(0o077)
    lock=open('/run/xuanjun-fee-policy-update.lock','a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    domestic=host==DOMESTIC
    root=DOMESTIC_APP if domestic else TOKYO_APP
    config=(DOMESTIC_BASE/'config/customer-referral/CUSTOMER_REFERRAL_CONFIG.json' if domestic
            else Path('/home/admin/.openclaw/workspace/xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json'))
    python=(DOMESTIC_BASE/'releases/domestic-real-ai-runtime-20260926-654-r8/venv/bin/python' if domestic else root/'venv/bin/python')
    if not python.is_file() or not os.access(str(python),os.X_OK): raise ValueError('PYTHON_UNAVAILABLE')
    if args.apply and not domestic:
        # Revert our earlier mistaken disabling of the independent payment
        # reconciliation timer. Preserve its original interval and service code.
        timer=Path('/etc/systemd/system/finance-collection-sync.timer')
        service=Path('/etc/systemd/system/finance-collection-sync.service')
        if not timer.is_file() or not service.is_file(): raise ValueError('PAYMENT_TIMER_FILES_MISSING')
        if 'OnCalendar=*:0/5' not in timer.read_text() or 'finance-sync' not in service.read_text():
            raise ValueError('PAYMENT_TIMER_SOURCE_SHAPE')
        r=subprocess.run(['systemctl','enable','--now','finance-collection-sync.timer'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=25)
        if r.returncode: raise ValueError('ORIGINAL_PAYMENT_TIMER_RESTORE_FAILED')
        r=subprocess.run(['systemctl','is-active','--quiet','finance-collection-sync.timer'],timeout=10)
        if r.returncode: raise ValueError('ORIGINAL_PAYMENT_TIMER_NOT_ACTIVE')
        print('ORIGINAL_PAYMENT_RECONCILIATION_TIMER_RESTORED; 24H_DEADLINE_UNCHANGED',flush=True)
    if json.loads(config.read_text()).get('fee_policy_id')==POLICY_ID:
        raise ValueError('ALREADY_APPLIED_USE_EXISTING_CHECKPOINT')
    candidates,originals=prepare(root,config,domestic)
    print('HOST:',host,'CANDIDATE_FILES:',len(candidates),flush=True)
    for p,b in candidates.items(): print('CANDIDATE:',p,'SHA256:',sha(b))
    if not args.apply:
        print('PREPARED_NOT_APPLIED'); return
    checkpoint=Path('/root/xuanjun-fee-policy-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    checkpoint.mkdir(mode=0o700)
    manifest=[]
    for n,(p,b) in enumerate(candidates.items()):
        item={'path':str(p),'new_sha256':sha(b),'existed':p in originals}
        if p in originals:
            name='%02d.original'%n; (checkpoint/name).write_bytes(originals[p])
            item.update(backup=name,old_sha256=sha(originals[p]))
        manifest.append(item)
    (checkpoint/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print('CHECKPOINT:',checkpoint,flush=True)
    changed=[]
    try:
        for p,b in candidates.items():
            if p in originals and p.read_bytes()!=originals[p]: raise ValueError('CONCURRENT_CHANGE: '+str(p))
            if p not in originals and p.exists(): raise ValueError('NEW_FILE_CONFLICT')
            atomic_write(p,b,config); changed.append(p)
        env=dict(os.environ,PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1',CUSTOMER_REFERRAL_CONFIG_PATH=str(config))
        test=subprocess.run([str(python),'-B','-c',LIVE_TEST,str(config),'domestic' if domestic else 'tokyo'],
            env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=45,cwd=str(root))
        (checkpoint/'offline-test.private.log').write_text(test.stdout+'\n'+test.stderr)
        if test.returncode: raise ValueError('OFFLINE_CHECK_FAILED; PRIVATE_LOG_AT_CHECKPOINT')
        print(test.stdout.strip(),flush=True)
        if domestic:
            subprocess.run(['systemctl','restart','provider-neutral-domestic-bridge.service'],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            import time
            for _ in range(10):
                h=subprocess.run([str(python),'-B',str(Path('/home/openclaw_ops/feishu-customer-recovery-v1/customer-bridge-call-v1.py')),'--health'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=10)
                if h.returncode==0 and 'BRIDGE_HEALTH_OK' in h.stdout: break
                time.sleep(1)
            else: raise ValueError('BRIDGE_HEALTH_FAILED')
        (checkpoint/'SUCCESS.json').write_text(json.dumps({'policy_id':POLICY_ID,'host':host,'files':len(candidates),'api_calls':0,'database_mutations':0,'timers_activated':0}))
        print('CURRENT_FEE_RULES_UPDATED: 20% / PERMANENT_0% / 70%')
        print('SCHEDULER_IMPLEMENTATION_AND_KOREA_MIGRATION: PENDING_NOT_ACTIVATED')
        print('OTHER_HOSTS_AND_UNLOCATED_DOCUMENTS: PENDING')
    except BaseException:
        for p in reversed(changed):
            if p in originals: atomic_write(p,originals[p],config)
            else: p.unlink()
        if domestic:
            subprocess.run(['systemctl','restart','provider-neutral-domestic-bridge.service'],timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        print('RESTORED_FILES; CHECKPOINT:',checkpoint,flush=True)
        raise

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('HOLD:',type(e).__name__,str(e)); raise SystemExit(2)
