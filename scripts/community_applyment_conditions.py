"""Conditional ordinary-provider application fields, official 4012719997.

Does not invent industry/bank requirements: current official catalogs and the
provider remain authoritative. Error messages contain field paths, no PII.
"""
import datetime as dt
import re

DOCS={ 'IDENTIFICATION_TYPE_'+s for s in ('IDCARD','OVERSEA_PASSPORT','HONGKONG_PASSPORT','MACAO_PASSPORT','TAIWAN_PASSPORT','FOREIGN_RESIDENT','HONGKONG_MACAO_RESIDENT','TAIWAN_RESIDENT') }
PASSPORT='IDENTIFICATION_TYPE_OVERSEA_PASSPORT'

def required(obj,fields,path):
    if type(obj) is not dict:raise ValueError('OFFICIAL_OBJECT_REQUIRED:'+path)
    missing=[path+'.'+k for k in fields if type(obj.get(k)) is not str or not obj[k].strip()]
    if missing:raise ValueError('MISSING_OFFICIAL_FIELDS:'+','.join(missing))
    if any(obj[k]!=obj[k].strip() or any(ord(c)<32 for c in obj[k]) for k in fields):raise ValueError('INVALID_OFFICIAL_TEXT:'+path)

def period(obj,begin,end,path,today):
    required(obj,(begin,end),path)
    try:
        start=dt.date.fromisoformat(obj[begin]);finish=None if obj[end]=='长期' else dt.date.fromisoformat(obj[end])
    except (ValueError,TypeError):raise ValueError('INVALID_OFFICIAL_PERIOD:'+path) from None
    if start<dt.date(1900,1,1) or start>=today or finish is not None and (finish<=start or finish<today):raise ValueError('INVALID_OR_EXPIRED_OFFICIAL_PERIOD:'+path)

def document(number,kind,path):
    if type(kind) is not str or kind not in DOCS:raise ValueError('INVALID_OFFICIAL_DOCUMENT_TYPE:'+path)
    patterns={'IDCARD':r'[0-9]{17}[0-9X]','OVERSEA_PASSPORT':r'[0-9A-Za-z-]{4,15}','HONGKONG_PASSPORT':r'[Hh](?:[0-9A-Za-z]{8}|[0-9A-Za-z]{10})','MACAO_PASSPORT':r'[Mm](?:[0-9A-Za-z]{8}|[0-9A-Za-z]{10})','TAIWAN_PASSPORT':r'(?:[0-9]{8}|[0-9]{10})','FOREIGN_RESIDENT':r'[0-9A-Za-z]{15}','HONGKONG_MACAO_RESIDENT':r'[0-9]{17}[0-9X]','TAIWAN_RESIDENT':r'[0-9]{17}[0-9X]'}
    if type(number) is not str or not re.fullmatch(patterns[kind.removeprefix('IDENTIFICATION_TYPE_')],number):raise ValueError('INVALID_OFFICIAL_DOCUMENT_NUMBER:'+path)

def images(value,path,max_count=5):
    if type(value) is not list or not 1<=len(value)<=max_count or any(type(v) is not str or not 1<=len(v)<=1024 for v in value):raise ValueError('INVALID_OFFICIAL_MEDIA_LIST:'+path)

