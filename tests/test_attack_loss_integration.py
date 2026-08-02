import io
import inspect
import math
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

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
        attack.frontier_lambda = 1.0
        attack.max_frontier_tokens = None
        attack.improvement_epsilon = 1e-6
        attack.max_refresh_candidates = 5
        return attack

    def test_invalid_mode_is_rejected_before_model_factory(self):
        with patch("Attack.ModelFactory") as model_factory:
            with self.assertRaisesRegex(ValueError, "Invalid loss_mode"):
                HotFlip(loss_mode="unknown")

        model_factory.assert_not_called()

    def test_frontier_lambda_defaults_to_one(self):
        default = inspect.signature(HotFlip).parameters[
            "frontier_lambda"
        ].default
        self.assertEqual(default, 1.0)

    def test_refresh_acceptance_parameters_are_bounded(self):
        invalid_parameters = (
            ({"improvement_epsilon": -1e-6}, "improvement_epsilon"),
            ({"max_refresh_candidates": 0}, "max_refresh_candidates"),
            ({"max_refresh_candidates": 6}, "max_refresh_candidates"),
        )
        for parameters, message in invalid_parameters:
            with self.subTest(parameters=parameters):
                with patch("Attack.ModelFactory") as model_factory:
                    with self.assertRaisesRegex(ValueError, message):
                        HotFlip(**parameters)
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

            def forward(self, input_ids=None, inputs_embeds=None, labels=None):
                if inputs_embeds is None:
                    inputs_embeds = self.embedding(input_ids)
                position_scale = torch.arange(
                    1,
                    inputs_embeds.shape[1] + 1,
                    dtype=inputs_embeds.dtype,
                    device=inputs_embeds.device,
                ).view(1, -1, 1)
                hidden = torch.cumsum(inputs_embeds * position_scale, dim=1)
                logits = self.output(hidden)
                loss = functional.cross_entropy(
                    logits[:, :-1].reshape(-1, logits.shape[-1]),
                    labels[:, 1:].reshape(-1),
                    ignore_index=-100,
                )
                return (loss,)

        attack = self.make_attack("baseline")
        attack.model = TinyCausalLM()
        attack.embedding_layer = attack.model.embedding
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

    def test_self_conditioned_refreshes_only_best_fixed_rollout_candidate(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.frontier_lambda = 4.0
        attack.hotflip_top_k = 2
        attack.num_restarts = 1
        attack.step = 1
        attack.anchor_window = 1
        attack.trigger_token_length = 1
        attack.trigger_tokens = [ord("A")]
        attack.model = Mock()
        attack._encode_completion_target = Mock(
            return_value=([], [], [ord("x")])
        )
        attack.get_effective_max_len = Mock(return_value=1)
        attack.get_triggers_grad = Mock(return_value=None)
        attack.hotflip_attack = Mock(
            return_value=[[ord("B"), ord("C")]]
        )
        attack._print_stage_summary = Mock()
        attack._validate_stage_zero_generation = Mock(return_value=True)

        refresh_states = []

        def refresh_rollout(**kwargs):
            source_trigger_ids = tuple(int(token) for token in kwargs["trigger_tokens"])
            state = {
                "refresh_id": len(refresh_states) + 1,
                "source_trigger_ids": source_trigger_ids,
            }
            refresh_states.append(state)
            return state

        attack._refresh_self_conditioned_rollouts = Mock(
            side_effect=refresh_rollout
        )
        loss_by_trigger_and_rollout = {
            ((ord("A"),), (ord("A"),)): 10.0,
            ((ord("B"),), (ord("A"),)): 6.0,
            ((ord("C"),), (ord("A"),)): 5.0,
            ((ord("C"),), (ord("C"),)): 4.0,
            ((ord("B"),), (ord("C"),)): 12.0,
        }
        loss_calls = []

        def compute_loss(_, trigger_tokens, __, **kwargs):
            rollout_state = kwargs["rollout_state"]
            trigger_ids = tuple(int(token) for token in trigger_tokens)
            rollout_trigger_ids = rollout_state["source_trigger_ids"]
            loss_calls.append(
                (
                    trigger_ids,
                    rollout_state,
                    kwargs["require_grad"],
                )
            )
            return loss_by_trigger_and_rollout[
                (trigger_ids, rollout_trigger_ids)
            ]

        attack.compute_loss = Mock(side_effect=compute_loss)

        output = io.StringIO()
        with redirect_stdout(output):
            attack.replace_triggers(["target"])

        old_rollout, candidate_rollout = refresh_states
        self.assertEqual(attack.trigger_tokens, [ord("C")])
        self.assertEqual(
            [call.kwargs["trigger_tokens"] for call in
             attack._refresh_self_conditioned_rollouts.call_args_list],
            [[ord("A")], [ord("C")]],
        )
        self.assertEqual(
            [(trigger_ids, rollout) for trigger_ids, rollout, _ in loss_calls[1:3]],
            [
                ((ord("B"),), old_rollout),
                ((ord("C"),), old_rollout),
            ],
        )
        self.assertIn(
            ((ord("C"),), candidate_rollout, False),
            loss_calls,
        )
        self.assertIn("fixed_rollout_candidate_loss=5.0", output.getvalue())
        self.assertIn("refreshed_candidate_loss=4.0", output.getvalue())
        self.assertIn("previous_actual_loss=10.0", output.getvalue())
        self.assertIn("accepted_after_refresh=True", output.getvalue())
        self.assertIn("rollback=False", output.getvalue())
        self.assertIn("old_rollout_id=1", output.getvalue())
        self.assertIn("candidate_rollout_id=2", output.getvalue())
        self.assertIn("active_rollout_id=2", output.getvalue())

    def test_self_conditioned_rejection_tries_next_fixed_ranked_candidate(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.hotflip_top_k = 2
        attack.num_restarts = 1
        attack.step = 1
        attack.anchor_window = 1
        attack.trigger_token_length = 1
        attack.trigger_tokens = [ord("A")]
        attack.model = Mock()
        attack._encode_completion_target = Mock(
            return_value=([], [], [ord("x")])
        )
        attack.get_effective_max_len = Mock(return_value=1)
        attack.get_triggers_grad = Mock(return_value=None)
        attack.hotflip_attack = Mock(
            return_value=[[ord("B"), ord("C")]]
        )
        attack._print_stage_summary = Mock()
        attack._validate_stage_zero_generation = Mock(return_value=True)

        refresh_states = []

        def refresh_rollout(**kwargs):
            state = {
                "refresh_id": len(refresh_states) + 1,
                "source_trigger_ids": tuple(
                    int(token) for token in kwargs["trigger_tokens"]
                ),
            }
            refresh_states.append(state)
            return state

        attack._refresh_self_conditioned_rollouts = Mock(
            side_effect=refresh_rollout
        )
        loss_by_trigger_and_rollout = {
            ((ord("A"),), (ord("A"),)): 10.0,
            ((ord("B"),), (ord("A"),)): 5.0,
            ((ord("C"),), (ord("A"),)): 6.0,
            ((ord("B"),), (ord("B"),)): 12.0,
            ((ord("C"),), (ord("C"),)): 8.0,
            ((ord("B"),), (ord("C"),)): 9.0,
        }
        loss_calls = []

        def compute_loss(_, trigger_tokens, __, **kwargs):
            rollout_state = kwargs["rollout_state"]
            trigger_ids = tuple(int(token) for token in trigger_tokens)
            rollout_trigger_ids = rollout_state["source_trigger_ids"]
            loss_calls.append(
                (trigger_ids, rollout_trigger_ids, kwargs["require_grad"])
            )
            return loss_by_trigger_and_rollout[
                (trigger_ids, rollout_trigger_ids)
            ]

        attack.compute_loss = Mock(side_effect=compute_loss)

        output = io.StringIO()
        with redirect_stdout(output):
            attack.replace_triggers(["target"])

        self.assertEqual(attack.trigger_tokens, [ord("C")])
        self.assertEqual(
            [state["source_trigger_ids"] for state in refresh_states],
            [(ord("A"),), (ord("B"),), (ord("C"),)],
        )
        self.assertEqual(
            [call.kwargs["stage_index"] for call in
             attack._refresh_self_conditioned_rollouts.call_args_list],
            [0, 0, 0],
        )
        self.assertIn(((ord("B"),), (ord("B"),), False), loss_calls)
        self.assertIn(((ord("C"),), (ord("C"),), False), loss_calls)
        self.assertIn(
            "fixed_rollout_candidate_loss=5.0 "
            "refreshed_candidate_loss=12.0 "
            "accepted_after_refresh=False rollback=True "
            "old_rollout_id=1 candidate_rollout_id=2 active_rollout_id=1",
            output.getvalue(),
        )
        self.assertIn(
            "fixed_rollout_candidate_loss=6.0 "
            "refreshed_candidate_loss=8.0 "
            "accepted_after_refresh=True rollback=False "
            "old_rollout_id=1 candidate_rollout_id=3 active_rollout_id=3",
            output.getvalue(),
        )

    def test_rejected_self_conditioned_candidate_restores_trigger_and_rollout(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.trigger_tokens = [ord("A")]
        old_rollout = {
            "refresh_id": 1,
            "source_trigger_ids": (ord("A"),),
        }
        candidate_rollout = {
            "refresh_id": 2,
            "source_trigger_ids": (ord("B"),),
        }
        attack._refresh_self_conditioned_rollouts = Mock(
            return_value=candidate_rollout
        )
        attack.compute_loss = Mock(return_value=9.9999995)

        output = io.StringIO()
        with redirect_stdout(output):
            accepted, actual_loss, returned_rollout = (
                attack._evaluate_self_conditioned_candidate(
                    target_texts=["target"],
                    candidate_trigger_tokens=[ord("B")],
                    stage_index=1,
                    stage_start=1,
                    stage_end=2,
                    fixed_rollout_candidate_loss=5.0,
                    previous_actual_loss=10.0,
                    rollout_state=old_rollout,
                )
            )

        self.assertFalse(accepted)
        self.assertEqual(actual_loss, 10.0)
        self.assertEqual(attack.trigger_tokens, [ord("A")])
        self.assertIs(returned_rollout, old_rollout)
        self.assertIsNot(returned_rollout, candidate_rollout)
        self.assertIs(
            attack.compute_loss.call_args.kwargs["rollout_state"],
            candidate_rollout,
        )
        self.assertIn("fixed_rollout_candidate_loss=5.0", output.getvalue())
        self.assertIn("refreshed_candidate_loss=9.9999995", output.getvalue())
        self.assertIn("previous_actual_loss=10.0", output.getvalue())
        self.assertIn("accepted_after_refresh=False", output.getvalue())
        self.assertIn("rollback=True", output.getvalue())
        self.assertIn("old_rollout_id=1", output.getvalue())
        self.assertIn("candidate_rollout_id=2", output.getvalue())
        self.assertIn("active_rollout_id=1", output.getvalue())

    def test_stage_zero_generation_requires_every_sample_to_match_the_start(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack._encode_completion_target = Mock(
            side_effect=[
                ([10], [], [20, 21], {}),
                ([11], [], [30, 31], {}),
            ]
        )
        attack.get_effective_max_len = Mock(return_value=2)
        attack._greedy_rollout = Mock(
            side_effect=[
                [20, 99],
                [98, 31],
            ]
        )

        output = io.StringIO()
        with redirect_stdout(output):
            accepted = attack._validate_stage_zero_generation(
                target_texts=["first", "second"],
                trigger_tokens=[ord("A")],
                stage_end=2,
            )

        self.assertFalse(accepted)
        self.assertEqual(
            [call.args[1] for call in attack._greedy_rollout.call_args_list],
            [2, 2],
        )
        self.assertIn(
            "sample_common_prefix_token_counts=[1, 0]",
            output.getvalue(),
        )
        self.assertIn("later_frontier_allowed=False", output.getvalue())

    def test_self_conditioned_final_chunk_uses_explicit_stage_start(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.anchor_window = 64
        target_ids = list(range(200))
        attack._encode_completion_target = Mock(
            return_value=(
                [400, 401],
                [],
                target_ids,
                {
                    "prefix_length": 0,
                    "trigger_start": 0,
                    "trigger_end": 1,
                    "target_start": 2,
                    "input_length": 202,
                },
            )
        )
        attack.get_effective_max_len = Mock(return_value=200)
        rollout_state = {
            "refresh_id": 1,
            "samples": [
                {
                    "stage_index": 3,
                    "source": "greedy_generation",
                    "frontier_start": 192,
                    "frontier_end": 200,
                    "generated_prefix_ids": [500] * 192,
                }
            ],
        }

        components = attack._self_conditioned_components(
            index=0,
            stage_index=3,
            stage_start=192,
            stage_end=200,
            target_text="target",
            triggers=[ord("A")],
            rollout_state=rollout_state,
        )

        anchor, frontier = components
        self.assertEqual(anchor["token_count"], 64)
        self.assertEqual(frontier["metadata"]["loss_start"], 192)
        self.assertEqual(frontier["metadata"]["loss_end"], 200)
        self.assertEqual(frontier["token_count"], 8)
        self.assertEqual(
            frontier["input_ids"][0, 2:194].tolist(),
            [500] * 192,
        )
        self.assertEqual(
            frontier["labels"][0, -8:].tolist(),
            target_ids[192:200],
        )

    def test_failed_stage_zero_generation_skips_later_frontier(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.hotflip_top_k = 1
        attack.num_restarts = 1
        attack.anchor_window = 1
        attack.frontier_window = 1
        attack.trigger_token_length = 1
        attack.trigger_tokens = [ord("A")]
        attack.model = Mock()
        attack._encode_completion_target = Mock(
            return_value=([], [], [ord("x"), ord("y")])
        )
        attack.get_effective_max_len = Mock(return_value=2)
        attack.compute_loss = Mock(return_value=10.0)
        attack.get_triggers_grad = Mock(return_value=None)
        attack.hotflip_attack = Mock(return_value=[[]])
        attack._print_stage_summary = Mock()
        attack._validate_stage_zero_generation = Mock(return_value=False)
        attack._refresh_self_conditioned_rollouts = Mock(
            return_value={
                "refresh_id": 1,
                "source_trigger_ids": (ord("A"),),
            }
        )

        output = io.StringIO()
        with redirect_stdout(output):
            attack.replace_triggers(["target"])

        self.assertEqual(
            [call.kwargs["stage_index"] for call in
             attack._refresh_self_conditioned_rollouts.call_args_list],
            [0],
        )
        self.assertEqual(
            [
                (call.kwargs["stage_start"], call.kwargs["stage_end"])
                for call in attack._refresh_self_conditioned_rollouts.call_args_list
            ],
            [(0, 1)],
        )
        self.assertIn(
            "stage0_generation_rejected later_frontier_skipped=True",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
