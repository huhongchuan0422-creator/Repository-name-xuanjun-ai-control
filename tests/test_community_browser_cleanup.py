"""Original class-fixture cleanup with only in-memory resources, never browser IO."""
import ast
import functools
import io
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
FIXTURES={
    'IntegratedReview':'test_community_review_runtime.py',
    'ClickThrough':'test_community_ui_preview.py',
}


def lifecycle(name,fail=(),active=None):
    """Run the exact source lifecycle methods, replacing every owned resource."""
    events=[];active={'pw':False} if active is None else active;fail=set(fail)
    def step(event):
        events.append(event)
        if event in fail:raise RuntimeError('synthetic '+event)
    class Output:
        def __init__(self,name):self.name=name
        def mkdir(self,**kwargs):step('evidence.mkdir')
        def __truediv__(self,name):return Output(name)
        def write_text(self,value):step('write.'+self.name)
    class Process:
        def __init__(self,*args,**kwargs):
            step('process.open');self.stdout=self;self.stderr=io.StringIO('synthetic startup failure')
            self.communications=0
        def readline(self):
            step('process.receipt')
            return 'not json' if 'process.bad_json' in fail else '{"url":"http://synthetic.invalid"}'
        def send_signal(self,value):step('process.signal')
        def communicate(self,timeout=None):
            step('process.communicate');self.communications+=1
            if 'process.timeout' in fail and self.communications==1:
                raise subprocess.TimeoutExpired('synthetic',timeout)
            return '','synthetic shutdown'
        def kill(self):step('process.kill')
    class Server:
        server_port=1
        def __init__(self,*args,**kwargs):step('server.open')
        def serve_forever(self):raise AssertionError('NO_REAL_SERVER_LOOP')
        def shutdown(self):step('server.shutdown')
        def server_close(self):step('server.close')
    class Thread:
        def __init__(self,*args,**kwargs):step('thread.open')
        def start(self):step('thread.start')
        def join(self,*args):step('thread.join')
    class Browser:
        def close(self):step('browser.close')
    class Playwright:
        def __init__(self):self.chromium=self
        def start(self):
            step('pw.start')
            if active['pw']:raise RuntimeError('synthetic active Sync API')
            active['pw']=True;return self
        def launch(self,**kwargs):step('browser.launch');return Browser()
        def stop(self):active['pw']=False;step('pw.stop')
    def build():step('build');return {}
    source=ROOT/'tests'/FIXTURES[name]
    original=next(n for n in ast.parse(source.read_text()).body
                  if isinstance(n,ast.ClassDef) and n.name==name)
    fixture=ast.ClassDef(name=name,bases=[ast.Attribute(value=ast.Name(id='unittest',ctx=ast.Load()),attr='TestCase',ctx=ast.Load())],
                        keywords=[],body=[n for n in original.body if isinstance(n,ast.FunctionDef)
                                          and n.name in ('setUpClass','tearDownClass','_stop_process')],decorator_list=[])
    module=ast.fix_missing_locations(ast.Module(body=[fixture],type_ignores=[]))
    namespace=dict(unittest=unittest,subprocess=SimpleNamespace(Popen=Process,PIPE=-1,TimeoutExpired=subprocess.TimeoutExpired),
                   sys=SimpleNamespace(executable='synthetic-python'),signal=SimpleNamespace(SIGINT=2),json=json,
                   os=SimpleNamespace(environ={}),Path=Output,ROOT='/synthetic-source',sync_playwright=Playwright,
                   ThreadingHTTPServer=Server,SimpleHTTPRequestHandler=object,threading=SimpleNamespace(Thread=Thread),
                   functools=functools,build=build)
    exec(compile(module,str(source),'exec'),namespace)
    target=namespace[name]
    target.test_body=lambda self:step('test.body')
    fake_api=ModuleType('playwright.sync_api');fake_api.sync_playwright=Playwright
    fake_package=ModuleType('playwright');fake_package.sync_api=fake_api
    result=unittest.TestResult()
    with patch.dict(sys.modules,{'playwright':fake_package,'playwright.sync_api':fake_api}):
        unittest.TestSuite([target('test_body')]).run(result)
    return result,events,active


