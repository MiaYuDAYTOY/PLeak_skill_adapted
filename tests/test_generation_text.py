"""Regression checks for text fidelity without loading model weights."""
import ast
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import Mock

from util.generation_text import decode_generation, GENERATION_DECODE_POLICY
from test_overlap_metrics import sampler_evaluator


class GenerationTextTests(unittest.TestCase):
    def test_decode_preserves_markdown_spaces_repetition_and_final_line(self):
        text = ('# 中文标题\n\nSave as .docx or text-based .pdf\n'
                '| 数量 | 12 |\n| --- | --- |\n'
                '```python\n    value = 1\n```\nTRIGGER\nTRIGGER\n最后一行')
        tokenizer = Mock()

        def decode(ids, *, skip_special_tokens, clean_up_tokenization_spaces):
            self.assertEqual(ids, [10, 20, 99])
            # A cleanup-sensitive decoder exposes the original regression.
            content = text.replace(' .', '.') if clean_up_tokenization_spaces else text
            return content if skip_special_tokens else content + '<EOS>'

        tokenizer.decode.side_effect = decode
        self.assertEqual(decode_generation(tokenizer, [10, 20, 99]), text)
        self.assertEqual(decode_generation(tokenizer, [10, 20, 99], skip_special_tokens=False), text + '<EOS>')

    def test_decode_preserves_empty_output(self):
        tokenizer = Mock()
        tokenizer.decode.return_value = ''
        self.assertEqual(decode_generation(tokenizer, []), '')

    def test_preserved_spaces_restore_complete_match_without_changing_tail_rule(self):
        target = '# 中文\nSave as .docx or text-based .pdf\n最后一行'
        evaluator = sampler_evaluator()
        with contextlib.redirect_stdout(io.StringIO()):
            old = evaluator.evaluate_skill_leakage([dict(context=target, generation=target.replace(' .', '.'))])
            exact = evaluator.evaluate_skill_leakage([dict(context=target, generation=target)])
            extra = evaluator.evaluate_skill_leakage([dict(context=target, generation=target + '\nTRIGGER\nTRIGGER')])
        self.assertEqual(old['full_skill_leak_count'], 0)
        self.assertEqual(exact['full_skill_leak_count'], 1)
        self.assertEqual(exact['exact_markdown_match_rate'], 1)
        self.assertEqual(exact['mean_body_rougeL_recall'], 1)
        self.assertEqual(extra['full_skill_leak_count'], 1)
        self.assertEqual(extra['exact_markdown_match_rate'], 0)
        self.assertLess(extra['mean_body_rougeL_precision'], 1)

    def test_runtime_metadata_identifies_the_decoding_policy(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'ModelFactory.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ModelFactory')
        cls.body = [n for n in cls.body if getattr(n, 'name', None) in ['get_runtime_config', 'get_generation_kwargs']]
        ns = dict(GENERATION_DECODE_POLICY=GENERATION_DECODE_POLICY)
        exec(compile(ast.Module(body=[cls], type_ignores=[]), 'ModelFactory.py', 'exec'), ns)
        factory = ns['ModelFactory']()
        factory.MODEL_CONF = {'qwen3': dict(alias='local/Qwen3', load_in_4bit=False)}
        config = factory.get_runtime_config('qwen3')
        self.assertEqual(config['generation_decode_policy'], GENERATION_DECODE_POLICY)


if __name__ == '__main__':
    unittest.main()
