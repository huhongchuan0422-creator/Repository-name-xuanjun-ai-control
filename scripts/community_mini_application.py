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
        self.server=serve(self.gateway,port)
        return self.server

    def close(self):
        if self.server is not None:
            self.server.server_close()
            self.server=None
        if self.stage is not None:
            self.stage.close()
            self.stage=None
        # The hosting application owns Center and its DB lifetime.

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
