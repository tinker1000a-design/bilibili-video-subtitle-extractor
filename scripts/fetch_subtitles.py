"""Fetch native captions; otherwise download audio and optionally transcribe it."""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

import requests

from subtitle_io import read_captions, write_result
from credentials import load_sessdata, resolve_token, session_state

UA = 'Mozilla/5.0'


def normalize_url(url):
    url = url.strip()
    if re.fullmatch(r'BV[0-9A-Za-z]+', url):
        return 'https://www.bilibili.com/video/' + url + '/'
    return url


def resolve_url(url, session=None):
    url = normalize_url(url)
    if urlparse(url).hostname in ('b23.tv', 'www.b23.tv'):
        response = (session or requests).get(url, timeout=30)
        response.raise_for_status()
        return normalize_url(response.url)
    return url


def login_state(session, has_token):
    """Tell "no token" / "expired token" / "token works" apart.

    This cannot be done from player/wbi/v2: an expired token and a video without
    captions both return zero tracks with need_login_subtitle unset, so treating
    that as "this video has no captions" is wrong. The nav endpoint answers the
    question directly: code 0 + isLogin true means the token works, -101 means it
    expired or is invalid.
    """
    state, detail = session_state(session, has_token)
    return state, detail.get('uname') if detail else None


def api(session, url, params):
    r = session.get(url, params=params, timeout=(15, 45))
    r.raise_for_status()
    payload = r.json()
    if payload.get('code') != 0:
        raise RuntimeError(f"Bilibili API {payload.get('code')}: {payload.get('message')}")
    return payload['data']


def download(session, urls, path):
    error = None
    for url in urls:
        try:
            url = url.replace('\\u0026', '&')
            if url.startswith('//'):
                url = 'https:' + url
            with session.get(url, stream=True, timeout=(15, 60)) as r:
                r.raise_for_status()
                with path.open('wb') as f:
                    for chunk in r.iter_content(1024 * 512):
                        f.write(chunk)
            if path.stat().st_size:
                return
            raise RuntimeError('Empty download')
        except (requests.RequestException, RuntimeError) as exc:
            error = type(exc).__name__
    raise RuntimeError(f'All media/caption URLs failed ({error})')


def language_rank(lang, preferred):
    lang = lang.lower().replace('_', '-')
    for i, value in enumerate(preferred):
        value = value.lower().replace('_', '-')
        if lang == value or lang.startswith(value + '-'):
            return i
    return len(preferred) + 1


def audio_duration(media):
    result = subprocess.run(['ffprobe', '-v', 'quiet', '-select_streams', 'a', '-show_streams', '-show_format', '-of', 'json', str(media)], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    if not data.get('streams'):
        raise RuntimeError('Downloaded media contains no audio stream')
    return float(data['format']['duration'])


def bilibili(args, session, work, out):
    match = re.search(r'BV[0-9A-Za-z]+', args.url)
    if not match:
        raise RuntimeError('No BV identifier in Bilibili URL')
    bvid = match.group()
    view = api(session, 'https://api.bilibili.com/x/web-interface/view', {'bvid': bvid})
    part = int(parse_qs(urlparse(args.url).query).get('p', ['1'])[0])
    page = next((p for p in view['pages'] if p['page'] == part), None)
    if not page:
        raise RuntimeError(f'Part {part} does not exist')
    cid = page['cid']
    meta = dict(url=f'https://www.bilibili.com/video/{bvid}/?p={part}', title=view['title'], part=part,
                duration=page['duration'], bvid=bvid, cid=cid,
                auth=getattr(args, 'auth', 'none'), uname=getattr(args, 'uname', None))
    (work / 'video_metadata.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    player = api(session, 'https://api.bilibili.com/x/player/wbi/v2', {'bvid': bvid, 'cid': cid})
    tracks = player.get('subtitle', {}).get('subtitles', [])
    failures, empty = [], 0
    for track in sorted(tracks, key=lambda t: language_rank(t.get('lan', ''), args.langs)):
        raw = work / 'native_caption.json'
        try:
            download(session, [track['subtitle_url']], raw)
            cues = read_captions(raw)
            if cues:
                method = 'native-auto-caption' if track.get('lan', '').startswith('ai-') or track.get('ai_type') else 'native-caption'
                return write_result(out, cues, dict(meta, method=method, language=track.get('lan'), timing='native', raw_file=str(raw.resolve())))
            empty += 1
        except (requests.RequestException, ValueError, RuntimeError, ET.ParseError, KeyError, TypeError) as exc:
            failures.append(type(exc).__name__)
    meta['native_tracks_seen'] = len(tracks)
    meta['native_attempt_failures'] = failures
    meta['subtitle_login_required'] = bool(player.get('need_login_subtitle'))
    if args.native_only:
        if tracks:
            # 有轨却一条都没取到（否则上面已经 return 了）
            return dict(meta, status='native_failed' if failures else 'native_empty', empty_tracks=empty)
        state = getattr(args, 'auth', 'none')
        if state == 'expired':
            return dict(meta, status='auth_expired')
        if state == 'none':
            # 匿名状态下看不到字幕轨，不能据此断言"这个视频没有字幕"
            return dict(meta, status='auth_missing')
        if state == 'unknown':
            return dict(meta, status='auth_unverified')
        return dict(meta, status='no_native_captions')
    media = work / 'audio.m4a'
    play = api(session, 'https://api.bilibili.com/x/player/playurl', {'bvid': bvid, 'cid': cid, 'qn': 32, 'fnval': 16})
    if play.get('dash'):
        dash = play['dash']
        audio = min(dash['audio'], key=lambda a: a.get('bandwidth', 0)) if dash.get('audio') else None
        if not audio:
            raise RuntimeError('Public DASH playback has no audio track')
        download(session, [audio.get('baseUrl') or audio['base_url']] + (audio.get('backupUrl') or audio.get('backup_url') or []), media)
    elif play.get('durl') and len(play['durl']) == 1:
        raw = work / 'source_download'
        download(session, [play['durl'][0]['url']] + (play['durl'][0].get('backup_url') or []), raw)
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(raw), '-vn', '-c:a', 'aac', '-b:a', '96k', '-y', str(media)], check=True)
    else:
        raise RuntimeError('Unsupported public playback layout; try the generic extractor')
    return dict(meta, status='audio_ready', duration=audio_duration(media), audio=str(media.resolve()), audio_bytes=media.stat().st_size)


