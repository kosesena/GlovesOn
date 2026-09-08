"""Pure routing tests; intentionally independent of database-reset fixtures."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('scope', Path(__file__).resolve().parents[1] / 'gateway/session_scope.py')
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class ScopeTests(unittest.TestCase):
    def test_two_sessions_have_distinct_scopes(self):
        a, b = (scope.issue('test-key', now=100) for _ in range(2))
        self.assertNotEqual(scope.verify(a, 'test-key', now=101), scope.verify(b, 'test-key', now=101))

    def test_tampering_and_wrong_key_rejected(self):
        token = scope.issue('test-key', now=100)
        self.assertIsNone(scope.verify(token, 'other-key', now=101))
        self.assertIsNone(scope.verify(token.replace('.520.', '.9999.'), 'test-key', now=101))

    def test_expiration_boundary(self):
        token = scope.issue('test-key', now=100, ttl=10)
        self.assertIsNotNone(scope.verify(token, 'test-key', now=109))
        self.assertIsNone(scope.verify(token, 'test-key', now=110))

    def test_interleaved_events_stay_in_their_session(self):
        a = scope.verify(scope.issue('test-key', now=100), 'test-key', now=101)
        b = scope.verify(scope.issue('test-key', now=100), 'test-key', now=101)
        events = [{'data': {'event_scope': a}}, {'data': {'event_scope': b}}, {'data': {}}]
        self.assertEqual([scope.owns_event(a, e) for e in events], [True, False, False])
        self.assertEqual([scope.owns_event(b, e) for e in events], [False, True, False])

    def test_invalid_input(self):
        for token in ('', 'v1.x.no.signature', 'x' * 1000, None):
            self.assertIsNone(scope.verify(token, 'test-key', now=100))


if __name__ == '__main__':
    unittest.main()
