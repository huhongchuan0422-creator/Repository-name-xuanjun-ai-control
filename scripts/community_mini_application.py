"""Compose admitted Center, original community stores and real WeChat transport.

The hosting customer Center supplies its existing live instance and secrets.
This module does not create an account store, issue a KMS key, import authority,
seed a merchant, deploy a listener or enable money operations.
"""
from scripts.pr122_customer_core import Center
from scripts.community_stage_local import LocalStage
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_mini_login import MiniGateway,WechatCodeClient
from scripts.community_mini_http import serve


class MiniApplication:
    def __init__(self,center,state_directory,bindings,merchant_scope,scenes,appid,app_secret):
        if type(center) is not Center:
            raise ValueError('EXISTING_CENTER_INSTANCE_REQUIRED')
        self.stage=None
        self.server=None
        self.operations=None
        self.onboarding=None
        self.saas=None
        self.fulfillment=None
        self.provider_actions=None
        self.merchant_bills=None
        self.communities=None
        self.commerce=None
        self.notifications=None
        self._socket=None
        self.center=center
        try:
            provider=WechatCodeClient(appid,app_secret)
            self.stage=LocalStage(state_directory,bindings,merchant_scope,clock=center.now)
            self.identity=CenterIdentity(center,self.stage.runtime,appid,scenes)
            self.gateway=MiniGateway(self.stage.runtime,self.identity,provider)
        except BaseException:
            self.close()
            raise

    def listen(self,port=0):
        """Loopback backend for the admitted HTTPS host; never a public bind."""
        if self.server is not None:
            raise ValueError('ALREADY_LISTENING')
        self.server=serve(self.gateway,port,operations=self.operations,onboarding=self.onboarding,saas=self.saas,fulfillment=self.fulfillment,provider_actions=self.provider_actions,merchant_bills=self.merchant_bills,communities=self.communities,commerce=self.commerce,notifications=self.notifications)
        return self.server

    def configure_payment_notifications(self,api_v3_key,path='/wechat/community/notify'):
        if self.server is not None or self.notifications is not None or getattr(self.gateway,'payments',None) is None:
            raise ValueError('ORIGINAL_PAYMENTS_REQUIRED_BEFORE_NOTIFICATIONS')
        from scripts.community_payment_notifications import PaymentNotifications
        self.notifications=PaymentNotifications(self.gateway.payments,api_v3_key,path)
        return self.notifications

    def configure_commerce(self):
        if self.server is not None or self.commerce is not None or self.operations is None:
            raise ValueError('ORIGINAL_OPERATIONS_REQUIRED_BEFORE_COMMERCE')
        from scripts.community_commerce import Commerce
        self.commerce=Commerce(self.operations,self.identity)
        if self.communities is not None:self.communities.commerce=self.commerce
        self.gateway.commerce=self.commerce
        if getattr(self.gateway,'payments',None) is not None:self.gateway.payments.commerce=self.commerce
        if self.provider_actions is not None:self.provider_actions.commerce=self.commerce
        return self.commerce

    def configure_communities(self,grants):
        if self.server is not None or self.communities is not None:
            raise ValueError('COMMUNITIES_ALREADY_CONFIGURED_OR_LISTENING')
        from scripts.community_center_communities import CenterCommunities
        self.communities=CenterCommunities(self.center,grants)
        self.communities.commerce=self.commerce
        self.communities.provider_actions=self.provider_actions
        return self.communities

    def configure_provider_actions(self,reader,bindings):
        if self.server is not None or self.provider_actions is not None or self.operations is None:
            raise ValueError('CONFIGURED_ORIGINAL_FINANCE_OPERATIONS_REQUIRED')
        from scripts.community_wechat_sp_actions import ProviderActions
        self.provider_actions=ProviderActions(self.operations,reader,bindings)
        self.provider_actions.commerce=self.commerce
        if self.communities is not None:self.communities.provider_actions=self.provider_actions
        if getattr(self.gateway,'payments',None) is not None:self.gateway.payments.rule_actions=self.provider_actions
        return self.provider_actions

    def configure_merchant_bills(self,grants=None):
        """Explicit host grants for merchant bill reads; never money authority."""
        if self.server is not None or self.merchant_bills is not None or self.provider_actions is None:
            raise ValueError('ORIGINAL_PROVIDER_ACTIONS_REQUIRED_BEFORE_MERCHANT_BILLS')
        from scripts.community_merchant_bills import MerchantBills
        self.merchant_bills=MerchantBills(self.provider_actions,grants)
        return self.merchant_bills

    def configure_fulfillment(self,finance,authority_id,price_bindings,*,reversal_finance=None):
        if self.server is not None or self.fulfillment is not None or self.operations is None:
            raise ValueError('CONFIGURED_ORIGINAL_OPERATIONS_REQUIRED_BEFORE_LISTEN')
        from scripts.community_saas_fulfillment import SaasFulfillment
        self.fulfillment=SaasFulfillment(self.operations,finance,authority_id,price_bindings,reversal_finance=reversal_finance)
        return self.fulfillment

    def configure_saas(self,grants):
        if self.server is not None or self.saas is not None:
            raise ValueError('SAAS_ALREADY_CONFIGURED_OR_LISTENING')
        from scripts.community_center_saas import CenterSaas
        self.saas=CenterSaas(self.center,self.stage.runtime,grants)
        return self.saas

    def configure_payments_from_applyments(self,reader,admissions):
        """Startup-only projection from verified applyment to existing MiniPayments."""
        if self.server is not None or getattr(self.gateway,'payments',None) is not None:
            raise ValueError('PAYMENTS_ALREADY_CONFIGURED_OR_LISTENING')
        if self.onboarding is None or self.onboarding.wechat_applyment is None:
            raise ValueError('ORIGINAL_WECHAT_APPLYMENT_REQUIRED')
        from scripts.community_wechat_payment_activation import project_wechat_merchants,project_wechat_scene
        merchants=project_wechat_merchants(self.identity,self.onboarding,reader,admissions)
        payments=self.configure_payments(reader,merchants=merchants)
        payments.activation_guard=lambda scene:project_wechat_scene(
            self.identity,self.onboarding,reader,scene,admissions[scene])['merchant']
        return payments

    def configure_payments(self,reader,bindings=None,*,merchants=None):
        """Protected opt-in; original customer orders and verified payer required."""
        if self.server is not None or getattr(self.gateway,'payments',None) is not None:
            raise ValueError('PAYMENTS_ALREADY_CONFIGURED_OR_LISTENING')
        from scripts.community_wechat_sp_prepay import PartnerPrepay
        from scripts.community_mini_payments import MiniPayments
        self.gateway.payments=MiniPayments(self.identity,PartnerPrepay(self.center,reader,{} if bindings is None else bindings),merchants=merchants)
        self.gateway.payments.rule_actions=self.provider_actions
        self.gateway.payments.commerce=self.commerce
        return self.gateway.payments

    def configure_operations(self,grants):
        """Host-supplied grants for existing Center users; no client role input."""
        if self.server is not None or self.operations is not None:
            raise ValueError('OPERATIONS_ALREADY_CONFIGURED_OR_LISTENING')
        from scripts.community_center_operations import CenterOperations
        self.operations=CenterOperations(self.center,self.stage.runtime,grants,onboarding=self.onboarding)
        if self.onboarding is not None:self.onboarding.operations=self.operations
        return self.operations

    def configure_wechat_applyment(self,reader,*,submission_enabled=False):
        if self.server is not None or self.onboarding is None or self.onboarding.wechat_applyment is not None:
            raise ValueError('ORIGINAL_ONBOARDING_REQUIRED_BEFORE_APPLYMENT')
        from scripts.community_wechat_applyment import WechatApplyment
        self.onboarding.wechat_applyment=WechatApplyment(self.onboarding,reader,submission_enabled=submission_enabled)
        return self.onboarding.wechat_applyment

    def configure_onboarding(self,reviewers):
        if self.server is not None or self.onboarding is not None:
            raise ValueError('ONBOARDING_ALREADY_CONFIGURED_OR_LISTENING')
        from scripts.community_merchant_onboarding import MerchantOnboarding
        self.onboarding=MerchantOnboarding(self.center,reviewers)
        if self.operations is not None:self.onboarding.operations=self.operations
        return self.onboarding

    def close(self):
        if self.server is not None:
            self.server.server_close()
            self.server=None
        if self._socket is not None:
            import stat
            path,device,inode=self._socket
            try:
                current=path.lstat()
                if stat.S_ISSOCK(current.st_mode) and (current.st_dev,current.st_ino)==(device,inode):path.unlink()
            except FileNotFoundError:pass
            self._socket=None
        if self.stage is not None:
            self.stage.close()
            self.stage=None
        # The hosting application owns Center and its DB lifetime.

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def listen_proxy(self,socket_path,https_origin,nginx_uid,nginx_gid):
        """Candidate Unix backend using the original pinned Nginx peer boundary.

        The existing deployment owner must supply the protected runtime directory,
        Nginx identity and TLS route. No proxy config or service is installed.
        """
        import os
        import socketserver
        from pathlib import Path
        from scripts.pr122_customer_core import private_path
        from scripts.pr122_customer_source import TrustedNginxSource
        from scripts.community_mini_http import make_handler
        if self.server is not None:raise ValueError('ALREADY_LISTENING')
        if os.geteuid()==0:raise PermissionError('NONROOT_PROXY_APPLICATION_REQUIRED')
        path=private_path(Path(socket_path).absolute())
        parent=path.parent.stat()
        if parent.st_uid!=os.geteuid() or parent.st_mode & 0o022 or path.exists():
            raise PermissionError('PRIVATE_SOCKET_DIRECTORY_REQUIRED')
        if type(nginx_gid) is not int or nginx_gid<0:raise ValueError('PINNED_NGINX_GROUP_REQUIRED')
        if (parent.st_gid!=nginx_gid or
                (nginx_uid!=os.geteuid() and parent.st_mode & 0o050 != 0o050)):
            raise PermissionError('NGINX_SOCKET_DIRECTORY_TRAVERSAL_REQUIRED')
        handler=make_handler(self.gateway,proxy_origin=https_origin,trusted_proxy=TrustedNginxSource(nginx_uid),operations=self.operations,onboarding=self.onboarding,saas=self.saas,fulfillment=self.fulfillment,provider_actions=self.provider_actions,merchant_bills=self.merchant_bills,communities=self.communities,commerce=self.commerce,notifications=self.notifications)
        class Server(socketserver.UnixStreamServer):request_queue_size=128
        server=Server(str(path),handler)
        info=path.lstat();self._socket=(path,info.st_dev,info.st_ino)
        self.server=server
        try:
            os.chown(path,-1,nginx_gid);os.chmod(path,0o660)
            return server
        except BaseException:
            self.close()
            raise
