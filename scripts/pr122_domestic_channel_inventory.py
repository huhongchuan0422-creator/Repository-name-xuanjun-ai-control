#!/usr/bin/env python3
"""Bounded non-root, no-secrets inventory for PR122's existing host channel."""
import json
import os
import pwd
import re
import subprocess


def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=15)


def main():
    if os.uname().nodename != 'iZvt5t8tlrm8oiZ' or pwd.getpwuid(os.geteuid()).pw_name != 'githubrunner':
        raise SystemExit('STOP_WRONG_HOST_OR_IDENTITY')
    out = {'schema_version': 1, 'host': os.uname().nodename,
           'user': 'githubrunner', 'production_mutation': False}
    fields = ('Id', 'ActiveState', 'SubState', 'User', 'MainPID', 'WorkingDirectory', 'FragmentPath')
    services = {}
    for name in ('provider-neutral-domestic-bridge.service', 'nginx.service'):
        result = command(['systemctl', 'show', name] + ['--property='+f for f in fields])
        services[name] = dict(line.split('=', 1) for line in result.stdout.splitlines()
                              if '=' in line and line.split('=', 1)[0] in fields)
        services[name]['query_exit'] = result.returncode
    out['services'] = services
    result = command(['ss', '-H', '-lnt'])
    out['loopback_tcp_ports'] = sorted(set(int(p) for p in re.findall(
        r'(?:127\.0\.0\.1|\[::1\]):(\d+)\s', result.stdout)))
    # Permissions are observed, never exercised. Do not publish command/env text.
    result = command(['sudo', '-n', '-l'])
    out['sudo_policy_visible'] = result.returncode == 0
    out['sudo_general_all_reported'] = bool(re.search(r'NOPASSWD:\s*ALL(?:\s|$)', result.stdout))
    print(json.dumps(out, ensure_ascii=True, indent=2, sort_keys=True))



# Read-only source inventory. No nginx -T/private-key access or sudo is needed.
def nginx_tokens(text):
    tokens, word, quote, escaped, comment = [], '', None, False, False
    for char in text:
        if comment:
            if char == '\n': comment = False
            continue
        if escaped:
            word += char; escaped = False; continue
        if char == '\\':
            escaped = True; continue
        if quote:
            if char == quote: quote = None
            else: word += char
            continue
        if char in ('"', "'"):
            quote = char; continue
        if char == '#':
            if word: tokens.append(word); word = ''
            comment = True; continue
        if char.isspace() or char in '{};':
            if word: tokens.append(word); word = ''
            if char in '{};': tokens.append(char)
        else: word += char
    if quote or escaped: raise ValueError('NGINX_LEXICAL_HOLD')
    if word: tokens.append(word)
    return tokens


def nginx_parse(text):
    tokens, index = nginx_tokens(text), 0
    def scope(nested=False):
        nonlocal index
        nodes, words = [], []
        while index < len(tokens):
            token = tokens[index]; index += 1
            if token == '}':
                if words or not nested: raise ValueError('NGINX_PARSE_HOLD')
                return nodes
            if token in (';', '{'):
                if not words: raise ValueError('NGINX_PARSE_HOLD')
                nodes.append({'name':words[0], 'args':words[1:],
                    'children':scope(True) if token == '{' else []})
                words = []
            else: words.append(token)
        if nested or words: raise ValueError('NGINX_PARSE_HOLD')
        return nodes
    return scope()


