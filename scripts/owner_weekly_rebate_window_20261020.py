#!/usr/bin/env python3
"""Install Monday rebate collection code on Tokyo; no API calls or invoice sends.
Prepare the original timers with explicit Shanghai time; do not enable disabled timers.
Payment reconciliation and the 24-hour deadline are untouched. Korea remains pending.
"""
import ast, datetime, fcntl, hashlib, json, os, stat, subprocess, tempfile, textwrap
from pathlib import Path
RUNTIME = '"""Monday-only fee rebate evidence. No payment collection or trading writes."""\nfrom datetime import datetime, timedelta, timezone\nfrom decimal import Decimal\nfrom zoneinfo import ZoneInfo\n\nPOLICY_ID = \'MONDAY_REBATE_WINDOW_20261020_V1\'\nSCOPE = \'weekly_copy_fee_rebate_window\'\n\n\ndef monday_window(now):\n    # Repository utc_now returns naive UTC; never interpret it as host local time.\n    if now.tzinfo is None:\n        now = now.replace(tzinfo=timezone.utc)\n    local = now.astimezone(ZoneInfo(\'Asia/Shanghai\'))\n    end = local.replace(hour=15, minute=0, second=0, microsecond=0)\n    if local.weekday() != 0 or local < end or local >= end + timedelta(minutes=30):\n        raise ValueError(\'OUTSIDE_MONDAY_1500_WINDOW\')\n    start = end.replace(hour=8)\n    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)\n\n\ndef verified_rebate_rows(adapter, start, end):\n    start_ms, end_ms = int(start.timestamp()*1000), int(end.timestamp()*1000)\n    payload = adapter.get_distribution_records(start_time=start_ms, end_time=end_ms, limit=500)\n    if not isinstance(payload, dict) or not isinstance(payload.get(\'rows\'), list):\n        raise ValueError(\'INVALID_DISTRIBUTION_RESPONSE\')\n    rows = payload[\'rows\']\n    total = payload.get(\'total\')\n    if isinstance(total, bool) or not isinstance(total, int) or total != len(rows) or len(rows) >= 500:\n        raise ValueError(\'INCOMPLETE_DISTRIBUTION_RESPONSE\')\n    selected, seen, amount = [], set(), Decimal(\'0\')\n    for row in rows:\n        if not isinstance(row, dict):\n            raise ValueError(\'INVALID_DISTRIBUTION_ROW\')\n        event = row.get(\'time\') or row.get(\'timestamp\') or row.get(\'divTime\') or row.get(\'updateTime\') or row.get(\'distributeTime\')\n        if isinstance(event, bool) or event is None or not start_ms <= int(event) <= end_ms:\n            raise ValueError(\'DISTRIBUTION_EVENT_OUTSIDE_WINDOW\')\n        text = \' \'.join(str(row.get(k) or \'\') for k in\n            (\'enInfo\',\'info\',\'remark\',\'description\',\'type\',\'source\')).lower()\n        if \'copy trading referral program\' not in text:\n            if \'copy\' in text and \'trading\' in text:\n                raise ValueError(\'UNCLASSIFIED_COPY_TRADING_CREDIT\')\n            continue\n        if row.get(\'asset\') != \'USDT\':\n            raise ValueError(\'REBATE_ASSET_REQUIRES_VERIFIED_CONVERSION\')\n        value = Decimal(str(row.get(\'amount\')))\n        if not value.is_finite() or value <= 0:\n            raise ValueError(\'INVALID_REBATE_AMOUNT\')\n        key = row.get(\'tranId\') or row.get(\'transactionId\') or row.get(\'id\') or row.get(\'recordId\')\n        if key is None or str(key) in seen:\n            raise ValueError(\'MISSING_OR_DUPLICATE_REBATE_ID\')\n        seen.add(str(key))\n        selected.append(row)\n        amount += value\n    return selected, amount\n\n\ndef sync_owner_weekly_rebate(repository, now):\n    from accounts.credential_store import CredentialStore\n    from binance_integration.adapter import BinanceReadOnlyAdapter\n    from binance_integration.commercial_ledger_adapter import CommercialLedgerAdapter, SPOT_DISTRIBUTION_ENDPOINT\n    from trading_execution.commercial_ledger_sync import normalize_spot_commercial_records, COMMERCIAL_LEDGER_HEALTHY\n    from trading_execution.credential_readiness import EnvironmentBoundCredentialProvider, PRODUCTION\n    from trading_execution.dual_api_readiness import ROLE_BINANCE_ACCOUNT_READONLY\n    from trading_execution.production_activation import OWNER_CUSTOMER_ID, OWNER_ACCOUNT_ID, load_local_env_if_needed\n    start, end = monday_window(now)\n    load_local_env_if_needed()\n    store = CredentialStore()\n    records = store.repository.list(customer_id=OWNER_CUSTOMER_ID, account_id=OWNER_ACCOUNT_ID,\n        exchange=\'BINANCE\', environment=PRODUCTION, status=\'ACTIVE\')\n    matches = [r for r in records if (r.get(\'metadata\') or {}).get(\'credential_role\') == ROLE_BINANCE_ACCOUNT_READONLY]\n    if len(matches) != 1:\n        raise ValueError(\'READONLY_CREDENTIAL_NOT_UNIQUE\')\n    provider = EnvironmentBoundCredentialProvider(matches[0][\'credential_id\'], PRODUCTION, store=store)\n    adapter = CommercialLedgerAdapter(BinanceReadOnlyAdapter(credential_provider=provider, timeout=10),\n        ROLE_BINANCE_ACCOUNT_READONLY)\n    rows, total = verified_rebate_rows(adapter, start, end)\n    normalized = normalize_spot_commercial_records(rows, SPOT_DISTRIBUTION_ENDPOINT,\n        ROLE_BINANCE_ACCOUNT_READONLY, OWNER_CUSTOMER_ID, OWNER_ACCOUNT_ID)\n    evidence = {\'policy_id\':POLICY_ID, \'window_start\':start.isoformat(), \'window_end\':end.isoformat(),\n        \'verified_count\':len(normalized), \'verified_rebate_usdt\':str(total), \'complete\':True,\n        \'source_credential_role\':ROLE_BINANCE_ACCOUNT_READONLY,\n        \'profit_share_service_fee\':0, \'profit_share_income\':\'UNKNOWN_NOT_COLLECTED\'}\n    # Existing tables and deduplication; a separate scope cannot certify the full old ledger.\n    repository.save_commercial_sync_batch(normalized, OWNER_CUSTOMER_ID, OWNER_ACCOUNT_ID,\n        SCOPE, end, COMMERCIAL_LEDGER_HEALTHY, last_successful_sync_at=end, metadata=evidence)\n    return evidence\n\n\ndef require_candidate_matches_rebate(candidate, evidence):\n    from math import isclose\n    actual = candidate.get(\'commercial_ledger_evidence\') or {}\n    total = Decimal(evidence[\'verified_rebate_usdt\'])\n    if (actual.get(\'fee_rebate_record_count\') != evidence[\'verified_count\']\n        or not isclose(float(actual.get(\'fee_rebate_total\', -1)), float(total), rel_tol=0, abs_tol=1e-8)):\n        raise ValueError(\'PERSISTED_REBATE_EVIDENCE_MISMATCH\')\n    # The candidate\'s combined B amount must contain no follow-profit service fee.\n    expected = (total * Decimal(\'0.70\')).quantize(Decimal(\'0.01\'))\n    if not isclose(float(candidate.get(\'SECTION_B_AMOUNT\', -1)), float(expected), rel_tol=0, abs_tol=1e-7):\n        raise ValueError(\'REBATE_INVOICE_AMOUNT_MISMATCH\')\n'
ORIGINAL_SHA = 'd68221751be31c888490d8e4b0c8ada31637825cdf686a4eabeedc6991488c9d'

