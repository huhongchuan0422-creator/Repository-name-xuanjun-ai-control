"""Build a review-only delta from the preserved November 10 website.

No production writes, redirects, login changes or mutable catalog edits.
Input files must match the independently downloaded public snapshot exactly.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

PINS = {
    'index.html': 'c56667b2dd589eab399729828e5935e2f3f3c4e28b2277f7a891ae94f1690600',
    'custom-ai.html': 'b6d877542cc17fbaa8c425225125248db559812bacd54a199c5bf3343d074f68',
    'customer/projects/index.html': '3ada1d2799ac80a07aca9676004714150901a1896f4406a05f35d0c39d213274',
    'customer/projects/acceptance/index.html': '90eba76af4bfd705c51a1a866385f0c928cbc11ba07a184bcf21e947f4d73cfa',
    'visual/index.html': '5e69621eac241c1e80aa68e4908bebd22c66e71fceff5fea8ddb01fe326b2ad9',
    'visual/catalog/index.html': '9c6c69a97ebdfdd3e611477a780a0e60655351d7d7a03500f5f199f727139895',
    'assets/xuanjun-site-integration.css': '7e2138921edcab4011ed8cf4873eb1120de9e731fb452b27b7b9038f8b7441ae',
}
ALIASES = {
    '/customer/projects/acceptance/': '/customer/projects/#acceptance',
    '/visual/catalog/': '/visual/#catalog',
}
CSS = '''
/* PR122: balanced navigation and action spacing; original menu behavior retained. */
@media(min-width:1181px){
 .site-header .primary-nav{align-items:center;column-gap:clamp(14px,1.2vw,24px)}
 .site-header .primary-nav .nav-group{align-items:center;flex-wrap:nowrap;column-gap:2px}
 .site-header .primary-nav .nav-group>a{display:flex;align-items:center;min-height:44px;padding-right:0}
 .site-header .primary-nav .nav-group>button{display:flex;align-items:center;justify-content:center;flex:0 0 28px;width:28px;height:44px;min-height:44px;padding:0;line-height:1;transform:none!important}
 .site-header .primary-nav .nav-group>button span{line-height:1}
}
.actions,.hero-actions,.visual-actions{display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.hero>div:has(>.btn){display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.actions>.button,.hero-actions>.button,.visual-actions>.btn{margin:0;max-width:100%;white-space:normal;text-align:center}
.primary-nav .nav-panel a{line-height:1.5;padding-top:12px;padding-bottom:12px}
.merged-reference{scroll-margin-top:110px;margin-top:40px}
.merged-reference>h2{margin-bottom:18px}
@media(max-width:780px){
 .actions,.hero-actions,.visual-actions{gap:10px}
 .hero>div:has(>.btn){gap:10px}
 .actions>.button,.visual-actions>.btn{min-height:44px;display:inline-flex;align-items:center;justify-content:center}
 .site-header .primary-nav .nav-group>button{width:44px;min-height:44px;justify-content:center}
}
'''

TASK_OVERVIEW = '''<section class="page-hero"><p class="eyebrow">任务调度中心</p>
<h1>从需求到交付，让每一步有记录。</h1>
<p>把需求、分工、开发、审核与交付串联起来。这里介绍工作流程；真实任务进度与操作仍沿原任务中心及其权限入口。</p></section>
<section><h2>围绕一项工作，协同推进</h2><div class="card-grid">
<article class="card"><h3>明确需求</h3><p>先确认目标、范围、输入资料与验收要求。</p></article>
<article class="card"><h3>分工执行</h3><p>沿原项目安排职责，复用已有成果，保留执行记录。</p></article>
<article class="card"><h3>审核与验证</h3><p>核对版本、测试与异常处理，区分候选成果和实际完成。</p></article>
<article class="card"><h3>交付与接续</h3><p>保留版本与交付记录，按原流程接续更新和后续服务。</p></article>
</div></section><section><h2>查看公开项目</h2>
<p>本页不公开内部任务、客户资料或管理控制，也不把介绍页作为任务系统已上线的证明。</p>
<div class="actions"><a class="button" href="/delivery/">开发中项目</a>
<a class="button secondary" href="/delivery/cases.html">已完成案例</a></div></section>'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main_body(text):
    match = re.search(r'<main\b[^>]*>(.*?)</main>', text, re.S)
    if not match:
        raise ValueError('MAIN_NOT_FOUND')
    return match


def merge_section(destination, source, anchor, title):
    body = main_body(source).group(1)
    if re.search(r'<(?:script|style)\b', body, re.I):
        raise ValueError('ACTIVE_MERGE_CONTENT_REQUIRES_REVIEW')
    body = re.sub(r'<h1\b', '<h3', body)
    body = body.replace('</h1>', '</h3>')
    section = ('<section class="merged-reference" id="' + anchor + '"><h2>'
               + title + '</h2>' + body + '</section>')
    pos = main_body(destination).end(1)
    return destination[:pos] + section + destination[pos:]


def compatibility_page(text, target, label):
    m = main_body(text)
    body = ('<section class="page-hero"><h1>' + label + '</h1>'
            '<p>相关说明已合并，原有内容和入口继续保留。</p>'
            '<a class="button" href="' + target + '">查看完整说明 →</a></section>')
    return text[:m.start(1)] + body + text[m.end(1):]


def remove_duplicate_contact(text):
    # Exactly the existing adjacent pair. Do not deduplicate unrelated CTAs,
    # private project links, or buttons whose destinations differ.
    return text.replace(
        '<a class="button" href="/contact">描述我的需求</a>'
        '<a class="button secondary" href="/contact">联系玄钧</a>',
        '<a class="button" href="/contact">描述我的需求</a>')


def transform(source):
    for name, expected in PINS.items():
        if name not in source or sha(source[name]) != expected:
            raise ValueError('SOURCE_DRIFT:' + name)
    out = dict(source)
    projects = source['customer/projects/index.html'].decode()
    acceptance = source['customer/projects/acceptance/index.html'].decode()
    visual = source['visual/index.html'].decode()
    catalog = source['visual/catalog/index.html'].decode()
    out['customer/projects/index.html'] = merge_section(
        projects, acceptance, 'acceptance', '版本预览、反馈与验收').encode()
    out['visual/index.html'] = merge_section(
        visual, catalog, 'catalog', '场景与模块索引').encode()
    for name, target, title in [
        ('customer/projects/acceptance/index.html', ALIASES['/customer/projects/acceptance/'], '项目验收说明'),
        ('visual/catalog/index.html', ALIASES['/visual/catalog/'], '场景演示目录'),
    ]:
        out[name] = compatibility_page(source[name].decode(), target, title).encode()
    for name in list(out):
        if name.endswith('.html'):
            text = remove_duplicate_contact(out[name].decode())
            for before, after in ALIASES.items():
                text = text.replace('href="' + before + '"', 'href="' + after + '"')
            out[name] = text.encode()
    # Distinguish real completed cases from conceptual demos. The original
    # homepage currently presents the same visual catalog twice.
    home = out['index.html'].decode()
    old = ('<h3>场景演示案例</h3><p>按场景浏览演示方案；演示不代表已完成的客户交付。</p>'
           '<a href="/visual/#catalog">查看场景演示 →</a>')
    new = ('<h3>已完成案例</h3><p>查看经确认交付且获准公开的精选页面、视频与说明。</p>'
           '<a href="/delivery/cases.html">查看已完成案例 →</a>')
    if home.count(old) != 1:
        raise ValueError('HOME_CASE_CARD_DRIFT')
    out['index.html'] = home.replace(old, new).encode()
    out['assets/xuanjun-site-integration.css'] += CSS.encode()
    shell = source['custom-ai.html'].decode()
    m = main_body(shell)
    task = shell[:m.start(1)] + TASK_OVERVIEW + shell[m.end(1):]
    task = task.replace('定制与交付 | 玄钧AI新', '任务调度中心 | 玄钧AI新')
    task = task.replace('https://wenwenwenyiyiyi.work/custom-ai', 'https://www.xuanjunai.xin/task-center/')
    task = task.replace('定制开发、验收、交付与持续服务。', '任务调度中心的协同、审核与交付流程说明。')
    task = task.replace('property="og:title" content="定制与交付"', 'property="og:title" content="任务调度中心"')
    out['task-center/index.html'] = task.encode()
    return out


def build(root, output):
    root = root.resolve(strict=True)
    if output.absolute().is_relative_to(root):
        raise ValueError('OUTPUT_INSIDE_SOURCE')
    if output.exists():
        raise ValueError('OUTPUT_EXISTS')
    source = {}
    for name in PINS:
        p = root / name
        if any(q.is_symlink() for q in (p, *p.parents) if q != root) or not p.is_file():
            raise ValueError('UNSAFE_SOURCE:' + name)
        source[name] = p.read_bytes()
    result = transform(source)
    # Re-read immediately before producing the review delta.
    if any((root / n).read_bytes() != b for n, b in source.items()):
        raise ValueError('SOURCE_CHANGED_DURING_BUILD')
    output.mkdir(parents=True)
    rows = []
    for name, data in result.items():
        if data == source.get(name):
            continue
        p = output / 'public' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        rows.append({'path': name, 'before_sha256': sha(source[name]) if name in source else None,
                     'sha256': sha(data), 'size': len(data)})
    report = {'schema': 1, 'state': 'REVIEW_DELTA_NOT_INSTALLED', 'files': rows,
              'aliases': ALIASES, 'deleted_files': [],
              'unmodified_scope': ['login', 'identity', 'project_permissions',
                                   'comments', 'CSP', 'dynamic_catalog', 'task_state'],
              'task_navigation_change': {'expected_revision': 1, 'id': 'task-dispatch',
                                         'href': '/task-center/', 'label': '任务调度中心',
                                         'visible': True, 'state': 'PROPOSED_NOT_APPLIED'},
              'pending': ['owner_preview', 'native_publisher_composition',
                          'full_site_alias_and_translation_audit',
                          'task_navigation_apply_after_page_delivery',
                          'real_task_center_backend_link_is_not_public_overview']}
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.output), ensure_ascii=False, indent=2))
