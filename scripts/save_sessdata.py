#!/usr/bin/env python3
"""Save a bilibili SESSDATA token into .credentials/sessdata.txt.

Reads from the Windows clipboard by default, so the token never has to be
typed or pasted into a chat window. Accepts a bare token, `SESSDATA=...`,
or a full cookie header, and keeps only the token value.
"""
import argparse
import pathlib
import subprocess
import sys
from credentials import extract_token
from check_auth import check
from file_io import atomic_text

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEST = ROOT / '.credentials' / 'sessdata.txt'


def read_clipboard():
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command', 'Get-Clipboard -Raw'],
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        raise RuntimeError('cannot read clipboard: ' + (result.stderr.strip()[:200] or 'unknown error'))
    return result.stdout


def extract(text):
    try:
        return extract_token(text)
    except ValueError:
        return None


def mask(token):
    return '***'


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()

    raw = read_clipboard()
    if not raw.strip():
        print('[FAIL] clipboard is empty - copy the SESSDATA value first')
        return 1

    token = extract(raw)
    if not token:
        print('[FAIL] no SESSDATA found in the clipboard content')
        return 1

    if 'http' in token.lower():
        print('[FAIL] that looks like a video URL, not a token')
        return 1

    state, _ = check(token)
    if state != 'valid':
        print('[FAIL] login could not be verified; previous credential has been kept')
        return 1
    atomic_text(DEST, token, private=True)

    print('[OK] saved to ' + str(DEST))
    print('     token: ' + mask(token) + '  (' + str(len(token)) + ' chars)')
    if '%2C' in token:
        print('     format looks correct (contains %2C)')
    else:
        print('     [WARN] no %2C found - this may not be the real SESSDATA value')
    return 0


if __name__ == '__main__':
    sys.exit(main())
