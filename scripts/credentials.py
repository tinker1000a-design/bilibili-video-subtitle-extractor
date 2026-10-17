"""Shared credential resolution and login-state parsing. Never echo input."""
import os
import pathlib
import re

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SESSDATA = ROOT / '.credentials' / 'sessdata.txt'
NAV = 'https://api.bilibili.com/x/web-interface/nav'


def extract_token(text):
    match = re.search(r'(?:^|[;\s])SESSDATA\s*=\s*([^;\s"\']+)', text)
    token = match.group(1) if match else text.strip().strip('"\'')
    if (len(token) < 30 or not re.fullmatch(r'[A-Za-z0-9_%.*,+/=-]+', token)
            or not re.search(r'%2c|,', token, re.I) or 'http' in token.lower()):
        raise ValueError('Invalid SESSDATA format; input has not been saved')
    return token


def load_sessdata(path):
    return extract_token(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def resolve_token(path=None, default=None):
    """Explicit file > environment > default file, consistently in all CLIs."""
    if path is None and os.environ.get('BILI_SESSDATA'):
        try:
            return extract_token(os.environ['BILI_SESSDATA']), 'BILI_SESSDATA', None
        except ValueError:
            return None, 'BILI_SESSDATA', 'invalid_format'
    candidate = pathlib.Path(path) if path is not None else pathlib.Path(default or DEFAULT_SESSDATA)
    try:
        if not candidate.is_file():
            return None, str(candidate), 'file_not_found'
        if not candidate.read_text(encoding='utf-8-sig').strip():
            return None, str(candidate), 'file_empty'
        return load_sessdata(candidate), str(candidate), None
    except (OSError, UnicodeError, ValueError):
        return None, str(candidate), 'invalid_or_unreadable_file'


def session_state(session, has_token):
    if not has_token:
        return 'none', None
    try:
        response = session.get(NAV, timeout=(10, 20))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return 'unknown', {'message': 'unexpected nav response'}
        data = payload.get('data') or {}
        if payload.get('code') == 0 and isinstance(data, dict) and data.get('isLogin') is True:
            return 'valid', {'uname': data.get('uname')}
        if payload.get('code') == -101:
            return 'expired', {'message': 'credential rejected'}
        return 'unknown', {'message': 'nav did not confirm login'}
    except (requests.RequestException, ValueError):
        return 'unknown', {'message': 'nav request failed'}