def once(src, old, new):
    if src.count(old)!=1:
        raise ValueError('SOURCE_SHAPE_MISMATCH:'+old[:70])
    return src.replace(old,new,1)

def patch_production(src):
    src=once(src,'from zoneinfo import ZoneInfo',
        'from zoneinfo import ZoneInfo\nfrom trading_execution.weekly_rebate_window import (\n    monday_window, sync_owner_weekly_rebate, require_candidate_matches_rebate,\n)')
    start=src.index('def _sync_owner_account_readonly(')
    end=src.index('\n\ndef _positions(',start)
    old=src[start:end]
    new=old.replace('_sync_owner_account_readonly','_sync_owner_account_trading').replace('readonly_credential_id','trading_credential_id').replace('readonly_id','trading_id').replace('ROLE_BINANCE_ACCOUNT_READONLY','ROLE_BINANCE_TRADING').replace('account-readonly credential missing','trading credential missing')
    # Select exactly one active credential for this Owner account and role.
    begin=new.index('    trading_id = trading_credential_id')
    finish=new.index('    provider = EnvironmentBoundCredentialProvider(',begin)
    new=new[:begin]+'''    records = store.repository.list(
        customer_id=OWNER_CUSTOMER_ID, account_id=OWNER_ACCOUNT_ID,
        exchange="BINANCE", environment=PRODUCTION, status="ACTIVE",
    )
    matches = [record for record in records
        if _credential_role(record) == ROLE_BINANCE_TRADING
        and (trading_credential_id is None or record["credential_id"] == trading_credential_id)]
    if len(matches) != 1:
        raise RuntimeError("Owner trading credential missing or ambiguous")
    trading_id = matches[0]["credential_id"]
'''+new[finish:]
    src=src[:start]+new+src[end:]
    src=once(src,'sync_evidence = _sync_owner_account_readonly(repository)',
        'sync_evidence = _sync_owner_account_trading(repository)')
    src=once(src,'"source": "BINANCE_ACCOUNT_READONLY_GET_SYNC",','"source": "BINANCE_TRADING_GET_SYNC",') if src.count('"source": "BINANCE_ACCOUNT_READONLY_GET_SYNC",')==1 else src
    # Two source labels in the original: replace the first, then the complete B block.
    if '"source": "BINANCE_ACCOUNT_READONLY_GET_SYNC",' in src:
        src=src.replace('"source": "BINANCE_ACCOUNT_READONLY_GET_SYNC",','"source": "BINANCE_TRADING_GET_SYNC",',1)
    src=once(src,'''        readonly_source_evidence={
            "source": "BINANCE_ACCOUNT_READONLY_GET_SYNC",
            "account_status": account.get("status"),
            "balance_count": account.get("balance_count"),
        },''','''        readonly_source_evidence={
            "source": "DEFERRED_TO_MONDAY_1500_REBATE_QUERY",
            "status": "NOT_COLLECTED_AT_0800",
        },''')
    # Treat repository naive datetimes as UTC, independent of the host timezone.
    src=once(src,'def next_weekly_time(now=None, hour=8, minute=0):', '''def _utc_aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def next_weekly_time(now=None, hour=8, minute=0):''')
    src=src.replace('(now or utc_now()).astimezone(zone)','_utc_aware(now or utc_now()).astimezone(zone)')
    src=src.replace('now = now or utc_now()','now = _utc_aware(now or utc_now())')
    src=once(src,'"next_final_invoice_trigger": next_weekly_time(now, 13, 30),','"next_final_invoice_trigger": next_weekly_time(now, 15, 0),')
    # Reject early/off-day invocation before scheduling or claiming a job.
    signature='def run_owner_weekly_final_invoice(repository=None, now=None, trigger_source="SYSTEMD_TIMER"):\n    now = _utc_aware(now or utc_now())'
    src=once(src,signature,signature+'''
    try:
        rebate_start, rebate_end = monday_window(now)
    except ValueError:
        return {"status":"FINAL_INVOICE_HOLD", "reason":"OUTSIDE_MONDAY_1500_WINDOW"}''')
    old='''    candidate = weekly.build_final_invoice_candidate(
        snapshot,
        candidate_at=now,
        commercial_period_start=_commercial_effective_start_for_utc_ledger(
            effective["effective_from"]
        ),
        commercial_period_end=_commercial_period_end_for_utc_ledger(now),
    )'''
    new='''    try:
        source = snapshot.get("trading_source_evidence") or {}
        if source.get("source") != "BINANCE_TRADING_GET_SYNC":
            raise ValueError("SNAPSHOT_TRADING_ROLE_EVIDENCE_MISSING")
        effective_start = _commercial_effective_start_for_utc_ledger(effective["effective_from"])
        if effective_start > rebate_start.replace(tzinfo=None):
            raise ValueError("BILLING_EFFECTIVE_AFTER_REBATE_WINDOW_START")
        rebate_evidence = sync_owner_weekly_rebate(repository, now)
        candidate = weekly.build_final_invoice_candidate(
            snapshot, candidate_at=now,
            commercial_period_start=rebate_start.replace(tzinfo=None),
            commercial_period_end=rebate_end.replace(tzinfo=None),
        )
        require_candidate_matches_rebate(candidate, rebate_evidence)
    except Exception as exc:
        finished = ops.complete_job(
            claimed, STATUS_BLOCKED, failure_code="WEEKLY_REBATE_EVIDENCE_FAILED",
            failure_message="weekly rebate source or reconciliation failed: " + type(exc).__name__,
        )
        return {"status":"FINAL_INVOICE_HOLD", "job":finished,
            "reason":"WEEKLY_REBATE_EVIDENCE_FAILED", "error_type":type(exc).__name__}'''
    src=once(src,old,new)
    src=once(src,'"owner_internal_invoice": True,','"owner_internal_invoice": True,\n        "weekly_rebate_evidence": rebate_evidence,')
    compile(src,'production_activation.py','exec')
    return src


