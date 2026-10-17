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
    parser.add_argument('--no-asr', action='store_true', help='stop when no native captions are available')
    parser.add_argument('--reuse', action='store_true',
                        help='rebuild outputs from an existing subtitles.json instead of fetching again')
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
    else:
        print('[hint] 未配置 SESSDATA（匿名模式）：多数字幕轨不可读，可能退回本地转写。'
              f'\n       填法见 {ROOT / ".credentials" / "README.txt"} ，或双击仓库根目录的 save-sessdata.bat。',
              file=sys.stderr, flush=True)

    print(json.dumps(dict(status='probing', slug=slug, auth='sessdata' if sessdata else 'anonymous'),
                     ensure_ascii=False), flush=True)

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
        if probe.get('status') == 'no_native_captions':
            duration = float(probe.get('duration') or 0)
            if args.no_asr:
                print(json.dumps(dict(status='need_asr', duration=duration, auth=probe.get('auth'),
                                      title=probe.get('title')), ensure_ascii=False))
                return 2
            print(json.dumps(dict(status='need_asr', duration=duration,
                                  eta_minutes=round(duration / 60 / 2.9, 1),
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
