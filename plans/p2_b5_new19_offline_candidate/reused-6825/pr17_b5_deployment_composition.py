"""Default-closed bridge to the original queue, policy, custody and OAuth resource.

Construction is local preparation, not an authority enrollment. The original
worker must attest intake through its authenticated GitHub receive path.
"""
import hashlib
import hmac
import math
from production.cloud_connection.queue import Queue, Hold, canonical
from production.cloud_connection.worker import Github, Cloud, Network
from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
from production.cloud_connection.oauth_resource import OAuthProjectResource
from production.cloud_connection.worker import PREFIX
from pr17_b5_original_algorithms import (success_set, custody_set,
    original_archive_proof, complete_original_chunk)


class OriginalComposition:
    def __init__(self, *, queue, github, cloud, policy, resource, requests,
                 archive_root_ref, destination_root, destination_owner,
                 authorization_from_request, clock, request_publisher=None,
                 test_only=False):
        if ((queue is not None and type(queue) is not Queue) or
                (resource is not None and type(resource) is not OAuthProjectResource) or
                (github is not None and type(github) is not Github) or
                (cloud is not None and type(cloud) is not Cloud) or
                type(policy) is not ApprovedObjectsPolicy or
                type(requests) not in (list, tuple) or
                len(requests) != 19 or not callable(authorization_from_request) or
                not callable(clock)):
            raise Hold('ORIGINAL_COMPOSITION_INCOMPLETE')
        # A publisher must be the reviewed original authenticated request path;
        # Github.call or Queue.submit alone cannot prove the B5 actor.
        self.publisher = request_publisher
        self.test_only = test_only
        self.runtime_phase = 'fixture' if test_only else 'unattached'
        self.queue, self.github, self.cloud = queue, github, cloud
        self.policy, self.resource = policy, resource
        self.requests = tuple(requests)
        self.catalog_raw = canonical(policy.catalog.value).encode()
        self.catalog_sha = hashlib.sha256(self.catalog_raw).hexdigest()
        self.policy_sha = policy.sha
        self.binding_bytes = canonical(policy.binding).encode()
        self.request_bytes = tuple(canonical(x).encode() for x in requests)
        self.request_ids = tuple(x['request_id'] for x in requests)
        self.recipient = policy.binding['recipient_id']
        self.project = policy.catalog.value['project']
        self.archive_root_ref = archive_root_ref
        self.destination_root, self.destination_owner = destination_root, destination_owner
        self.authorization_from_request, self.clock = authorization_from_request, clock
        self.verify_binding(active=False)

    def attach_after_worker_start(self, queue, resource):
        """Bind original reopened queue and protected OAuth resource only after start."""
        if type(queue) is not Queue or type(resource) is not OAuthProjectResource:
            raise Hold('ORIGINAL_RUNTIME_TYPE')
        if self.queue is not None and self.queue is not queue:
            raise Hold('ORIGINAL_QUEUE_REBOUND_UNRECONCILED')
        if self.resource is not None and self.resource is not resource:
            raise Hold('ORIGINAL_RESOURCE_REBOUND_UNRECONCILED')
        self.queue, self.resource = queue, resource
        result=self.verify_binding(active=True)
        self.runtime_phase='observe'
        return result

    def replace_runtime_phase(self, queue, resource, expected, next_phase):
        """Rebind an already admitted original pair around one custody action.

        A failed new binding closes the new handle and leaves the prior handle
        unchanged. There is no implicit write or retry here.
        """
        if (self.runtime_phase != expected or
                (expected,next_phase) not in (('observe','custody'),('custody','observe'))):
            raise Hold('ORIGINAL_RUNTIME_PHASE_ORDER')
        self.verify_binding(active=True)
        old_queue,old_resource=self.queue,self.resource
        if queue is old_queue or resource is old_resource:
            raise Hold('ORIGINAL_RUNTIME_PHASE_REUSED')
        self.queue,self.resource=queue,resource
        try:self.verify_binding(active=True)
        except BaseException:
            self.queue,self.resource=old_queue,old_resource
            try:queue.close()
            except BaseException:
                try:queue.db.close()
                except BaseException:pass
                self.detach_runtime_unknown()
                raise Hold('ORIGINAL_RUNTIME_NEW_HANDLE_UNKNOWN') from None
            raise
        try:old_queue.close()
        except BaseException:
            self.queue,self.resource=None,None
            self.runtime_phase='uncertain'
            try:queue.close()
            except BaseException:
                try:queue.db.close()
                except BaseException:pass
            try:old_queue.db.close()
            except BaseException:pass
            raise Hold('ORIGINAL_RUNTIME_OLD_HANDLE_UNKNOWN') from None
        self.runtime_phase=next_phase
        return True

    def detach_runtime_unknown(self):
        """Drop every owned writable reference after an uncertain phase change."""
        old_queue=self.queue
        old_resource=self.resource
        self.queue=None
        self.resource=None
        self.runtime_phase='uncertain'
        if old_queue is not None:
            try:old_queue.close()
            except BaseException:
                # A failed wrapper close may leave the same sqlite handle in
                # the resource. Try its concrete handle as well; never claim
                # that a failed close has definitely released the OS handle.
                try:old_queue.db.close()
                except BaseException:pass
                raise Hold('ORIGINAL_RUNTIME_CLOSE_UNKNOWN') from None
        del old_resource
        return True

    def verify_binding(self, catalog_raw=None, catalog_sha=None, request_ids=None,
                       recipient=None, project=None, active=True):
        p = self.policy
        if (self.catalog_sha != p.catalog.sha or
                p.sha != self.policy_sha or
                not hmac.compare_digest(canonical(p.binding).encode(), self.binding_bytes) or
                not hmac.compare_digest(canonical(p.catalog.value).encode(), self.catalog_raw) or
                self.catalog_sha != hashlib.sha256(self.catalog_raw).hexdigest() or
                p.binding['recipient_id'] != self.recipient or
                p.catalog.value['project'] != self.project or
                len(self.request_ids) != 19 or len(set(self.request_ids)) != 19 or
                tuple(canonical(x).encode() for x in self.requests) != self.request_bytes or
                tuple(x['request_id'] for x in self.requests) != self.request_ids or
                set(self.request_ids) != set(p.binding['requests'].values())):
            raise Hold('ORIGINAL_COMPOSITION_CHANGED')
        for request in self.requests:
            p.request_object(request)
        if (catalog_raw is not None and (type(catalog_raw) is not bytes or
                not hmac.compare_digest(catalog_raw, self.catalog_raw)) or
                catalog_sha is not None and catalog_sha != self.catalog_sha or
                request_ids is not None and tuple(request_ids) != self.request_ids or
                recipient is not None and recipient != self.recipient or
                project is not None and project != self.project):
            raise Hold('ORIGINAL_AUTHORITY_CATALOG_REQUEST_MISMATCH')
        if active:
            if (type(self.queue) is not Queue or type(self.resource) is not OAuthProjectResource
                    or self.queue.approved_objects is not p or
                    self.resource.db is not self.queue.db):
                raise Hold('ORIGINAL_RUNTIME_NOT_BOUND')
            entry = self.resource.catalogs.get(self.catalog_sha)
            custody = (self.resource.custodies or {}).get(self.catalog_sha)
            if (entry is None or entry[0] is not p.catalog or
                    entry[1] != p.binding['roots'] or
                    set(self.resource.custodies or {}) != {self.catalog_sha} or
                    type(custody) not in (tuple, list) or
                    tuple(custody) != (self.destination_root,self.destination_owner) or
                    self.resource.enabled is not True):
                raise Hold('ORIGINAL_ACTIVE_RESOURCE_NOT_BOUND')
            if self.test_only is not True:
                files = self.queue.db.execute('PRAGMA database_list').fetchall()
                if (len(files) != 1 or files[0][1] != 'main' or
                        files[0][2] != '/var/lib/xuanjun-cloud-connection/queue.sqlite'):
                    raise Hold('ORIGINAL_QUEUE_PATH_NOT_ENROLLED')
        if self.test_only is not True and (
                self.destination_root !=
                '/var/lib/xuanjun-cloud-connection/b5-material-custody' or
                self.destination_owner != 0 or
                (active and set(p.binding.get('archives',{})) != {self.archive_root_ref})):
            raise Hold('ORIGINAL_CUSTODY_TARGET_NOT_ENROLLED')
        return True

    def preflight(self):
        self.verify_binding(active=False)
        if self.test_only is True:
            if self.publisher is None or not callable(self.publisher):
                raise Hold('ORIGINAL_AUTHENTICATED_INTAKE_PROVIDER_UNAVAILABLE')
        elif (self.publisher is not None or type(self.github) is not Github or
                type(self.cloud) is not Cloud or
                type(self.github.network) is not Network or
                self.cloud.network is not self.github.network or
                self.github.token_ref != '/etc/xuanjun-development/github-intake-token' or
                self.github.token_owner != 1003 or
                self.cloud.credentials_ref != '/etc/xuanjun-cloud-executor/credentials.json'):
            raise Hold('ORIGINAL_RUNTIME_PROVIDER_NOT_ENROLLED')
        return True

    def ready(self, request):
        self.verify_binding()
        if type(request) is not dict or canonical(request).encode() not in self.request_bytes:
            raise Hold('B5_INTAKE_REQUEST_NOT_FROZEN')
        row = self.queue.db.execute(
            'SELECT state,request_json,request_sha,actor_id FROM connection_jobs WHERE request_id=?',
            (request['request_id'],)).fetchone()
        body = canonical(request)
        if (row is None or row[0] not in
                ('READY','DISPATCHING','UNKNOWN','SUCCESS','FAILED') or row[1] != body or
                row[2] != hashlib.sha256(body.encode()).hexdigest() or
                type(row[3]) is not int or row[3] != 332398908):
            raise Hold('B5_INTAKE_PENDING_OR_UNKNOWN_NO_REPOST')
        return row

    def send_once(self, request, persist_intent, persist_sent):
        """Persist-before-POST; a missing response is UNKNOWN and never reposted.

        The caller owns an O_EXCL, fsynced fixed-job journal. A POST response
        proves only SENT. The separate original worker must later prove READY.
        """
        self.verify_binding()
        body = canonical(request)
        if body.encode() not in self.request_bytes:
            raise Hold('B5_INTAKE_REQUEST_NOT_FROZEN')
        self.preflight()
        if not callable(persist_intent) or not callable(persist_sent):
            raise Hold('B5_INTAKE_DURABLE_JOURNAL_REQUIRED')
        start = self.clock()
        end = min(self.policy.catalog.value['valid_until'], request['expires_unix'])
        if (type(start) not in (int, float) or not math.isfinite(start) or
                not start < end):
            raise Hold('B5_INTAKE_EXPIRED')
        digest = hashlib.sha256(body.encode()).hexdigest()
        persist_intent(request['request_id'], digest)
        try:
            current = self.clock()
            if (type(current) not in (int, float) or not math.isfinite(current)
                    or current < start or not current < end):
                raise Hold('B5_INTAKE_EXPIRED_AFTER_INTENT_NO_REPOST')
            response = self.publisher(request) if self.publisher is not None else self.github.call(
                '/issues/17/comments', {'body': PREFIX + body})
            if (type(response) is not dict or type(response.get('id')) is not int or
                    type(response.get('user')) is not dict or
                    response['user'].get('id') != 332398908 or
                    response.get('body') != PREFIX + body or
                    response.get('created_at') != response.get('updated_at')):
                raise Hold('B5_POST_RESPONSE_UNPROVEN_UNKNOWN_NO_REPOST')
            persist_sent(request['request_id'], digest, response['id'])
            return {'request_id': request['request_id'], 'state': 'SENT_NOT_ACCEPTED'}
        except BaseException:
            # The intent already exists: the next process may only reconcile.
            raise Hold('B5_INTAKE_UNKNOWN_NO_REPOST') from None

    def success(self):
        self.verify_binding()
        return success_set(self.queue.db, self.policy, self.requests,
                           self.policy.binding['recipient_id'],
                           self.policy.catalog.sha, int(self.clock()))

    def success_progress(self):
        self.verify_binding()
        states = [self.ready(request)[0] for request in self.requests]
        if 'FAILED' in states:
            raise Hold('B5_ORIGINAL_JOB_FAILED_NO_REPOST')
        if all(state == 'SUCCESS' for state in states):
            self.success()  # Original bound_job validates InvokeId and receipt.
        return sum(state == 'SUCCESS' for state in states)

    def archive(self, size, digest):
        self.verify_binding()
        return original_archive_proof(self.policy, self.archive_root_ref, size, digest)

    def custody(self):
        self.verify_binding()
        return custody_set(self.queue.db, self.policy, self.requests,
                           self.policy.binding['recipient_id'],
                           self.policy.catalog.sha, self.destination_root,
                           self.destination_owner, int(self.clock()), self.clock)

    def body(self, request, item):
        self.verify_binding()
        if canonical(request).encode() not in self.request_bytes:
            raise Hold('B5_BODY_REQUEST_NOT_FROZEN')
        header = self.authorization_from_request()
        try:
            return complete_original_chunk(self.resource, header,
                {'manifest_sha256': self.policy.catalog.sha,
                 'request_id': request['request_id'],
                 'object_ref': request['arguments']['object_ref'], 'offset': 0},
                request, item, self.policy,
                self.queue.db, int(self.clock()))
        finally:
            del header