def offline_checks(runtime, production):
    from datetime import datetime, timezone
    from decimal import Decimal
    import types
    ns={}
    exec(compile(runtime,'weekly_rebate_window.py','exec'),ns)
    utc=timezone.utc
    valid=datetime(2026,10,26,7,0,tzinfo=utc)
    start,end=ns['monday_window'](valid)
    assert start==datetime(2026,10,26,0,0,tzinfo=utc)
    assert end==valid
    assert ns['monday_window'](valid.replace(tzinfo=None))==(start,end)
    assert ns['monday_window'](datetime.fromisoformat('2026-10-26T16:00:00+09:00'))==(start,end)
    for bad in (datetime(2026,10,26,6,59,59,tzinfo=utc),datetime(2026,10,26,7,30,tzinfo=utc),datetime(2026,10,27,7,tzinfo=utc)):
        try: ns['monday_window'](bad)
        except ValueError: pass
        else: raise AssertionError('off-window accepted')
    def row(event, **kw):
        return dict({'tranId':'r1','divTime':int(event.timestamp()*1000),
            'asset':'USDT','amount':'100','enInfo':'Copy Trading Referral Program'},**kw)
    class Adapter:
        def __init__(self,payload): self.payload=payload;self.calls=[]
        def get_distribution_records(self,**kw): self.calls.append(kw);return self.payload
    a=Adapter({'rows':[row(start)],'total':1})
    rows,total=ns['verified_rebate_rows'](a,start,end)
    assert total==Decimal('100') and len(rows)==1
    assert a.calls==[{'start_time':int(start.timestamp()*1000),'end_time':int(end.timestamp()*1000),'limit':500}]
    assert ns['verified_rebate_rows'](Adapter({'rows':[],'total':0}),start,end)==([],Decimal('0'))
    at_end=row(end);at_end['tranId']='r2'
    assert len(ns['verified_rebate_rows'](Adapter({'rows':[row(start),at_end],'total':2}),start,end)[0])==2
    badrow=row(start);badrow['divTime']-=1
    wrongasset=row(start);wrongasset['asset']='BTC'
    unknown=row(start);unknown['enInfo']='copy trading unclear credit'
    nan=row(start);nan['amount']='NaN'
    for payload in ({'rows':[],'total':1},{'rows':[]},{'code':-1,'msg':'error'},
        {'rows':[badrow],'total':1},{'rows':[wrongasset],'total':1},{'rows':[unknown],'total':1},
        {'rows':[nan],'total':1},{'rows':[row(start),row(start)],'total':2},
        {'rows':[row(start)]*500,'total':500}):
        try: ns['verified_rebate_rows'](Adapter(payload),start,end)
        except (ValueError,TypeError): pass
        else: raise AssertionError('invalid evidence accepted')
    candidate={'commercial_ledger_evidence':{'fee_rebate_record_count':1,'fee_rebate_total':100},'SECTION_B_AMOUNT':70}
    evidence={'verified_count':1,'verified_rebate_usdt':'100'}
    ns['require_candidate_matches_rebate'](candidate,evidence)
    for bad in ({**candidate,'SECTION_B_AMOUNT':40},{**candidate,'commercial_ledger_evidence':{'fee_rebate_record_count':2,'fee_rebate_total':100}}):
        try: ns['require_candidate_matches_rebate'](bad,evidence)
        except ValueError: pass
        else: raise AssertionError('mismatched invoice accepted')
    # Execute the actual patched final-invoice function with deliberately failing adapters.
    tree=ast.parse(production)
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_owner_weekly_final_invoice']
    assert len(functions)==1
    class Repo:
        def get_weekly_settlement_snapshot(self,*a): return {'trading_source_evidence':{'source':'BINANCE_TRADING_GET_SYNC'}}
        def get_production_billing_effective_from(self,*a): return {'effective_from':start}
    class Ops:
        def __init__(self,r):pass
        def schedule_job(self,*a,**kw):return {'run_id':'one'}
        def claim_job(self,*a):return {'claimed':True}
        def complete_job(self,*a,**kw):return {'status':a[1]}
    class Gate:
        def require_owner(self,*a):return {}
    def fail(*a,**kw):raise ConnectionError('offline failure')
    n=dict(ns, _utc_aware=lambda t:t.replace(tzinfo=utc) if t.tzinfo is None else t,
        utc_now=lambda:valid, TradingIntegrationRepository=Repo, ProductionEligibilityGate=Gate,
        OWNER_CUSTOMER_ID='owner',OWNER_ACCOUNT_ID='account',current_cycle_cut=lambda t:start,
        settlement_cycle_for_cut=lambda t:{'billing_cycle_id':'cycle'},ProductionOperationsOrchestrator=Ops,
        make_job_key=lambda *a,**kw:'job',JOB_FINAL_INVOICE_PREPARATION='FINAL',STATUS_SUCCESS='SUCCESS',
        STATUS_BLOCKED='BLOCKED',WeeklySettlementService=lambda r:None,
        _commercial_effective_start_for_utc_ledger=lambda t:t.replace(tzinfo=None),
        sync_owner_weekly_rebate=fail,BillingLifecycleService=lambda r:(_ for _ in ()).throw(AssertionError('invoice must not be created')),
        OWNER_INVOICE_DELIVERY_MODE='INTERNAL')
    code=ast.Module(body=functions,type_ignores=[])
    exec(compile(code,'patched-final-invoice','exec'),n)
    assert n['run_owner_weekly_final_invoice'](Repo(),valid)['status']=='FINAL_INVOICE_HOLD'
    assert n['run_owner_weekly_final_invoice'](Repo(),datetime(2026,10,27,7,tzinfo=utc))['reason']=='OUTSIDE_MONDAY_1500_WINDOW'
    # A valid API receipt followed by contaminated persisted records must also HOLD.
    class Weekly:
        def build_final_invoice_candidate(self,*a,**kw):
            assert kw['commercial_period_start']==start.replace(tzinfo=None)
            assert kw['commercial_period_end']==end.replace(tzinfo=None)
            return {**candidate,'SECTION_B_AMOUNT':40}
    n['WeeklySettlementService']=lambda r:Weekly()
    n['sync_owner_weekly_rebate']=lambda r,t:evidence
    assert n['run_owner_weekly_final_invoice'](Repo(),valid)['status']=='FINAL_INVOICE_HOLD'
    # The morning helper selects Trading, passes that provider, and records that real role.
    helpers=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='_sync_owner_account_trading']
    seen=[]
    records=[{'credential_id':'read','metadata':{'credential_role':'READONLY'}},
             {'credential_id':'trade','metadata':{'credential_role':'TRADING'}}]
    class Store:
        repository=types.SimpleNamespace(list=lambda **kw:records)
    def provider(cid,env,store):seen.append(('provider',cid));return cid
    class ReadAdapter:
        def __init__(self,credential_provider,timeout):self.session=types.SimpleNamespace(calls=[]);assert credential_provider=='trade'
    class Sync:
        def __init__(self,adapter,repository,source_credential_role):seen.append(('role',source_credential_role))
        def sync(self,*a):return {'status':'SUCCESS'}
    h={'load_local_env_if_needed':lambda:None,'CredentialStore':Store,'OWNER_CUSTOMER_ID':'owner',
        'OWNER_ACCOUNT_ID':'account','PRODUCTION':'PRODUCTION','ROLE_BINANCE_TRADING':'TRADING',
        '_credential_role':lambda r:r['metadata']['credential_role'],'EnvironmentBoundCredentialProvider':provider,
        'BinanceReadOnlyAdapter':ReadAdapter,'AccountSyncService':Sync,'OWNER_SYMBOLS':('BTCUSDT',)}
    exec(compile(ast.Module(body=helpers,type_ignores=[]),'morning-helper','exec'),h)
    h['_sync_owner_account_trading'](Repo())
    assert seen==[('provider','trade'),('role','TRADING')]
    records.append(records[-1])
    try:h['_sync_owner_account_trading'](Repo())
    except RuntimeError:pass
    else:raise AssertionError('ambiguous Trading credential accepted')
    print('OFFLINE_WINDOW_BOUNDARIES_COMPLETENESS_ROLE_AND_INVOICE_HOLD_CHECKS_PASS',flush=True)


