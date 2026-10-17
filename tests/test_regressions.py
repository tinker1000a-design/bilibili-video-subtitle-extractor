"""Offline regression checks: python -m unittest discover -s tests -v."""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import digest
import fetch_subtitles as fetch
import credentials
from subtitle_io import read_captions, write_result

VIDEO = 'https://www.bilibili.com/video/BV16vdHBPExG/'


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        patch.object(credentials, 'DEFAULT_SESSDATA', self.root/'missing-token').start()
        patch.object(fetch.requests.sessions.Session, 'request', side_effect=AssertionError('unexpected network access')).start()

    def cache(self, url=VIDEO, method='native-caption', text='We visited Star Bay.'):
        out = self.root / digest.slug_for(url) / 'probe'
        write_result(out, [dict(start=1, end=3, text=text)],
                     dict(url=url, title='Fixture', method=method))
        return out

    def run_reuse(self, url=VIDEO, extra=()):
        argv = ['digest.py', url, '--reuse', '--out-root', str(self.root), *extra]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as output:
            rc = digest.main()
        self.assertEqual(rc, 0)
        return json.loads(output.getvalue().splitlines()[-1])

    def test_parts_and_generic_urls_have_distinct_keys(self):
        self.assertNotEqual(digest.slug_for(VIDEO), digest.slug_for(VIDEO + '?p=2'))
        self.assertEqual(digest.slug_for(VIDEO), digest.slug_for(VIDEO + '?p=1&share=abc'))
        self.assertNotEqual(digest.slug_for('https://example.org/' + 'a'*80 + '/1'),
                            digest.slug_for('https://example.org/' + 'a'*80 + '/2'))

    def test_wrong_part_cache_is_rejected(self):
        self.cache()
        with self.assertRaises(RuntimeError):
            digest.find_cache(self.root, digest.slug_for(VIDEO + '?p=2'), VIDEO + '?p=2')

    def test_legacy_cache_is_checked_before_reuse(self):
        out = self.cache()
        legacy = self.root / 'BV16vdHBPExG'
        out.parent.rename(legacy)
        self.assertEqual(digest.find_cache(self.root, digest.slug_for(VIDEO), VIDEO), legacy / 'probe')
        with self.assertRaises(RuntimeError):
            digest.find_cache(self.root, digest.slug_for(VIDEO+'?p=2'), VIDEO+'?p=2')

    def test_metadata_mismatch_is_rejected(self):
        out = self.cache()
        path = out / 'subtitles.json'
        data = json.loads(path.read_text())
        data['metadata']['part'] = 2
        path.write_text(json.dumps(data))
        with self.assertRaises(RuntimeError):
            digest.find_cache(self.root, digest.slug_for(VIDEO), VIDEO)

    def test_reuse_needs_no_token_or_network(self):
        self.cache()
        with patch.object(digest, 'check_token', side_effect=AssertionError('auth called')), \
             patch.object(digest, 'call', side_effect=AssertionError('fetch called')), \
             patch.object(fetch.requests.sessions.Session, 'request', side_effect=AssertionError('network called')):
            result = self.run_reuse(extra=['--sessdata-file', str(self.root/'missing-token'), '--relogin'])
        self.assertEqual(result['status'], 'ok')

    def test_native_source_text_is_not_corrected(self):
        text = 'We visited Star Bay. Notebook ALM. 繁體字'
        self.cache(text=text)
        result = self.run_reuse()
        self.assertEqual(pathlib.Path(result['text']).read_text(encoding='utf-8'), text)
        self.assertIn('Star Bay', pathlib.Path(result['markdown']).read_text(encoding='utf-8'))
        self.assertIsNone(result['corrected_text'])

    def test_asr_corrections_are_separate_and_auditable(self):
        self.cache(method='speech-recognition')
        result = self.run_reuse()
        self.assertIn('Star Bay', pathlib.Path(result['text']).read_text())
        self.assertIn('SubBatch', pathlib.Path(result['corrected_text']).read_text())
        changes = json.loads(pathlib.Path(result['corrections']).read_text())
        self.assertEqual(changes[0]['original'], 'We visited Star Bay.')

    def test_bare_bv_uses_bilibili_extractor(self):
        argv = ['fetch_subtitles.py', 'BV16vdHBPExG', '--native-only',
                '--work', str(self.root/'work'), '--out', str(self.root/'out')]
        with patch.object(sys, 'argv', argv), patch.object(fetch, 'login_state', return_value=('none', None)), \
             patch.object(fetch, 'bilibili', return_value={'status':'auth_missing'}) as bili, \
             patch.object(fetch, 'generic', side_effect=AssertionError('generic called')), \
             contextlib.redirect_stdout(io.StringIO()):
            fetch.main()
        self.assertEqual(bili.call_args.args[0].url, VIDEO)

    def test_srv3_and_ttml_timestamps(self):
        path = self.root / 'caption.xml'
        for source in ('<timedtext format="3"><body><p t="1000" d="2000"><s>Hello</s><s> world</s></p></body></timedtext>',
                       '<tt xmlns="http://www.w3.org/ns/ttml"><body><p begin="1s" end="3s">Hello world</p></body></tt>'):
            path.write_text(source)
            self.assertEqual(read_captions(path), [dict(start=1.0, end=3.0, text='Hello world')])


if __name__ == '__main__':
    unittest.main()
