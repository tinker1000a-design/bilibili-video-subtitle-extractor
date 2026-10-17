"""Small caption readers and a common, source-labelled output format."""
import html
import json
import pathlib
import re
import xml.etree.ElementTree as ET


def clean(text):
    text = re.sub(r'<[^>]*>', '', text)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def seconds(value):
    value = value.strip().replace(',', '.')
    if value.endswith('ms'):
        return float(value[:-2]) / 1000
    if value.endswith('s'):
        return float(value[:-1])
    parts = value.split(':')
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def read_captions(path):
    text = pathlib.Path(path).read_text(encoding='utf-8-sig')
    stripped = text.lstrip()
    cues = []
    if stripped.startswith(('{', '[')):
        data = json.loads(text)
        if isinstance(data, dict) and 'body' in data:
            cues = [dict(start=float(c['from']), end=float(c['to']), text=clean(c['content'])) for c in data['body']]
        elif isinstance(data, dict) and 'events' in data:
            for event in data['events']:
                content = clean(''.join(s.get('utf8', '') for s in event.get('segs', [])))
                if content:
                    start = event.get('tStartMs', 0) / 1000
                    cues.append(dict(start=start, end=start + event.get('dDurationMs', 0) / 1000, text=content))
        elif isinstance(data, list):
            cues = data
    elif '-->' in text:
        for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
            lines = block.splitlines()
            for i, line in enumerate(lines):
                if '-->' in line:
                    left, right = line.split('-->', 1)
                    cues.append(dict(start=seconds(left), end=seconds(right.strip().split()[0]),
                                     text=clean(' '.join(lines[i + 1:]))))
                    break
    elif stripped.startswith('<'):
        root = ET.fromstring(text)
        for node in root.iter():
            if node.tag.split('}')[-1] == 'p' and 'begin' in node.attrib:
                start = seconds(node.attrib['begin'])
                end = seconds(node.attrib['end']) if 'end' in node.attrib else start + seconds(node.attrib.get('dur', '0s'))
                cues.append(dict(start=start, end=end, text=clean(' '.join(node.itertext()))))
    return normalize(cues)


def normalize(cues):
    result = []
    for cue in sorted(cues, key=lambda c: float(c['start'])):
        cue = dict(cue, start=round(float(cue['start']), 3), end=round(float(cue['end']), 3), text=clean(cue['text']))
        if not cue['text'] or cue['end'] <= cue['start']:
            continue
        if result and result[-1]['text'] == cue['text'] and cue['start'] <= result[-1]['end'] + 0.15:
            result[-1]['end'] = max(result[-1]['end'], cue['end'])
        else:
            result.append(cue)
    return result


def stamp(t):
    ms = round(t * 1000)
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'


def write_result(out, cues, metadata):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cues = normalize(cues)
    metadata = dict(metadata, cue_count=len(cues), status='complete' if cues else 'no_text',
                    first_cue=cues[0]['start'] if cues else None, last_cue=cues[-1]['end'] if cues else None)
    (out / 'subtitles.json').write_text(json.dumps(dict(metadata=metadata, cues=cues), ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'subtitles.srt').write_text('\n\n'.join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i, c in enumerate(cues, 1)) + '\n', encoding='utf-8')
    (out / 'subtitles.txt').write_text('\n'.join(f"[{stamp(c['start']).replace(',', '.')}–{stamp(c['end']).replace(',', '.')}] {c['text']}" for c in cues) + '\n', encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    return metadata