def atomic(path,raw,mode,uid,gid):
    fd,tmp=tempfile.mkstemp(prefix='.weekly-window-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode);os.fchown(fd,uid,gid)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    if os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZ6wee8q9z4t03hvqumwfhZ':
        raise SystemExit('HOLD_NOT_TOKYO')
    os.umask(0o077)
    lock=open('/run/xuanjun-weekly-window-update.lock','a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    root=Path('/opt/trading-system')
    p=root/'trading_execution/production_activation.py'
    if not p.is_file() or p.is_symlink():raise SystemExit('HOLD_PRODUCTION_SOURCE')
    original=p.read_bytes()
    if hashlib.sha256(original).hexdigest()!=ORIGINAL_SHA:raise SystemExit('HOLD_PRODUCTION_SOURCE_CHANGED')
    config=Path('/home/admin/.openclaw/workspace/xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json')
    if json.loads(config.read_text()).get('fee_policy_id')!='OWNER_FEE_POLICY_20261020_20_0_70_V1':
        raise SystemExit('HOLD_FEE_POLICY_NOT_APPLIED')
    foundation=root/'trading_execution/business_fee_foundation.py'
    ns=ast.parse(foundation.read_text())
    constants={n.targets[0].id:ast.literal_eval(n.value) for n in ns.body if isinstance(n,ast.Assign)
        and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
        and n.targets[0].id=='PAYMENT_DUE_HOURS_FROM_ACTUAL_INVOICE_SENT_AT'}
    if constants.get('PAYMENT_DUE_HOURS_FROM_ACTUAL_INVOICE_SENT_AT')!=24:raise SystemExit('HOLD_PAYMENT_DEADLINE')
    payment=Path('/etc/systemd/system/finance-collection-sync.timer')
    payment_before=payment.read_bytes()
    if subprocess.run(['systemctl','is-active','--quiet',payment.name]).returncode:raise SystemExit('HOLD_ORIGINAL_PAYMENT_TIMER_INACTIVE')
    patched=patch_production(original.decode())
    compile(RUNTIME,'weekly_rebate_window.py','exec')
    offline_checks(RUNTIME,patched)
    candidates={p:patched.encode(),root/'trading_execution/weekly_rebate_window.py':RUNTIME.encode()}
    for name,hour in (('billing-operations-weekly-settlement.timer',8),('billing-operations-weekly-final-invoice.timer',15)):
        unit=Path('/etc/systemd/system')/name
        if not unit.is_file() or unit.is_symlink():raise SystemExit('HOLD_TIMER_MISSING:'+name)
        drop=Path(str(unit)+'.d')/'owner-weekly-window.conf'
        if drop.exists():raise SystemExit('HOLD_EXISTING_TIMER_DROPIN:'+str(drop))
        candidates[drop]=('[Timer]\nOnCalendar=\nOnCalendar=Mon *-*-* %02d:00:00 Asia/Shanghai\nPersistent=false\nRandomizedDelaySec=0\nAccuracySec=1s\n'%hour).encode()
    doc=config.parent/'WEEKLY_REBATE_IMPLEMENTATION.md'
    candidates[doc]=('''# 当前周一财务采集实现

收费：交易利润20%，跟单利润服务费永久0%，实际到账跟单手续费返佣70%。
时间统一 Asia/Shanghai。周一08:00由带单凭据经只读GET适配器采集原快照；
周一15:00由账户只读凭据查询当天08:00至15:00（含边界）返佣。
只读取原分发接口；总条数不符、500条截断、缺时间/ID、重复ID、非USDT、
无法识别的跟单入账、API失败或持久化金额不符时HOLD，不按零金额出账。
确认完整的空回执才可确认为本窗口返佣0。分润服务费0不表示原始分润收入0。
仍使用原账本、幂等键和Owner内部账单路径；不开放真实客户发账。
原付款核销每五分钟入口与实际发账后24小时期限不变。
东京代码已更新；08:00原启用状态保留，15:00原禁用状态保留。
韩国财务迁移、凭据绑定和实际API验收尚未完成，不能声称迁移已验收。
''').encode()
    if (root/'trading_execution/weekly_rebate_window.py').exists() or doc.exists():raise SystemExit('HOLD_EXISTING_INSTALL')
    checkpoint=Path('/root')/('xuanjun-weekly-window-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    checkpoint.mkdir(mode=0o700)
    entries=[]
    for i,(path,raw) in enumerate(candidates.items()):
        if path.is_symlink():raise SystemExit('HOLD_SYMLINK:'+str(path))
        old=path.read_bytes() if path.exists() else None
        st=path.stat() if old is not None else p.stat()
        mode=stat.S_IMODE(st.st_mode) if old is not None else (0o644 if str(path).startswith('/etc/') else stat.S_IMODE(p.stat().st_mode))
        uid,gid=(0,0) if str(path).startswith('/etc/') else (st.st_uid,st.st_gid)
        if old is not None:(checkpoint/(str(i)+'.original')).write_bytes(old)
        entries.append((path,raw,old,mode,uid,gid))
    (checkpoint/'manifest.json').write_text(json.dumps([{'path':str(p),'existed':old is not None,
        'new_sha256':hashlib.sha256(raw).hexdigest(),'original_sha256':hashlib.sha256(old).hexdigest() if old is not None else None}
        for p,raw,old,*_ in entries],indent=2))
    print('CHECKPOINT:',checkpoint,flush=True)
    changed=[]
    try:
        for path,raw,old,mode,uid,gid in entries:
            if (path.read_bytes() if path.exists() else None)!=old:raise ValueError('CONCURRENT_CHANGE')
            path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            atomic(path,raw,mode,uid,gid);changed.append((path,raw,old,mode,uid,gid))
        r=subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=20)
        if r.returncode:raise ValueError('SYSTEMD_RELOAD_FAILED')
        if payment.read_bytes()!=payment_before:raise ValueError('PAYMENT_TIMER_CHANGED')
        for path,raw,*_ in entries:
            if path.read_bytes()!=raw:raise ValueError('WRITTEN_CONTENT_MISMATCH')
        for name in ('billing-operations-weekly-settlement.timer','billing-operations-weekly-final-invoice.timer','finance-collection-sync.timer'):
            r=subprocess.run(['systemctl','show',name,'--property=ActiveState,TimersCalendar'],capture_output=True,text=True,timeout=10)
            print('UNIT:',name,flush=True);print(r.stdout.strip(),flush=True)
        print('TOKYO_WEEKLY_WINDOW_CODE_INSTALLED; NO_BUSINESS_JOB_INVOKED')
        print('PAYMENT_RECONCILIATION_AND_24H_DEADLINE_UNCHANGED')
        print('KOREA_MIGRATION_AND_LIVE_API_ACCEPTANCE_PENDING; DISABLED_TIMERS_NOT_ENABLED')
    except Exception as exc:
        for path,raw,old,mode,uid,gid in reversed(changed):
            if path.read_bytes()!=raw:continue
            if old is None:path.unlink()
            else:atomic(path,old,mode,uid,gid)
        subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=20)
        print('UPDATE_FAILED:',type(exc).__name__,'FILES_RESTORED; CHECKPOINT:',checkpoint)
        raise SystemExit(2)

if __name__=='__main__':main()
