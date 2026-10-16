#!/usr/bin/env python3
"""Inspect the exact static handoff without granting production release."""
import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

HEAD = 'aed5820c4dd8ca6f7e9a2020ea92a498cb41ae76'

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.inline_scripts = 0
        self.language = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if tag == 'script' and 'src' not in attrs:
            self.inline_scripts += 1
        for attr in ('href', 'src'):
            if attrs.get(attr):
                self.refs.append((tag, attr, attrs[attr]))

def inspect(root):
    hub = root / 'demos/xuanjun-site-hub'
    demo = root / 'demos/community-local-e2e'
    files = sorted(p for p in hub.rglob('*') if p.is_file())
    pages = []
    unresolved = []
    for path in files:
        if path.suffix != '.html':
            continue
        parser = Page()
        parser.feed(path.read_text())
        route = '/' + path.relative_to(hub).as_posix()
        route = route[:-10] if route.endswith('index.html') else route
        for tag, attr, ref in parser.refs:
            target = urlsplit(urljoin('https://candidate.invalid' + route, ref))
            if target.netloc != 'candidate.invalid':
                continue
            local = hub / target.path.lstrip('/')
            if target.path.endswith('/'):
                local = local / 'index.html'
            if not local.is_file():
                mapping = target.path.startswith('/visual/community-local-e2e/')
                mapped = demo / target.path.removeprefix('/visual/community-local-e2e/')
                unresolved.append({'page': route, 'target': target.path,
                                   'demo_source_exists': mapping and mapped.is_file()})
        pages.append({'path': str(path.relative_to(root)), 'route': route,
                      'language': parser.language,
                      'inline_script_count': parser.inline_scripts})
    demo_routes = set()
    demo_assets = set()
    for path in demo.glob('*'):
        if path.suffix in ('.js', '.mjs') and '.test.' not in path.name:
            for endpoint in re.findall(r'[\"\'](/demo/[^\"\']*)[\"\']', path.read_text()):
                demo_routes.add(endpoint)
        if path.suffix == '.html':
            parser = Page()
            parser.feed(path.read_text())
            demo_assets.update(ref for tag, attr, ref in parser.refs if attr == 'src')
    return {
        'original_handoff_head': HEAD,
        'release_decision': 'HOLD',
        'production_deployed': False,
        'candidate_file_count': len(files),
        'html_page_count': len(pages),
        'files': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'pages': pages,
        'mapping_required': unresolved,
        'demo_api_routes_referenced': sorted(demo_routes),
        'demo_script_paths_referenced': sorted(demo_assets),
        'limitations': [
            'Static inspection, not browser, hosted CI, independent audit or production acceptance.',
            'Demo uses /demo POST APIs; copying files alone cannot provide its interactions.',
            'Original handoff pages are zh-CN; staging generates reviewed English variants separately.',
            'Inline calculator requires exact CSP hash or externalization; never weaken CSP.',
        ],
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = inspect(args.root)
    if result['candidate_file_count'] != 20 or result['html_page_count'] != 15:
        raise SystemExit('HANDOFF_INVENTORY_DRIFT')
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload)

if __name__ == '__main__':
    main()
