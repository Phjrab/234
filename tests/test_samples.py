"""Published beginner samples are synthetic and match the actual parser."""
import json
from pathlib import Path
import unittest
from workspace import Workspace

ROOT = Path(__file__).resolve().parent.parent


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace(':memory:')

    def tearDown(self):
        self.workspace.close()

    def check_sample(self, name, kind):
        text = (ROOT / 'docs' / 'samples' / name).read_text()
        report = self.workspace.validate_dataset({'name': 'Synthetic beginner sample', 'kind': kind,
                                                  'text': text, 'synthetic': True})
        self.assertTrue(report['valid'], report['errors'])
        self.assertEqual(report['count'], 3)
        self.assertEqual(report['errors'], [])
        self.assertTrue(all(isinstance(json.loads(line), dict) for line in text.splitlines()))

    def test_chat_sample(self):
        self.check_sample('llm-chat.jsonl', 'LLM')

    def test_instruction_sample(self):
        self.check_sample('llm-instruction.jsonl', 'LLM')

    def test_vlm_sample(self):
        self.check_sample('vlm-image-text.jsonl', 'VLM')

    def test_csv_json_array_and_binary_are_not_jsonl(self):
        for text in ['prompt,response\nHi,Hello', '[{"instruction":"Hi","output":"Hello"}]', 'PAR1\x00\x01']:
            with self.subTest(text=repr(text)):
                report = self.workspace.validate_dataset({'kind': 'LLM', 'text': text})
                self.assertFalse(report['valid'])
                self.assertTrue(report['errors'])


if __name__ == '__main__':
    unittest.main()
