"""Isolated task contracts; no production identity or sensitive artifacts."""
import copy, json, sqlite3, unittest
from task_center_role_contract import RoleContractResolver

class ContractDelta(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.executescript('''CREATE TABLE tasks(task_id TEXT,attempt_id TEXT,spec_sha256 TEXT);
          CREATE TABLE gateway_task_metadata(task_id TEXT,tenant_id TEXT,project_id TEXT);
          CREATE TABLE model_assignments(tenant_id TEXT,task_id TEXT,attempt_id TEXT,role_id TEXT,role_version TEXT,provider_id TEXT,state TEXT);
          CREATE TABLE role_templates(tenant_id TEXT,role_id TEXT,version TEXT,capabilities_json TEXT,enabled INTEGER);''')
        self.dev=self.contract('dev-task','developer','provider-a',['code'],['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT','INSTALL','SOURCE'],{})
        self.ui=self.contract('ui-task','designer','provider-b',['design'],['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT'],{'SOURCE':'NON_SOURCE_WORK_PRODUCT','INSTALL':'NO_INSTALLATION_SCOPE'})
        for c in (self.dev,self.ui):
            self.db.execute('INSERT INTO tasks VALUES(?,?,?)',(c['task_id'],c['attempt_id'],c['task_spec_sha256']))
            self.db.execute('INSERT INTO gateway_task_metadata VALUES(?,?,?)',(c['task_id'],c['tenant_id'],c['project_id']))
            self.db.execute('INSERT INTO model_assignments VALUES(?,?,?,?,?,?,?)',(c['tenant_id'],c['task_id'],c['attempt_id'],c['role_id'],c['role_version'],c['provider_id'],'ASSIGNED'))
            self.db.execute('INSERT INTO role_templates VALUES(?,?,?,?,?)',(c['tenant_id'],c['role_id'],c['role_version'],json.dumps(c['role_scope']),1))
        self.db.commit()
    def tearDown(self):self.db.close()
    def contract(self,task,role,provider,scope,required,na):
        return dict(contract_id='contract-'+task,contract_version=1,tenant_id='tenant',project_id='project',task_id=task,attempt_id='attempt',task_spec_sha256='a'*64,role_id=role,role_version='v1',role_scope=scope,provider_id=provider,required_categories=required,not_applicable=na)
    def test_distinct_roles_providers_and_explicit_na(self):
        r=RoleContractResolver(self.db,[self.dev,self.ui]);a=r.resolve('tenant','dev-task','attempt','provider-a');b=r.resolve('tenant','ui-task','attempt','provider-b')
        self.assertIn('SOURCE',a['required_checks']);self.assertIn('INSTALL_ENTRY',a['required_checks'])
        self.assertNotIn('SOURCE',b['required_checks']);self.assertNotIn('INSTALL_ENTRY',b['required_checks'])
        self.assertEqual(b['not_applicable'],self.ui['not_applicable']);self.assertIn('ARTIFACT',b['required_checks']);self.assertIn('AUTH_ENTRY',b['required_checks']);self.assertEqual(len(b['contract_sha256']),64)
    def test_wrong_provider_role_attempt_or_mutated_authority_denied(self):
        r=RoleContractResolver(self.db,[self.dev,self.ui])
        for args in [('tenant','ui-task','attempt','provider-a'),('other','ui-task','attempt','provider-b'),('tenant','ui-task','old','provider-b')]:
            with self.assertRaises(ValueError):r.resolve(*args)
        self.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='designer'")
        with self.assertRaises(ValueError):r.resolve('tenant','ui-task','attempt','provider-b')
    def test_na_cannot_remove_common_or_infer_missing(self):
        for change in ({'required_categories':['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE']}, {'not_applicable':{}}, {'not_applicable':{'SOURCE':'NO_INSTALLATION_SCOPE','INSTALL':'NO_INSTALLATION_SCOPE'}}):
            bad=copy.deepcopy(self.ui);bad.update(change)
            with self.assertRaises(ValueError):RoleContractResolver(self.db,[bad])
    def test_trusted_registry_is_copied_and_missing_contract_fails(self):
        c=copy.deepcopy(self.ui);r=RoleContractResolver(self.db,[c]);c['not_applicable'].clear()
        self.assertEqual(r.resolve('tenant','ui-task','attempt','provider-b')['not_applicable'],self.ui['not_applicable'])
        with self.assertRaises(ValueError):r.resolve('tenant','dev-task','attempt','provider-a')

if __name__=='__main__':unittest.main()
