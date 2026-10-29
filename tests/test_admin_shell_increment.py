import unittest,zipfile,re
from scripts.community_web_entries import asset,PREFIX
from playwright.sync_api import sync_playwright

class Increment(unittest.TestCase):
 def test_original_ids_and_business_bytes_unchanged(self):
  from pathlib import Path
  with zipfile.ZipFile('/tmp/miniapp-c19-readonly/community-stage-source.zip') as z:
   for name in ['communities.html','web-session.js','workbench.css','workbench.js','onboarding.js']:
    actual=Path('demos/community-stage/'+name).read_bytes()
    if name=='communities.html':
     increment='<section id="communityMerchantMembers"><h2>社区商家成员</h2><label>社区编号<input id="memberCommunityReference"></label><button id="queryMerchantMembers">查询商家成员</button><p>读取当前授权社区的原商家资料与已有渠道查询状态；成员关系不代表收款或分账已验收。</p></section>'.encode()
     self.assertEqual(actual.count(increment),1)
     for added in ['communityMerchantMembers','memberCommunityReference','queryMerchantMembers']:self.assertEqual(actual.count(('id="'+added+'"').encode()),1)
     actual=actual.replace(increment,b'',1)
    self.assertEqual(z.read('demos/community-stage/'+name),actual)
   original=z.read('demos/community-stage/communities.html').decode()
   rendered=asset('/community/portal')[0].decode()
   for id in re.findall(r'id="([^"]+)"',original): self.assertEqual(rendered.count('id="'+id+'"'),1)
 def test_scoped_shell_and_local_browser(self):
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium')
   try:
    page=b.new_page(viewport={'width':1440,'height':1000});errors=[];posts=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def respond(route):
     if route.request.method!='GET':
      posts.append(route.request.url);route.fulfill(status=403,body='{}');return
     path=route.request.url.removeprefix('https://community-ui.test')
     found=asset(path[len(PREFIX):]) if path.startswith(PREFIX) else None
     if found: route.fulfill(status=200,body=found[0],content_type=found[1])
     else: route.fulfill(status=404,body='Not found')
    page.route('https://community-ui.test/**',respond)
    page.goto('https://community-ui.test'+PREFIX+'/community/portal');page.wait_for_load_state('networkidle')
    self.assertEqual(page.locator('.admin-card').count(),10)
    self.assertFalse(page.locator('#profile').is_visible())
    page.screenshot(path='../community-home-1440.png',full_page=True)
    page.get_by_role('navigation',name='社区功能').get_by_role('button',name='社区资料',exact=True).click()
    self.assertFalse(page.locator('#profile').is_visible())
    self.assertTrue(page.locator('#mine').is_visible())
    page.screenshot(path='../community-profile-1440.png',full_page=True)
    page.get_by_role('button',name='返回工作台',exact=True).click()
    self.assertEqual(posts,[])
    self.assertEqual(errors,[])
    page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='返回工作台',exact=True).click()
    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
    page.screenshot(path='../community-home-390.png',full_page=True)
   finally:b.close()
