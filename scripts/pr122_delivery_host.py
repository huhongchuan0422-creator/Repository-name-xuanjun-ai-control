"""Integrate the frozen synthetic review in the existing static build only.
No identity, customer authority, task status or deployment authority is created.
"""
import hashlib
import re

FROZEN = {'DESIGN-NOTES.md': '8af0aaaa1d236bd9e648e354088a872594d67683cc58d873dd19e59db292d308', 'index.html': '44c030ceb88b5ea740fb68e098c0e51be349d20ad9359bf0c5fe0e53b1097662', 'join/app.js': 'ad720e58ba6ff648cf13be62fb779668ae51d2b11ade3c88a7a59fc1b99f1ffb', 'join/index.html': 'dd5134d4652a1bec1bd9a2b603bd540cb2687a3039ad7f306c16243862e4887c', 'join/original-form.js': 'b1f515141fc2954fe64e568d9e6ac35f1cb5b0eededa2730f734182bf576725c', 'join/source-provenance.json': 'df5109f467f4a2be8486faddf6d260bf4a65fb4abf9485637222b94d60a78a44', 'join/style.css': '4c2290edc92c6cbdf4c41d72000fca0b4c57f083c6161d5b039b8a3c759527cb', 'suite.css': 'ff3d1c8e8d2b85302290750160e6c91ff5ecc07a1de5cfcb076b8720661b7efa', 'suite.js': '0656915654039b21bbf0ec21e341c72ceed074d3f3a3903d7666ca806b5761a7'}
HOST_FILES = ('index.html','cases.html','host.css','host.mjs','feedback-client.mjs','project-projection.mjs')


def integrate(root, public):
    source = root/'demos/pr122-delivery-review'
    actual = {p.relative_to(source/'community-next').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (source/'community-next').rglob('*') if p.is_file()}
    if actual != FROZEN:
        raise ValueError('FROZEN_REVIEW_TEMPLATE_DRIFT')
    inputs = {name: (source/name).read_bytes() for name in HOST_FILES}
    inputs.update({'community-next/'+name: (source/'community-next'/name).read_bytes() for name in FROZEN})
    if (public/'delivery').exists():
        raise ValueError('DELIVERY_HOST_COLLISION')
    # Resolve all destinations and validate every existing navigation before writes.
    patches = {}
    pattern = r'(<a href="[^"]*/custom-ai">(?:定制与交付|Custom &amp; Delivery|Custom & Delivery)</a>.*?<div class="nav-panel">)'
    for path in sorted(public.rglob('*.html')):
        text = path.read_text()
        if 'id="primary-nav"' not in text:
            continue
        english = bool(re.search(r'<html[^>]*lang="en"', text))
        # The frozen review is Chinese; retain locale on the surrounding host.
        labels = ('Developing projects · Chinese review','Completed cases') if english else ('开发中项目','已完成案例')
        links = '<a href="/delivery/">'+labels[0]+'</a><a href="/delivery/cases.html">'+labels[1]+'</a>'
        updated, count = re.subn(pattern, lambda m:m[0]+links, text, count=1, flags=re.S)
        if count != 1:
            raise ValueError('DELIVERY_NAV_STRUCTURE:'+str(path.relative_to(public)))
        if '/delivery/' in text:
            raise ValueError('DELIVERY_NAV_ALREADY_PRESENT')
        # Existing home project-card entry joins the same catalog.
        updated = updated.replace('href="/visual/community-payment/">查看开发中的作品', 'href="/delivery/">查看开发中的作品')
        patches[path] = updated
    if not patches:
        raise ValueError('DELIVERY_OFFICIAL_HOST_MISSING')
    for name, data in inputs.items():
        if name == 'index.html':
            text = data.decode().replace('../xuanjun-site-hub/', '/')
            text = re.sub(r'<section id="cases">.*?</section>', '', text, count=1, flags=re.S)
            # The shared projector may be invoked by a future authorized host;
            # retain its hidden target without adding review comments here.
            text = text.replace('</main>', '<div id="case-cards" hidden></div></main>')
            data = text.encode()
        target = public/'delivery'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for path, text in patches.items():
        path.write_text(text)
    return {'template_commit':'60f1dcd2dd1313fe91919ae1b75b21feb9693916',
            'frozen_files':FROZEN,'host_files':list(HOST_FILES),'navigation_pages':len(patches),
            'scope':'SYNTHETIC_REVIEW_ONLY','customer_identity_connected':False,
            'persistent_feedback_connected':False,'task_source_connected':False,
            'public_case_authorizations_present':False}
