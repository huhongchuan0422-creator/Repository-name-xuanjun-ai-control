"""Synthetic role acceptance for loopback tests only, never a publication input."""
import argparse
import re
from pathlib import Path
from scripts import pr122_showcase as s

PROJECT = 'synthetic-role-fixture'
ROLES = {
    'consumer': 'phone', 'merchant': 'phone', 'community': 'desktop',
    'beneficiary': 'desktop', 'platform': 'desktop', 'website-admin': 'desktop',
}


def fixture_records():
    def record(kind, identifier, **fields):
        return dict(kind=kind, id=identifier, project_id=PROJECT, version=1,
                    visibility='PUBLIC',
                    title={'zh': '合成测试 ' + identifier, 'en': 'Synthetic test ' + identifier},
                    summary={'zh': '仅限本地测试，非真实验收', 'en': 'Loopback fixture only, not real acceptance'},
                    **fields)
    items = [record('project', PROJECT, state='DEVELOPING', scenarios=[],
                    required_milestones=list(ROLES))]
    files = {}
    for role, device in ROLES.items():
        relative = 'showcase/projects/' + PROJECT + '/views/' + role + '/v1/index.html'
        raw = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
               '<meta name="viewport" content="width=device-width,initial-scale=1">'
               '<title>Synthetic test</title></head><body><main><h1>Synthetic ' + role +
               '</h1><p>Loopback fixture only.</p></main><footer>'
               '<a href="https://beian.miit.gov.cn/">ICP</a></footer></body></html>').encode()
        files[relative] = raw
        rows = {'index.html': {'sha256': s.sha(raw), 'size': len(raw)}}
        items += [
            record('page', role, role=role, href='/' + relative.removesuffix('index.html'),
                   artifact_sha256=s.sha(raw), release_artifact_sha256=s.sha(s.canonical(rows))),
            record('milestone', role, state='DONE',
                   evidence_url='https://github.com/example/synthetic-fixture/issues/1'),
            record('feature', role + '-feature', role=role, device=device,
                   milestone_id=role, page_id=role, page_version=1, page_artifact_sha256=s.sha(raw)),
        ]
    published = {i['href']: {k: i[k] for k in ('artifact_sha256', 'release_artifact_sha256')}
                 for i in items if i['kind'] == 'page'}
    def proofs(records):
        return {s.sha(s.canonical(i)): {'decision': 'PUBLIC_CONTENT_APPROVED',
                'comment_id': 1, 'commit': '0' * 40, 'ci_run_id': 1} for i in records}
    project = s.compile_catalog(items, proofs(items), published_pages=published)['projects'][0]
    for feature in [i for i in items if i['kind'] == 'feature']:
        items.append(record('feature_acceptance', feature['id'] + '-accepted',
                            project_version=1, snapshot_sha256=project['snapshot_sha256'],
                            members=project['snapshot_members'], feature_sha256=s.sha(s.canonical(feature)),
                            evidence_url='https://github.com/example/synthetic-fixture/issues/2'))
    return items, proofs(items), published, files


def generate(output, stage):
    items, proofs, published, files = fixture_records()
    shell = {}
    for language, prefix in (('zh', ''), ('en', 'en/')):
        source = (Path(stage) / 'public' / prefix / 'index.html').read_text()
        shell[language] = {tag: re.search(r'<' + tag + r'\b.*?</' + tag + '>', source, re.S)[0]
                           for tag in ('header', 'footer')}
    catalog = s.compile_catalog(items, proofs, published_pages=published)
    s.render(catalog, output, preview=True, project_files=files, shell=shell)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--stage', required=True)
    args = parser.parse_args()
    generate(args.output, args.stage)
