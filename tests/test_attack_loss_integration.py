import math
import unittest
from unittest.mock import patch

try:
    import torch
    import torch.nn.functional as functional
except ModuleNotFoundError:
    torch = None

if torch is not None:
    from Attack import HotFlip
    from util.template import TextTemplate


class CharacterTokenizer:
    bos_token_id = 300

    def encode(self, text, add_special_tokens=True):
        token_ids = [ord(character) for character in text]
        if add_special_tokens:
            return [self.bos_token_id] + token_ids
        return token_ids

    def decode(self, token_ids, clean_up_tokenization_spaces=False):
        return "".join(chr(int(token_id)) for token_id in token_ids)


@unittest.skipIf(torch is None, "Torch is only installed in the pleak environment")
class AttackLossIntegrationTests(unittest.TestCase):
    def make_attack(self, loss_mode):
        attack = HotFlip.__new__(HotFlip)
        attack.device = torch.device("cpu")
        attack.target_model = "fake"
        attack.template = TextTemplate(prefix_1="", prefix_2="")
        attack.tokenizer = CharacterTokenizer()
        attack.user_prefix = ""
        attack.loss_mode = loss_mode
        attack.max_loss_tokens = 3
        attack.anchor_len = 1
        attack.frontier_window = 1
        attack.max_frontier_tokens = None
        return attack

    def test_invalid_mode_is_rejected_before_model_factory(self):
        with patch("Attack.ModelFactory") as model_factory:
            with self.assertRaisesRegex(ValueError, "Invalid loss_mode"):
                HotFlip(loss_mode="unknown")

        model_factory.assert_not_called()

    def test_make_target_keeps_context_but_masks_anchor_middle(self):
        attack = self.make_attack("anchor_frontier")
        trigger_ids = [ord("X"), ord("Y")]
        input_ids, labels = attack.make_target(
            index=0,
            stage_end=4,
            target_text="abcd",
            triggers=trigger_ids,
        )
        prompt_ids, _, target_ids = attack._encode_completion_target(
            "abcd",
            trigger_ids,
        )
        target_labels = labels[0, len(prompt_ids):].tolist()

        self.assertEqual(input_ids.shape, labels.shape)
        self.assertEqual(
            input_ids[0, len(prompt_ids):].tolist(),
            target_ids,
        )
        self.assertEqual(
            target_labels,
            [target_ids[0], -100, -100, target_ids[3]],
        )
        self.assertTrue(all(label == -100 for label in labels[0, :len(prompt_ids)]))

    def test_make_target_clamps_a_short_sample_to_its_own_length(self):
        attack = self.make_attack("baseline")
        trigger_ids = [ord("X"), ord("Y")]
        input_ids, labels = attack.make_target(
            index=0,
            stage_end=10,
            target_text="abcd",
            triggers=trigger_ids,
        )
        prompt_ids, _, target_ids = attack._encode_completion_target(
            "abcd",
            trigger_ids,
        )

        self.assertEqual(input_ids.shape, labels.shape)
        self.assertEqual(input_ids.shape[1], len(prompt_ids) + len(target_ids))
        self.assertEqual(
            labels[0, len(prompt_ids):].tolist(),
            target_ids,
        )

    def test_compute_loss_backward_produces_trigger_gradient(self):
        class TinyCausalLM(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.embedding = torch.nn.Embedding(512, 8)
                self.output = torch.nn.Linear(8, 512)

            def forward(self, input_ids, labels):
                hidden = torch.cumsum(self.embedding(input_ids), dim=1)
                logits = self.output(hidden)
                loss = functional.cross_entropy(
                    logits[:, :-1].reshape(-1, logits.shape[-1]),
                    labels[:, 1:].reshape(-1),
                    ignore_index=-100,
                )
                return (loss,)

        attack = self.make_attack("baseline")
        attack.model = TinyCausalLM()
        attack.vocab_size = 512
        attack.trigger_tokens = [ord("X"), ord("Y")]

        loss = attack.compute_loss(
            target_texts=["abcd"],
            trigger_tokens=attack.trigger_tokens,
            stage_end=4,
            require_grad=True,
        )
        trigger_grad = attack.get_triggers_grad()

        self.assertTrue(math.isfinite(loss))
        self.assertEqual(tuple(trigger_grad.shape), (2, 8))
        self.assertGreater(trigger_grad.abs().sum().item(), 0.0)


if __name__ == "__main__":
    unittest.main()
