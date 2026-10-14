"""Source-only selected read-only primitives. No historical capture/resume/pins.
Exact function provenance is recorded in reviewed_sources.json.
"""
import hashlib, json, os, stat, tempfile, types, importlib.util, io, marshal, struct, re, sqlite3
def database_manifest(path):
    with sqlite3.connect('file:' + path + '?mode=ro', uri=True) as db:
        check = db.execute('PRAGMA quick_check').fetchone()[0]
        if check != 'ok':
            raise ValueError('SQLite quick_check failed')
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {name: db.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                  for name in tables}
        pragmas = {name: db.execute('PRAGMA ' + name).fetchone()[0]
                   for name in ('user_version', 'application_id', 'page_size')}
        schema = [row[0] for row in db.execute(
            "SELECT coalesce(sql,'') FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        schema_sha = hashlib.sha256(json.dumps(schema, separators=(',', ':'),
                                               ensure_ascii=False).encode('utf-8')).hexdigest()
        table_hashes = {}
        for name in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [row[1] for row in db.execute('PRAGMA table_info(' + quoted + ')')]
            order = ','.join('"' + column.replace('"', '""') + '"' for column in columns)
            rows = db.execute('SELECT * FROM ' + quoted + (' ORDER BY ' + order if order else ''))
            table_digest = hashlib.sha256()
            for row in rows:
                values = [{'blob': value.hex()} if isinstance(value, bytes) else value
                          for value in row]
                table_digest.update((json.dumps(values, sort_keys=True, separators=(',', ':'),
                                                ensure_ascii=False) + '\n').encode('utf-8'))
            table_hashes[name] = table_digest.hexdigest()
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'sha256': digest.hexdigest(), 'size': os.path.getsize(path), 'counts': counts,
            'pragmas': pragmas, 'schema_sha256': schema_sha,
            'table_sha256': table_hashes, 'quick_check': 'ok'}