def nginx_inventory(config_path='/etc/nginx/nginx.conf', *, permitted_roots=None):
    import glob, hashlib, ipaddress, urllib.parse
    from pathlib import Path
    base = Path(config_path).absolute().parent
    roots = tuple(Path(p).resolve() for p in (permitted_roots or (
        '/etc/nginx','/usr/share/nginx/modules','/usr/share/nginx/modules-enabled')))
    ssl_options = Path('/etc/letsencrypt/options-ssl-nginx.conf')
    files, total, active = {}, 0, set()
    def expand(path, depth=0):
        nonlocal total
        path = Path(path).resolve()
        if not any(path.is_relative_to(root) for root in roots) and path != ssl_options:
            raise ValueError('INCLUDE_OUTSIDE_PUBLIC_CONFIG_ROOT')
        if path in active or depth > 12 or len(files) > 256:
            raise ValueError('CONFIG_INCLUDE_CYCLE_OR_LIMIT')
        if not path.is_file(): raise ValueError('NON_REGULAR_CONFIG_HOLD')
        data = path.read_bytes();total += len(data)
        if len(data)>512000 or total>2000000: raise ValueError('CONFIG_SIZE_LIMIT')
        files[str(path)]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        active.add(path)
        def descend(nodes):
            result=[]
            for node in nodes:
                if node['name']=='include':
                    if len(node['args'])!=1 or '$' in node['args'][0]: raise ValueError('DYNAMIC_INCLUDE_HOLD')
                    pattern=Path(node['args'][0]);pattern=pattern if pattern.is_absolute() else base/pattern
                    matches=sorted(glob.glob(str(pattern)))
                    if not matches and not glob.has_magic(str(pattern)): raise ValueError('MISSING_CONFIG_INCLUDE')
                    for match in matches: result.extend(expand(match,depth+1))
                else:
                    node['children']=descend(node['children']);result.append(node)
            return result
        nodes=descend(nginx_parse(data.decode('utf-8')))
        active.remove(path)
        return nodes
    tree=expand(config_path)
    security={'allow','deny','auth_basic','auth_basic_user_file','auth_request',
        'satisfy','limit_except','limit_req','limit_conn','real_ip_header',
        'set_real_ip_from','real_ip_recursive','proxy_set_header','proxy_pass_request_headers',
        'proxy_pass_request_body','client_max_body_size','proxy_next_upstream'}
    def safe_directive(node):
        name,args=node['name'],node['args']
        if name in {'allow','deny','set_real_ip_from'}:
            values=[]
            for value in args:
                if value in {'all','unix:'}:values.append(value)
                else:
                    try: values.append(str(ipaddress.ip_network(value,strict=False)))
                    except ValueError: values.append('UNRESOLVED_ADDRESS')
        elif name=='proxy_set_header':
            value='REDACTED'
            if len(args)==2 and args[0].lower() in {'host','x-forwarded-proto','x-forwarded-for','x-real-ip'} and args[1] in {
                    '$host','$http_host','$remote_addr','$proxy_add_x_forwarded_for','$scheme',
                    'https','http','wenwenwenyiyiyi.work'}:value=args[1]
            values=[args[0] if args else 'MISSING',value]
        elif name in {'auth_basic','auth_request'}:
            values=['off' if args==['off'] else 'CONFIGURED_VALUE_REDACTED']
        elif name in {'satisfy','real_ip_header','real_ip_recursive','proxy_pass_request_headers','proxy_pass_request_body','proxy_next_upstream','client_max_body_size'}:
            values=[v if re.fullmatch(r'[A-Za-z0-9_$-]{1,64}',v) else 'REDACTED' for v in args]
        else:values=['CONFIGURED_VALUE_REDACTED']
        return {'directive':name,'arguments':values}
    def settings(nodes):return [safe_directive(n) for n in nodes if n['name'] in security]
    def public_route(args):
        value=' '.join(args)
        if '/telegram-webhook/' in value:return value.split('/telegram-webhook/',1)[0]+'/telegram-webhook/[REDACTED]'
        if '@' in value or '?' in value or len(value)>240:return '[ROUTE_REDACTED_REQUIRES_PRIVATE_REVIEW]'
        return value
    servers=[]
    for http in [n for n in tree if n['name']=='http']:
        for server in [n for n in http['children'] if n['name']=='server']:
            nodes=server['children'];names=[a for n in nodes if n['name']=='server_name' for a in n['args']]
            if 'wenwenwenyiyiyi.work' not in names:continue
            record={'server_names':['wenwenwenyiyiyi.work'],'public_roots':[[a if a.startswith('/var/www/') else '[PRIVATE_PATH_REDACTED]' for a in n['args']] for n in nodes if n['name']=='root'],'listen':[n['args'] for n in nodes if n['name']=='listen'],
                'http_security':settings(http['children']),'server_security':settings(nodes),'locations':[]}
            for node in nodes:
                if node['name']!='location':continue
                item={'match':public_route(node['args']),'security':settings(node['children']),
                    'nested_control_present':any(n['children'] for n in node['children'])}
                for directive in ('try_files','root','alias','return','proxy_pass'):
                    found=[]
                    for child in node['children']:
                        if child['name']!=directive:continue
                        args=child['args']
                        if directive=='proxy_pass':
                            parsed=urllib.parse.urlsplit(args[0] if args else '')
                            found.append({'scheme':parsed.scheme,'host':parsed.hostname,'port':parsed.port,
                                'path_present':bool(parsed.path),'credentials_present':bool(parsed.username or parsed.password)})
                        elif directive in {'root','alias'}:
                            found.append([a if a.startswith('/var/www/') else '[PRIVATE_PATH_REDACTED]' for a in args])
                        elif directive=='return':found.append([args[0] if args else 'MISSING','BODY_OR_LOCATION_REDACTED'])
                        else:found.append([a if re.fullmatch(r'[A-Za-z0-9_./$=~-]{1,200}',a) else '[REDACTED]' for a in args])
                    if found:item[directive]=found
                record['locations'].append(item)
            servers.append(record)
    return {'schema_version':1,'status':'READ_ONLY_SOURCE_INVENTORY' if servers else 'APEX_CONFIG_NOT_FOUND',
        'files':files,'apex_servers':servers,'production_mutation':False,'raw_config_exported':False,
        'private_keys_read':False,'release_authorization':False}


def nginx_readonly_main():
    if os.uname().nodename!='iZ6wee8q9z4t03hvqumwfhZ' or pwd.getpwuid(os.geteuid()).pw_name!='githubrunner':
        raise SystemExit('HOLD: WRONG_HOST_OR_USER')
    try:
        output=nginx_inventory()
    except Exception as error:
        output={'status':'INVENTORY_HOLD','error_type':type(error).__name__,
            'production_mutation':False,'raw_config_exported':False,'private_keys_read':False}
    print(json.dumps(output,ensure_ascii=True,sort_keys=True,indent=2))
    if output['status']!='READ_ONLY_SOURCE_INVENTORY':raise SystemExit(2)


if __name__ == '__main__':
    if os.environ.get('XJ_PR122_NGINX_READONLY')=='1':nginx_readonly_main()
    else:main()
