"""Nonblocking persistent scheduler core using the existing ExecutionLedger.

The service deployment must provide isolated per-job cgroups. This class does
not install services, authenticate workers, consume arbitrary issues or claim
that unit tests are production work. A verified pipeline_factory is mandatory.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from execution_ledger import LeaseLost


class DevelopmentLoop(object):
    def __init__(self, ledger, pipeline_factory, worker_prefix, poll_seconds=5,
                 max_workers=2, clock=None, executor=None):
        if max_workers not in (1, 2) or not worker_prefix or poll_seconds <= 0:
            raise ValueError('invalid bounded scheduler configuration')
        self.ledger, self.pipeline_factory = ledger, pipeline_factory
        self.prefix, self.poll_seconds = worker_prefix, poll_seconds
        self.max_workers, self.clock = max_workers, clock or time.monotonic
        self.pool = executor or ThreadPoolExecutor(max_workers=max_workers)
        self.active = {}
        self.sequence = 0
        self.stop_event = threading.Event()

    def _blocked(self, claim, reason):
        ids = (claim['task_id'], claim['worker_id'], claim['fence'])
        try:
            observed = self.ledger.observation(claim['task_id'])
            cp = dict(observed['checkpoint'])
            cp['error_code'] = reason
            self.ledger.checkpoint(*(ids + (cp,)))
            self.ledger.finish(*(ids + ('WAITING_HUMAN',)), effects='unknown')
        except LeaseLost:
            pass

    def tick(self):
        """Bounded dispatch/poll; running model turns do not block Owner intake."""
        if self.stop_event.is_set():
            return {'active': len(self.active), 'dispatched': 0, 'stopping': True}
        now = self.clock()
        for task_id, entry in list(self.active.items()):
            claim = entry['claim']
            ids = (task_id, claim['worker_id'], claim['fence'])
            future = entry.get('future')
            if future is not None and future.done():
                try:
                    result = future.result()
                    if not isinstance(result, dict) or result.get('state') not in (
                            'RUNNING', 'DONE', 'FAILED', 'WAITING_HUMAN', 'PAUSED_RESOURCE'):
                        raise ValueError('invalid pipeline result')
                    observed = self.ledger.observation(task_id)
                    if observed['fence'] != claim['fence'] or observed['state'] != result['state']:
                        raise ValueError('pipeline state not persisted')
                    if result['state'] == 'RUNNING':
                        cp = result.get('checkpoint')
                        if not isinstance(cp, dict) or cp != observed['checkpoint']:
                            raise ValueError('missing continuation checkpoint')
                        self.ledger.assert_live(*ids)
                        claim['checkpoint'] = cp
                        entry['future'] = None
                        entry['next_poll'] = now + self.poll_seconds
                    else:
                        # Pipeline must persist its own fenced terminal state.
                        # This loop never marks DONE based on a returned claim.
                        self.active.pop(task_id)
                        continue
                except Exception:
                    self._blocked(claim, 'PIPELINE_RESULT_UNCONFIRMED')
                    self.active.pop(task_id)
                    continue
            try:
                phase = claim.get('checkpoint', {}).get('phase', 'EXECUTING')
                if not isinstance(phase, str) or not phase.isupper() or len(phase) > 32:
                    phase = 'EXECUTING'
                self.ledger.heartbeat(*ids, ttl=180, phase=phase)
            except LeaseLost:
                if entry.get('future') is not None:
                    entry['future'].cancel()
                self.active.pop(task_id)
                continue
            if entry.get('future') is None and now >= entry.get('next_poll', 0):
                entry['future'] = self.pool.submit(entry['pipeline'].run, dict(claim))
        dispatched = 0
        attempts = 0
        while (len(self.active) < self.max_workers and attempts < self.max_workers
               and not self.stop_event.is_set()):
            attempts += 1
            self.sequence += 1
            worker = self.prefix + '-' + str(self.sequence)
            claim = self.ledger.claim(worker, ttl=180)
            if claim is None:
                break
            try:
                pipeline = self.pipeline_factory(claim)
                future = self.pool.submit(pipeline.run, dict(claim))
            except Exception:
                self._blocked(claim, 'PIPELINE_START_UNCONFIRMED')
                continue
            self.active[claim['task_id']] = {'claim': claim, 'pipeline': pipeline,
                                              'future': future, 'next_poll': now}
            dispatched += 1
        return {'active': len(self.active), 'dispatched': dispatched, 'stopping': False}

    def serve(self):
        # Recover only uncertain stale executions; unrelated ready work proceeds.
        self.ledger.recover_expired()
        while not self.stop_event.is_set():
            self.tick()
            self.stop_event.wait(min(1, self.poll_seconds))

    def stop(self):
        """Gracefully stop dispatch; running jobs retain their existing leases."""
        self.stop_event.set()

    def close(self):
        self.stop()
        # Supervised cgroups, not Future.cancel(), terminate running OS jobs.
        self.pool.shutdown(wait=False)
