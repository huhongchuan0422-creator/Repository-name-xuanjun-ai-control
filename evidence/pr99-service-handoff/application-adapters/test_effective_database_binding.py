"""Shape fixtures for initialized factories; not a live SQLAlchemy/app inspection."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import effective_database_binding as c


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.url=NS(drivername='sqlite',database='/opt/trading-system/runtime/actual.db',query={},
                    username=None,password=None,host=None,port=None)
        self.engine=NS(url=self.url);self.factory=NS(kw={'bind':self.engine})
        self.repository=NS(session_factory=self.factory)
    def capture(self,verifier=lambda *a:True):return c.capture_repository_database(self.repository,verifier)
    def test_reads_attached_engine_not_environment_default(self):
        with patch.dict('os.environ',{'TRADING_DATABASE_URL':'sqlite:////opt/trading-system/runtime/wrong.db'}):
            r=self.capture()
        self.assertEqual(r['database_path'],'/opt/trading-system/runtime/actual.db')
        self.assertFalse(r['derived_from_environment_or_defaults']);self.assertFalse(r['all_writers_proven'])
    def test_relative_initialized_path_uses_process_cwd(self):
        self.url.database='runtime/actual.db'
        with patch.object(c.os,'getcwd',return_value='/opt/trading-system'):
            self.assertEqual(self.capture()['database_path'],'/opt/trading-system/runtime/actual.db')
    def test_multiple_table_engines_not_silently_ignored(self):
        self.factory.kw['binds']={'fixture-table':NS()}
        with self.assertRaises(c.ConfigurationBindingHold):self.capture()
    def test_uri_query_not_removed_to_invent_file_path(self):
        self.url.query={'uri':'true'}
        with self.assertRaises(c.ConfigurationBindingHold):self.capture()
    def test_remote_or_non_sqlite_engine_rejected(self):
        for field,value in (('host','remote.invalid'),('password','PRIVATE_PASSWORD'),('drivername','postgresql')):
            prior=getattr(self.url,field);setattr(self.url,field,value)
            with self.assertRaises(c.ConfigurationBindingHold) as error:self.capture()
            self.assertNotIn('PRIVATE_PASSWORD',str(error.exception));setattr(self.url,field,prior)
    def test_memory_uri_or_outside_project_rejected(self):
        for path in (':memory:','file:private.db','/tmp/unrelated.db','abc\x00def'):
            self.url.database=path
            with self.assertRaises(c.ConfigurationBindingHold):self.capture()
    def test_no_default_fallback_for_missing_factory(self):
        self.repository.session_factory=None
        with self.assertRaises(c.ConfigurationBindingHold):self.capture()
    def test_unverified_original_instance_rejected(self):
        with self.assertRaises(c.ConfigurationBindingHold):self.capture(lambda *a:False)
    def test_withdrawn_binding_rejected(self):
        calls=[]
        def verify(*args):calls.append(args);return len(calls)==1
        with self.assertRaises(c.ConfigurationBindingHold):self.capture(verify)
        self.assertEqual(len(calls),2)
    def test_factory_replacement_during_capture_rejected(self):
        calls=[]
        def verify(*args):
            calls.append(args)
            if len(calls)==2:self.repository.session_factory=NS(kw={'bind':self.engine})
            return True
        # The verifier itself may detect withdrawal, but the sampler must also
        # recheck identity after that final callback before publishing a record.
        with self.assertRaises(c.ConfigurationBindingHold):self.capture(verify)
    def test_engine_url_replacement_during_final_check_rejected(self):
        calls=[]
        def verify(*args):
            calls.append(args)
            if len(calls)==2:self.url.database='/opt/trading-system/runtime/different.db'
            return True
        with self.assertRaises(c.ConfigurationBindingHold):self.capture(verify)


if __name__=='__main__':unittest.main()
