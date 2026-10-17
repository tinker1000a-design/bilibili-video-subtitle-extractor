"""Counterexamples for the audit, also runnable against the audited revision."""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import check_punct
import digest
import fetch_subtitles as fetch
import install_skill
import qr_login
import requests
import save_sessdata
from subtitle_io import read_captions, write_result

VIDEO = 'https://www.bilibili.com/video/BV16vdHBPExG/'
TOKEN = 'a' * 32 + '%2C1234567890%2C' + 'b' * 32


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        patch.object(digest, 'DEFAULT_SESSDATA', self.root / 'token.txt').start()
        patch.object(requests.sessions.Session, 'request', side_effect=AssertionError('unexpected network access')).start()

    def cues(self, out, url=VIDEO, method='native-caption', **metadata):
        write_result(out, [dict(start=0, end=2, text='source text')],
                     dict(url=url, title='Fixture', method=method, **metadata))

    def punctuation(self, original, revised):
        orig, rev = self.root / 'orig.txt', self.root / 'rev.txt'
        orig.write_text(original, encoding='utf-8')
        rev.write_text(revised, encoding='utf-8')
        with patch.object(sys, 'argv', ['check_punct.py', str(orig), str(rev), '--json']), \
                contextlib.redirect_stdout(io.StringIO()):
            return check_punct.main()

    def test_plain_json_preserves_angle_brackets(self):
        path = self.root / 'caption.json'
        text = '使用 <T>，比较 a < b > c，字面量 &lt;'
        path.write_text(json.dumps({'body': [dict(**{'from': 0, 'to': 2}, content=text)]}), encoding='utf-8')
        cues = read_captions(path)
        self.assertEqual(cues[0]['text'], text)
        write_result(self.root / 'out', cues, {})
        self.assertEqual(json.loads((self.root/'out/subtitles.json').read_text(encoding='utf-8'))['cues'][0]['text'], text)

    def test_xml_entities_are_decoded_only_once(self):
        path = self.root / 'caption.ttml'
        path.write_text('<tt><p begin="0s" end="2s">a &lt; b &gt; c &amp;lt;</p></tt>', encoding='utf-8')
        self.assertEqual(read_captions(path)[0]['text'], 'a < b > c &lt;')

    def test_punctuation_rejects_numeric_changes(self):
        for original, revised in [('收益 -1.5%', '收益 15%'), ('金额15元', '金额1.5元'),
                                  ('增长5%', '增长5'), ('a+b', 'ab'), ('a||b', 'ab')]:
            with self.subTest(original=original):
                self.assertEqual(self.punctuation(original, revised), 1)

    def test_punctuation_preserves_original_punctuation(self):
        self.assertEqual(self.punctuation('这是真的？', '这是真的。'), 1)

    def test_valid_punctuation_is_accepted(self):
        self.assertEqual(self.punctuation('收益为-1.5%请注意', '收益为-1.5%，请注意。'), 0)

    def test_native_cache_is_preferred_over_old_asr(self):
        directory = self.root / digest.slug_for(VIDEO)
        self.cues(directory, method='speech-recognition')
        self.cues(directory / 'probe')
        self.assertEqual(digest.find_cache(self.root, directory.name, VIDEO), directory / 'probe')

    def test_generic_input_alias_matches_canonical_metadata(self):
        original, canonical = 'https://example.org/short/1', 'https://example.org/watch/1'
        directory = self.root / digest.slug_for(original)
        self.cues(directory / 'probe', canonical, input_url=original)
        self.assertEqual(digest.find_cache(self.root, directory.name, original), directory / 'probe')

    def test_expired_bilibili_token_does_not_block_other_sites(self):
        token_path = self.root / 'token.txt'
        token_path.write_text(TOKEN, encoding='utf-8')
        url = 'https://example.org/video/1'
        self.cues(self.root / digest.slug_for(url) / 'probe', url)
        with patch.object(sys, 'argv', ['digest.py', url, '--out-root', str(self.root)]), \
                patch.object(digest, 'check_token', return_value=('expired', None)) as check, \
                patch.object(digest, 'call', return_value=(0, {'status': 'complete'}, '')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(digest.main(), 0)
        check.assert_not_called()

    def test_environment_credential_is_checked_by_main(self):
        with patch.dict(os.environ, {'BILI_SESSDATA': TOKEN}), \
                patch.object(sys, 'argv', ['digest.py', VIDEO, '--out-root', str(self.root)]), \
                patch.object(digest, 'check_token', return_value=('valid', {'uname': 'fixture'})) as check, \
                patch.object(digest, 'call', return_value=(0, {'status': 'no_native_captions', 'auth': 'valid'}, '')), \
                contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(digest.main(), 2)
        check.assert_called_once_with(TOKEN)
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['auth'], 'valid')

    def generic(self, formats, responses):
        ydl = MagicMock()
        ydl.__enter__.return_value.extract_info.return_value = {
            'webpage_url': 'https://example.org/video/1', 'subtitles': {'en': formats}}
        session = MagicMock()
        session.get.side_effect = responses
        args = types.SimpleNamespace(url='https://example.org/video/1', langs=['en'], native_only=True)
        with patch.dict(sys.modules, {'yt_dlp': types.SimpleNamespace(YoutubeDL=lambda options: ydl)}):
            return fetch.generic(args, session, self.root, self.root / 'out')

    def response(self, content):
        response = MagicMock()
        response.__enter__.return_value = response
        response.content = content
        return response

    def test_generic_failed_track_is_not_no_captions(self):
        result = self.generic([{'ext': 'vtt', 'url': 'https://example.org/caption'}], [requests.HTTPError('fixture')])
        self.assertEqual(result['status'], 'native_failed')

    def test_bad_xml_does_not_prevent_next_format(self):
        result = self.generic([
            {'ext': 'ttml', 'url': 'https://example.org/bad'},
            {'ext': 'srv3', 'url': 'https://example.org/good'}],
            [self.response(b'<tt>broken'), self.response(b'<timedtext><p t="0" d="2000">hello</p></timedtext>')])
        self.assertEqual(result['status'], 'complete')

    def test_invalid_clipboard_is_not_echoed(self):
        secret = 'private-clipboard-secret\nwrapped'
        with patch.object(sys, 'argv', ['save_sessdata.py']), \
                patch.object(save_sessdata, 'read_clipboard', return_value=secret), \
                patch.object(save_sessdata, 'DEST', self.root/'token.txt'), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(save_sessdata.main(), 1)
        self.assertNotIn('private-clipboard-secret', output.getvalue())

    def test_invalid_token_keeps_previous_credential(self):
        dest = self.root / 'token.txt'
        dest.write_text('previous', encoding='utf-8')
        with patch.object(sys, 'argv', ['save_sessdata.py']), \
                patch.object(save_sessdata, 'read_clipboard', return_value='not-a-token'), \
                patch.object(save_sessdata, 'DEST', dest), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(save_sessdata.main(), 1)
        self.assertEqual(dest.read_text(encoding='utf-8'), 'previous')

    def test_short_sensitive_values_are_always_masked(self):
        self.assertNotIn('secret', save_sessdata.mask('secret'))
        self.assertNotIn('secret', qr_login.mask('secret'))

    def test_foreign_skill_is_not_overwritten(self):
        dest = self.root / 'video-digest' / 'SKILL.md'
        dest.parent.mkdir()
        dest.write_text('user customization', encoding='utf-8')
        result = install_skill.install_one('fixture', self.root, 'new content', False)
        self.assertEqual(result['action'], 'conflict')
        self.assertEqual(dest.read_text(encoding='utf-8'), 'user customization')

    def test_qr_poll_error_has_final_json(self):
        with patch.object(sys, 'argv', ['qr_login.py']), \
                patch.object(qr_login, 'fresh_key', return_value=('https://example.org/qr', 'fixture')), \
                patch.object(qr_login, 'render', return_value=self.root/'qr.png'), \
                patch.object(qr_login, 'wait_for_scan', side_effect=requests.Timeout('secret must not appear')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(qr_login.main(), 1)
        result = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual((result['status'], result['stage']), ('error', 'poll'))
        self.assertNotIn('secret must not appear', output.getvalue())

    def test_no_asr_conflicts_with_transcribe(self):
        with patch.object(sys, 'argv', ['digest.py', VIDEO, '--transcribe', '--no-asr', '--out-root', str(self.root)]), \
                patch.object(digest, 'check_token', return_value=('none', None)), \
                patch.object(digest, 'call', return_value=(1, None, 'fixture')), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as error:
            digest.main()
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
