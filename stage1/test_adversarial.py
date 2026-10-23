"""Adversarial concurrency and restart tests for Stage1 queue."""
import multiprocessing as mp
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from stage1_queue import Queue

def claim_once(path, barrier, output, identity):
    q = Queue(path)
    try:
        barrier.wait(timeout=10)
        result = q.claim(identity, ttl=60)
        output.put((identity, result["id"] if result else None))
    finally:
        q.close()

class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "state.sqlite")
        self.q = Queue(self.path)

    def tearDown(self):
        self.q.close()
        self.temp.cleanup()

    def test_two_processes_only_one_wins(self):
        self.q.add("one")
        ctx = mp.get_context("spawn")
        barrier = ctx.Barrier(2)
        output = ctx.Queue()
        workers = [ctx.Process(target=claim_once, args=(self.path, barrier, output, "worker-"+str(i))) for i in range(2)]
        for p in workers: p.start()
        for p in workers:
            p.join(15)
            if p.is_alive():
                p.terminate()
                p.join()
            self.assertEqual(p.exitcode, 0)
        results = [output.get(timeout=3) for _ in workers]
        self.assertEqual(sum(task == "one" for _,task in results), 1)
        self.assertEqual(sum(task is None for _,task in results), 1)

    def test_reopen_stale_fence_rejected(self):
        self.q.add("job")
        first = self.q.claim("old", now=100, ttl=20)
        self.q.close()
        self.q = Queue(self.path)
        self.assertIsNone(self.q.claim("new", now=121, ttl=20))
        self.assertEqual(self.q.get("job")["state"], "WAITING_HUMAN")
        self.assertTrue(self.q.resume("job", "WAITING_HUMAN"))
        second = self.q.claim("new", now=121, ttl=20)
        self.assertGreater(second["fence"],first["fence"])
        self.assertFalse(self.q.finish("job","old",first["fence"],"DONE",now=122))
        self.assertTrue(self.q.finish("job","new",second["fence"],"DONE",now=122))

    def test_expired_task_must_not_auto_retry_unknown_external_side_effect(self):
        """Safety contract: old worker might still operate externally.
        This intentionally fails against PR #14 until reconciliation is implemented.
        """
        self.q.add("effect")
        first = self.q.claim("old",now=100,ttl=20)
        second = self.q.claim("new",now=121,ttl=20)
        self.assertIsNone(second, "Unknown external effect must be reconciled before re-claim")

if __name__ == "__main__":
    unittest.main()
