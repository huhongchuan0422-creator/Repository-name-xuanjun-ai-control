"""Isolated spawned-child wire-protocol negative tests; no sockets or OAuth callbacks."""
import multiprocessing
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from production.cloud_connection import github_network as net
from production.cloud_connection.queue import Hold


def send_malformed(pipe, *unused):
    try: pipe.send_bytes(b'0DNS\x00code=evil&state=evil&token=evil&secret=evil')
    finally: pipe.close()


def send_unknown(pipe, *unused):
    try: pipe.send_bytes(b'0NOT_A_REASON')
    finally: pipe.close()


def hang_child(pipe, *unused):
    time.sleep(8)
    pipe.close()


class TrackingContext:
    def __init__(self, context):
        self.context=context
        self.children=[]
    def Pipe(self, *args, **kwargs): return self.context.Pipe(*args, **kwargs)
    def Process(self, *args, **kwargs):
        p=self.context.Process(*args, **kwargs)
        self.children.append(p)
        return p


class WireBoundary(unittest.TestCase):
    def request(self):
        return SimpleNamespace(method='GET', url='https://api.github.com/user',
                               headers={}, body=None)

    def run_child(self, target, budget):
        context=TrackingContext(multiprocessing.get_context('spawn'))
        with patch.object(net.multiprocessing,'get_context',return_value=context), patch.object(net,'_wire',target):
            with self.assertRaises(Hold) as error:
                net.GithubNetwork().send(self.request(),time.monotonic()+budget)
        self.assertEqual(len(context.children),1)
        child=context.children[0]
        self.assertFalse(child.is_alive())
        self.assertIsNotNone(child.exitcode)
        return str(error.exception), child

    def test_unknown_enum_falls_back_to_other(self):
        reason,_=self.run_child(send_unknown,3)
        self.assertEqual(reason,'GITHUB_WIRE_OTHER')

    def test_malformed_secret_bearing_enum_never_leaves_parent(self):
        reason,_=self.run_child(send_malformed,3)
        self.assertEqual(reason,'GITHUB_WIRE_OTHER')
        for marker in ('code=','state=','token=','secret=','evil'):
            self.assertNotIn(marker,reason)

    def test_real_spawn_timeout_cleans_child(self):
        started=time.monotonic()
        reason,child=self.run_child(hang_child,.5)
        self.assertEqual(reason,'GITHUB_TOTAL_DEADLINE')
        self.assertLess(time.monotonic()-started,3.5)
        self.assertFalse(child.is_alive())

if __name__=='__main__':unittest.main()
