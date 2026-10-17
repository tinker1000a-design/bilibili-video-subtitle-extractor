"""Exercise state transitions, atomic failures and installation boundaries offline."""
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
import credentials
import digest
import file_io
import install_skill
import qr_login
import requests
import save_sessdata
from subtitle_io import clean, markup_text, normalize, write_result
from test_audit_regressions import TOKEN, VIDEO


class SafetyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        patch.object(credentials, 'DEFAULT_SESSDATA', self.root/'default-token').start()
        patch.object(requests.sessions.Session, 'request', side_effect=AssertionError('unexpected network access')).start()

    def test_plain_text_normalization_is_idempotent(self):
        text = 'Use <T> and &lt;: a < b > c'
        self.assertEqual(clean(clean(text)), text)
        cue = [dict(start=0, end=1, text=text)]
        self.assertEqual(normalize(normalize(cue)), cue)

    def test_subtitle_presentation_tags_do_not_eat_literals(self):
        self.assertEqual(markup_text('<b>Use</b> <T> &lt; b &gt; &amp;lt;'), 'Use <T> < b > &lt;')

    def test_credential_precedence_and_input_validation(self):
        path = self.root/'explicit-token'
        path.write_text(TOKEN.replace('a', 'c'), encoding='utf-8')
        with patch.dict(os.environ, {'BILI_SESSDATA': TOKEN}):
            self.assertEqual(credentials.resolve_token()[0], TOKEN)
            self.assertEqual(credentials.resolve_token(path)[0], TOKEN.replace('a', 'c'))
            self.assertIsNone(credentials.resolve_token(self.root/'missing')[0])
        for value in ('https://example.org', 'short', 'secret\nwrapped'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                credentials.extract_token(value)
        self.assertEqual(credentials.extract_token('Cookie: buvid=other; SESSDATA='+TOKEN+'; x=y'), TOKEN)

    def test_all_login_states_and_invalid_responses(self):
        session = MagicMock()
        self.assertEqual(credentials.session_state(session, False), ('none', None))
        session.get.assert_not_called()
        for payload, expected in [({'code': 0, 'data': {'isLogin': True, 'uname': 'fixture'}}, 'valid'),
                                  ({'code': -101}, 'expired'), ({'code': 0, 'data': {}}, 'unknown'),
                                  ([], 'unknown'), ({'code': 0, 'data': 123}, 'unknown')]:
            session.get.return_value.json.return_value = payload
            self.assertEqual(credentials.session_state(session, True)[0], expected)
        session.get.side_effect = requests.Timeout('sensitive detail')
        self.assertEqual(credentials.session_state(session, True), ('unknown', {'message': 'nav request failed'}))

    def test_current_pointer_can_select_latest_asr(self):
        directory = self.root/digest.slug_for(VIDEO)
        for out, method in [(directory/'probe', 'native-caption'), (directory, 'speech-recognition')]:
            write_result(out, [dict(start=0, end=1, text='fixture')], dict(url=VIDEO, method=method))
        digest.select_cache(self.root, directory, directory, {'url': VIDEO})
        self.assertEqual(digest.find_cache(self.root, directory.name, VIDEO), directory)

    def test_canonical_alias_reuses_input_directory_without_network(self):
        original, canonical = 'https://example.org/short/1', 'https://example.org/watch/1'
        directory = self.root/digest.slug_for(original)
        metadata = dict(url=canonical, input_url=original)
        write_result(directory/'probe', [dict(start=0, end=1, text='fixture')], metadata)
        digest.select_cache(self.root, directory, directory/'probe', metadata)
        with patch.object(sys, 'argv', ['digest.py', canonical, '--reuse', '--out-root', str(self.root)]), \
                patch.object(digest, 'check_token', side_effect=AssertionError('auth called')), \
                patch.object(digest, 'call', side_effect=AssertionError('network called')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(digest.main(), 0)
        self.assertEqual(pathlib.Path(json.loads(output.getvalue().splitlines()[-1])['text']).read_text(encoding='utf-8'), 'fixture')

    def test_invalid_pointer_is_rejected(self):
        directory = self.root/digest.slug_for(VIDEO)
        directory.mkdir()
        (directory/'current-result.json').write_text('{"result":"../outside"}', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            digest.find_cache(self.root, directory.name, VIDEO)

    def test_probe_failures_never_start_asr(self):
        cases = [('native_failed', 5), ('native_empty', 3), ('auth_missing', 4),
                 ('auth_expired', 4), ('auth_unverified', 4)]
        for status, expected in cases:
            with self.subTest(status=status), \
                    patch.object(sys, 'argv', ['digest.py', VIDEO, '--transcribe', '--out-root', str(self.root)]), \
                    patch.object(digest, 'DEFAULT_SESSDATA', self.root/'missing'), \
                    patch.object(digest, 'call', return_value=(0, {'status': status}, '')) as call, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(digest.main(), expected)
                self.assertEqual(call.call_count, 1)
                self.assertIn('--native-only', call.call_args.args[1])

    def test_no_caption_requires_explicit_asr(self):
        with patch.object(sys, 'argv', ['digest.py', VIDEO, '--out-root', str(self.root)]), \
                patch.object(digest, 'DEFAULT_SESSDATA', self.root/'missing'), \
                patch.object(digest, 'call', return_value=(0, {'status': 'no_native_captions'}, '')) as call, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(digest.main(), 2)
            self.assertEqual(call.call_count, 1)

    def test_expired_credential_stops_before_probe_or_asr(self):
        path = self.root/'default-token'
        path.write_text(TOKEN, encoding='utf-8')
        with patch.object(sys, 'argv', ['digest.py', VIDEO, '--transcribe', '--out-root', str(self.root)]), \
                patch.object(digest, 'DEFAULT_SESSDATA', path), \
                patch.object(digest, 'check_token', return_value=('expired', None)), \
                patch.object(digest, 'call', side_effect=AssertionError('fetch called')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(digest.main(), 4)
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['status'], 'auth_expired')

    def test_relogin_replaces_expired_environment_source_for_child(self):
        path = self.root/'default-token'
        def fake_login(command):
            self.assertIn('--open-image', command)
            path.write_text(TOKEN, encoding='utf-8')
            return 0
        with patch.dict(os.environ, {'BILI_SESSDATA': TOKEN}), \
                patch.object(sys, 'argv', ['digest.py', VIDEO, '--relogin', '--out-root', str(self.root)]), \
                patch.object(digest, 'DEFAULT_SESSDATA', path), \
                patch.object(digest, 'check_token', side_effect=[('expired', None), ('valid', {})]), \
                patch.object(digest.subprocess, 'call', side_effect=fake_login), \
                patch.object(digest, 'call', return_value=(0, {'status': 'no_native_captions'}, '')) as fetch, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(digest.main(), 2)
        command = fetch.call_args.args[1]
        self.assertEqual(command[command.index('--sessdata-file')+1], str(path))

    def test_atomic_replace_failure_keeps_old_file_and_removes_temporary(self):
        path = self.root/'token'
        path.write_text('previous', encoding='utf-8')
        with patch.object(file_io.os, 'replace', side_effect=PermissionError('fixture')), self.assertRaises(PermissionError):
            file_io.atomic_text(path, 'replacement', private=True)
        self.assertEqual(path.read_text(encoding='utf-8'), 'previous')
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_unverified_credential_does_not_replace_file(self):
        path = self.root/'token'
        path.write_text('previous', encoding='utf-8')
        for state in ('expired', 'unknown'):
            with patch.object(sys, 'argv', ['save_sessdata.py']), \
                    patch.object(save_sessdata, 'read_clipboard', return_value=TOKEN), \
                    patch.object(save_sessdata, 'check', return_value=(state, None)), \
                    patch.object(save_sessdata, 'DEST', path), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(save_sessdata.main(), 1)
                self.assertNotIn(TOKEN, output.getvalue())
                self.assertEqual(path.read_text(encoding='utf-8'), 'previous')

    def test_verified_credential_is_saved_without_echo(self):
        path = self.root/'token'
        with patch.object(sys, 'argv', ['save_sessdata.py']), \
                patch.object(save_sessdata, 'read_clipboard', return_value=TOKEN), \
                patch.object(save_sessdata, 'check', return_value=('valid', {})), \
                patch.object(save_sessdata, 'DEST', path), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(save_sessdata.main(), 0)
        self.assertEqual(path.read_text(encoding='utf-8'), TOKEN)
        self.assertNotIn(TOKEN, output.getvalue())

    def test_qr_stages_have_safe_structured_errors(self):
        for stage in ('generate', 'render', 'poll', 'verify', 'save'):
            with self.subTest(stage=stage), \
                    patch.object(sys, 'argv', ['qr_login.py', '--out', str(self.root/'token')]), \
                    patch.object(qr_login, 'fresh_key', return_value=('url', 'key')) as generate, \
                    patch.object(qr_login, 'render', return_value=self.root/'qr.png') as render, \
                    patch.object(qr_login, 'wait_for_scan', return_value=({}, MagicMock())) as poll, \
                    patch.object(qr_login, 'extract_token', return_value=TOKEN), \
                    patch.object(qr_login, 'check', return_value=('valid', {})) as check, \
                    patch.object(qr_login, 'atomic_text') as save, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                {'generate': generate, 'render': render, 'poll': poll, 'verify': check, 'save': save}[stage].side_effect = RuntimeError(TOKEN)
                self.assertEqual(qr_login.main(), 1)
                self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['stage'], stage)
                self.assertNotIn(TOKEN, output.getvalue())

    def test_qr_success_and_expiration(self):
        for result, expected in [(({}, MagicMock()), 0), ((None, MagicMock()), 2), ((None, None), 2)]:
            with patch.object(sys, 'argv', ['qr_login.py', '--out', str(self.root/'token')]), \
                    patch.object(qr_login, 'fresh_key', return_value=('url', 'key')), \
                    patch.object(qr_login, 'render', return_value=self.root/'qr.png'), \
                    patch.object(qr_login, 'wait_for_scan', return_value=result), \
                    patch.object(qr_login, 'extract_token', return_value=TOKEN), \
                    patch.object(qr_login, 'check', return_value=('valid', {})), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(qr_login.main(), expected)
                self.assertNotIn(TOKEN, output.getvalue())
        self.assertEqual((self.root/'token').read_text(encoding='utf-8'), TOKEN)

    def test_poll_retries_are_bounded_and_api_errors_fail(self):
        session = MagicMock()
        session.get.side_effect = requests.Timeout('fixture')
        with patch.object(qr_login.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(requests.Timeout):
            qr_login.wait_for_scan(session, 'key', 300, 0.5)
        self.assertEqual(session.get.call_count, 3)
        session.get.side_effect = None
        session.get.return_value.json.return_value = {'code': -1, 'data': {}}
        with self.assertRaises(RuntimeError):
            qr_login.wait_for_scan(session, 'key', 300, 0.5)

    def test_poll_can_recover_from_one_timeout_and_observe_confirmation(self):
        session = MagicMock()
        waiting, confirmed = MagicMock(), MagicMock()
        waiting.json.return_value = {'code': 0, 'data': {'code': qr_login.WAITING_CONFIRM}}
        confirmed.json.return_value = {'code': 0, 'data': {'code': 0}}
        session.get.side_effect = [requests.Timeout(), waiting, confirmed]
        with patch.object(qr_login.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()) as output:
            data, response = qr_login.wait_for_scan(session, 'key', 300, 0.5)
        self.assertEqual(data['code'], 0)
        self.assertIs(response, confirmed)
        self.assertIn('waiting_confirm', output.getvalue())
        self.assertEqual(session.get.call_count, 3)

    def test_identical_legacy_skill_can_be_explicitly_adopted(self):
        dest = self.root/'video-digest/SKILL.md'
        dest.parent.mkdir()
        dest.write_text('same content', encoding='utf-8')
        self.assertEqual(install_skill.install_one('fixture', self.root, 'same content', False)['action'], 'conflict')
        install_skill.install_one('fixture', self.root, 'same content', False, replace_existing=True)
        self.assertEqual(install_skill.install_one('fixture', self.root, 'same content', False)['action'], 'unchanged')

    def test_owned_skill_updates_preserve_unique_backups(self):
        for text in ('first', 'second', 'third'):
            install_skill.install_one('fixture', self.root, text, False)
        directory = self.root/'video-digest'
        backups = sorted(p.read_text(encoding='utf-8') for p in directory.glob('SKILL.*.bak'))
        self.assertEqual(backups, ['first', 'second'])
        (directory/'SKILL.md').write_text('user edit', encoding='utf-8')
        self.assertEqual(install_skill.install_one('fixture', self.root, 'fourth', False)['action'], 'conflict')
        install_skill.install_one('fixture', self.root, 'fourth', False, replace_existing=True)
        self.assertEqual(len(list(directory.glob('SKILL.*.bak'))), 3)

    def test_no_host_does_not_create_fallback_directory(self):
        with patch.object(install_skill, 'CANDIDATES', [('missing', self.root/'absent')]):
            self.assertEqual(install_skill.plan_targets(None), ([], False))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_install_conflict_preflight_writes_nothing(self):
        conflict, fresh = self.root/'conflict', self.root/'fresh'
        (conflict/'video-digest').mkdir(parents=True)
        dest = conflict/'video-digest/SKILL.md'
        dest.write_text('user', encoding='utf-8')
        with patch.object(sys, 'argv', ['install_skill.py', '--target', str(fresh), '--target', str(conflict)]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(install_skill.main(), 1)
        self.assertFalse(fresh.exists())
        self.assertEqual(dest.read_text(encoding='utf-8'), 'user')


if __name__ == '__main__':
    unittest.main()
