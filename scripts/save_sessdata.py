#!/usr/bin/env python3
"""Save a bilibili SESSDATA token into .credentials/sessdata.txt.

Reads from the Windows clipboard by default, so the token never has to be
typed or pasted into a chat window. Accepts a bare token, `SESSDATA=...`,
or a full cookie header, and keeps only the token value.
"""
import argparse
import pathlib
import re
import subprocess
import sys

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
    match = re.search(r'SESSDATA\s*=\s*([^;\s"\']+)', text)
    if match:
        return match.group(1)
    token = text.strip().strip('"\'')
    if token and not any(ch in token for ch in '\r\n \t'):
        return token
    return None


def mask(token):
    return token[:4] + '...' + token[-4:] if len(token) > 12 else token


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', default=None, help='use this text instead of the clipboard (for testing)')
    args = parser.parse_args()

    raw = args.text if args.text is not None else read_clipboard()
    if not raw.strip():
        print('[FAIL] clipboard is empty - copy the SESSDATA value first')
        return 1

    token = extract(raw)
    if not token:
        print('[FAIL] no SESSDATA found in the clipboard content')
        print('       content preview: ' + raw.strip()[:80].replace('\n', ' '))
        return 1

    if 'http' in token.lower():
        print('[FAIL] that looks like a video URL, not a token')
        return 1

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(token, encoding='utf-8')

    print('[OK] saved to ' + str(DEST))
    print('     token: ' + mask(token) + '  (' + str(len(token)) + ' chars)')
    if '%2C' in token:
        print('     format looks correct (contains %2C)')
    else:
        print('     [WARN] no %2C found - this may not be the real SESSDATA value')
    return 0


if __name__ == '__main__':
    sys.exit(main())
