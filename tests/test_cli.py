"""Real subprocess checks against temporary files; no account or model needed."""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import digest
from subtitle_io import write_result


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def run_cli(self, script, *args):
        env = dict(os.environ, PYTHONUTF8='1', HF_HUB_OFFLINE='1')
        env.pop('BILI_SESSDATA', None)
        return subprocess.run([sys.executable, str(ROOT/'scripts'/script), *map(str, args)],
                              capture_output=True, text=True, encoding='utf-8', env=env, timeout=20)

    def test_reuse_cli_preserves_source_symbols(self):
        url = 'https://www.bilibili.com/video/BV16vdHBPExG/'
        source = '使用 <T>，收益 -1.5%，字面量 &lt;，繁體字'
        write_result(self.root/digest.slug_for(url)/'probe',
                     [dict(start=0, end=2, text=source)], dict(url=url, title='Fixture', method='native-caption'))
        result = self.run_cli('digest.py', url, '--reuse', '--out-root', self.root, '--relogin', '--sessdata-file', self.root/'missing')
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(pathlib.Path(payload['text']).read_text(encoding='utf-8'), source)
        self.assertEqual(payload['method'], 'native-caption')

    def test_punctuation_cli_rejects_numeric_changes_and_accepts_insertions(self):
        original, revised = self.root/'source.txt', self.root/'revised.txt'
        original.write_text('收益-1.5%请注意', encoding='utf-8')
        for text, expected in [('收益15%请注意。', 1), ('收益-1.5%，请注意。', 0)]:
            revised.write_text(text, encoding='utf-8')
            result = self.run_cli('check_punct.py', original, revised, '--json')
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual(json.loads(result.stdout)['ok'], expected == 0)

    def test_install_cli_dry_run_conflict_and_explicit_replacement(self):
        target = self.root/'skills'
        preview = self.run_cli('install_skill.py', '--target', target, '--dry-run')
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(target.exists())
        result = self.run_cli('install_skill.py', '--target', target)
        self.assertEqual(result.returncode, 0, result.stderr)
        dest = target/'video-digest/SKILL.md'
        self.assertNotIn('{REPO}', dest.read_text(encoding='utf-8'))
        dest.write_text('user customization', encoding='utf-8')
        result = self.run_cli('install_skill.py', '--target', target)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(dest.read_text(encoding='utf-8'), 'user customization')
        result = self.run_cli('install_skill.py', '--target', target, '--replace-existing')
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list(dest.parent.glob('SKILL.*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), 'user customization')

    def test_asr_keeps_identity_and_plain_text_without_loading_a_model(self):
        segment = types.SimpleNamespace(start=0, end=2, text='Use <T> &lt;', avg_logprob=-0.1,
                                        no_speech_prob=0.1, compression_ratio=1)
        info = types.SimpleNamespace(duration=2, language='en', language_probability=1)
        class FakeModel:
            def __init__(self, *args, **kwargs):
                pass
            def transcribe(self, *args, **kwargs):
                return iter([segment]), info
        spec = importlib.util.spec_from_file_location('asr_under_test', ROOT/'scripts/transcribe_audio.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'faster_whisper': types.SimpleNamespace(WhisperModel=FakeModel)}):
            spec.loader.exec_module(module)
        metadata = dict(url='https://example.org/watch/1', input_url='https://example.org/short/1',
                        part=2, bvid='fixture', cid=123, title='Fixture')
        path = self.root/'metadata.json'
        path.write_text(json.dumps(metadata), encoding='utf-8')
        with patch.object(sys, 'argv', ['transcribe_audio.py', str(self.root/'audio'), '--metadata', str(path),
                                      '--work', str(self.root/'work'), '--out', str(self.root/'out')]), \
                patch('builtins.print'):
            module.main()
        result = json.loads((self.root/'out/subtitles.json').read_text(encoding='utf-8'))
        for key, value in metadata.items():
            self.assertEqual(result['metadata'][key], value)
        self.assertEqual(result['cues'][0]['text'], segment.text)
        self.assertTrue(result['metadata']['review_required'])


if __name__ == '__main__':
    unittest.main()
