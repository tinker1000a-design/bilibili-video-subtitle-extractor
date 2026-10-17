#!/usr/bin/env python3
"""Check whether the Bilibili credential is missing, valid, or expired.

The `player/wbi/v2` endpoint cannot tell these apart - an expired token and a
video without captions both come back as "zero tracks, need_login_subtitle
unset". The `nav` endpoint can: code 0 with isLogin=true means the token works,
code -101 means it is expired or invalid.

Output is one JSON line so a caller (human or AI) can branch on it.
"""
import argparse
import json
import os
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SESSDATA = ROOT / '.credentials' / 'sessdata.txt'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from credentials import resolve_token as shared_resolve_token, session_state  # noqa: E402


def resolve_token(path):
    return shared_resolve_token(path, default=DEFAULT_SESSDATA)


def check(token):
    """Return (state, detail). state in valid / expired / unknown."""
    session = requests.Session()
    session.headers.update({'User-Agent': UA, 'Referer': 'https://www.bilibili.com/'})
    session.cookies.set('SESSDATA', token, domain='.bilibili.com')
    return session_state(session, True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sessdata-file', default=None)
    args = parser.parse_args()

    path = args.sessdata_file
    token, source, problem = resolve_token(path)
    if not token and problem is None and not os.environ.get('BILI_SESSDATA'):
        source, problem = str(DEFAULT_SESSDATA), 'file_not_found'
    if not token:
        emit = dict(status='ok', auth='none', source=source, problem=problem)
        if problem:
            emit['action'] = 'login_required'
            emit['hint'] = 'run scripts/qr_login.py to log in by QR code, or fill %s' % (
                source or 'the credential file')
        print(json.dumps(emit, ensure_ascii=False))
        return 0

    state, detail = check(token)
    emit = dict(status='ok', auth=state, source=source, detail=detail)
    if state == 'valid':
        emit['uname'] = detail.get('uname')
    if state == 'expired':
        emit['action'] = 'login_required'
        emit['hint'] = ('SESSDATA exists but bilibili rejects it (code -101), so caption tracks '
                        'will silently look empty. Run scripts/qr_login.py to log in again.')
    elif state == 'valid':
        emit['action'] = 'ready'
    else:
        emit['action'] = 'retry_later'
        emit['hint'] = 'could not reach bilibili; credential state unknown'
    print(json.dumps(emit, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
