#!/usr/bin/env python3
"""Log in to bilibili by scanning a QR code, then save SESSDATA.

Built for people who cannot or do not want to dig through browser devtools.
The user scans the QR code with the bilibili mobile app and confirms on the
phone; this script waits for that, receives the session, and writes the
SESSDATA token to .credentials/sessdata.txt - the same file save_sessdata.py
writes to, so the rest of the pipeline is unchanged.

What this script does NOT do: read the browser cookie store, ask for a
password, or log in silently. Scanning and confirming are always done by the
account owner on their own device.
"""
import argparse
import json
import os
import pathlib
import sys
import time
from urllib.parse import parse_qs, urlparse

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEST = ROOT / '.credentials' / 'sessdata.txt'
QR_PNG = ROOT / '.credentials' / 'login_qr.png'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
GEN = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
POLL = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'

# inner payload codes returned by the poll endpoint
WAITING_SCAN = 86101
WAITING_CONFIRM = 86090
EXPIRED = 86038


def emit(**fields):
    print(json.dumps(fields, ensure_ascii=False), flush=True)


def mask(token):
    return token[:4] + '...' + token[-4:] if len(token) > 12 else token


def fresh_key(session):
    response = session.get(GEN, timeout=15)
    payload = response.json()
    if payload.get('code') != 0:
        raise RuntimeError('generate rejected: %s' % payload.get('message'))
    data = payload['data'] or {}
    url, key = data.get('url'), data.get('qrcode_key')
    if not url or not key:
        raise RuntimeError('generate returned no url/key')
    return url, key


def render(url):
    import segno
    qr = segno.make(url, error='m')
    QR_PNG.parent.mkdir(parents=True, exist_ok=True)
    qr.save(str(QR_PNG), scale=9, border=2)
    return QR_PNG


def extract_token(data, session, response):
    """Pull SESSDATA from whichever place the login response put it."""
    for jar in (session.cookies, response.cookies):
        try:
            token = jar.get('SESSDATA')
        except Exception:
            token = None
        if token:
            return token
    url = data.get('url') or ''
    if url:
        query = parse_qs(urlparse(url).query)
        if query.get('SESSDATA'):
            return query['SESSDATA'][0]
    for header in response.raw.headers.getlist('Set-Cookie') if hasattr(response.raw, 'headers') else []:
        if header.startswith('SESSDATA='):
            return header.split(';', 1)[0].split('=', 1)[1]
    return None


def wait_for_scan(session, key, timeout, interval):
    """Poll until the user confirms, the code expires, or time runs out."""
    deadline = time.monotonic() + timeout
    last_state = None
    while time.monotonic() < deadline:
        response = session.get(POLL, params={'qrcode_key': key}, timeout=15)
        payload = response.json()
        data = payload.get('data') or {}
        code = data.get('code')
        state = {WAITING_SCAN: 'waiting_scan', WAITING_CONFIRM: 'waiting_confirm',
                 EXPIRED: 'expired', 0: 'ok'}.get(code, 'unknown:%s' % code)
        if state != last_state:
            if state != 'ok':
                emit(status=state)
            last_state = state
        if state == 'ok':
            return data, response
        if state == 'expired':
            return None, response
        time.sleep(interval)
    return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(DEST), help='where to write the token')
    parser.add_argument('--timeout', type=int, default=300, help='seconds to wait for the scan')
    parser.add_argument('--interval', type=float, default=2.0, help='poll interval in seconds')
    parser.add_argument('--retries', type=int, default=1, help='how many times to refresh an expired code')
    parser.add_argument('--open-image', action='store_true', help='open the QR image with the default viewer')
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({'User-Agent': UA, 'Referer': 'https://www.bilibili.com/'})
    dest = pathlib.Path(args.out)

    attempt = 0
    while True:
        attempt += 1
        try:
            url, key = fresh_key(session)
        except Exception as exc:
            emit(status='error', stage='generate', message=str(exc)[:300])
            return 1

        png = render(url)
        if args.open_image and hasattr(os, 'startfile'):
            try:
                os.startfile(str(png))
            except Exception:
                pass
        emit(status='qr', png=str(png), url=url, timeout=args.timeout, attempt=attempt)

        data, response = wait_for_scan(session, key, args.timeout, args.interval)

        if data is None and response is None:
            emit(status='timeout', hint='no scan within %ds' % args.timeout)
            return 2
        if data is None:
            if attempt <= args.retries:
                emit(status='refreshing', reason='code expired')
                continue
            emit(status='expired', hint='code expired before confirmation')
            return 2

        token = extract_token(data, session, response)
        if not token:
            emit(status='error', stage='extract', message='logged in but SESSDATA not found in response')
            return 1
        if 'http' in token.lower():
            emit(status='error', stage='extract', message='extracted value looks like a URL')
            return 1

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(token, encoding='utf-8')
        emit(status='ok', saved=str(dest), token=mask(token), token_len=len(token),
             has_pct2c='%2C' in token)
        return 0


if __name__ == '__main__':
    sys.exit(main())
