"""Default-closed local maintenance attachment for a *new reviewed release*.

This file is not in the c53 source manifest. The caller first prepares the
transaction and only then assigns this closure as runtime_attachment. It does
not start/stop a service, submit a request, or receive Authorization.
"""
import hashlib
import os
from pathlib import Path

from production.cloud_connection.queue import Queue, Hold, decode
from production.cloud_connection.runtime import protected_read, code_pin
from production.cloud_connection.oauth_entrypoint import private_bytes
from production.cloud_connection.oauth_resource import Introspection, OAuthProjectResource
import pr17_c53_r2_review_transaction as c53


def attachment_for_prepared(transaction):
    from pr17_c53_r2_host_backend_candidate import R2HostBackend
    if (type(transaction) is not c53.Transaction or
            type(transaction.b) is not R2HostBackend or
            transaction.b.authority is None):
        raise Hold('MAINTENANCE_PREPARED_TRANSACTION_REQUIRED')
    b=transaction.b
    if b.authority.original is None:
        raise Hold('MAINTENANCE_ORIGINAL_COMPOSITION_REQUIRED')

    def attach(mode='observe'):
        if (b.db is not None or b.lock_fd is not None or
                b.activation_committed is not True or
                b.tried_start is not True):
            raise Hold('MAINTENANCE_AFTER_WORKER_ONLY')
        if mode not in ('observe','custody'):
            raise Hold('MAINTENANCE_PHASE')
        if mode=='custody' and (transaction.stage!='ONE_CUSTODY' or
                                 b.window_open is not True):
            raise Hold('MAINTENANCE_CUSTODY_CHECKPOINT_REQUIRED')
        raw=protected_read(c53.CONFIGS[0],16384)
        if raw!=b.bundle['files'][c53.CONFIGS[0]]:
            raise Hold('MAINTENANCE_CONNECTION_CHANGED')
        config=decode(raw.decode('utf-8'))
        if (config.get('state_root')!='/var/lib/xuanjun-cloud-connection' or
                config.get('allowed_actor_ids')!=[332398908] or
                config.get('executor_sha256')!=c53.PIN):
            raise Hold('MAINTENANCE_CONNECTION_BINDING')
        from production.cloud_connection import queue as queue_module
        installed=Path(queue_module.__file__).resolve().parent
        if code_pin(installed)!=c53.PIN:
            raise Hold('MAINTENANCE_NEW_RELEASE_PIN_REQUIRED')
        original=b.authority._bound_original(active=False)
        policy=original.policy
        hook=config.get('approved_objects')
        if (type(hook) is not dict or
                hook!={'metadata_ref':c53.binder.BIND,
                       'metadata_sha256':hashlib.sha256(b.bundle['files'][c53.binder.BIND]).hexdigest()}):
            raise Hold('MAINTENANCE_POLICY_HOOK_CHANGED')
        binding=protected_read(c53.binder.BIND,16384)
        if binding!=b.bundle['files'][c53.binder.BIND]:
            raise Hold('MAINTENANCE_POLICY_CHANGED')
        resource_raw=private_bytes(c53.CONFIGS[1],262144)
        if resource_raw!=b.bundle['files'][c53.CONFIGS[1]]:
            raise Hold('MAINTENANCE_RESOURCE_CHANGED')
        resource_config=c53.strict_json(resource_raw)
        settings=resource_config.get('settings')
        if (type(settings) is not dict or
                set(settings)!={'issuer','endpoint','client_id','audience','subjects'} or
                resource_config.get('catalogs')!=[{
                    'manifest_ref':c53.binder.CATALOG,
                    'manifest_sha256':b.bundle['catalog_sha'],
                    'policy':policy.binding['policy'],
                    'roots':policy.binding['roots']}] or
                resource_config.get('custodies')!={b.bundle['catalog_sha']:
                    [original.destination_root,original.destination_owner]}):
            raise Hold('MAINTENANCE_RESOURCE_BINDING')
        catalog_raw=private_bytes(c53.binder.CATALOG,131072)
        if catalog_raw!=b.bundle['files'][c53.binder.CATALOG]:
            raise Hold('MAINTENANCE_CATALOG_CHANGED')
        secret_ref=resource_config.get('client_secret_ref')
        if type(secret_ref) is not str or not secret_ref.startswith('/etc/'):
            raise Hold('MAINTENANCE_SECRET_REF')
        auth=Introspection(secret_provider=lambda:private_bytes(secret_ref,4096).decode().strip(),
                           **settings)
        # Reuse the original protected STATE root and database identity guard.
        # The old immutable connector itself requires stopped worker/no WAL and
        # cannot be invoked against this live phase. Keep its identity contract
        # while the candidate Queue opens its own WAL-aware existing handle.
        root=b.legacy.state_directory()
        held=None;queue=None
        try:
            held=os.open('queue.sqlite',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,
                         dir_fd=root)
            before=os.fstat(held)
            b.legacy.database_identity(before)
            pre=b._snapshot_live_fds()
            queue=Queue('/var/lib/xuanjun-cloud-connection/queue.sqlite',c53.PIN,
                        [332398908],approved_objects=policy,
                        existing_readonly=(mode=='observe'),
                        existing_custody=(mode=='custody'))
            live=os.stat('queue.sqlite',dir_fd=root,follow_symlinks=False)
            after=os.fstat(held)
            b.legacy.database_identity(after)
            post=b._snapshot_live_fds()
            if (not all(post.get(fd)==identity for fd,identity in pre.items()) or
                    not 1<=len(set(post)-set(pre))<=3):
                raise Hold('MAINTENANCE_QUEUE_FD_BOUNDARY')
            for fd in set(post)-set(pre):
                target=os.readlink('/proc/self/fd/%d'%fd)
                if target not in (c53.DB,c53.DB+'-wal',c53.DB+'-shm'):
                    raise Hold('MAINTENANCE_QUEUE_FD_PROVENANCE')
            if ((before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino) or
                    (before.st_dev,before.st_ino)!=(live.st_dev,live.st_ino)):
                raise Hold('MAINTENANCE_QUEUE_IDENTITY_CHANGED')
        except BaseException:
            if queue is not None:queue.close()
            raise
        finally:
            if held is not None:os.close(held)
            os.close(root)
        try:
            resource=OAuthProjectResource(queue.db,
                {policy.catalog.sha:(policy.catalog,policy.binding['roots'])},auth,
                enabled=True,custodies={policy.catalog.sha:
                (original.destination_root,original.destination_owner)})
            original.verify_binding(active=False)
            return queue,resource
        except BaseException:
            queue.close()
            raise
    return attach
