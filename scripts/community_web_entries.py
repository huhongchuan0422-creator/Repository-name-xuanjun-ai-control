"""Original role-page paths under the fixed UK prefix; grants stay server-owned."""
import re
from pathlib import Path

PREFIX='/community-preview'
ROOT=Path(__file__).resolve().parents[1]/'demos'/'community-stage'
PAGES={
 '/merchant/workbench':('workbench.html','商家工作台'),
 '/community/portal':('communities.html','社区管理'),
 '/merchant/review':('onboarding.html','平台入驻审核'),
 '/merchant/join':('onboarding.html','商家入驻'),
}
ASSETS={
 '/merchant/workbench.js':('workbench.js','application/javascript; charset=utf-8'),
 '/merchant/workbench.css':('workbench.css','text/css; charset=utf-8'),
 '/community/portal.js':('communities.js','application/javascript; charset=utf-8'),
 '/community/portal.css':('workbench.css','text/css; charset=utf-8'),
 '/merchant/onboarding.js':('onboarding.js','application/javascript; charset=utf-8'),
 '/merchant/onboarding.css':('onboarding.css','text/css; charset=utf-8'),
}

def entries():
    # This catalog describes entry points, never possession of any role or grant.
    return {'schema':1,'production_acceptance':False,'roles':[
        {'role':'CONSUMER','kind':'WECHAT_MINIPROGRAM','path':'pages/home/index','scene':'shop1','authorization':'WECHAT_LOGIN_REQUIRED'},
        {'role':'MERCHANT','kind':'WEB','path':PREFIX+'/merchant/workbench','authorization':'ORIGINAL_ROLE_REQUIRED'},
        {'role':'COMMUNITY','kind':'WEB','path':PREFIX+'/community/portal','authorization':'ORIGINAL_ROLE_REQUIRED'},
        {'role':'PLATFORM','kind':'WEB','path':PREFIX+'/merchant/review','authorization':'ORIGINAL_REVIEWER_REQUIRED','scope':'MERCHANT_ADMISSION_REVIEW'},
    ]}

def asset(path):
    if path in PAGES:
        name,title=PAGES[path]
        raw=(ROOT/name).read_text()
        # Only original same-origin application assets are rebased, no base tag or URL input.
        raw=re.sub(r'((?:href|src)=["\'])(/(?:merchant|community)/[^"\']+)',lambda m:m[1]+PREFIX+m[2],raw)
        nav='<nav aria-label="角色入口">'+''.join('<a href="'+PREFIX+p+'">'+t+'</a> ' for p,(_,t) in PAGES.items())+'</nav>'
        raw=raw.replace('<body>','<body>'+nav,1)
        return raw.encode(),'text/html; charset=utf-8'
    if path not in ASSETS:return None
    name,mime=ASSETS[path];raw=(ROOT/name).read_text()
    if name.endswith('.js'):
        raw=re.sub(r'(["\'])(/(?:merchant|community)/[A-Za-z0-9_./-]+)\1',lambda m:m[1]+PREFIX+m[2]+m[1],raw)
    return raw.encode(),mime
