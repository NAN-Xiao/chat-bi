import importlib.util
import unittest
from pathlib import Path


class AutoContinueTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name('codex_auto_continue.py')
        self.assertTrue(path.exists(), 'Auto-continue script has not been implemented')
        spec = importlib.util.spec_from_file_location('codex_auto_continue', path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def thread(self, status='failed', error=None, runtime='idle'):
        return {'status': {'type': runtime}, 'turns': [
            {'id': 'turn-1', 'status': status, 'error': error or {'message': 'unexpected status 429 Too Many Requests'}}
        ]}

    def test_only_terminal_http_failures_trigger(self):
        self.assertEqual(self.module.candidate(self.thread(), {429, 503}), ('turn-1', 429))
        error = {'codexErrorInfo': {'httpConnectionFailed': {'httpStatusCode': 503}}}
        self.assertEqual(self.module.candidate(self.thread(error=error), {429, 503}), ('turn-1', 503))
        for status in ('inProgress', 'completed', 'interrupted'):
            self.assertIsNone(self.module.candidate(self.thread(status=status), {429, 503}))
        self.assertIsNone(self.module.candidate(self.thread(runtime='active'), {429, 503}))

    def test_numbers_and_generic_errors_do_not_trigger(self):
        for message in ('elapsed_ms=429 tokens=503', 'rate limit reached', 'user requested 429 or 503'):
            self.assertIsNone(self.module.candidate(self.thread(error={'message': message}), {429, 503}))

    def test_old_failure_does_not_override_latest_turn(self):
        thread = self.thread()
        thread['turns'].append({'id': 'turn-2', 'status': 'completed', 'error': None})
        self.assertIsNone(self.module.candidate(thread, {429, 503}))

    def test_deduplication_and_retry_limit_survive_reload(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            state = self.module.State(path, 'thread-1')
            self.assertTrue(state.allowed('turn-1', 3))
            state.reserve('turn-1')
            restored = self.module.State(path, 'thread-1')
            self.assertFalse(restored.allowed('turn-1', 3))
            self.assertTrue(restored.allowed('turn-2', 3))
            restored.reserve('turn-2')
            restored.reserve('turn-3')
            self.assertFalse(restored.allowed('turn-4', 3))
            self.assertEqual(json.loads(path.read_text())['attempts'], 3)

    def test_actual_error_formats(self):
        for message in ('HTTP/2 503 Service Unavailable', 'status_code=429', '429 Too Many Requests'):
            result = self.module.candidate(self.thread(error={'message': message}), {429, 503})
            self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
