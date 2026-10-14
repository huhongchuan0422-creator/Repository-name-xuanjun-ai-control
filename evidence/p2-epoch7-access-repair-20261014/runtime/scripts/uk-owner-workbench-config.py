#!/usr/bin/env python3
"""Render and validate the HTTPS Owner workbench proxy configuration.

This is a no-deploy release entry: it emits reviewed bytes for the existing
platform installer. It never changes nginx, systemd, the webhook or the DB.
"""
import argparse
import os
import re
import stat
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, 'deploy', 'uk-owner-workbench', 'nginx.conf.template')


def safe_regular(path, secret=False):
    if not os.path.isabs(path):
        raise ValueError('ABSOLUTE_PATH_REQUIRED')
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError('UNSAFE_TLS_FILE')
    if secret and info.st_mode & 0o077:
        raise ValueError('TLS_KEY_PERMISSIONS')
    return path


def render(owner_host, certificate, certificate_key):
    if not re.fullmatch(r'(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', owner_host):
        raise ValueError('INVALID_OWNER_HOST')
    for value in (certificate, certificate_key):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]{1,500}', value) or '..' in value.split('/'):
            raise ValueError('INVALID_TLS_PATH')
    with open(TEMPLATE) as stream:
        template = stream.read()
    return (template.replace('@@OWNER_HOST@@', owner_host)
            .replace('@@TLS_CERT@@', certificate)
            .replace('@@TLS_KEY@@', certificate_key))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner-host', required=True)
    parser.add_argument('--tls-cert', required=True)
    parser.add_argument('--tls-key', required=True)
    parser.add_argument('--verify-files', action='store_true')
    args = parser.parse_args()
    if args.verify_files:
        safe_regular(args.tls_cert)
        safe_regular(args.tls_key, secret=True)
    sys.stdout.write(render(args.owner_host, args.tls_cert, args.tls_key))


if __name__ == '__main__':
    main()
