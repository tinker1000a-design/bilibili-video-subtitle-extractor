"""One-shot pipeline: video URL -> clean readable transcript ready for analysis.

Native captions first (uses .credentials/sessdata.txt automatically when present),
local Whisper transcription as fallback, then Simplified-Chinese normalisation and
paragraph rebuilding. Emits a final JSON line describing what was produced.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SESSDATA = ROOT / '.credentials' / 'sessdata.txt'
GLOSSARY = ROOT / 'glossary.json'

sys.path.insert(0, str(HERE))
from check_auth import check as check_token  # noqa: E402
from fetch_subtitles import load_sessdata  # noqa: E402

try:
    import opencc
    CC = opencc.OpenCC('t2s')
except Exception:
    CC = None


def to_simplified(text):
    return CC.convert(text) if CC else text


def load_glossary(path=GLOSSARY):
    """Correct ASR mishearings of brand names. Longest key wins, applied before paragraphing."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return []
    pairs = [(k, v) for k, v in data.items() if k and v and k != v and not k.startswith('_')]
    pairs.sort(key=lambda kv: len(kv[0]), reverse=True)
    return pairs


def apply_glossary(text, pairs):
    for wrong, right in pairs:
        if wrong in text:
            text = text.replace(wrong, right)
    return text


def call(script, args_list):
    proc = subprocess.run([sys.executable, str(HERE / script)] + args_list,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    payload = None
    for line in reversed((proc.stdout or '').strip().splitlines()):
        line = line.strip()
        if line.startswith('{'):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    return proc.returncode, payload, (proc.stderr or '').strip()


def slug_for(url):
    match = re.search(r'BV[0-9A-Za-z]+', url)
    if match:
        return match.group()
    return re.sub(r'[^0-9A-Za-z]+', '_', url)[:40].strip('_') or 'video'


def clock(seconds):
    seconds = int(round(seconds or 0))
    return f'{seconds // 60:02}:{seconds % 60:02}'


def build_paragraphs(cues, target=120, glossary=None):
    glossary = glossary or []
    paragraphs, buf, start = [], [], None
    size = 0
    for cue in cues:
        if start is None:
            start = cue['start']
        text = apply_glossary(to_simplified(cue['text']), glossary)
        buf.append(text)
        size += len(text)
        if size >= target:
            paragraphs.append((start, ''.join(buf)))
            buf, start, size = [], None, 0
    if buf:
        paragraphs.append((start or 0, ''.join(buf)))
    return paragraphs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--sessdata-file', default=None,
                        help='defaults to .credentials/sessdata.txt when that file is non-empty')
    parser.add_argument('--model', default='turbo')
    parser.add_argument('--language', default='zh')
    parser.add_argument('--transcribe', action='store_true',
                        help='allow local ASR when no caption track is readable (downloads a '
                             '1.6GB model on first use, ~10 min for a 30 min video). '
                             'Without this flag the tool stops at need_asr and reports why')
    parser.add_argument('--no-asr', action='store_true',
                        help='kept for compatibility; not transcribing is now the default')
    parser.add_argument('--reuse', action='store_true',
                        help='rebuild outputs from an existing subtitles.json instead of fetching again')
    parser.add_argument('--relogin', action='store_true',
                        help='when the credential is expired, run the QR login flow and then continue')
    parser.add_argument('--out-root', default=str(ROOT / 'outputs'))
    parser.add_argument('--work-root', default=str(ROOT / 'work'))
    args = parser.parse_args()

    slug = slug_for(args.url)
    out_root = pathlib.Path(args.out_root)
    work_root = pathlib.Path(args.work_root)
    out_dir = out_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    sessdata = args.sessdata_file
    if sessdata is None and DEFAULT_SESSDATA.is_file() and DEFAULT_SESSDATA.read_text(encoding='utf-8-sig').strip():
        sessdata = str(DEFAULT_SESSDATA)

    common = ['--model', args.model, '--language', args.language]
    if sessdata:
        common += ['--sessdata-file', sessdata]

    # 先确认凭据到底是「没有」「过期」还是「可用」。
    # player/wbi/v2 对过期凭据和无字幕视频返回完全一样的空结果，所以这一步不能省。
    auth_state, auth_detail = 'none', None
    if sessdata:
        try:
            token = load_sessdata(sessdata)
        except Exception as exc:
            token = None
            auth_detail = {'message': str(exc)[:200]}
        if token:
            auth_state, auth_detail = check_token(token)

    uname = auth_detail.get('uname') if isinstance(auth_detail, dict) else None
    print(json.dumps(dict(status='probing', slug=slug, auth=auth_state, uname=uname),
                     ensure_ascii=False), flush=True)

    if auth_state == 'expired' and not args.relogin:
        print(json.dumps(dict(
            status='auth_expired',
            action='login_required',
            hint='SESSDATA 存在但 B 站判定未登录（nav 返回 -101）。用过期凭据探测会让所有视频都看起来'
                 '「没有字幕」，所以这里直接停下，不进入转写。重新登录：'
                 r'.\.runtime\Scripts\python.exe scripts\qr_login.py'
                 '（加 --relogin 可让本脚本自动接上这一步）',
        ), ensure_ascii=False), flush=True)
        return 4

    if args.relogin and auth_state in ('expired', 'none'):
        target = sessdata or str(DEFAULT_SESSDATA)
        print(json.dumps(dict(status='relogin', reason='credential %s' % auth_state,
                              hint='启动二维码登录，扫完自动继续'), ensure_ascii=False), flush=True)
        rc = subprocess.call([sys.executable, str(HERE / 'qr_login.py'), '--out', target])
        if rc != 0:
            print(json.dumps(dict(status='auth_expired', action='login_required',
                                  hint='二维码登录没有完成，凭据仍不可用。重跑或手动扫码后再试'),
                             ensure_ascii=False), flush=True)
            return 4
        sessdata = target
        if '--sessdata-file' not in common:
            common += ['--sessdata-file', sessdata]
        try:
            token = load_sessdata(sessdata)
            auth_state, auth_detail = check_token(token)
        except Exception as exc:
            auth_state, auth_detail = 'none', {'message': str(exc)[:200]}
        uname = auth_detail.get('uname') if isinstance(auth_detail, dict) else None
        print(json.dumps(dict(status='probing', slug=slug, auth=auth_state, uname=uname),
                         ensure_ascii=False), flush=True)
        if auth_state != 'valid':
            print(json.dumps(dict(status='auth_expired', action='login_required',
                                  hint='扫码完成后凭据仍不可用，请重试一次'),
                             ensure_ascii=False), flush=True)
            return 4

    if auth_state == 'none':
        print('[hint] 未配置有效 SESSDATA（匿名模式）：公开字幕轨仍可尝试，但登录专属轨道一律不可见。\n'
              f'       登录方式：{ROOT / "login-qr.bat"}（扫码，推荐）或 {ROOT / ".credentials" / "README.txt"}',
              file=sys.stderr, flush=True)
    elif auth_state == 'unknown':
        print('[warn] 无法确认凭据状态（nav 请求失败），继续按已配置凭据尝试。',
              file=sys.stderr, flush=True)

    result_out = None
    payload = None
    if args.reuse:
        for candidate in (out_dir, out_dir / 'probe'):
            if (candidate / 'subtitles.json').is_file():
                result_out = candidate
                print(json.dumps(dict(status='reusing', path=str(candidate)), ensure_ascii=False), flush=True)
                break
    if result_out is None:
        code, probe, err = call('fetch_subtitles.py',
                                [args.url, '--native-only', '--work', str(work_root / slug / 'probe'),
                                 '--out', str(out_dir / 'probe')] + common)
        if code != 0 or probe is None:
            print(json.dumps(dict(status='error', stage='probe', message=err[:400] or 'probe failed'),
                             ensure_ascii=False), file=sys.stderr)
            return 1
        payload = probe
        result_out = out_dir / 'probe'
        probe_status = probe.get('status')

        if probe_status in ('auth_expired', 'auth_missing', 'auth_unverified'):
            # 这几种都不是「视频没有字幕」，而是「我们看不到字幕」，绝不能拿去触发转写
            status, hint = {
                'auth_expired': ('auth_expired', 'SESSDATA 已失效，重新扫码后再跑'),
                'auth_missing': ('auth_missing', '匿名状态下看不到登录专属字幕轨，先登录再跑'),
                'auth_unverified': ('auth_unverified', 'nav 请求失败，无法确认凭据状态，稍后重试'),
            }[probe_status]
            print(json.dumps(dict(status=status, action='login_required', hint=hint,
                                  title=probe.get('title'),
                                  tracks_seen=probe.get('native_tracks_seen')), ensure_ascii=False),
                  flush=True)
            return 4

        if probe_status == 'native_failed':
            print(json.dumps(dict(status='native_failed', action='retry',
                                  hint='字幕轨存在但一条都没下载成功，先重试；不要直接转写',
                                  tracks_seen=probe.get('native_tracks_seen'),
                                  failures=probe.get('native_attempt_failures'),
                                  title=probe.get('title')), ensure_ascii=False), flush=True)
            return 5

        if probe_status == 'no_native_captions':
            duration = float(probe.get('duration') or 0)
            eta = round(duration / 60 / 2.9, 1)
            if not args.transcribe:
                print(json.dumps(dict(status='need_asr', reason='no_caption_track', auth=auth_state,
                                      duration=duration, eta_minutes=eta, title=probe.get('title'),
                                      hint='登录有效且这个视频确实没有字幕轨。要转写需显式加 --transcribe，'
                                           '首次会下载约 1.6GB 模型'), ensure_ascii=False), flush=True)
                return 2
            print(json.dumps(dict(status='need_asr', duration=duration, eta_minutes=eta,
                                  title=probe.get('title')), ensure_ascii=False), flush=True)
            code, payload, err = call('fetch_subtitles.py',
                                      [args.url, '--transcribe', '--work', str(work_root / slug / 'full'),
                                       '--out', str(out_dir)] + common)
            if code != 0 or payload is None:
                print(json.dumps(dict(status='error', stage='transcribe', message=err[:400]),
                                 ensure_ascii=False), file=sys.stderr)
                return 1
            result_out = out_dir

    data = json.loads((result_out / 'subtitles.json').read_text(encoding='utf-8-sig'))
    meta, cues = data['metadata'], data['cues']
    if not cues:
        print(json.dumps(dict(status='empty', title=meta.get('title')), ensure_ascii=False))
        return 3

    paragraphs = build_paragraphs(cues, glossary=load_glossary())
    title = (meta.get('title') or slug).strip()
    method = meta.get('method') or 'unknown'
    asr = method == 'speech-recognition'

    lines = [
        f'# {title}', '',
        f"- 链接：{meta.get('url') or args.url}",
        f"- 时长：{clock(meta.get('duration'))}　　段数：{len(cues)}　　字数：{sum(len(c['text']) for c in cues)}",
        f"- 字幕来源：`{method}`" + ('（本地语音识别，非官方字幕）' if asr else '（站点字幕轨道）'),
        '',
    ]
    if asr:
        lines.insert(5, f"- 模型：{meta.get('model') or '-'}　　识别耗时：{meta.get('transcription_seconds') or '-'}s")
        lines += ['> 本文由本地语音识别生成，已做简繁统一。专有名词、数字与同音词仍可能有误，'
                  '引用前请回听原文对应时间点。', '']
    lines += ['## 正文', '']
    for start, text in paragraphs:
        lines.append(f'**[{clock(start)}]** {text}')
        lines.append('')

    md_path = out_dir / 'transcript.md'
    txt_path = out_dir / 'transcript.txt'
    md_path.write_text('\n'.join(lines), encoding='utf-8')
    txt_path.write_text('\n\n'.join(apply_glossary(to_simplified(c['text']), load_glossary())
                                  for c in cues), encoding='utf-8')

    print(json.dumps(dict(status='ok', title=title, method=method,
                          paragraphs=len(paragraphs), chars=sum(len(c['text']) for c in cues),
                          simplified=CC is not None,
                          markdown=str(md_path), text=str(txt_path),
                          subtitles=str(result_out / 'subtitles.srt')), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__, message=str(exc)),
                         ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
