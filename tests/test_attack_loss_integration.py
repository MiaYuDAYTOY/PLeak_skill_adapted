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
        attack.stage0_greedy_candidates = 5
        attack.preserve_anchor_utility = True
        attack.anchor_loss_tolerance = 0.05
        attack.anchor_mean_prefix_tolerance = 0.0
        attack._last_stage0_validation_state = None
        return attack

    @staticmethod
    def make_stage0_generation_state(trigger_tokens, common_prefix_counts):
        return {
            "source_trigger_ids": tuple(int(token) for token in trigger_tokens),
            "common_prefix_counts": list(common_prefix_counts),
        }

    @staticmethod
    def make_anchor_state(trigger_tokens, common_prefix_counts, anchor_loss):
        return {
            "trigger_tokens": [int(token) for token in trigger_tokens],
            "common_prefix_counts": list(common_prefix_counts),
            "min_common_prefix": min(common_prefix_counts),
            "mean_common_prefix": (
                sum(common_prefix_counts) / len(common_prefix_counts)
            ),
            "anchor_loss": anchor_loss,
        }

    def run_stage1_guarded_candidate(
        self,
        current_common_prefix,
        current_anchor_loss,
        candidate_common_prefix,
        candidate_anchor_loss,
        preserve_anchor_utility=True,
    ):
        attack = self.make_attack("self_conditioned_frontier")
        attack.preserve_anchor_utility = preserve_anchor_utility
        attack.trigger_tokens = [ord("A")]
        current_anchor_state = self.make_anchor_state(
            [ord("A")],
            current_common_prefix,
            current_anchor_loss,
        )
        baseline = self.make_anchor_state(
            [ord("A")],
            current_common_prefix,
            current_anchor_loss,
        )
        candidate_anchor_state = self.make_anchor_state(
            [ord("B")],
            candidate_common_prefix,
            candidate_anchor_loss,
        )
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

        def compute_loss(*args, **kwargs):
            if kwargs.get("return_diagnostics"):
                return 5.0, {
                    "anchor_loss": candidate_anchor_loss,
                    "frontier_loss": 4.0,
                    "total_loss": 5.0,
                }
            return 5.0

        attack.compute_loss = Mock(side_effect=compute_loss)
        attack._measure_anchor_utility = Mock(
            return_value=candidate_anchor_state
        )

        output = io.StringIO()
        with redirect_stdout(output):
            accepted, active_loss, returned_rollout = (
                attack._evaluate_self_conditioned_candidate(
                    target_texts=["one", "two", "three"],
                    candidate_trigger_tokens=[ord("B")],
                    stage_index=1,
                    stage_start=1,
                    stage_end=2,
                    fixed_rollout_candidate_loss=4.0,
                    previous_actual_loss=10.0,
                    rollout_state=old_rollout,
                    stage0_anchor_baseline=baseline,
                    current_anchor_state=current_anchor_state,
                    candidate_rank=1,
                )
            )
        return (
            attack,
            accepted,
            active_loss,
            returned_rollout,
            old_rollout,
            candidate_rollout,
            output.getvalue(),
        )

    def run_stage0_candidate_selection(
        self,
        current_common_prefix,
        current_loss,
        candidate_common_prefix,
        candidate_loss,
    ):
        attack = self.make_attack("self_conditioned_frontier")
        current_trigger = [ord("A")]
        candidate_trigger = [ord("B")]
        current_state = self.make_stage0_generation_state(
            current_trigger,
            current_common_prefix,
        )
        candidate_state = self.make_stage0_generation_state(
            candidate_trigger,
            candidate_common_prefix,
        )
        attack._measure_stage0_generation = Mock(
            return_value=candidate_state
        )
        fixed_candidates = [
            {
                "loss": candidate_loss,
                "trigger_tokens": candidate_trigger,
                "changed_trigger_position": 0,
                "candidate_token": ord("B"),
            }
        ]

        output = io.StringIO()
        with redirect_stdout(output):
            selected = attack._select_stage0_greedy_candidate(
                target_texts=["one", "two", "three"],
                stage_end=1,
                current_trigger_tokens=current_trigger,
                current_anchor_loss=current_loss,
                current_generation_state=current_state,
                fixed_candidates=fixed_candidates,
            )
        return selected, output.getvalue()

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

    def test_stage0_greedy_candidates_defaults_to_five(self):
        default = inspect.signature(HotFlip).parameters[
            "stage0_greedy_candidates"
        ].default
        self.assertEqual(default, 5)

    def test_anchor_utility_guard_defaults(self):
        parameters = inspect.signature(HotFlip).parameters
        self.assertTrue(parameters["preserve_anchor_utility"].default)
        self.assertEqual(parameters["anchor_loss_tolerance"].default, 0.05)
        self.assertEqual(
            parameters["anchor_mean_prefix_tolerance"].default,
            0.0,
        )

    def test_refresh_acceptance_parameters_are_bounded(self):
        invalid_parameters = (
            ({"improvement_epsilon": -1e-6}, "improvement_epsilon"),
            ({"max_refresh_candidates": 0}, "max_refresh_candidates"),
            ({"max_refresh_candidates": 6}, "max_refresh_candidates"),
            ({"stage0_greedy_candidates": -1}, "stage0_greedy_candidates"),
            ({"preserve_anchor_utility": "yes"}, "preserve_anchor_utility"),
            ({"anchor_loss_tolerance": -0.01}, "anchor_loss_tolerance"),
            (
                {"anchor_mean_prefix_tolerance": -0.01},
                "anchor_mean_prefix_tolerance",
            ),
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

    def test_stage0_greedy_zero_restores_original_anchor_loss_selection(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.frontier_lambda = 4.0
        attack.stage0_greedy_candidates = 0
        attack.preserve_anchor_utility = False
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
        attack._measure_stage0_generation = Mock()

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
        attack._measure_stage0_generation.assert_not_called()

    def test_self_conditioned_rejection_tries_next_fixed_ranked_candidate(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.stage0_greedy_candidates = 0
        attack.preserve_anchor_utility = False
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
        attack.preserve_anchor_utility = False
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

    def test_stage1_rejects_lower_frontier_loss_when_anchor_min_regresses(self):
        (
            attack,
            accepted,
            active_loss,
            returned_rollout,
            old_rollout,
            _,
            output,
        ) = self.run_stage1_guarded_candidate(
            current_common_prefix=[5, 4, 6],
            current_anchor_loss=0.10,
            candidate_common_prefix=[3, 4, 6],
            candidate_anchor_loss=0.09,
        )

        self.assertFalse(accepted)
        self.assertEqual(active_loss, 10.0)
        self.assertEqual(attack.trigger_tokens, [ord("A")])
        self.assertIs(returned_rollout, old_rollout)
        self.assertIn("anchor_min_prefix_regressed", output)
        self.assertNotIn("candidate_accepted_with_anchor_preserved=True", output)

    def test_stage1_accepts_three_percent_anchor_loss_increase(self):
        (
            attack,
            accepted,
            active_loss,
            returned_rollout,
            _,
            candidate_rollout,
            output,
        ) = self.run_stage1_guarded_candidate(
            current_common_prefix=[5, 4, 6],
            current_anchor_loss=0.10,
            candidate_common_prefix=[5, 4, 6],
            candidate_anchor_loss=0.103,
        )

        self.assertTrue(accepted)
        self.assertEqual(active_loss, 5.0)
        self.assertEqual(attack.trigger_tokens, [ord("B")])
        self.assertIs(returned_rollout, candidate_rollout)
        self.assertIn("anchor_preserved=True", output)
        self.assertIn("candidate_accepted_with_anchor_preserved=True", output)

    def test_stage1_rejects_eight_percent_anchor_loss_increase(self):
        (
            attack,
            accepted,
            _,
            returned_rollout,
            old_rollout,
            _,
            output,
        ) = self.run_stage1_guarded_candidate(
            current_common_prefix=[5, 4, 6],
            current_anchor_loss=0.10,
            candidate_common_prefix=[5, 4, 6],
            candidate_anchor_loss=0.108,
        )

        self.assertFalse(accepted)
        self.assertEqual(attack.trigger_tokens, [ord("A")])
        self.assertIs(returned_rollout, old_rollout)
        self.assertIn("anchor_loss_exceeded_current_tolerance", output)
        self.assertIn("anchor_loss_exceeded_baseline_tolerance", output)

    def test_stage1_accepts_higher_anchor_mean_and_lower_frontier_loss(self):
        (
            attack,
            accepted,
            _,
            returned_rollout,
            _,
            candidate_rollout,
            output,
        ) = self.run_stage1_guarded_candidate(
            current_common_prefix=[5, 4, 6],
            current_anchor_loss=0.10,
            candidate_common_prefix=[5, 5, 6],
            candidate_anchor_loss=0.103,
        )

        self.assertTrue(accepted)
        self.assertEqual(attack.trigger_tokens, [ord("B")])
        self.assertIs(returned_rollout, candidate_rollout)
        self.assertIn("anchor_preserved=True", output)

    def test_stage_anchor_validation_failure_rolls_back_entire_stage(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.trigger_tokens = [ord("B")]
        checkpoint_anchor = self.make_anchor_state(
            [ord("A")],
            [5, 4, 6],
            0.10,
        )
        baseline = self.make_anchor_state(
            [ord("A")],
            [5, 4, 6],
            0.10,
        )
        after_anchor = self.make_anchor_state(
            [ord("B")],
            [3, 4, 6],
            0.09,
        )
        checkpoint_rollout = {
            "refresh_id": 1,
            "source_trigger_ids": (ord("A"),),
        }
        checkpoint_diagnostics = {
            "anchor_loss": 0.10,
            "frontier_loss": 9.0,
            "total_loss": 10.0,
        }
        checkpoint = {
            "trigger_tokens": [ord("A")],
            "anchor_state": checkpoint_anchor,
            "rollout_state": checkpoint_rollout,
            "stage_loss": 10.0,
            "loss_diagnostics": checkpoint_diagnostics,
        }
        attack._measure_anchor_utility = Mock(return_value=after_anchor)

        output = io.StringIO()
        with redirect_stdout(output):
            result = attack._validate_stage_anchor_and_maybe_rollback(
                target_texts=["one", "two", "three"],
                stage_index=1,
                stage_start_checkpoint=checkpoint,
                stage0_anchor_baseline=baseline,
                rollout_state={"refresh_id": 2},
                stage_loss=5.0,
                loss_diagnostics={"total_loss": 5.0},
            )

        self.assertTrue(result["rollback"])
        self.assertEqual(attack.trigger_tokens, [ord("A")])
        self.assertEqual(result["rollout_state"], checkpoint_rollout)
        self.assertEqual(result["anchor_state"], checkpoint_anchor)
        self.assertEqual(result["stage_loss"], 10.0)
        self.assertIn("stage_anchor_validation_failed=True", output.getvalue())
        self.assertIn("stage_rollback=True", output.getvalue())

    def test_no_preserve_anchor_utility_keeps_original_stage1_acceptance(self):
        (
            attack,
            accepted,
            active_loss,
            returned_rollout,
            _,
            candidate_rollout,
            output,
        ) = self.run_stage1_guarded_candidate(
            current_common_prefix=[5, 4, 6],
            current_anchor_loss=0.10,
            candidate_common_prefix=[0, 0, 0],
            candidate_anchor_loss=1.0,
            preserve_anchor_utility=False,
        )

        self.assertTrue(accepted)
        self.assertEqual(active_loss, 5.0)
        self.assertEqual(attack.trigger_tokens, [ord("B")])
        self.assertIs(returned_rollout, candidate_rollout)
        attack._measure_anchor_utility.assert_not_called()
        self.assertNotIn("candidate_anchor_guard", output)

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

    def test_stage0_accepts_higher_min_prefix_despite_higher_loss(self):
        selected, output = self.run_stage0_candidate_selection(
            current_common_prefix=[0, 0, 1],
            current_loss=0.05,
            candidate_common_prefix=[1, 1, 1],
            candidate_loss=0.10,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["trigger_tokens"], [ord("B")])
        self.assertIn("common_prefix_improved=True", output)
        self.assertIn("loss_tiebreak_used=False", output)

    def test_stage0_rejects_lower_min_prefix_despite_lower_loss(self):
        selected, output = self.run_stage0_candidate_selection(
            current_common_prefix=[1, 1, 1],
            current_loss=0.10,
            candidate_common_prefix=[0, 5, 5],
            candidate_loss=0.01,
        )

        self.assertIsNone(selected)
        self.assertIn("accepted=False", output)
        self.assertIn("stage0_no_greedy_improvement=True", output)

    def test_stage0_uses_lower_loss_when_prefix_scores_are_equal(self):
        selected, output = self.run_stage0_candidate_selection(
            current_common_prefix=[1, 1, 1],
            current_loss=0.10,
            candidate_common_prefix=[1, 1, 1],
            candidate_loss=0.08,
        )

        self.assertIsNotNone(selected)
        self.assertIn("common_prefix_improved=False", output)
        self.assertIn("loss_tiebreak_used=True", output)

    def test_stage0_accepts_higher_mean_when_min_prefix_is_equal(self):
        selected, output = self.run_stage0_candidate_selection(
            current_common_prefix=[1, 2, 1],
            current_loss=0.10,
            candidate_common_prefix=[1, 3, 2],
            candidate_loss=0.12,
        )

        self.assertIsNotNone(selected)
        self.assertIn("common_prefix_improved=True", output)
        self.assertIn("loss_tiebreak_used=False", output)

    def test_stage0_greedy_generation_is_limited_to_lowest_loss_k(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.stage0_greedy_candidates = 2
        current_trigger = [ord("A")]
        current_state = self.make_stage0_generation_state(
            current_trigger,
            [0, 0, 0],
        )
        fixed_candidates = [
            {
                "loss": loss,
                "trigger_tokens": [token],
                "changed_trigger_position": 0,
                "candidate_token": token,
            }
            for token, loss in (
                (ord("B"), 0.30),
                (ord("C"), 0.10),
                (ord("D"), 0.20),
            )
        ]
        measured_trigger_ids = []

        def measure_generation(**kwargs):
            trigger_ids = tuple(int(token) for token in kwargs["trigger_tokens"])
            measured_trigger_ids.append(trigger_ids)
            return self.make_stage0_generation_state(
                trigger_ids,
                [0, 0, 0],
            )

        attack._measure_stage0_generation = Mock(
            side_effect=measure_generation
        )

        with redirect_stdout(io.StringIO()):
            selected = attack._select_stage0_greedy_candidate(
                target_texts=["one", "two", "three"],
                stage_end=1,
                current_trigger_tokens=current_trigger,
                current_anchor_loss=0.40,
                current_generation_state=current_state,
                fixed_candidates=fixed_candidates,
            )

        self.assertEqual(
            measured_trigger_ids,
            [(ord("C"),), (ord("D"),)],
        )
        self.assertEqual(selected["trigger_tokens"], [ord("C")])

    def test_stage0_accepted_generation_cache_becomes_next_current_score(self):
        attack = self.make_attack("self_conditioned_frontier")
        attack.hotflip_top_k = 1
        attack.num_restarts = 1
        attack.anchor_window = 1
        attack.frontier_window = 1
        attack.trigger_token_length = 1
        attack.trigger_tokens = [ord("A")]
        attack.model = Mock()
        attack._encode_completion_target = Mock(
            return_value=([], [], [ord("x")])
        )
        attack.get_effective_max_len = Mock(return_value=1)
        attack.get_triggers_grad = Mock(return_value=None)
        attack.hotflip_attack = Mock(
            side_effect=[[[ord("B")]], [[]]]
        )
        attack._print_stage_summary = Mock()
        attack._validate_stage_zero_generation = Mock(return_value=True)
        attack._refresh_self_conditioned_rollouts = Mock(
            return_value={
                "refresh_id": 1,
                "source_trigger_ids": (ord("A"),),
            }
        )
        attack.compute_loss = Mock(
            side_effect=lambda _, trigger_tokens, __, **kwargs: (
                0.05 if list(trigger_tokens) == [ord("A")] else 0.10
            )
        )

        measured_trigger_ids = []

        def measure_generation(**kwargs):
            trigger_ids = tuple(int(token) for token in kwargs["trigger_tokens"])
            measured_trigger_ids.append(trigger_ids)
            counts = [0, 0, 1] if trigger_ids == (ord("A"),) else [1, 1, 1]
            return self.make_stage0_generation_state(trigger_ids, counts)

        attack._measure_stage0_generation = Mock(
            side_effect=measure_generation
        )
        attack._measure_anchor_utility = Mock(
            return_value=self.make_anchor_state(
                [ord("B")],
                [1, 1, 1],
                0.10,
            )
        )

        output = io.StringIO()
        with redirect_stdout(output):
            attack.replace_triggers(["one", "two", "three"])

        self.assertEqual(attack.trigger_tokens, [ord("B")])
        self.assertEqual(
            measured_trigger_ids,
            [(ord("A"),), (ord("B"),)],
        )
        self.assertEqual(
            output.getvalue().count("stage0_current_generation_score"),
            2,
        )
        self.assertIn(
            "current_common_prefix_counts=[1, 1, 1]",
            output.getvalue(),
        )
        self.assertIn("stage0_generation_cache_updated=True", output.getvalue())
        self.assertIn("anchor_baseline_saved", output.getvalue())
        self.assertIn("selected_trigger_kind=best_safe_trigger", output.getvalue())

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
        attack.stage0_greedy_candidates = 0
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
