import pathlib,re,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
SERVER=(ROOT/'deploy/community-preview/server.py').read_text()
NGINX=(ROOT/'deploy/community-preview/nginx.conf').read_text()
DEPLOY=(ROOT/'deploy/community-preview/deploy.sh').read_text()
WORKFLOW=(ROOT/'.github/workflows/community-preview-deploy.yml').read_text()
README=(ROOT/'deploy/community-preview/README.md').read_text()
class PreviewCandidateContract(unittest.TestCase):
 def test_dedicated_host_and_cookie_do_not_claim_shared_routes(self):
  self.assertIn('community-preview.wenwenwenyiyiyi.work',NGINX)
  self.assertNotIn('server_name wenwenwenyiyiyi.work;',NGINX)
  self.assertIn('__Host-xj_community_preview',SERVER)
  self.assertIn('PRODUCTION_COOKIE_DENIED',SERVER)
  self.assertNotIn("Set-Cookie','__Host-xj_customer=",SERVER)
 def test_nginx_overwrites_private_origin_header(self):
  self.assertRegex(NGINX,r'proxy_set_header X-Xuanjun-Client-IP "";\s*proxy_set_header X-Xuanjun-Client-IP \$remote_addr;')
  self.assertIn('TrustedNginxSource',SERVER)
 def test_candidate_workflow_has_no_deploy_job_or_automatic_push(self):
  self.assertIn('workflow_dispatch:',WORKFLOW)
  self.assertNotRegex(WORKFLOW,r'(?m)^\s*push:')
  self.assertNotRegex(WORKFLOW,r'(?m)^\s*deploy:')
  for forbidden in ('systemctl','nginx -t','sudo -n','/etc/nginx'):self.assertNotIn(forbidden,WORKFLOW)
 def test_scope_discloses_mock_login_and_disabled_money(self):
  for phrase in ('test Mock','payments are disabled','Finance remains UNCONFIRMED','not real wx.login/code2session'):self.assertIn(phrase,README)
 def test_rollback_covers_external_checks_and_old_objects(self):
  for token in ('current.symlink','backup/unit','backup/nginx','backup/enabled','backup/active'):self.assertIn(token,DEPLOY)
  trap=DEPLOY.index("trap 'rollback; exit 90' ERR")
  public=DEPLOY.index('curl --fail --silent --show-error --max-time 10 "https://$HOST/community/health"')
  clear=DEPLOY.index('trap - ERR')
  self.assertLess(trap,public);self.assertLess(public,clear)
if __name__=='__main__':unittest.main()
