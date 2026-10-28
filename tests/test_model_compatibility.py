"""Offline regression checks with a tiny, random Qwen3; no weight downloads."""

import contextlib
import io
import os
import unittest
from unittest.mock import patch

import numpy as np
import torch
from tokenizers import Tokenizer, models, pre_tokenizers, decoders, processors
from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast, Qwen3Config

from Attack import HotFlip
from ModelFactory import ModelFactory
from Sampler import Sampler
from util.trigger_tokens import allowed_trigger_token_ids


def byte_tokenizer(add_bos=False):
    # Byte-level BPE with a newline merge reproduces the boundary failure that
    # the previous Llama-only initialization did not handle.
    vocabulary = {token: i for i, token in enumerate(sorted(pre_tokenizers.ByteLevel.alphabet()))}
    for token in ['ĊĊ', '<|endoftext|>', '[BOS]']:
        vocabulary[token] = len(vocabulary)
    core = Tokenizer(models.BPE(vocab=vocabulary, merges=[('Ċ', 'Ċ')]))
    core.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    core.decoder = decoders.ByteLevel()
    if add_bos:
        core.post_processor = processors.TemplateProcessing(
            single='[BOS] $A', special_tokens=[('[BOS]', vocabulary['[BOS]'])],
        )
    return PreTrainedTokenizerFast(tokenizer_object=core, bos_token='[BOS]',
                                  eos_token='<|endoftext|>', pad_token='<|endoftext|>',
                                  model_input_names=['input_ids', 'attention_mask'])


def tiny_qwen(tokenizer):
    config = Qwen3Config(
        vocab_size=len(tokenizer) + 7, hidden_size=32, intermediate_size=64,
        num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1,
        head_dim=16, max_position_embeddings=256,
        eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id,
        attention_dropout=0.0, sliding_window=None, use_sliding_window=False,
    )
    return AutoModelForCausalLM.from_config(config).to(dtype=torch.bfloat16)


def make_attack(tokenizer, *, checkpointing=False, trigger='abc'):
    model = tiny_qwen(tokenizer)
    with patch.object(ModelFactory, 'get_model', return_value=model), \
            patch.object(ModelFactory, 'get_tokenizer', return_value=tokenizer):
        return HotFlip(shadow_model='qwen3', trigger_token_length=len(trigger),
                       init_triggers=trigger, prefix_length=3,
                       gradient_checkpointing=checkpointing)


class ModelCompatibilityTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(1)
        np.random.seed(1)

    def test_base_load_is_bf16_without_bitsandbytes(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch('ModelFactory.AutoModelForCausalLM.from_pretrained') as loader, \
                patch('ModelFactory.BitsAndBytesConfig') as quantization:
            factory = ModelFactory()
            factory.get_model('qwen3')
            self.assertEqual(loader.call_args.args[0], 'Qwen/Qwen3-0.6B-Base')
            self.assertEqual(loader.call_args.kwargs['torch_dtype'], torch.bfloat16)
            self.assertNotIn('quantization_config', loader.call_args.kwargs)
            self.assertNotIn('load_in_4bit', loader.call_args.kwargs)
            quantization.assert_not_called()
            self.assertFalse(loader.return_value.config.use_cache)
            factory.get_model('qwen3', compute_dtype=torch.float16)
            self.assertEqual(loader.call_args.kwargs['torch_dtype'], torch.float16)
            with self.assertRaises(ValueError):
                factory.get_model('qwen3', compute_dtype=torch.int8)

    def test_local_path_and_legacy_quantization(self):
        with patch.dict(os.environ, {'PLEAK_QWEN3_MODEL_PATH': '/tmp/qwen-test'}), \
                patch('ModelFactory.AutoModelForCausalLM.from_pretrained') as loader, \
                patch('ModelFactory.BitsAndBytesConfig') as quantization:
            factory = ModelFactory()
            factory.get_model('qwen3')
            self.assertEqual(loader.call_args.args[0], '/tmp/qwen-test')
            self.assertTrue(loader.call_args.kwargs['local_files_only'])
            factory.get_model('llama')
            quantization.assert_called_once_with(load_in_4bit=True,
                                                  bnb_4bit_compute_dtype=torch.bfloat16)
            self.assertIs(loader.call_args.kwargs['quantization_config'], quantization.return_value)
            self.assertEqual(factory.get_runtime_config('qwen3')['quantization'], 'none')
            self.assertEqual(factory.get_runtime_config('llama')['quantization'], '4bit')

    def test_trigger_content_does_not_drop_first_token_with_or_without_bos(self):
        for add_bos in [False, True]:
            with self.subTest(add_bos=add_bos):
                tokenizer = byte_tokenizer(add_bos)
                attack = make_attack(tokenizer)
                self.assertEqual(attack.trigger_tokens.tolist(),
                                 tokenizer.encode('abc', add_special_tokens=False))
                self.assertEqual(attack.decode_triggers(), 'abc')
                inputs, labels, start, end = attack.make_target(0, 0, 'Body\n', attack.trigger_tokens)
                expected_prompt = tokenizer.encode('Body\nabc\n')
                self.assertEqual(inputs[0, :len(expected_prompt)].tolist(), expected_prompt)
                self.assertEqual(inputs[0, start:end].tolist(), attack.trigger_tokens.tolist())
                self.assertTrue(labels[0, :len(expected_prompt)].eq(-100).all())
                self.assertEqual(labels[0, len(expected_prompt):].tolist(),
                                 tokenizer.encode('Bod', add_special_tokens=False))

    def test_candidate_search_excludes_special_punctuation_and_unused_rows(self):
        tokenizer = byte_tokenizer()
        attack = make_attack(tokenizer, trigger='a')
        allowed = set(allowed_trigger_token_ids(tokenizer, attack.embedding_weight.shape[0]))
        self.assertFalse(allowed.intersection(tokenizer.all_special_ids))
        punctuation = tokenizer.encode('!', add_special_tokens=False)[0]
        self.assertNotIn(punctuation, allowed)
        self.assertTrue(allowed.issubset(set(tokenizer.get_vocab().values())))
        # Give forbidden rows the highest scores: they must never win top-k.
        weights = torch.full((len(tokenizer) + 7, 4), -1000.)
        weights[list(allowed)] = 0
        attack.embedding_weight = weights
        ids = attack.hotflip_attack(torch.ones(1, 4), num_candidates=999)
        self.assertEqual(ids.shape, (1, len(allowed)))
        self.assertEqual(set(ids[0].tolist()), allowed)
        ids = attack.hotflip_attack(torch.ones(1, 4), num_candidates=1)
        self.assertEqual(ids.shape, (1, 1))
        for invalid in [tokenizer.eos_token_id, punctuation, len(tokenizer) + 2]:
            with self.assertRaises(ValueError):
                attack._decode_trigger_tokens([invalid])

    def test_trailing_newline_merge_is_rejected_before_candidate_evaluation(self):
        tokenizer = byte_tokenizer()
        attack = make_attack(tokenizer)
        ids = tokenizer.encode('a\n', add_special_tokens=False)
        self.assertIn(ids[-1], attack.allowed_trigger_id_set)
        with self.assertRaisesRegex(ValueError, 'trailing newline'):
            attack._decode_trigger_tokens(ids)
        np.random.seed(5)
        for _ in range(10):
            ids = attack.init_triggers(12)
            text = attack._decode_trigger_tokens(ids)
            self.assertTrue(text)
            attack.make_target(0, 0, 'Body\n', ids)

    def test_qwen_bf16_backward_with_and_without_checkpointing(self):
        tokenizer = byte_tokenizer()
        for checkpointing in [False, True]:
            with self.subTest(checkpointing=checkpointing):
                attack = make_attack(tokenizer, checkpointing=checkpointing)
                loss, gradient = attack.compute_loss(['Body\n'], attack.trigger_tokens, 0, require_grad=True)
                self.assertTrue(np.isfinite(loss))
                self.assertEqual(tuple(gradient.shape), (3, 32))
                self.assertTrue(torch.isfinite(gradient).all())
                self.assertGreater(gradient.float().norm().item(), 0)
                self.assertTrue(all(parameter.grad is None for parameter in attack.model.parameters()))
                self.assertTrue(all(not parameter.requires_grad for parameter in attack.model.parameters()))

    def test_sampler_keeps_identical_plain_prompt_and_base_eos(self):
        tokenizer = byte_tokenizer()
        attack = make_attack(tokenizer)
        model = attack.model
        with patch.object(ModelFactory, 'get_model', return_value=model), \
                patch.object(ModelFactory, 'get_tokenizer', return_value=tokenizer):
            sampler = Sampler(target_model='qwen3')

        def finish_with_eos(**kwargs):
            return torch.cat([kwargs['input_ids'], torch.tensor([[tokenizer.eos_token_id]])], dim=1)

        with patch.object(model, 'generate', side_effect=finish_with_eos) as generate, \
                contextlib.redirect_stdout(io.StringIO()):
            rows = sampler.sample_sequence(['Body\n'], attack.decode_triggers(),
                                           trigger_token_ids=attack.trigger_tokens.tolist())
        kwargs = generate.call_args.kwargs
        self.assertEqual(kwargs['input_ids'][0].tolist(), tokenizer.encode('Body\nabc\n'))
        self.assertEqual(kwargs['eos_token_id'], tokenizer.eos_token_id)
        self.assertEqual(kwargs['max_new_tokens'], len(tokenizer.encode('Body\nabc\n')) + 50)
        self.assertNotIn('max_length', kwargs)
        self.assertEqual((kwargs['do_sample'], kwargs['num_beams'], kwargs['top_k']), (True, 3, 50))
        self.assertEqual((kwargs['temperature'], kwargs['top_p']), (0.9, 0.6))
        self.assertTrue(kwargs['use_cache'])
        self.assertTrue(rows[0]['ended_with_eos'])
        self.assertEqual(rows[0]['status'], 'ok')
        with self.assertRaisesRegex(ValueError, 'token IDs'):
            sampler.sample_sequence(['Body\n'], 'abc', trigger_token_ids=[0, 0, 0])

    def test_sampler_generation_overrides_checkpoint_length_defaults(self):
        tokenizer = byte_tokenizer()
        for inherited_limit in [2, 2048]:
            with self.subTest(inherited_limit=inherited_limit):
                model = tiny_qwen(tokenizer).eval()
                model.generation_config.max_new_tokens = inherited_limit
                # Force generation to reach the budget instead of drawing EOS.
                model.generation_config.suppress_tokens = [tokenizer.eos_token_id]
                with patch.object(ModelFactory, 'get_model', return_value=model), \
                        patch.object(ModelFactory, 'get_tokenizer', return_value=tokenizer):
                    sampler = Sampler(target_model='qwen3')
                with contextlib.redirect_stdout(io.StringIO()), \
                        patch('transformers.generation.utils.logger.warning') as warning:
                    rows = sampler.sample_sequence(['Body\n', 'Longer body\n'], 'abc', length=3)
                warning.assert_not_called()
                for row in rows:
                    self.assertEqual(row['status'], 'ok', row['error'])
                    self.assertEqual(row['generated_token_count'], row['prompt_token_count'] + 3)
                    self.assertFalse(row['ended_with_eos'])
                self.assertEqual(model.generation_config.max_new_tokens, inherited_limit)

    def test_supervised_logits_match_original_loss_and_gradients(self):
        tokenizer = byte_tokenizer()
        body = '# A longer skill\n' + 'Read the document carefully.\n' * 3
        for dtype in [torch.float32, torch.bfloat16]:
            for checkpointing in [False, True]:
                attack = make_attack(tokenizer, checkpointing=checkpointing)
                attack.model.to(dtype=dtype)
                for prefix in [1, 8, 16, 32]:
                    with self.subTest(dtype=dtype, checkpointing=checkpointing, prefix=prefix):
                        attack.prefix_length = prefix
                        inputs, labels, left, right = attack.make_target(
                            0, 0, body, attack.trigger_tokens,
                        )
                        embeddings = attack.model.get_input_embeddings()(inputs).detach()
                        original_input = embeddings.clone().requires_grad_(True)
                        with attack._loss_model_mode(True):
                            original_loss = attack.model(
                                inputs_embeds=original_input, labels=labels,
                                use_cache=False, return_dict=True,
                            ).loss
                            original_loss.backward()
                            original_gradient = original_input.grad.detach().clone()

                        compact_input = embeddings.clone().requires_grad_(True)
                        projected_lengths, context_lengths = [], []
                        head_hook = attack.model.lm_head.register_forward_pre_hook(
                            lambda module, args: projected_lengths.append(args[0].shape[1]),
                        )
                        context_hook = attack.model.model.register_forward_pre_hook(
                            lambda module, args, kwargs: context_lengths.append(kwargs['inputs_embeds'].shape[1]),
                            with_kwargs=True,
                        )
                        try:
                            with attack._loss_model_mode(True):
                                compact_loss = attack._forward_loss({'inputs_embeds': compact_input}, labels)
                                compact_loss.backward()
                                compact_gradient = compact_input.grad.detach().clone()
                        finally:
                            head_hook.remove()
                            context_hook.remove()
                        # The full context still reaches the transformer, while
                        # the expensive vocabulary projection sees only P rows.
                        self.assertEqual(context_lengths, [inputs.shape[1]])
                        self.assertEqual(projected_lengths, [prefix])
                        tolerance = dict(rtol=1e-5, atol=1e-6) if dtype == torch.float32 else dict(rtol=0.02, atol=2e-4)
                        torch.testing.assert_close(compact_loss, original_loss, **tolerance)
                        torch.testing.assert_close(compact_gradient, original_gradient, **tolerance)
                        self.assertGreater(compact_gradient[:, left:right].float().norm().item(), 0)

                        with attack._loss_model_mode(False), torch.no_grad():
                            original_score = attack.model(input_ids=inputs, labels=labels,
                                                          use_cache=False, return_dict=True).loss
                            compact_score = attack._forward_loss({'input_ids': inputs}, labels)
                        torch.testing.assert_close(compact_score, original_score, **tolerance)

    def test_supervised_logits_respect_causal_shift_and_sparse_batch_labels(self):
        tokenizer = byte_tokenizer()
        attack = make_attack(tokenizer)
        inputs = torch.tensor([tokenizer.encode('abcdef'), tokenizer.encode('ghijkl')])
        labels = inputs.clone()
        labels[0, [1, 3, 4]] = -100
        labels[1, [1, 2, 5]] = -100
        with torch.no_grad():
            original = attack.model(input_ids=inputs, labels=labels,
                                    use_cache=False, return_dict=True).loss
            compact = attack._forward_loss({'input_ids': inputs}, labels)
        torch.testing.assert_close(compact, original, rtol=0.02, atol=2e-4)
        labels[:, 1:] = -100
        with self.assertRaisesRegex(ValueError, 'No supervised tokens'):
            attack._forward_loss({'input_ids': inputs}, labels)

    def test_real_qwen_generation_with_cache_and_beam_sampling(self):
        tokenizer = byte_tokenizer()
        model = tiny_qwen(tokenizer).eval()
        inputs = tokenizer('Body\nabc\n', return_tensors='pt')
        kwargs = ModelFactory().get_generation_kwargs('qwen3')
        with torch.no_grad():
            generated = model.generate(**inputs, **kwargs, max_new_tokens=3,
                                       eos_token_id=tokenizer.eos_token_id,
                                       pad_token_id=tokenizer.pad_token_id)
        self.assertEqual(generated.shape[0], 1)
        self.assertGreater(generated.shape[1], inputs.input_ids.shape[1])


if __name__ == '__main__':
    unittest.main()