def validate(profile,entity,now):
    today=dt.datetime.fromtimestamp(now,dt.timezone(dt.timedelta(hours=8))).date()
    contact=profile['contact_info'];subject=profile['subject_info'];identity=subject['identity_info'];bank=profile['bank_account_info']
    required(contact,('contact_type','contact_name','mobile_phone','contact_email'),'contact_info')
    if contact['contact_type'] not in ('LEGAL','SUPER'):raise ValueError('INVALID_OFFICIAL_CONTACT_TYPE')
    if not re.fullmatch(r'[0-9+-]{5,20}',contact['mobile_phone']) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',contact['contact_email']):raise ValueError('INVALID_OFFICIAL_CONTACT_FORMAT')
    if contact['contact_type']=='SUPER':
        required(contact,('contact_id_doc_type','contact_id_number','contact_id_doc_copy'),'contact_info')
        document(contact['contact_id_number'],contact['contact_id_doc_type'],'contact_info')
        if contact['contact_id_doc_type']!=PASSPORT:required(contact,('contact_id_doc_copy_back',),'contact_info')
        period(contact,'contact_period_begin','contact_period_end','contact_info',today)
    if identity.get('id_holder_type','LEGAL')!='LEGAL':raise ValueError('ENTERPRISE_OR_INDIVIDUAL_LEGAL_IDENTITY_REQUIRED')
    kind=identity.get('id_doc_type')
    if type(kind) is not str or kind not in DOCS:raise ValueError('OFFICIAL_LEGAL_DOCUMENT_TYPE_REQUIRED')
    if kind=='IDENTIFICATION_TYPE_IDCARD':
        info=identity.get('id_card_info');required(info,('id_card_copy','id_card_national','id_card_name','id_card_number'),'subject_info.identity_info.id_card_info')
        document(info['id_card_number'],kind,'subject_info.identity_info')
        period(info,'card_period_begin','card_period_end','subject_info.identity_info.id_card_info',today)
        name=info['id_card_name']
    else:
        info=identity.get('id_doc_info');required(info,('id_doc_copy','id_doc_name','id_doc_number'),'subject_info.identity_info.id_doc_info')
        if kind!=PASSPORT:required(info,('id_doc_copy_back',),'subject_info.identity_info.id_doc_info')
        if entity=='ENTERPRISE':required(info,('id_doc_address',),'subject_info.identity_info.id_doc_info')
        document(info['id_doc_number'],kind,'subject_info.identity_info')
        period(info,'doc_period_begin','doc_period_end','subject_info.identity_info.id_doc_info',today)
        name=info['id_doc_name']
    expected=subject['business_license_info']['merchant_name'] if bank['bank_account_type']=='BANK_ACCOUNT_TYPE_CORPORATE' else name
    if bank['account_name']!=expected:raise ValueError('OFFICIAL_ACCOUNT_HOLDER_NAME_MISMATCH')
    if bank['account_bank']=='其他银行' and not (bank.get('bank_branch_id') or bank.get('bank_name')):raise ValueError('OFFICIAL_BANK_BRANCH_REQUIRED')
    ubos=subject.get('ubo_info_list')
    if ubos is not None:
        if entity!='ENTERPRISE' or type(ubos) is not list or not 1<=len(ubos)<=4:raise ValueError('INVALID_OFFICIAL_UBO_LIST')
        identities=set()
        for index,ubo in enumerate(ubos):
            path='subject_info.ubo_info_list.'+str(index)
            required(ubo,('ubo_id_doc_type','ubo_id_doc_copy','ubo_id_doc_name','ubo_id_doc_number','ubo_id_doc_address'),path)
            document(ubo['ubo_id_doc_number'],ubo['ubo_id_doc_type'],path)
            identity_key=(ubo['ubo_id_doc_type'],ubo['ubo_id_doc_number'].upper())
            if identity_key in identities:raise ValueError('DUPLICATE_OFFICIAL_UBO_DOCUMENT')
            identities.add(identity_key)
            if ubo['ubo_id_doc_type']!=PASSPORT:required(ubo,('ubo_id_doc_copy_back',),path)
            period(ubo,'ubo_period_begin','ubo_period_end',path,today)
    if subject.get('finance_institution') is True:
        info=subject.get('finance_institution_info');required(info,('finance_type',),'subject_info.finance_institution_info')
        if info['finance_type'] not in ('BANK_AGENT','PAYMENT_AGENT','INSURANCE','TRADE_AND_SETTLE','SMALL_LOAN','OTHER'):raise ValueError('INVALID_FINANCE_INSTITUTION_TYPE')
        images(info.get('finance_license_pics'),'subject_info.finance_institution_info.finance_license_pics')
    elif 'finance_institution' in subject and type(subject['finance_institution']) is not bool:raise ValueError('INVALID_FINANCE_INSTITUTION_FLAG')
    sales=profile['business_info']['sales_info'];scenes=sales.get('sales_scenes_type')
    if type(scenes) is not list or not scenes or any(type(v) is not str for v in scenes) or len(set(scenes))!=len(scenes) or any(v not in ('SALES_SCENES_MINI_PROGRAM','SALES_SCENES_STORE') for v in scenes):raise ValueError('CURRENT_PROJECT_MINI_OR_STORE_SCENES_REQUIRED')
    if 'SALES_SCENES_MINI_PROGRAM' in scenes:
        mini=sales.get('mini_program_info')
        if type(mini) is not dict:raise ValueError('OFFICIAL_MINI_SCENE_REQUIRED')
        images(mini.get('mini_program_pics'),'business_info.sales_info.mini_program_info.mini_program_pics')
    if 'SALES_SCENES_STORE' in scenes:
        store=sales.get('biz_store_info');required(store,('biz_store_name','biz_address_code','biz_store_address'),'business_info.sales_info.biz_store_info')
        for field in ('store_entrance_pic','indoor_pic'):images(store.get(field),'business_info.sales_info.biz_store_info.'+field)
    settlement=profile['settlement_info']
    for field in ('qualifications','activities_additions'):
        if field in settlement:images(settlement[field],'settlement_info.'+field)
    if settlement.get('activities_id'):
        required(settlement,('debit_activities_rate','credit_activities_rate'),'settlement_info')
        for field in ('debit_activities_rate','credit_activities_rate'):
            if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?',settlement[field]):raise ValueError('INVALID_OFFICIAL_ACTIVITY_RATE')
