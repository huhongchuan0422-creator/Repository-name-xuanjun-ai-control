"""Exact opt-in attached only by the original UK preview host at startup."""
import re
from scripts.native_lifecycle import CHANNEL, read_opened, open_native
from scripts.native_leaves import NativeWorkbench, Opening
from scripts.observer_reconcile import ObserverReconcile

SCENE=re.compile(r'wxn_[a-f0-9]{28}\Z')

class Registry:
    def __init__(self, service, operations, identity):
        self.service,self.operations,self.identity=service,operations,identity
        if identity.center is not service.center or identity.center is not operations.center:
            raise ValueError('ORIGINAL_NATIVE_SERVICES_REQUIRED')

    def is_reserved_scene(self, scene):
        # Namespace is not authority. current_opening requires exact owner,
        # current evidence and the scene derived from its durable workspace.
        return type(scene) is str and bool(SCENE.fullmatch(scene)) and scene not in self.identity.scenes

    def get_application(self, application, owner):
        candidate=read_opened(self.service,self.operations,application,owner)
        if candidate and self.is_reserved_scene(candidate['scene']):
            return candidate
        return None

    def current_opening(self, owner, scene):
        if not self.is_reserved_scene(scene):return None
        rows=self.service.center.db.execute('SELECT project FROM links WHERE channel=? AND user_id=? AND active=1 ORDER BY project',
                                             (CHANNEL,owner)).fetchall()
        matches=[]
        for (application,) in rows:
            try:
                item=self.get_application(application,owner)
            except (ValueError,PermissionError):
                continue
            if item and item['scene']==scene:
                matches.append(item)
        if len(matches)!=1:
            return None
        item=matches[0]
        return Opening(owner,item['application'],scene,item['workspace'],item['revision'],
                       item['receipt_sha256'],**item['scope'])

def attach_native_workbench(host):
    app=host.application
    observer=host.applyment_observer
    if app is None or observer is None or app.operations is None or app.onboarding is None:
        return None
    if (observer.onboarding is not app.onboarding or observer.applyment is not app.onboarding.wechat_applyment
            or observer.center is not app.center or app.onboarding.center is not app.center
            or app.identity.center is not app.center):
        raise ValueError('ORIGINAL_NATIVE_WORKBENCH_HOST_REQUIRED')
    registry=Registry(app.onboarding,app.operations,app.identity)
    from scripts.community_native_collection import NativeCollectionCodes
    codes=NativeCollectionCodes(app.gateway,registry)
    cashier=getattr(app,'fixed_cashier',None)
    if cashier is not None:
        if cashier.identity is not app.identity or cashier.operations is not app.operations:
            raise PermissionError('ORIGINAL_NATIVE_CASHIER_REQUIRED')
        cashier.native_registry=registry
        codes.fixed_cashier=cashier
    adapter=NativeWorkbench(app.identity,app.operations.runtime.demo,registry,collection_codes=codes)
    app.gateway.native_collection_codes=codes
    app.onboarding.native_workbench_adapter=adapter
    return ObserverReconcile(app.center,lambda a,u:open_native(app.onboarding,app.operations,a,u))
