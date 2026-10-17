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
        self.server=serve(self.gateway,port,operations=self.operations,onboarding=self.onboarding)
        return self.server

    def configure_operations(self,grants):
        """Host-supplied grants for existing Center users; no client role input."""
        if self.server is not None or self.operations is not None:
            raise ValueError('OPERATIONS_ALREADY_CONFIGURED_OR_LISTENING')
        from scripts.community_center_operations import CenterOperations
        self.operations=CenterOperations(self.center,self.stage.runtime,grants)
        return self.operations

    def configure_onboarding(self,reviewers):
        if self.server is not None or self.onboarding is not None:
            raise ValueError('ONBOARDING_ALREADY_CONFIGURED_OR_LISTENING')
        from scripts.community_merchant_onboarding import MerchantOnboarding
        self.onboarding=MerchantOnboarding(self.center,reviewers)
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
        handler=make_handler(self.gateway,proxy_origin=https_origin,trusted_proxy=TrustedNginxSource(nginx_uid),operations=self.operations,onboarding=self.onboarding)
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