class BrowserFixtureCleanup(unittest.TestCase):
    def assert_owner_closed(self,name,events):
        expected=(['process.signal','process.communicate'] if name=='IntegratedReview'
                  else ['server.shutdown','thread.join','server.close'])
        self.assertEqual([x for x in events if x in expected],expected)
    def test_start_and_launch_failures_stay_errors_and_release_acquired_resources(self):
        for name in FIXTURES:
            for failure in ('pw.start','browser.launch'):
                with self.subTest(name=name,failure=failure):
                    result,events,active=lifecycle(name,[failure])
                    self.assertEqual(len(result.errors),1);self.assertEqual(result.skipped,[])
                    self.assertIn('synthetic '+failure,result.errors[0][1])
                    self.assertNotIn('test.body',events);self.assertFalse(active['pw'])
                    self.assertEqual(events.count('pw.stop'),int(failure=='browser.launch'))
                    self.assertNotIn('browser.close',events);self.assert_owner_closed(name,events)
    def test_post_launch_failures_release_browser_then_playwright_then_owner(self):
        for name in FIXTURES:
            for failure in ('evidence.mkdir',*(['build'] if name=='ClickThrough' else [])):
                with self.subTest(name=name,failure=failure):
                    result,events,active=lifecycle(name,[failure])
                    self.assertEqual(len(result.errors),1);self.assertFalse(active['pw'])
                    self.assertNotIn('test.body',events)
                    self.assertLess(events.index('browser.close'),events.index('pw.stop'))
                    self.assertLess(events.index('pw.stop'),events.index('process.signal' if name=='IntegratedReview' else 'server.shutdown'))
                    self.assert_owner_closed(name,events)
    def test_success_closes_each_resource_once_and_keeps_evidence(self):
        for name in FIXTURES:
            with self.subTest(name=name):
                result,events,active=lifecycle(name)
                self.assertTrue(result.wasSuccessful());self.assertEqual(result.testsRun,1)
                for event in ('test.body','browser.close','pw.stop'):
                    self.assertEqual(events.count(event),1)
                self.assertFalse(active['pw']);self.assert_owner_closed(name,events)
                self.assertIn('write.'+('runner-shutdown.log' if name=='IntegratedReview' else 'browser-metrics.json'),events)
    def test_cleanup_errors_do_not_prevent_later_independent_cleanup(self):
        for name in FIXTURES:
            for failure in ('browser.close','pw.stop'):
                with self.subTest(name=name,failure=failure):
                    result,events,active=lifecycle(name,[failure])
                    self.assertEqual(len(result.errors),1);self.assertEqual(result.skipped,[])
                    self.assertEqual(events.count('browser.close'),1);self.assertEqual(events.count('pw.stop'),1)
                    self.assert_owner_closed(name,events)
        result,events,_=lifecycle('ClickThrough',['server.shutdown'])
        self.assertEqual(len(result.errors),1)
        self.assertLess(events.index('server.shutdown'),events.index('thread.join'))
        self.assertLess(events.index('thread.join'),events.index('server.close'))
    def test_ui_early_thread_failure_closes_server_without_joining_unstarted_thread(self):
        result,events,_=lifecycle('ClickThrough',['thread.start'])
        self.assertEqual(len(result.errors),1);self.assertEqual(events.count('server.close'),1)
        self.assertNotIn('thread.join',events);self.assertNotIn('server.shutdown',events)
        self.assertNotIn('pw.start',events)
    def test_review_receipt_failures_stop_process_before_playwright(self):
        for failure in ('process.receipt','process.bad_json'):
            with self.subTest(failure=failure):
                result,events,_=lifecycle('IntegratedReview',[failure])
                self.assertEqual(len(result.errors),1);self.assertNotIn('pw.start',events)
                self.assert_owner_closed('IntegratedReview',events)
                self.assertNotIn('write.runner-shutdown.log',events)
    def test_review_shutdown_timeout_kills_and_reaps_only_the_owned_process(self):
        result,events,_=lifecycle('IntegratedReview',['process.timeout'])
        self.assertTrue(result.wasSuccessful())
        self.assertEqual([x for x in events if x.startswith('process.')],
                         ['process.open','process.receipt','process.signal','process.communicate','process.kill','process.communicate'])
    def test_review_signal_error_still_attempts_process_reaping(self):
        result,events,_=lifecycle('IntegratedReview',['process.signal'])
        self.assertEqual(len(result.errors),1);self.assert_owner_closed('IntegratedReview',events)
    def test_metrics_write_failure_does_not_skip_ui_resource_cleanup(self):
        result,events,active=lifecycle('ClickThrough',['write.browser-metrics.json'])
        self.assertEqual(len(result.errors),1);self.assertFalse(active['pw'])
        self.assertEqual(events.count('browser.close'),1);self.assert_owner_closed('ClickThrough',events)
    def test_failed_fixture_does_not_poison_the_next_sync_fixture(self):
        active={'pw':False}
        failed,_,_=lifecycle('IntegratedReview',['browser.launch'],active)
        following,events,_=lifecycle('ClickThrough',active=active)
        self.assertEqual(len(failed.errors),1);self.assertTrue(following.wasSuccessful())
        self.assertIn('test.body',events);self.assertFalse(active['pw'])
    def test_failed_owner_acquisition_does_not_clean_unacquired_resources(self):
        for name,failure in [('IntegratedReview','process.open'),('ClickThrough','server.open')]:
            with self.subTest(name=name):
                result,events,_=lifecycle(name,[failure])
                self.assertEqual(len(result.errors),1);self.assertEqual(events,[failure])


if __name__=='__main__':unittest.main()
