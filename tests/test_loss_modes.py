import unittest

from util.loss_modes import (
    build_target_labels,
    get_effective_max_len,
    get_loss_regions,
    iter_stage_ends,
    validate_loss_mode,
)


class LossModeTests(unittest.TestCase):
    def assert_valid_labels(self, labels, stage_end):
        self.assertEqual(len(labels), stage_end)
        self.assertTrue(any(label != -100 for label in labels))

    def test_baseline_labels_every_target_token(self):
        labels = build_target_labels(
            "baseline",
            list(range(20)),
            stage_end=10,
        )

        self.assertEqual(labels, list(range(10)))
        self.assert_valid_labels(labels, 10)

    def test_baseline_does_not_apply_either_cap(self):
        self.assertEqual(
            get_effective_max_len(
                "baseline",
                target_len=3000,
                max_loss_tokens=300,
                max_frontier_tokens=1000,
            ),
            3000,
        )

    def test_prefix_cap_stage_ends_without_duplicate_cap(self):
        effective_max_len = get_effective_max_len(
            "prefix_cap",
            target_len=20,
            max_loss_tokens=12,
        )

        self.assertEqual(
            list(iter_stage_ends(5, 5, effective_max_len)),
            [5, 10, 12],
        )
        self.assertEqual(
            build_target_labels(
                "prefix_cap",
                list(range(20)),
                stage_end=12,
            ),
            list(range(12)),
        )

    def test_exact_multiple_has_no_duplicate_final_stage(self):
        self.assertEqual(
            list(iter_stage_ends(100, 100, 300)),
            [100, 200, 300],
        )

    def test_init_step_can_differ_from_step(self):
        self.assertEqual(
            list(iter_stage_ends(50, 100, 380)),
            [50, 150, 250, 350, 380],
        )

    def test_short_target_has_one_stage(self):
        self.assertEqual(
            list(iter_stage_ends(100, 100, 20)),
            [20],
        )

    def test_prefix_cap_larger_than_target_uses_target_length(self):
        effective_max_len = get_effective_max_len(
            "prefix_cap",
            target_len=20,
            max_loss_tokens=300,
        )

        self.assertEqual(effective_max_len, 20)
        self.assertEqual(
            list(iter_stage_ends(100, 100, effective_max_len)),
            [20],
        )

    def test_anchor_frontier_respects_optional_position_cap(self):
        capped_length = get_effective_max_len(
            "anchor_frontier",
            target_len=3000,
            max_frontier_tokens=1000,
        )
        self.assertEqual(capped_length, 1000)
        self.assertEqual(
            list(iter_stage_ends(100, 100, capped_length))[-2:],
            [900, 1000],
        )
        self.assertEqual(
            get_effective_max_len(
                "anchor_frontier",
                target_len=3000,
                max_frontier_tokens=5000,
            ),
            3000,
        )
        self.assertEqual(
            get_effective_max_len(
                "anchor_frontier",
                target_len=3000,
                max_frontier_tokens=None,
            ),
            3000,
        )

    def test_stage_steps_must_be_positive(self):
        for init_step, step in ((0, 100), (100, 0)):
            with self.subTest(init_step=init_step, step=step):
                with self.assertRaises(ValueError):
                    list(iter_stage_ends(init_step, step, 300))

    def test_anchor_frontier_expected_regions(self):
        target_ids = list(range(20))
        labels = build_target_labels(
            "anchor_frontier",
            target_ids,
            stage_end=15,
            anchor_len=4,
            frontier_window=3,
        )

        self.assertEqual(labels[:4], target_ids[:4])
        self.assertEqual(labels[4:12], [-100] * 8)
        self.assertEqual(labels[12:15], target_ids[12:15])
        self.assertEqual(
            get_loss_regions("anchor_frontier", 15, 4, 3),
            ((0, 4), (12, 15)),
        )
        self.assert_valid_labels(labels, 15)

    def test_stage_shorter_than_anchor(self):
        labels = build_target_labels(
            "anchor_frontier",
            list(range(20)),
            stage_end=3,
            anchor_len=4,
            frontier_window=3,
        )

        self.assertEqual(labels, [0, 1, 2])
        self.assert_valid_labels(labels, 3)

    def test_anchor_and_frontier_overlap_without_double_counting(self):
        labels = build_target_labels(
            "anchor_frontier",
            list(range(20)),
            stage_end=6,
            anchor_len=4,
            frontier_window=4,
        )

        self.assertEqual(labels, list(range(6)))
        self.assertEqual(
            get_loss_regions("anchor_frontier", 6, 4, 4),
            ((0, 4), (4, 6)),
        )
        self.assert_valid_labels(labels, 6)

    def test_frontier_window_larger_than_stage(self):
        labels = build_target_labels(
            "anchor_frontier",
            list(range(20)),
            stage_end=5,
            anchor_len=2,
            frontier_window=10,
        )

        self.assertEqual(labels, list(range(5)))
        self.assert_valid_labels(labels, 5)

    def test_multiple_samples_use_global_maximum(self):
        target_lengths = [3, 12, 7]
        effective_max_len = max(
            get_effective_max_len(
                "prefix_cap",
                target_len=target_len,
                max_loss_tokens=10,
            )
            for target_len in target_lengths
        )

        self.assertEqual(effective_max_len, 10)
        self.assertEqual(
            list(iter_stage_ends(5, 5, effective_max_len)),
            [5, 10],
        )

    def test_target_label_and_full_input_shapes_match(self):
        prompt_ids = [90, 91, 92]
        target_ids = list(range(20))

        for loss_mode in ("baseline", "prefix_cap", "anchor_frontier"):
            with self.subTest(loss_mode=loss_mode):
                target_labels = build_target_labels(
                    loss_mode,
                    target_ids,
                    stage_end=15,
                    anchor_len=4,
                    frontier_window=3,
                )
                input_ids = prompt_ids + target_ids[:15]
                labels = [-100] * len(prompt_ids) + target_labels

                self.assertEqual(len(input_ids), len(labels))
                self.assert_valid_labels(target_labels, 15)

    def test_invalid_loss_mode_raises_clear_value_error(self):
        with self.assertRaisesRegex(ValueError, "Invalid loss_mode"):
            validate_loss_mode("unknown")

        with self.assertRaisesRegex(ValueError, "Invalid loss_mode"):
            validate_loss_mode([])

    def test_anchor_frontier_requires_an_active_region(self):
        with self.assertRaisesRegex(ValueError, "requires anchor_len"):
            build_target_labels(
                "anchor_frontier",
                list(range(5)),
                stage_end=5,
                anchor_len=0,
                frontier_window=0,
            )

    def test_stage_end_must_be_a_positive_integer(self):
        for stage_end in (0, "1"):
            with self.subTest(stage_end=stage_end):
                with self.assertRaisesRegex(ValueError, "stage_end"):
                    build_target_labels(
                        "baseline",
                        list(range(5)),
                        stage_end=stage_end,
                    )

    def test_stage_end_cannot_exceed_target(self):
        with self.assertRaisesRegex(ValueError, "exceeds target length"):
            build_target_labels(
                "baseline",
                list(range(5)),
                stage_end=6,
            )


if __name__ == "__main__":
    unittest.main()
