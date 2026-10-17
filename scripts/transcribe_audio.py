"""Local audio transcription fallback; never processes video frames."""
import argparse
import json
import os
import pathlib
import sys
import time

from faster_whisper import WhisperModel

from subtitle_io import write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio')
    parser.add_argument('--out', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--metadata')
    parser.add_argument('--model', default='turbo', help='Multilingual model name or a local CTranslate2 model directory')
    parser.add_argument('--language', default='auto')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--threads', type=int, default=min(8, os.cpu_count() or 4))
    parser.add_argument('--initial-prompt', default=None, help='Optional short glossary, never a candidate transcript')
    parser.add_argument('--download-root', default=str(pathlib.Path(__file__).resolve().parents[1] / '.models'))
    args = parser.parse_args()
    work = pathlib.Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(pathlib.Path(args.metadata).read_text(encoding='utf-8')) if args.metadata else {}
    cached = pathlib.Path(args.download_root) / args.model
    model_name = str(cached) if (cached / 'model.bin').is_file() else args.model
    started = time.perf_counter()
    print(json.dumps(dict(status='loading_model', model=args.model, device=args.device)), flush=True)
    model = WhisperModel(model_name, device=args.device, compute_type='int8' if args.device == 'cpu' else 'float32',
                         cpu_threads=args.threads, download_root=args.download_root)
    loaded = time.perf_counter()
    print(json.dumps(dict(status='transcribing', model_load_seconds=round(loaded-started, 2))), flush=True)
    segments, info = model.transcribe(args.audio, language=None if args.language == 'auto' else args.language,
                                      beam_size=5, vad_filter=True, condition_on_previous_text=False,
                                      initial_prompt=args.initial_prompt)
    cues = []
    progress = 0
    with (work / 'segments_raw.jsonl').open('w', encoding='utf-8') as raw:
        for segment in segments:
            cue = dict(start=segment.start, end=segment.end, text=segment.text.strip(),
                       avg_logprob=segment.avg_logprob, no_speech_prob=segment.no_speech_prob,
                       compression_ratio=segment.compression_ratio)
            raw.write(json.dumps(cue, ensure_ascii=False) + '\n')
            raw.flush()
            cues.append(cue)
            if segment.end >= progress:
                print(json.dumps(dict(status='progress', audio_seconds=round(segment.end, 2),
                                      elapsed_seconds=round(time.perf_counter()-loaded, 2))), flush=True)
                progress = segment.end + 20
    meta = dict(url=metadata.get('url'), title=metadata.get('title'), method='speech-recognition',
                model=args.model, device=args.device, compute_type='int8' if args.device == 'cpu' else 'float32',
                audio=str(pathlib.Path(args.audio).resolve()), duration=info.duration,
                language=info.language, language_probability=info.language_probability,
                timing='ASR segment estimates, not validated word alignment', review_required=True,
                review_candidates=[i+1 for i,c in enumerate(cues) if c['avg_logprob'] < -0.6 or c['no_speech_prob'] > 0.5],
                model_load_seconds=round(loaded-started, 2),
                transcription_seconds=round(time.perf_counter()-loaded, 2),
                elapsed_seconds=round(time.perf_counter()-started, 2))
    result = write_result(args.out, cues, meta)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not cues:
        raise RuntimeError('Transcription completed without usable speech segments')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__, message=str(exc)), ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
