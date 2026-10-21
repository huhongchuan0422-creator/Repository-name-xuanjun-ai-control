"""Project verified WeChat applyment results into existing MiniPayments config.

This is an adapter only. It does not create a payment system, merchant account,
provider application, product entitlement or Finance authority. A signed provider
FINISHED result supplies sub_mchid; host product admission remains a separate,
protected startup input. Other channels can implement the same projection
boundary without changing MiniPayments or the original order/identity model.
"""
import hashlib
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_opening import authorize_workspace


def _admission(value):
    required={'channel','description','notify_url','profit_sharing',
              'jsapi_admitted','profit_sharing_admitted'}
    if type(value) is not dict or set(value)!=required:
        raise ValueError('EXACT_PAYMENT_PRODUCT_ADMISSION_REQUIRED')
    if value['channel']!='WECHAT':
        raise ValueError('WECHAT_PAYMENT_ADMISSION_REQUIRED')
    if (type(value['description']) is not str or not value['description']
            or type(value['notify_url']) is not str
            or not value['notify_url'].startswith('https://')
            or any(type(value[k]) is not bool for k in
                    ('profit_sharing','jsapi_admitted','profit_sharing_admitted'))):
        raise ValueError('INVALID_PAYMENT_PRODUCT_ADMISSION')
    if not value['jsapi_admitted']:
        raise PermissionError('WECHAT_JSAPI_PRODUCT_NOT_ADMITTED')
    if value['profit_sharing'] and not value['profit_sharing_admitted']:
        raise PermissionError('WECHAT_PROFIT_SHARING_PRODUCT_NOT_ADMITTED')
    return value


def project_wechat_merchants(identity,onboarding,reader,admissions):
    """Return the existing MiniPayments merchants mapping for startup composition.

    sub_mchid is derived only from the provider-signed applyment record. The host
    admission supplies product eligibility and non-secret presentation/callback
    configuration. Missing/unknown/revoked evidence fails closed.
    """
    from scripts.community_mini_center_identity import CenterIdentity
    from scripts.community_merchant_onboarding import MerchantOnboarding
    from scripts.community_wechat_sp_readonly import PartnerOrderReader
    if (type(identity) is not CenterIdentity or type(onboarding) is not MerchantOnboarding
            or not isinstance(reader,PartnerOrderReader)
            or onboarding.center is not identity.center
            or onboarding.operations is None
            or onboarding.wechat_applyment is None
            or onboarding.wechat_applyment.reader is not reader):
        raise ValueError('SAME_EXISTING_PAYMENT_COMPOSITION_REQUIRED')
    if type(admissions) is not dict or not admissions:
        raise PermissionError('PAYMENT_PRODUCT_ADMISSION_REQUIRED')

    result={}
    seen_applications=set()
    c=identity.center
    for scene,binding in identity.scenes.items():
        if scene not in admissions:
            raise PermissionError('SCENE_PAYMENT_ADMISSION_REQUIRED')
        product=_admission(admissions[scene])
        principal=binding['principal']
        if principal not in identity.runtime.bindings:
            raise PermissionError('REGISTERED_SCENE_PRINCIPAL_REQUIRED')
        scope=dict(identity.runtime.bindings[principal])
        if binding['project'] is None:
            raise PermissionError('SCENE_PROJECT_REQUIRED')
        key=hashlib.sha256(canonical(scope)).hexdigest()
        rows=c.db.execute(
            "SELECT user_id,project,payload,active FROM links "
            "WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=?",
            (key,)).fetchall()
        if len(rows)!=1 or rows[0]['active']!=1:
            raise PermissionError('CURRENT_OPENED_MERCHANT_REQUIRED')
        owner,application,payload,_=rows[0]
        record=onboarding._decode(payload,'community-opening:'+key+':'+application)
        if (record.get('state')!='OPENED' or record.get('scope')!=scope
                or record.get('project')!=binding['project']):
            raise PermissionError('SCENE_OPENING_BINDING_MISMATCH')
        authorize_workspace(onboarding,onboarding.operations,record['workspace'],owner)
        if application in seen_applications:
            raise PermissionError('APPLICATION_PAYMENT_MAPPING_CONFLICT')
        seen_applications.add(application)

        applyment=onboarding.wechat_applyment._read(application)
        if (type(applyment) is not dict
                or applyment.get('provider_state')!='APPLYMENT_STATE_FINISHED'
                or type(applyment.get('provider_sub_mchid')) is not str
                or type(applyment.get('provider_sp_mchid')) is not str
                or applyment.get('provider_sp_mchid')!=reader._mchid
                or not applyment.get('business_code')
                or not applyment.get('applyment_id')):
            raise PermissionError('TRUSTED_FINISHED_WECHAT_APPLYMENT_REQUIRED')
        sub_mchid=applyment['provider_sub_mchid']
        if not sub_mchid.isdigit() or not 6<=len(sub_mchid)<=32:
            raise PermissionError('TRUSTED_FINISHED_WECHAT_APPLYMENT_REQUIRED')

        result[scene]={
            'sp_appid':identity.appid,
            'sub_mchid':sub_mchid,
            'description':product['description'],
            'notify_url':product['notify_url'],
            'profit_sharing':product['profit_sharing']
        }
    if set(result)!=set(identity.scenes):
        raise PermissionError('COMPLETE_SCENE_PAYMENT_MAPPING_REQUIRED')
    return result
