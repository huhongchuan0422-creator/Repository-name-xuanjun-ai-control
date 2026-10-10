import tempfile
import unittest
from pathlib import Path
from stage1_queue import Queue

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "queue.sqlite"
        self.q = Queue(self.path)

    def tearDown(self):
        self.q.close()
        self.dir.cleanup()

    def test_restart_and_dependencies(self):
        self.q.add("a")
        self.q.add("b", deps=["a"])
        first = self.q.claim("worker", now=100)
        self.assertEqual(first["id"], "a")
        self.q.close()
        self.q = Queue(self.path)
        self.assertIsNone(self.q.claim("other", now=101))
        self.assertFalse(self.q.finish("a", "worker", first["fence"], "DONE", now=300))
        renewed = self.q.claim("other", now=300)
        self.assertEqual(renewed["id"], "a")
        self.assertGreater(renewed["fence"], first["fence"])
        self.assertTrue(self.q.finish("a", "other", renewed["fence"], "DONE", {"ci":"passed"}, now=301))
        self.assertEqual(self.q.claim("other", now=302)["id"], "b")
        self.assertEqual(self.q.get("a")["checkpoint"], {"ci":"passed"})

    def test_human_and_resource_do_not_block_independent(self):
        self.q.add("human")
        self.q.add("quota")
        self.q.add("independent")
        self.q.add("depends_on_human", deps=["human"])
        for state in ("WAITING_HUMAN","PAUSED_RESOURCE"):
            task = self.q.claim("w")
            self.assertTrue(self.q.finish(task["id"],"w",task["fence"],state))
        self.assertEqual(self.q.claim("w")["id"],"independent")
        self.assertIsNone(self.q.claim("w"))
        self.assertTrue(self.q.resume("human","WAITING_HUMAN"))

    def test_heavy_limit_and_idempotency(self):
        for tid in ("a","b","c"): self.q.add(tid)
        self.q.add("light", heavy=False)
        self.q.add("a")
        a = self.q.claim("w1", now=10)
        b = self.q.claim("w2", now=10)
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(self.q.claim("w3", now=11)["id"], "light")
        self.assertIsNone(self.q.claim("w4", now=11))
        self.assertTrue(self.q.finish(a["id"],"w1",a["fence"],"DONE",now=12))
        self.assertFalse(self.q.finish(a["id"],"w1",a["fence"],"DONE",now=12))
        self.assertIsNotNone(self.q.claim("w4", now=13))

    def test_invalid_and_missing_dep(self):
        with self.assertRaises(ValueError): self.q.add("self", deps=["self"])
        self.q.add("waiting", deps=["missing"])
        self.assertIsNone(self.q.claim("w"))

if __name__ == "__main__":
    unittest.main()
