"""Original role-page paths under the fixed UK prefix; grants stay server-owned."""
import re
import os
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
 '/community/admin-shell.css':('admin-shell.css','text/css; charset=utf-8'),
 '/community/admin-shell.js':('admin-shell.js','application/javascript; charset=utf-8'),
 '/community/web-session.js':('web-session.js','application/javascript; charset=utf-8'),
 '/merchant/workbench.js':('workbench.js','application/javascript; charset=utf-8'),
 '/merchant/workbench.css':('workbench.css','text/css; charset=utf-8'),
 '/community/portal.js':('communities.js','application/javascript; charset=utf-8'),
 '/community/portal.css':('workbench.css','text/css; charset=utf-8'),
 '/merchant/onboarding.js':('onboarding.js','application/javascript; charset=utf-8'),
 '/merchant/onboarding.css':('onboarding.css','text/css; charset=utf-8'),
}

# Isolated static projection; these bytes never receive a session panel or API JS.
UI_ASSETS={'/community/ui-preview/':('ui-preview/index.html','text/html; charset=utf-8')}
UI_ASSETS.update({'/community/ui-preview/'+name:('ui-preview/'+name,mime) for name,mime in [
 ('index.html','text/html; charset=utf-8'),('route-gallery.html','text/html; charset=utf-8'),('sources.js','application/javascript; charset=utf-8'),
 ('preview.js','application/javascript; charset=utf-8'),('preview.css','text/css; charset=utf-8'),('original.css','text/css; charset=utf-8')]})

def entries(projects=()):
    # This catalog describes entry points, never possession of any role or grant.
    source=os.environ.get('COMMUNITY_SOURCE_SHA','')
    return {'schema':1,'source_sha':source if re.fullmatch('[0-9a-f]{40}',source) else None,
        'project_ids':sorted(set(projects)),'status':'ROLE_ACCEPTANCE_PENDING',
        'production_acceptance':False,'roles':[
        {'role':'CONSUMER','kind':'WECHAT_MINIPROGRAM','path':'pages/home/index','scene':'shop1','authorization':'WECHAT_LOGIN_REQUIRED'},
        {'role':'MERCHANT','kind':'WEB','path':PREFIX+'/merchant/workbench','authorization':'ORIGINAL_ROLE_REQUIRED'},
        {'role':'COMMUNITY','kind':'WEB','path':PREFIX+'/community/portal','authorization':'ORIGINAL_ROLE_REQUIRED'},
        {'role':'PLATFORM','kind':'WEB','path':PREFIX+'/merchant/review','authorization':'ORIGINAL_REVIEWER_REQUIRED','scope':'MERCHANT_ADMISSION_REVIEW'},
    ]}

def asset(path):
    if path in UI_ASSETS:
        name,mime=UI_ASSETS[path]
        return (ROOT/name).read_bytes(),mime
    if path in PAGES:
        name,title=PAGES[path]
        raw=(ROOT/name).read_text()
        # Only original same-origin application assets are rebased, no base tag or URL input.
        raw=re.sub(r'((?:href|src)=["\'])(/(?:merchant|community)/[^"\']+)',lambda m:m[1]+PREFIX+m[2],raw)
        nav='<nav aria-label="角色入口">'+''.join('<a href="'+PREFIX+p+'">'+t+'</a> ' for p,(_,t) in PAGES.items())+'</nav>'
        panel='<section id="community-session" aria-label="社区分账管理后台登录"><div class="admin-login-copy"><span class="admin-login-kicker">社区分账管理后台</span><h1>登录社区分账管理后台</h1></div><form><label>邮箱<input name="email" type="email" autocomplete="username" placeholder="请输入您的邮箱" required></label><label>密码<input name="password" type="password" autocomplete="current-password" placeholder="请输入密码" required></label><button type="submit">登录</button></form><div class="admin-login-visual" aria-hidden="true"><span class="admin-visual-core"></span><span class="admin-visual-node node-a"></span><span class="admin-visual-node node-b"></span><span class="admin-visual-node node-c"></span><span class="admin-visual-node node-d"></span></div><div class="admin-session-tools"><span class="admin-role-badge">待确认角色</span><label>当前管理范围<select aria-label="当前管理范围"><option value="">请选择</option></select></label><button type="button" data-logout>退出登录</button></div><p role="status">请登录。</p></section>'
        if path == '/community/portal':
            # Presentation-only shell. Original form IDs and session module remain unchanged.
            raw=raw.replace('</head>','<link rel="stylesheet" href="'+PREFIX+'/community/admin-shell.css"></head>',1)
            raw=raw.replace('<body>','<body class="community-admin admin-logged-out"><header class="admin-brand"><span class="admin-brand-mark" aria-hidden="true"></span><strong>社区分账管理后台</strong><span class="admin-brand-role">待确认角色</span></header><aside class="admin-sidebar">'+nav+'<nav id="admin-sections" aria-label="后台功能"></nav></aside><div class="admin-account">'+panel+'</div>',1)
            raw=raw.replace('</body>','<script src="'+PREFIX+'/community/admin-shell.js" defer></script></body>',1)
        else:
            raw=re.sub(r'<body([^>]*)>',lambda m:'<body'+m.group(1)+'>'+nav+panel,raw,count=1)
        raw=raw.replace('</body>','<script src="'+PREFIX+'/community/web-session.js" defer></script></body>',1)
        return raw.encode(),'text/html; charset=utf-8'
    if path not in ASSETS:return None
    name,mime=ASSETS[path];raw=(ROOT/name).read_text()
    if name.endswith('.js'):
        raw=re.sub(r'(["\'])(/(?:merchant|community)/[A-Za-z0-9_./-]+)\1',lambda m:m[1]+PREFIX+m[2]+m[1],raw)
    return raw.encode(),mime
