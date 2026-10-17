"""One-shot pipeline: video URL -> clean readable transcript ready for analysis.

Native captions first (uses .credentials/sessdata.txt automatically when present),
local Whisper transcription as fallback, then Simplified-Chinese normalisation and
paragraph rebuilding. Emits a final JSON line describing what was produced.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SESSDATA = ROOT / '.credentials' / 'sessdata.txt'
GLOSSARY = ROOT / 'glossary.json'

sys.path.insert(0, str(HERE))
from check_auth import check as check_token  # noqa: E402
from fetch_subtitles import load_sessdata, normalize_url, resolve_url  # noqa: E402

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
    url = normalize_url(url)
    parsed = urlparse(url)
    match = re.search(r'/video/(BV[0-9A-Za-z]+)', parsed.path)
    if match and (parsed.hostname == 'bilibili.com' or (parsed.hostname or '').endswith('.bilibili.com')):
        part = int(parse_qs(parsed.query).get('p', ['1'])[0])
        if part < 1:
            raise ValueError('Part must be positive')
        return f'{match.group(1)}_p{part}'
    label = re.sub(r'[^0-9A-Za-z]+', '_', url)[:40].strip('_') or 'video'
    return label + '_' + hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]


def find_cache(out_root, slug, url):
    """Reuse only matching metadata, including old BV-only output directories."""
    directories = [out_root / slug]
    if re.fullmatch(r'BV[0-9A-Za-z]+_p[0-9]+', slug):
        directories.append(out_root / slug.rsplit('_p', 1)[0])
    for directory in directories:
        for candidate in (directory, directory / 'probe'):
            path = candidate / 'subtitles.json'
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding='utf-8-sig'))
                meta = data['metadata']
                cached_url = meta.get('url')
                if not cached_url or slug_for(cached_url) != slug:
                    continue
                if meta.get('part') is not None and re.fullmatch(r'BV[0-9A-Za-z]+_p[0-9]+', slug):
                    if int(meta['part']) != int(slug.rsplit('_p', 1)[1]):
                        continue
                if not isinstance(data['cues'], list):
                    continue
                return candidate
            except (OSError, ValueError, KeyError, TypeError):
                continue
    raise RuntimeError('No matching subtitle cache for this video/part; fetch it without --reuse first')


def clock(seconds):
    seconds = int(round(seconds or 0))
    return f'{seconds // 60:02}:{seconds % 60:02}'


SENTENCE_END = '。！？!?…'
CLAUSE_END = '，、；：,;:'
# 段落提前断开用的「话语标记」，按可靠度分两层。
# 强标记几乎只出现在句首；弱标记（但是/然后/就是/所以…）在句中很常见——
# 遇到无标点文稿时只用强标记，否则会把「诗意的语言模糊，但是却完善了世界观」
# 从「但是」处切断，制造出错误的句界。
STRONG_MARKERS = ('那么', '接下来', '首先', '其次', '再者', '总之', '因此',
                  '另外', '换句话说', '总结一下')
WEAK_MARKERS = ('但是', '然后', '其实', '就是', '所以', '不过', '而且', '最后', '你看', '对吧')
DISCOURSE_MARKERS = STRONG_MARKERS + WEAK_MARKERS


def _sentence_units(cues, glossary, limit):
    """把 cue 展平成「句子」单元，一条 cue 含多个句子时按字数比例插值时间。

    分段只允许发生在单元边界，所以段落永远不会断在句子中间。
    """
    units = []
    for cue in cues:
        text = apply_glossary(to_simplified(cue['text']), glossary)
        if not text.strip():
            continue
        parts = [p for p in re.split(f'(?<=[{SENTENCE_END}])', text) if p.strip()] or [text]
        # 没有标点的超长 cue（B 站 AI 字幕常见）先按上限硬切，避免单段爆掉
        flat = []
        for part in parts:
            if len(part) > limit:
                flat.extend(part[i:i + limit] for i in range(0, len(part), limit))
            else:
                flat.append(part)
        span = max(0.0, float(cue.get('end') or cue['start']) - float(cue['start']))
        total = sum(len(p) for p in flat) or 1
        offset = 0
        for part in flat:
            units.append((round(float(cue['start']) + span * offset / total, 2), part))
            offset += len(part)
    return units


def _has_punctuation(units):
    """判断这份文稿有没有「标点体系」。

    B 站 AI 字幕轨 0 标点（实测 846 段里一个都没有），ASR 则有（638 段里
    440 段以逗号或句号结尾）。两者必须走不同的分段策略，否则前者会被拉长成
    216 字的巨段。
    """
    if not units:
        return False
    hits = sum(1 for _, text in units
               if text and text.rstrip()[-1] in SENTENCE_END + CLAUSE_END)
    return hits >= max(3, len(units) * 0.2)


def _join(parts):
    """拼接段落文本，只在「英文/数字接英文/数字」处补空格，避免 One two three2019年 粘连。"""
    out = ''
    for part in parts:
        if out and re.search(r'[A-Za-z0-9]$', out) and re.match(r'[A-Za-z0-9]', part):
            out += ' '
        out += part
    return out


def build_paragraphs(cues, target=120, glossary=None, max_chars=None, marker_min=None):
    """按句子重组段落。

    实测（2026-10-17，29.5 分钟样本）：
      · B 站 AI 字幕轨：846 段、0 个标点，cue 首尾相接（gap 中位 0.00），
        「用时间间隔判断句子边界」这条路走不通；
      · 本地 ASR：638 段、162 个句末标点 + 420 个逗号，440/638 的 cue 以标点结尾，
        所以 cue 边界本身就是可靠的句读边界。

    策略分两套：
      · 有标点 → 攒够长度后**等到句末标点再断**，实在等不到才退到逗号，最后才硬断；
      · 无标点 → 按字数断，并在话语标记处提前断，让节奏不那么闷。
    """
    glossary = glossary or []
    units = _sentence_units(cues, glossary, max(target, 40))
    if not units:
        return []
    max_chars = max_chars or int(target * 1.8)
    marker_min = marker_min if marker_min is not None else target * 0.5
    punctuated = _has_punctuation(units)

    paragraphs, buf, start, size = [], [], None, 0
    for t, text in units:
        if buf:
            tail = buf[-1].rstrip()[-1:] if buf[-1].strip() else ''
            if punctuated:
                should = (
                    (size >= target and tail in SENTENCE_END)       # 够长且句号收尾
                    or (size >= target * 1.3 and tail in CLAUSE_END)  # 等不到句号，逗号也行
                    or size + len(text) > max_chars                  # 兜底硬断
                    or (size >= marker_min and text.startswith(DISCOURSE_MARKERS))
                )
            else:
                # 无标点就没有句界证据，只认「几乎只在句首出现」的强标记
                should = (
                    size >= target
                    or size + len(text) > max_chars
                    or (size >= marker_min and text.startswith(STRONG_MARKERS))
                )
            if should:
                paragraphs.append((start, _join(buf)))
                buf, start, size = [], None, 0
        if not buf:
            start = t
        buf.append(text)
        size += len(text)
    if buf:
        paragraphs.append((start or 0, _join(buf)))
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
    parser.add_argument('--readable', action='store_true',
                        help='shorter paragraphs for human reading (70 chars instead of 120, '
                             'breaks earlier at discourse markers). No effect on accuracy')
    parser.add_argument('--reuse', action='store_true',
                        help='rebuild outputs from an existing subtitles.json instead of fetching again')
    parser.add_argument('--relogin', action='store_true',
                        help='when the credential is expired, run the QR login flow and then continue')
    parser.add_argument('--out-root', default=str(ROOT / 'outputs'))
    parser.add_argument('--work-root', default=str(ROOT / 'work'))
    args = parser.parse_args()

    args.url = resolve_url(args.url)
    slug = slug_for(args.url)
    out_root = pathlib.Path(args.out_root)
    work_root = pathlib.Path(args.work_root)
    out_dir = out_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    result_out = find_cache(out_root, slug, args.url) if args.reuse else None

    sessdata = args.sessdata_file
    if not args.reuse and sessdata is None and DEFAULT_SESSDATA.is_file() and DEFAULT_SESSDATA.read_text(encoding='utf-8-sig').strip():
        sessdata = str(DEFAULT_SESSDATA)

    common = ['--model', args.model, '--language', args.language]
    if sessdata:
        common += ['--sessdata-file', sessdata]

    # 先确认凭据到底是「没有」「过期」还是「可用」。
    # player/wbi/v2 对过期凭据和无字幕视频返回完全一样的空结果，所以这一步不能省。
    auth_state, auth_detail = 'none', None
    if sessdata and not args.reuse:
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

    if not args.reuse and args.relogin and auth_state in ('expired', 'none'):
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

    if auth_state == 'none' and not args.reuse:
        print('[hint] 未配置有效 SESSDATA（匿名模式）：公开字幕轨仍可尝试，但登录专属轨道一律不可见。\n'
              f'       登录方式：{ROOT / "login-qr.bat"}（扫码，推荐）或 {ROOT / ".credentials" / "README.txt"}',
              file=sys.stderr, flush=True)
    elif auth_state == 'unknown':
        print('[warn] 无法确认凭据状态（nav 请求失败），继续按已配置凭据尝试。',
              file=sys.stderr, flush=True)

    payload = None
    if args.reuse:
        print(json.dumps(dict(status='reusing', path=str(result_out)), ensure_ascii=False), flush=True)
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

    paragraphs = build_paragraphs(
        cues,
        target=70 if args.readable else 120,
        marker_min=25 if args.readable else None,
    )
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

    # --readable 另存一份，免得把给 AI 读的长段版本覆盖掉
    stem = 'transcript-readable' if args.readable else 'transcript'
    md_path = out_dir / f'{stem}.md'
    txt_path = out_dir / f'{stem}.txt'
    md_path.write_text('\n'.join(lines), encoding='utf-8')
    # The source text remains suitable for punctuation-only comparison. Any
    # spelling/glossary edits are a separate, explicitly labelled artifact.
    txt_path.write_text('\n\n'.join(c['text'] for c in cues), encoding='utf-8')
    corrections = []
    glossary = load_glossary() if asr else []
    for i, cue in enumerate(cues, 1):
        revised = apply_glossary(cue['text'], glossary)
        if revised != cue['text']:
            corrections.append(dict(cue=i, original=cue['text'], revised=revised))
    corrected_path = out_dir / f'{stem}-corrected.txt'
    corrections_path = out_dir / f'{stem}-corrections.json'
    if corrections:
        corrected_path.write_text('\n\n'.join(apply_glossary(c['text'], glossary) for c in cues), encoding='utf-8')
        corrections_path.write_text(json.dumps(corrections, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        corrected_path.unlink(missing_ok=True)
        corrections_path.unlink(missing_ok=True)

    print(json.dumps(dict(status='ok', title=title, method=method,
                          paragraphs=len(paragraphs), chars=sum(len(c['text']) for c in cues),
                          readable=args.readable,
                          simplified=CC is not None,
                          markdown=str(md_path), text=str(txt_path),
                          corrected_text=str(corrected_path) if corrections else None,
                          corrections=str(corrections_path) if corrections else None,
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