def generic(args, session, work, out):
    import yt_dlp
    # Inspect one video, never silently traverse a whole playlist.
    options = dict(quiet=True, no_warnings=True, noplaylist=True, socket_timeout=30, retries=2)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(args.url, download=False)
    if info.get('_type') in ('playlist', 'multi_video'):
        raise RuntimeError('This URL resolves to multiple videos; use a single-video URL')
    meta = dict(url=info.get('webpage_url') or args.url, input_url=args.url,
                title=info.get('title'), duration=info.get('duration'),
                extractor=info.get('extractor'), video_id=info.get('id'))
    candidates = []
    for source, tracks in [('native-caption', info.get('subtitles', {})), ('native-auto-caption', info.get('automatic_captions', {}))]:
        for lang, formats in tracks.items():
            for fmt in formats:
                ext = fmt.get('ext')
                if ext in ('srt', 'vtt', 'json3', 'ttml', 'srv3') and fmt.get('url'):
                    rank = (language_rank(lang, args.langs), source != 'native-caption', ['srt', 'vtt', 'json3', 'ttml', 'srv3'].index(ext))
                    candidates.append((rank, source, lang, fmt))
    errors, empty = [], 0
    for _, source, lang, fmt in sorted(candidates, key=lambda t: t[0]):
        raw = work / ('native_caption.' + fmt['ext'])
        try:
            headers = dict(info.get('http_headers') or {})
            headers.update(fmt.get('http_headers') or {})
            with session.get(fmt['url'], headers=headers, timeout=(15, 45)) as r:
                r.raise_for_status()
                raw.write_bytes(r.content)
            cues = read_captions(raw)
            if cues:
                return write_result(out, cues, dict(meta, method=source, language=lang, timing='native', raw_file=str(raw.resolve())))
            empty += 1
        except (requests.RequestException, ValueError, RuntimeError, ET.ParseError, KeyError, TypeError) as exc:
            errors.append(type(exc).__name__)
    meta['native_attempt_failures'] = errors
    if args.native_only:
        status = ('native_failed' if errors else 'native_empty') if candidates else 'no_native_captions'
        return dict(meta, status=status, native_tracks_seen=len(candidates), empty_tracks=empty)
    options.update(format='bestaudio/best', outtmpl=str(work / 'audio.%(ext)s'))
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(args.url, download=True)
    media = next((p for p in work.glob('audio.*') if p.suffix in ('.m4a', '.mp3', '.mp4', '.ogg', '.opus', '.mkv', '.webm', '.wav', '.flac')), None)
    if not media:
        raise RuntimeError('Downloader did not produce a media file')
    return dict(meta, status='audio_ready', duration=audio_duration(media), audio=str(media.resolve()), audio_bytes=media.stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--work', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--langs', default='zh-Hans,zh-CN,zh,ai-zh,en')
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--generic', action='store_true')
    parser.add_argument('--transcribe', action='store_true', help='Automatically transcribe downloaded audio when no captions are accessible')
    parser.add_argument('--model', default='turbo')
    parser.add_argument('--language', default='auto')
    parser.add_argument('--sessdata-file', default=None,
                        help='File holding a Bilibili SESSDATA token to read login-only caption tracks')
    args = parser.parse_args()
    if args.native_only and args.transcribe:
        parser.error('--native-only and --transcribe cannot be combined')
    args.langs = args.langs.split(',')
    work, out = pathlib.Path(args.work), pathlib.Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({'User-Agent': UA})
    args.url = resolve_url(args.url, session)
    parsed = urlparse(args.url)
    is_bili = parsed.hostname == 'bilibili.com' or (parsed.hostname or '').endswith('.bilibili.com')
    args.auth, args.uname = 'not_applicable', None
    if is_bili:
        token, source, problem = resolve_token(args.sessdata_file)
        if args.sessdata_file and problem:
            raise ValueError('Credential file is missing, unreadable or invalid')
        if token:
            session.cookies.set('SESSDATA', token, domain='.bilibili.com', secure=True)
        args.auth, args.uname = login_state(session, bool(token))
    if not args.native_only and (not shutil.which('ffmpeg') or not shutil.which('ffprobe')):
        raise RuntimeError('ffmpeg and ffprobe are required for media fallback')
    if is_bili and not args.generic:
        session.headers['Referer'] = 'https://www.bilibili.com/'
        result = bilibili(args, session, work, out)
    else:
        result = generic(args, session, work, out)
    (work / 'acquisition.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.transcribe and result['status'] == 'audio_ready':
        subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name('transcribe_audio.py')),
                        result['audio'], '--metadata', str(work / 'acquisition.json'),
                        '--work', str(work / 'asr'), '--out', str(out), '--model', args.model,
                        '--language', args.language], check=True)
        result = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__, message=str(exc)), ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
