import importlib.util
import json
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scoped', root / 'gateway/scoped_agent.py')
scoped = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoped)

class ScopedAgentTests(unittest.TestCase):
    def test_isolated_headers_and_unchanged_template(self):
        template = json.loads((root / 'agent/agent.json').read_text())
        original = json.dumps(template)
        a = scoped.build(template, 'https://example.com', 'test-only', 'scope-a')
        b = scoped.build(template, 'https://example.com', 'test-only', 'scope-b')
        self.assertEqual(json.dumps(template), original)
        self.assertEqual(a['system_prompt'], template['system_prompt'])
        for ta, tb in zip(a['tools'], b['tools'], strict=True):
            self.assertEqual(ta['parameters'], tb['parameters'])
            self.assertNotEqual(ta['http']['headers'][-1], tb['http']['headers'][-1])
            self.assertEqual(ta['http']['headers'][0]['value'], 'test-only')
    def test_refuses_missing_credentials(self):
        with self.assertRaises(ValueError):
            scoped.build({}, 'https://example.com', '', 'scope')
    def test_refuses_insecure_destination(self):
        with self.assertRaises(ValueError):
            scoped.build({}, 'http://example.com', 'test-only', 'scope')

if __name__ == '__main__':
    unittest.main()
