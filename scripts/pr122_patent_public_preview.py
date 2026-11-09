"""Compile the exact approved synthetic patent source into a static overlay.

No publication, current switch, runtime permissions or CSP changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

SOURCE_COMMIT = 'cba85bf2fb89c03ca46cd6ce0c343b0cbfb0ec93'
SOURCE = {
    'app.js': (42128, '75b45df08ca18f2b7732ed57e26029b0b9b3d2ae782aa30c712ddbebea66f8ad'),
    'style.css': (17515, '1fae7d55c4f3ae7a31d30bb8a72454dea71cf4bb177a0688e939d394efa69d5c'),
    'index.html': (3482, '8c79f1f42d5f724cdcb3e5f76fffa3721214613017db6fec1e0d2498f25a4486'),
    'preview.html': (2708, '6940295216949b2d8dcc535be44e8a89080219111846f133dfb7196974cba723'),
    'patent-public-preview-manifest.json': (693, '709f1f2aa4085597abc039bfe8656631720464dda71f4c295eddbb925ace4122'),
}
DESTINATION = 'labs/patent-20261109'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compile_overlay(source, output):
    source, output = Path(source), Path(output)
    if {p.name for p in source.iterdir()} != set(SOURCE):
        raise ValueError('EXACT_PATENT_INPUT_MEMBERS_REQUIRED')
    files = {}
    for name, (size, digest) in SOURCE.items():
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('PATENT_INPUT_TYPE:' + name)
        raw = path.read_bytes()
        if len(raw) != size or sha(raw) != digest:
            raise ValueError('PATENT_INPUT_HASH:' + name)
        files[name] = raw
    manifest = json.loads(files['patent-public-preview-manifest.json'])
    if manifest['source_commit'] != SOURCE_COMMIT:
        raise ValueError('PATENT_SOURCE_COMMIT')
    styles = sorted({value for name in ('index.html', 'app.js')
                     for value in re.findall(r'\bstyle="([^"]*)"', files[name].decode())})
    expected = ['font-size:27px;color:var(--teal)', 'margin-top:15px', 'margin-top:16px',
                'margin-top:18px', 'margin-top:20px', 'text-align:center', 'width:35%']
    if styles != expected:
        raise ValueError('PATENT_STYLE_SET_DRIFT')
    mapping = {style: 'xj-patent-inline-' + str(i) for i, style in enumerate(styles)}
    replacements = []

    def rewrite(name):
        def tag(match):
            before = match[0]
            style = re.search(r'\bstyle="([^"]*)"', before)[1]
            cls = mapping[style]
            after = re.sub(r'\s+style="[^"]*"', '', before)
            if re.search(r'\bclass="', after):
                after = re.sub(r'(\bclass=")([^"]*)"', lambda m: m[1] + m[2] + ' ' + cls + '"', after, count=1)
            else:
                after = after[:-1] + ' class="' + cls + '">'
            replacements.append({'file': name, 'before': before, 'after': after})
            return after
        return re.sub(r'<[^>]*\bstyle="[^"]*"[^>]*>', tag, files[name].decode()).encode()

    public = {'index.html': rewrite('index.html'), 'app.js': rewrite('app.js')}
    # Equivalent declarations retain inline precedence without enabling inline CSS.
    rules = '\n/* Exact approved inline declarations moved to self-hosted CSS. */\n'
    for style, cls in mapping.items():
        declarations = ';'.join(value + '!important' for value in style.split(';'))
        rules += '.' + cls + '{' + declarations + '}\n'
    public['style.css'] = files['style.css'] + rules.encode()
    # Never overwrite a previous output or merge into a live filesystem here.
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'public' / DESTINATION
    target.mkdir(parents=True)
    for name, raw in public.items():
        (target / name).write_bytes(raw)
    receipt = {
        'state': 'STATIC_OVERLAY_NOT_PUBLISHED', 'source_commit': SOURCE_COMMIT,
        'authorization_ref': 'Sentinel_0230d08e829081919a51ffa74154b26d',
        'scope': 'PUBLIC_SYNTHETIC_PROTOTYPE_ONLY', 'destination': '/' + DESTINATION + '/',
        'entry': 'index.html', 'original_inputs': {name: {'bytes': n, 'sha256': h} for name, (n, h) in SOURCE.items()},
        'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in public.items()},
        'style_mapping': mapping, 'exact_tag_replacements': replacements,
        'preview_wrapper': 'ORIGINAL_RETAINED_NOT_SERVED_IFRAME_DENIED_BY_EXISTING_POLICY',
        'csp_changed': False, 'dynamic_management_completed': False, 'production_changes': 0,
        'installation_precondition': 'Original coordinator binds current full source and preserves all other project bytes before original publisher release.',
    }
    (output / 'PATENT_HOSTING_MANIFEST.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compile_overlay(args.source, args.output), ensure_ascii=False))
