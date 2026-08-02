import torch
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
import re
from util.template import TextTemplate
from torchmetrics import ExtendedEditDistance, CatMetric
from util.data import Harmful
from util.loss_modes import (
    VALID_LOSS_MODES,
    build_target_labels,
    get_effective_max_len as calculate_effective_max_len,
    get_loss_regions,
    get_separate_loss_regions,
    iter_stage_ends,
    iter_stage_ranges,
    validate_loss_parameters,
)
from ModelFactory import ModelFactory

class HotFlip:
    def __init__(
        self,
        trigger_token_length=6,
        shadow_model='gpt2',
        step=100,
        template=None,
        init_triggers='',
        init_step=None,
        loss_mode="baseline",
        max_loss_tokens=300,
        anchor_len=128,
        anchor_window=None,
        frontier_window=128,
        frontier_lambda=1.0,
        max_frontier_tokens=None,
        hotflip_top_k=30,
        num_restarts=1,
        improvement_epsilon=1e-6,
        max_refresh_candidates=5,
    ):
        if anchor_window is not None:
            anchor_len = anchor_window
        validate_loss_parameters(
            loss_mode=loss_mode,
            max_loss_tokens=max_loss_tokens,
            anchor_len=anchor_len,
            frontier_window=frontier_window,
            max_frontier_tokens=max_frontier_tokens,
            frontier_lambda=frontier_lambda,
        )
        if (
            isinstance(hotflip_top_k, bool)
            or not isinstance(hotflip_top_k, int)
            or hotflip_top_k <= 0
        ):
            raise ValueError("hotflip_top_k must be a positive integer")
        if (
            isinstance(num_restarts, bool)
            or not isinstance(num_restarts, int)
            or num_restarts <= 0
        ):
            raise ValueError("num_restarts must be a positive integer")
        if (
            isinstance(improvement_epsilon, bool)
            or not isinstance(improvement_epsilon, (int, float))
            or not np.isfinite(improvement_epsilon)
            or improvement_epsilon < 0
        ):
            raise ValueError(
                "improvement_epsilon must be a finite non-negative number"
            )
        if (
            isinstance(max_refresh_candidates, bool)
            or not isinstance(max_refresh_candidates, int)
            or max_refresh_candidates <= 0
            or max_refresh_candidates > 5
        ):
            raise ValueError(
                "max_refresh_candidates must be an integer between 1 and 5"
            )

        self.loss_mode = loss_mode
        self.max_loss_tokens = max_loss_tokens
        self.anchor_len = anchor_len
        self.anchor_window = anchor_len
        self.frontier_window = frontier_window
        self.frontier_lambda = float(frontier_lambda)
        self.max_frontier_tokens = max_frontier_tokens
        self.hotflip_top_k = hotflip_top_k
        self.num_restarts = num_restarts
        self.improvement_epsilon = float(improvement_epsilon)
        self.max_refresh_candidates = max_refresh_candidates
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.target_model = shadow_model
        self.template = TextTemplate(prefix_1='') if template is None else template
        modelFactory = ModelFactory()
        self.model = modelFactory.get_model(shadow_model)
        self.tokenizer = modelFactory.get_tokenizer(shadow_model)
        self.vocab_size = modelFactory.get_vocab_size(shadow_model)
        self.embedding_layer = self.get_embedding_layer()
        self.embedding_weight = self.get_embedding_weight()
        self.step = step
        self.init_step = init_step if init_step is not None else self.step
        self.user_prefix = ''
        self.trigger_token_length = trigger_token_length
        self.trigger_tokens = self.init_triggers(trigger_token_length, init_triggers, self.user_prefix)
        self._last_trigger_grads = None
        self._last_trigger_grad = None
        self._last_anchor_grads = None
        self._last_frontier_grads = None
        self._last_loss_diagnostics = None
        self._rollout_refresh_count = 0

    def init_triggers(self, trigger_token_length, init_trigger='', user_prefix=''):
        init_tokens = self.tokenizer.encode(init_trigger)
        len_init = len(init_tokens)
        len_user = len(self.tokenizer.encode(user_prefix))
        if self.target_model == 'opt' or 'llama' in self.target_model or self.target_model=='vicuna':
            init_tokens = init_tokens[1:]
            len_init -= 1
            len_user -= 1
        if len_init >= trigger_token_length:
            triggers = np.asarray(init_tokens[:trigger_token_length])
            self._decode_trigger_tokens(triggers)
            return triggers
        triggers = np.empty(trigger_token_length-len_user, dtype=int)
        random_start = min(len_init, len(triggers))
        triggers[:random_start] = init_tokens[:random_start]

        # Only keep IDs that survive the exact decode/concatenate/encode path
        # used later by Sampler.
        for _ in range(1000):
            for idx in range(random_start, len(triggers)):
                t = np.random.randint(self.vocab_size)
                while re.search(
                    r"[^a-zA-Z0-9s\s]",
                    self.tokenizer.decode([int(t)]),
                ):
                    t = np.random.randint(self.vocab_size)
                triggers[idx] = int(t)

            try:
                self._decode_trigger_tokens(triggers)
                return triggers
            except ValueError:
                continue

        raise RuntimeError(
            "无法初始化可在训练和测试间稳定编码的 trigger"
        )

    def get_embedding_layer(self):
        get_input_embeddings = getattr(self.model, "get_input_embeddings", None)
        if callable(get_input_embeddings):
            module = get_input_embeddings()
            if (
                isinstance(module, torch.nn.Embedding)
                and module.weight.shape[0] == self.vocab_size
            ):
                return module

        for module in self.model.modules():
            if not isinstance(module, torch.nn.Embedding): continue
            if module.weight.shape[0] != self.vocab_size: continue
            return module

        raise RuntimeError("Cannot find the token embedding layer.")

    def get_embedding_weight(self):
        layer = getattr(self, "embedding_layer", None)
        if layer is None:
            layer = self.get_embedding_layer()
            self.embedding_layer = layer
        return layer.weight.detach()

    def get_triggers_grad(self):
        if self._last_trigger_grads is None or self._last_trigger_grad is None:
            raise RuntimeError(
                "Trigger gradients are unavailable; call compute_loss(..., "
                "require_grad=True) first."
            )
        return self._last_trigger_grad

    def _decode_trigger_tokens(self, trigger_tokens):
        """Decode IDs without changing them at the prompt boundary."""
        trigger_ids = [int(token_id) for token_id in trigger_tokens]
        context = "\n" + self.template.prefix_trigger + self.user_prefix
        context_ids = self.tokenizer.encode(
            context,
            add_special_tokens=False,
        )

        decoded_context = self.tokenizer.decode(
            context_ids,
            clean_up_tokenization_spaces=False,
        )
        decoded_with_trigger = self.tokenizer.decode(
            context_ids + trigger_ids,
            clean_up_tokenization_spaces=False,
        )
        if not decoded_with_trigger.startswith(decoded_context):
            raise ValueError(
                "无法在 trigger 上下文中稳定解码 token IDs"
            )

        trigger_text = decoded_with_trigger[len(decoded_context):]
        roundtrip_ids = self.tokenizer.encode(
            context + trigger_text,
            add_special_tokens=False,
        )
        if roundtrip_ids != context_ids + trigger_ids:
            raise ValueError(
                "trigger token IDs 在文本往返编码后发生变化"
            )

        return trigger_text

    def decode_triggers(self):
        trigger_text = self._decode_trigger_tokens(self.trigger_tokens)
        return self.user_prefix + trigger_text

    def _encode_completion_target(
        self,
        target_text,
        triggers,
        return_metadata=False,
    ):
        trigger_text = self.user_prefix + self._decode_trigger_tokens(triggers)
        prompt_text = target_text + self.template.format_trigger(trigger_text)
        full_text = prompt_text + target_text

        prompt_ids = self.tokenizer.encode(
            prompt_text,
            add_special_tokens=True,
        )
        full_ids = self.tokenizer.encode(
            full_text,
            add_special_tokens=True,
        )
        if full_ids[:len(prompt_ids)] != prompt_ids:
            raise ValueError(
                "目标文本拼接后改变了 prompt 的 token 边界"
            )

        before_trigger_text = (
            target_text
            + self.template.prefix_trigger
            + self.user_prefix
        )
        before_trigger_ids = self.tokenizer.encode(
            before_trigger_text,
            add_special_tokens=True,
        )
        trigger_ids = [int(token_id) for token_id in triggers]
        trigger_start = len(before_trigger_ids)
        actual_trigger_ids = prompt_ids[
            trigger_start:trigger_start + len(trigger_ids)
        ]
        if actual_trigger_ids != trigger_ids:
            raise ValueError(
                "训练输入中的 trigger token IDs 与待优化 IDs 不一致"
            )

        encoded_target = full_ids[len(prompt_ids):]
        trigger_end = trigger_start + len(trigger_ids)
        if trigger_end - trigger_start != len(trigger_ids):
            raise AssertionError("trigger slice length does not match trigger length")

        metadata = {
            "prefix_length": trigger_start,
            "trigger_start": trigger_start,
            "trigger_end": trigger_end,
            "target_start": len(prompt_ids),
            "input_length": len(full_ids),
        }
        if return_metadata:
            return prompt_ids, full_ids, encoded_target, metadata
        return prompt_ids, full_ids, encoded_target

    def get_effective_max_len(self, target_len):
        return calculate_effective_max_len(
            loss_mode=self.loss_mode,
            target_len=target_len,
            max_loss_tokens=self.max_loss_tokens,
            max_frontier_tokens=self.max_frontier_tokens,
        )

    def make_target(
        self,
        index,
        stage_end,
        target_text,
        triggers,
        return_metadata=False,
    ):
        prompt_ids, full_ids, encoded_target, metadata = self._encode_completion_target(
            target_text,
            triggers,
            return_metadata=True,
        )
        len_non_label = len(prompt_ids)
        local_stage_end = min(
            stage_end,
            self.get_effective_max_len(len(encoded_target)),
        )
        target_labels = build_target_labels(
            loss_mode=self.loss_mode,
            target_ids=encoded_target,
            stage_end=local_stage_end,
            anchor_len=self.anchor_len,
            frontier_window=self.frontier_window,
        )
        encoded_label = [-100] * len_non_label + target_labels

        encoded_text = full_ids[:len(encoded_label)]
        label = torch.tensor([encoded_label], device=self.device, dtype=torch.long)
        lm_input= torch.tensor([encoded_text], device=self.device, dtype=torch.long)
        metadata = dict(metadata)
        metadata["input_length"] = len(encoded_text)
        metadata["target_start"] = len_non_label
        if return_metadata:
            return lm_input, label, metadata
        return lm_input, label

    def make_target_chat(self, index, idx_loss, target_text, triggers):
        target = [
                {"role": "system", "content": target_text},
                {"role": "user", "content": self.tokenizer.decode(triggers)},
                {"role": "assistant", "content": target_text},
            ]
        target = self.tokenizer.apply_chat_template(target)
        non_label = [
                {"role": "system", "content": target_text},
                {"role": "user", "content": self.tokenizer.decode(triggers)},
            ]
        non_label = self.tokenizer.apply_chat_template(non_label)
        label = [-100]*len(non_label) + target[len(non_label):]

        label = torch.tensor([label], device=self.device, dtype=torch.long)
        lm_input= torch.tensor([target], device=self.device, dtype=torch.long)
        return lm_input, label

    def make_adaptive_chat(self, index, idx_loss, target_text, triggers):
        text = target_text.split('\n')[::-1]
        text = " ".join(text)
        target = [
                {"role": "system", "content": target_text},
                {"role": "user", "content": self.tokenizer.decode(triggers)},
                {"role": "assistant", "content": text},
            ]
        target = self.tokenizer.apply_chat_template(target)
        non_label = [
                {"role": "system", "content": target_text},
                {"role": "user", "content": self.tokenizer.decode(triggers)},
            ]
        non_label = self.tokenizer.apply_chat_template(non_label)
        # lm_input = target[:len(non_label)] + target[len(non_label):][::-1]
        label = [-100]*len(non_label) + target[len(non_label):]

        label = torch.tensor([label], device=self.device, dtype=torch.long)
        lm_input= torch.tensor([target], device=self.device, dtype=torch.long)
        return lm_input, label

    @staticmethod
    def _make_region_labels(input_length, target_start, target_ids, start, end):
        if not 0 <= start < end <= len(target_ids):
            raise AssertionError(
                f"invalid loss region [{start}, {end}) for "
                f"{len(target_ids)} target tokens"
            )
        labels = [-100] * input_length
        labels[target_start + start:target_start + end] = target_ids[start:end]
        if sum(label != -100 for label in labels) != end - start:
            raise AssertionError("labels must cover exactly the requested region")
        return labels

    def _teacher_forced_components(
        self,
        index,
        stage_end,
        target_text,
        triggers,
    ):
        prompt_ids, full_ids, target_ids, metadata = self._encode_completion_target(
            target_text,
            triggers,
            return_metadata=True,
        )
        local_stage_end = min(
            stage_end,
            self.get_effective_max_len(len(target_ids)),
        )
        input_ids = full_ids[:len(prompt_ids) + local_stage_end]
        input_tensor = torch.tensor(
            [input_ids],
            device=self.device,
            dtype=torch.long,
        )
        base_metadata = dict(metadata)
        base_metadata.update(
            {
                "sample_index": index,
                "target_start": len(prompt_ids),
                "input_length": len(input_ids),
                "teacher_forcing": True,
            }
        )

        if self.loss_mode != "anchor_frontier":
            labels = [-100] * len(prompt_ids) + target_ids[:local_stage_end]
            return [
                {
                    "name": "full",
                    "weight": 1.0,
                    "input_ids": input_tensor,
                    "labels": torch.tensor(
                        [labels],
                        device=self.device,
                        dtype=torch.long,
                    ),
                    "metadata": base_metadata,
                    "token_count": local_stage_end,
                }
            ]

        anchor, frontier = get_separate_loss_regions(
            loss_mode=self.loss_mode,
            stage_end=local_stage_end,
            anchor_len=self.anchor_window,
            frontier_window=self.frontier_window,
        )
        components = []
        for name, weight, region in (
            ("anchor", 1.0, anchor),
            ("frontier", self.frontier_lambda, frontier),
        ):
            start, end = region
            if start == end:
                continue
            component_metadata = dict(base_metadata)
            component_metadata.update(
                {
                    "component": name,
                    "loss_start": start,
                    "loss_end": end,
                }
            )
            components.append(
                {
                    "name": name,
                    "weight": weight,
                    "input_ids": input_tensor,
                    "labels": torch.tensor(
                        [self._make_region_labels(
                            input_length=len(input_ids),
                            target_start=len(prompt_ids),
                            target_ids=target_ids[:local_stage_end],
                            start=start,
                            end=end,
                        )],
                        device=self.device,
                        dtype=torch.long,
                    ),
                    "metadata": component_metadata,
                    "token_count": end - start,
                }
            )
        return components

    def _self_conditioned_components(
        self,
        index,
        stage_index,
        stage_start,
        stage_end,
        target_text,
        triggers,
        rollout_state,
    ):
        if rollout_state is None:
            raise AssertionError(
                "self_conditioned_frontier requires a fixed rollout state"
            )
        rollout = rollout_state["samples"][index]
        if rollout["stage_index"] != stage_index:
            raise AssertionError("rollout stage does not match loss stage")
        if rollout["source"] != "greedy_generation":
            raise AssertionError("frontier context must come from greedy generation")

        prompt_ids, _, target_ids, metadata = self._encode_completion_target(
            target_text,
            triggers,
            return_metadata=True,
        )
        local_stage_end = min(
            stage_end,
            self.get_effective_max_len(len(target_ids)),
        )
        local_stage_start = min(stage_start, local_stage_end)
        anchor_end = min(self.anchor_window, local_stage_end)
        components = []

        anchor_input = prompt_ids + target_ids[:anchor_end]
        anchor_metadata = dict(metadata)
        anchor_metadata.update(
            {
                "sample_index": index,
                "component": "anchor",
                "target_start": len(prompt_ids),
                "input_length": len(anchor_input),
                "loss_start": 0,
                "loss_end": anchor_end,
                "teacher_forcing": True,
            }
        )
        components.append(
            {
                "name": "anchor",
                "weight": 1.0,
                "input_ids": torch.tensor(
                    [anchor_input], device=self.device, dtype=torch.long
                ),
                "labels": torch.tensor(
                    [[-100] * len(prompt_ids) + target_ids[:anchor_end]],
                    device=self.device,
                    dtype=torch.long,
                ),
                "metadata": anchor_metadata,
                "token_count": anchor_end,
            }
        )

        if stage_index == 0:
            return components

        frontier_start = local_stage_start
        frontier_end = local_stage_end
        if frontier_start == frontier_end:
            return components
        generated_prefix = list(rollout["generated_prefix_ids"])
        if len(generated_prefix) != frontier_start:
            raise AssertionError(
                "generated prefix length does not match frontier start: "
                f"{len(generated_prefix)} != {frontier_start}"
            )
        if rollout["frontier_start"] != frontier_start:
            raise AssertionError("rollout frontier start changed during comparison")
        if rollout["frontier_end"] != frontier_end:
            raise AssertionError("rollout frontier end changed during comparison")

        gold_frontier = target_ids[frontier_start:frontier_end]
        frontier_context = prompt_ids + generated_prefix
        frontier_input = frontier_context + gold_frontier
        frontier_target_start = len(frontier_context)
        frontier_labels = [-100] * frontier_target_start + gold_frontier
        if frontier_input[:len(prompt_ids)] != prompt_ids:
            raise AssertionError("self-conditioned prompt was modified")
        if frontier_input[len(prompt_ids):frontier_target_start] != generated_prefix:
            raise AssertionError("gold prefix was used instead of generated prefix")
        if sum(label != -100 for label in frontier_labels) != len(gold_frontier):
            raise AssertionError("frontier labels must cover only the frontier")

        frontier_metadata = dict(metadata)
        frontier_metadata.update(
            {
                "sample_index": index,
                "component": "frontier",
                "target_start": frontier_target_start,
                "input_length": len(frontier_input),
                "loss_start": frontier_start,
                "loss_end": frontier_end,
                "teacher_forcing": False,
                "rollout_refresh_id": rollout_state["refresh_id"],
            }
        )
        components.append(
            {
                "name": "frontier",
                "weight": self.frontier_lambda,
                "input_ids": torch.tensor(
                    [frontier_input], device=self.device, dtype=torch.long
                ),
                "labels": torch.tensor(
                    [frontier_labels], device=self.device, dtype=torch.long
                ),
                "metadata": frontier_metadata,
                "token_count": len(gold_frontier),
            }
        )
        return components

    def _forward_component(self, component, require_grad):
        input_ids = component["input_ids"]
        labels = component["labels"]
        metadata = component["metadata"]
        trigger_start = metadata["trigger_start"]
        trigger_end = metadata["trigger_end"]
        trigger_len = len(self.trigger_tokens)

        if input_ids.shape != labels.shape:
            raise AssertionError("input IDs and labels must have identical shapes")
        if trigger_end - trigger_start != trigger_len:
            raise AssertionError("trigger slice length does not match trigger length")

        if require_grad:
            inputs_embeds = self.embedding_layer(input_ids).detach()
            inputs_embeds.requires_grad_(True)
            inputs_embeds.retain_grad()
            output = self.model(inputs_embeds=inputs_embeds, labels=labels)
            loss = output[0]
            loss.backward()
            if inputs_embeds.grad is None:
                raise AssertionError("input embedding gradient is None")
            trigger_grad = inputs_embeds.grad[
                :, trigger_start:trigger_end, :
            ].detach()
            expected_shape = (
                input_ids.shape[0],
                trigger_len,
                inputs_embeds.shape[-1],
            )
            if tuple(trigger_grad.shape) != expected_shape:
                raise AssertionError(
                    f"unexpected trigger gradient shape {tuple(trigger_grad.shape)}; "
                    f"expected {expected_shape}"
                )
            if not torch.isfinite(trigger_grad).all():
                raise AssertionError("trigger gradient contains NaN or Inf")
            return loss, trigger_grad

        output = self.model(input_ids=input_ids, labels=labels)
        return output[0], None

    def _log_gradient_diagnostics(self, metadata_rows):
        print(f"trigger_gradient_shape={list(self._last_trigger_grads.shape)}")
        for metadata in metadata_rows:
            print(
                "gradient_slice "
                f"sample={metadata['sample_index']} "
                f"component={metadata.get('component', 'full')} "
                f"prefix_length={metadata['prefix_length']} "
                f"trigger_start={metadata['trigger_start']} "
                f"trigger_end={metadata['trigger_end']} "
                f"target_start={metadata['target_start']} "
                f"input_length={metadata['input_length']}"
            )

        averaged_grad = self._last_trigger_grad
        position_norms = torch.linalg.vector_norm(averaged_grad, dim=-1)
        if averaged_grad.shape[0] > 1:
            adjacent_cosines = F.cosine_similarity(
                averaged_grad[:-1],
                averaged_grad[1:],
                dim=-1,
                eps=1e-12,
            )
            cosine_values = adjacent_cosines.detach().cpu().tolist()
        else:
            cosine_values = []
        print(f"trigger_gradient_norms={position_norms.detach().cpu().tolist()}")
        print(f"adjacent_trigger_gradient_cosines={cosine_values}")
        print(
            "loss_components "
            f"anchor_loss={self._last_loss_diagnostics['anchor_loss']} "
            f"frontier_loss={self._last_loss_diagnostics['frontier_loss']} "
            f"frontier_lambda={self.frontier_lambda} "
            f"total_loss={self._last_loss_diagnostics['total_loss']} "
            f"anchor_token_count={self._last_loss_diagnostics['anchor_token_count']} "
            f"frontier_token_count={self._last_loss_diagnostics['frontier_token_count']} "
            f"anchor_gradient_norm={self._last_loss_diagnostics['anchor_gradient_norm']} "
            f"frontier_gradient_norm={self._last_loss_diagnostics['frontier_gradient_norm']} "
            f"total_trigger_gradient_norm={self._last_loss_diagnostics['total_trigger_gradient_norm']}"
        )

    def compute_loss(
        self,
        target_texts,
        trigger_tokens,
        stage_end,
        require_grad=False,
        stage_index=0,
        stage_start=0,
        rollout_state=None,
    ):
        target_texts = list(target_texts)
        if not target_texts:
            raise ValueError("target_texts must contain at least one sample")

        total_loss = 0.0
        component_loss_sums = {"anchor": 0.0, "frontier": 0.0}
        component_token_counts = {"anchor": 0, "frontier": 0}
        total_grads = []
        anchor_grads = []
        frontier_grads = []
        metadata_rows = []

        for index, text in enumerate(target_texts):
            if self.loss_mode == "self_conditioned_frontier":
                components = self._self_conditioned_components(
                    index=index,
                    stage_index=stage_index,
                    stage_start=stage_start,
                    stage_end=stage_end,
                    target_text=text,
                    triggers=trigger_tokens,
                    rollout_state=rollout_state,
                )
            else:
                components = self._teacher_forced_components(
                    index=index,
                    stage_end=stage_end,
                    target_text=text,
                    triggers=trigger_tokens,
                )

            sample_total_grad = None
            sample_anchor_grad = None
            sample_frontier_grad = None
            for component in components:
                loss, trigger_grad = self._forward_component(
                    component,
                    require_grad=require_grad,
                )
                loss_value = float(loss.item())
                weighted_loss = component["weight"] * loss_value
                total_loss += weighted_loss / len(target_texts)
                name = component["name"]
                if name in component_loss_sums:
                    component_loss_sums[name] += loss_value / len(target_texts)
                    component_token_counts[name] += component["token_count"]

                if require_grad:
                    weighted_grad = component["weight"] * trigger_grad
                    sample_total_grad = (
                        weighted_grad
                        if sample_total_grad is None
                        else sample_total_grad + weighted_grad
                    )
                    if name == "anchor":
                        sample_anchor_grad = trigger_grad
                    elif name == "frontier":
                        sample_frontier_grad = trigger_grad
                    metadata_rows.append(component["metadata"])

            if require_grad:
                if sample_total_grad is None:
                    raise AssertionError("sample did not produce a trigger gradient")
                zero_grad = torch.zeros_like(sample_total_grad)
                total_grads.append(sample_total_grad)
                anchor_grads.append(
                    sample_anchor_grad if sample_anchor_grad is not None else zero_grad
                )
                frontier_grads.append(
                    sample_frontier_grad if sample_frontier_grad is not None else zero_grad
                )

        if require_grad:
            self._last_trigger_grads = torch.cat(total_grads, dim=0)
            self._last_anchor_grads = torch.cat(anchor_grads, dim=0)
            self._last_frontier_grads = torch.cat(frontier_grads, dim=0)
            expected_batch_shape = (
                len(target_texts),
                len(trigger_tokens),
            )
            if tuple(self._last_trigger_grads.shape[:2]) != expected_batch_shape:
                raise AssertionError(
                    "position-specific trigger gradient batch shape is wrong: "
                    f"{tuple(self._last_trigger_grads.shape)}"
                )
            if not torch.isfinite(self._last_trigger_grads).all():
                raise AssertionError("trigger gradients contain NaN or Inf")

            self._last_trigger_grad = self._last_trigger_grads.mean(dim=0)
            if len(trigger_tokens) > 1:
                all_positions_identical = all(
                    torch.equal(
                        self._last_trigger_grad[0],
                        self._last_trigger_grad[position],
                    )
                    for position in range(1, len(trigger_tokens))
                )
                if all_positions_identical:
                    raise AssertionError(
                        "all trigger positions received the exact same gradient vector"
                    )

            averaged_anchor_grad = self._last_anchor_grads.mean(dim=0)
            averaged_frontier_grad = self._last_frontier_grads.mean(dim=0)
            self._last_loss_diagnostics = {
                "anchor_loss": component_loss_sums["anchor"],
                "frontier_loss": component_loss_sums["frontier"],
                "total_loss": total_loss,
                "anchor_token_count": component_token_counts["anchor"],
                "frontier_token_count": component_token_counts["frontier"],
                "anchor_gradient_norm": float(
                    torch.linalg.vector_norm(averaged_anchor_grad).item()
                ),
                "frontier_gradient_norm": float(
                    torch.linalg.vector_norm(averaged_frontier_grad).item()
                ),
                "total_trigger_gradient_norm": float(
                    torch.linalg.vector_norm(self._last_trigger_grad).item()
                ),
            }
            self._log_gradient_diagnostics(metadata_rows)

        return total_loss

    def hotflip_attack(
        self,
        averaged_grad,
        increase_loss=False,
        num_candidates=None,
    ):
        if num_candidates is None:
            num_candidates = self.hotflip_top_k
        num_candidates = min(num_candidates, self.embedding_weight.shape[0])
        averaged_grad = averaged_grad
        embedding_matrix = self.embedding_weight
        averaged_grad = averaged_grad.unsqueeze(0)
        gradient_dot_embedding_matrix = torch.einsum("bij,kj->bik",
                (averaged_grad, embedding_matrix))        
        gradient_dot_embedding_matrix *= -1 
        _, best_k_ids = torch.topk(gradient_dot_embedding_matrix, num_candidates, dim=2)
        return best_k_ids.detach().squeeze(0).cpu().numpy()

    def _greedy_rollout(self, prompt_ids, rollout_length):
        if rollout_length == 0:
            return []
        input_ids = torch.tensor(
            [prompt_ids],
            device=self.device,
            dtype=torch.long,
        )
        generation_kwargs = {
            "input_ids": input_ids,
            "attention_mask": torch.ones_like(input_ids),
            "do_sample": False,
            "num_beams": 1,
            "min_new_tokens": rollout_length,
            "max_new_tokens": rollout_length,
        }
        pad_token_id = getattr(self.tokenizer, "pad_token_id", None)
        if pad_token_id is None:
            pad_token_id = getattr(self.tokenizer, "eos_token_id", None)
        if pad_token_id is not None:
            generation_kwargs["pad_token_id"] = pad_token_id

        with torch.no_grad():
            generated = self.model.generate(**generation_kwargs)
        generated_prefix = generated[0, len(prompt_ids):].detach().cpu().tolist()
        if len(generated_prefix) != rollout_length:
            raise AssertionError(
                "greedy rollout length is wrong: "
                f"{len(generated_prefix)} != {rollout_length}"
            )
        return [int(token_id) for token_id in generated_prefix]

    def _decode_token_preview(self, token_ids, limit=64):
        preview_ids = list(token_ids[:limit])
        try:
            text = self.tokenizer.decode(
                preview_ids,
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
        except TypeError:
            text = self.tokenizer.decode(preview_ids)
        suffix = "..." if len(token_ids) > limit else ""
        return text + suffix

    @staticmethod
    def _common_prefix_count(first, second):
        count = 0
        for first_id, second_id in zip(first, second):
            if first_id != second_id:
                break
            count += 1
        return count

    def _validate_stage_zero_generation(
        self,
        target_texts,
        trigger_tokens,
        stage_end,
    ):
        """Require a real greedy match at the start before frontier search."""
        common_prefix_counts = []
        print(
            "stage0_generation_validation "
            "strategy=greedy do_sample=False "
            "required_common_prefix_tokens=1"
        )

        for index, target_text in enumerate(target_texts):
            prompt_ids, _, target_ids, _ = self._encode_completion_target(
                target_text,
                trigger_tokens,
                return_metadata=True,
            )
            validation_length = min(
                stage_end,
                self.get_effective_max_len(len(target_ids)),
            )
            generated_prefix = self._greedy_rollout(
                prompt_ids,
                validation_length,
            )
            gold_prefix = target_ids[:validation_length]
            common_prefix = self._common_prefix_count(
                gold_prefix,
                generated_prefix,
            )
            common_prefix_counts.append(common_prefix)
            print(
                "stage0_generation_sample "
                f"sample={index} "
                f"validation_length={validation_length} "
                f"common_prefix_token_count={common_prefix} "
                f"passed={common_prefix >= 1} "
                f"generated_prefix={self._decode_token_preview(generated_prefix)!r} "
                f"gold_prefix={self._decode_token_preview(gold_prefix)!r}"
            )

        passed = all(count >= 1 for count in common_prefix_counts)
        print(
            "stage0_generation_acceptance "
            f"passed={passed} "
            "required_common_prefix_tokens=1 "
            f"sample_common_prefix_token_counts={common_prefix_counts} "
            f"later_frontier_allowed={passed}"
        )
        return passed

    def _refresh_self_conditioned_rollouts(
        self,
        target_texts,
        trigger_tokens,
        stage_index,
        stage_start,
        stage_end,
        reason,
    ):
        self._rollout_refresh_count += 1
        refresh_id = self._rollout_refresh_count
        samples = []
        print(
            "rollout_refresh "
            f"id={refresh_id} stage={stage_index} reason={reason} "
            "strategy=greedy do_sample=False"
        )

        for index, target_text in enumerate(target_texts):
            prompt_ids, _, target_ids, _ = self._encode_completion_target(
                target_text,
                trigger_tokens,
                return_metadata=True,
            )
            local_stage_end = min(
                stage_end,
                self.get_effective_max_len(len(target_ids)),
            )
            frontier_start = min(stage_start, local_stage_end)
            frontier_end = local_stage_end
            generated_prefix = self._greedy_rollout(
                prompt_ids,
                frontier_start,
            )
            gold_prefix = target_ids[:frontier_start]
            common_prefix = self._common_prefix_count(
                gold_prefix,
                generated_prefix,
            )
            rollout = {
                "sample_index": index,
                "stage_index": stage_index,
                "stage_start": frontier_start,
                "stage_end": local_stage_end,
                "frontier_start": frontier_start,
                "frontier_end": frontier_end,
                "generated_prefix_ids": generated_prefix,
                "gold_prefix_ids": gold_prefix,
                "common_prefix_token_count": common_prefix,
                "source": "greedy_generation",
            }
            samples.append(rollout)
            print(
                "rollout_sample "
                f"sample={index} stage={stage_index} "
                f"rollout_length={len(generated_prefix)} "
                f"common_prefix_token_count={common_prefix} "
                f"frontier_start={frontier_start} "
                f"frontier_end={frontier_end} "
                f"generated_prefix={self._decode_token_preview(generated_prefix)!r} "
                f"gold_prefix={self._decode_token_preview(gold_prefix)!r}"
            )

        return {
            "refresh_id": refresh_id,
            "reason": reason,
            "stage_index": stage_index,
            "stage_start": stage_start,
            "stage_end": stage_end,
            "source_trigger_ids": tuple(int(token) for token in trigger_tokens),
            "samples": samples,
        }

    def _evaluate_self_conditioned_candidate(
        self,
        target_texts,
        candidate_trigger_tokens,
        stage_index,
        stage_start,
        stage_end,
        fixed_rollout_candidate_loss,
        previous_actual_loss,
        rollout_state,
    ):
        if self.loss_mode != "self_conditioned_frontier":
            raise AssertionError(
                "candidate-specific rollout evaluation is only valid for "
                "self_conditioned_frontier"
            )

        previous_trigger_tokens = deepcopy(self.trigger_tokens)
        previous_rollout_state = rollout_state
        previous_trigger_ids = tuple(
            int(token) for token in previous_trigger_tokens
        )
        old_rollout_id = previous_rollout_state["refresh_id"]
        candidate_rollout_state = self._refresh_self_conditioned_rollouts(
            target_texts=target_texts,
            trigger_tokens=candidate_trigger_tokens,
            stage_index=stage_index,
            stage_start=stage_start,
            stage_end=stage_end,
            reason="candidate_evaluation",
        )
        expected_source_trigger_ids = tuple(
            int(token) for token in candidate_trigger_tokens
        )
        if (
            candidate_rollout_state["source_trigger_ids"]
            != expected_source_trigger_ids
        ):
            raise AssertionError(
                "candidate rollout was not generated from the candidate trigger"
            )

        with torch.no_grad():
            refreshed_candidate_loss = self.compute_loss(
                target_texts,
                candidate_trigger_tokens,
                stage_end,
                require_grad=False,
                stage_index=stage_index,
                stage_start=stage_start,
                rollout_state=candidate_rollout_state,
            )
        accepted_after_refresh = (
            refreshed_candidate_loss
            < previous_actual_loss - self.improvement_epsilon
        )

        if accepted_after_refresh:
            self.trigger_tokens = deepcopy(candidate_trigger_tokens)
            rollout_state = candidate_rollout_state
            if not refreshed_candidate_loss < previous_actual_loss:
                raise AssertionError(
                    "accepted flip refreshed loss must be lower than the "
                    "previous actual loss"
                )
            if rollout_state is not candidate_rollout_state:
                raise AssertionError(
                    "accepted candidate rollout did not become active"
                )
            rollback = False
            active_loss = refreshed_candidate_loss
        else:
            self.trigger_tokens = previous_trigger_tokens
            rollout_state = previous_rollout_state
            rollback = True
            active_loss = previous_actual_loss
            active_trigger_ids = tuple(
                int(token) for token in self.trigger_tokens
            )
            if active_trigger_ids != previous_trigger_ids:
                raise AssertionError(
                    "rejected candidate did not restore the previous trigger"
                )
            if rollout_state is not previous_rollout_state:
                raise AssertionError(
                    "rejected candidate did not restore the previous rollout"
                )
            if rollout_state is candidate_rollout_state:
                raise AssertionError(
                    "rejected candidate rollout became the active rollout"
                )

        candidate_rollout_id = candidate_rollout_state["refresh_id"]
        active_rollout_id = rollout_state["refresh_id"]
        print(
            "candidate_refresh_evaluation "
            f"previous_actual_loss={previous_actual_loss} "
            f"fixed_rollout_candidate_loss={fixed_rollout_candidate_loss} "
            f"refreshed_candidate_loss={refreshed_candidate_loss} "
            f"accepted_after_refresh={accepted_after_refresh} "
            f"rollback={rollback} "
            f"old_rollout_id={old_rollout_id} "
            f"candidate_rollout_id={candidate_rollout_id} "
            f"active_rollout_id={active_rollout_id}"
        )
        return accepted_after_refresh, active_loss, rollout_state

    def _active_loss_token_count(
        self,
        stage_end,
        stage_index=None,
        stage_start=0,
    ):
        if self.loss_mode in {"anchor_frontier", "self_conditioned_frontier"}:
            anchor, frontier = get_separate_loss_regions(
                loss_mode=self.loss_mode,
                stage_end=stage_end,
                anchor_len=self.anchor_window,
                frontier_window=self.frontier_window,
            )
            anchor_count = anchor[1] - anchor[0]
            if self.loss_mode == "self_conditioned_frontier" and stage_index == 0:
                return anchor_count
            if self.loss_mode == "self_conditioned_frontier":
                return anchor_count + stage_end - stage_start
            return anchor_count + frontier[1] - frontier[0]
        return stage_end

    def _print_stage_summary(
        self,
        stage_index,
        stage_start,
        stage_end,
        effective_max_len,
        target_lengths,
        loss,
    ):
        sample_stage_ends = [
            min(stage_end, self.get_effective_max_len(target_len))
            for target_len in target_lengths
        ]
        sample_active_loss_tokens = [
            self._active_loss_token_count(
                sample_stage_end,
                stage_index,
                min(stage_start, sample_stage_end),
            )
            for sample_stage_end in sample_stage_ends
        ]

        summary = [
            f"loss_mode={self.loss_mode}",
            f"stage={stage_index}",
            f"stage_start={stage_start}",
            f"stage_end={stage_end}",
            f"stage_chunk=[{stage_start},{stage_end})",
            f"effective_max_len={effective_max_len}",
            f"active_loss_tokens={self._active_loss_token_count(stage_end, stage_index, stage_start)}",
            f"sample_active_loss_tokens={sample_active_loss_tokens}",
            f"teacher_forcing={self.loss_mode != 'self_conditioned_frontier'}",
            f"frontier_lambda={self.frontier_lambda}",
            f"hotflip_top_k={self.hotflip_top_k}",
            f"num_restarts={self.num_restarts}",
        ]
        if self.loss_mode in {"anchor_frontier", "self_conditioned_frontier"}:
            if self.loss_mode == "self_conditioned_frontier":
                anchor = (0, min(self.anchor_window, stage_end))
                frontier = (stage_start, stage_end)
            else:
                anchor, frontier = get_separate_loss_regions(
                    loss_mode=self.loss_mode,
                    stage_end=stage_end,
                    anchor_len=self.anchor_window,
                    frontier_window=self.frontier_window,
                )
            summary.extend(
                [
                    f"anchor=[{anchor[0]},{anchor[1]})",
                    f"frontier=[{frontier[0]},{frontier[1]})",
                ]
            )
        summary.extend(
            [
                f"loss={loss}",
                f"trigger={self.decode_triggers()!r}",
            ]
        )
        print("\n".join(summary))

    def replace_triggers(self, target_texts):
        target_texts = list(target_texts)
        if not target_texts:
            raise ValueError("target_texts must contain at least one sample")
        print(
            "Attack search config: "
            f"loss_mode={self.loss_mode}, "
            "trigger_gradient_slicing=position_specific_inputs_embeds, "
            f"conditioning={'self_conditioned' if self.loss_mode == 'self_conditioned_frontier' else 'teacher_forcing'}, "
            f"rollout_refresh={'stage_and_candidate_evaluation' if self.loss_mode == 'self_conditioned_frontier' else 'none'}, "
            f"frontier_lambda={self.frontier_lambda}, "
            f"hotflip_top_k={self.hotflip_top_k}, "
            f"num_restarts={self.num_restarts}, "
            f"improvement_epsilon={self.improvement_epsilon}, "
            f"max_refresh_candidates={self.max_refresh_candidates}"
        )

        best_restart_loss = float("inf")
        best_restart_tokens = deepcopy(self.trigger_tokens)
        initial_trigger_tokens = deepcopy(self.trigger_tokens)

        for restart_index in range(self.num_restarts):
            if restart_index == 0:
                self.trigger_tokens = deepcopy(initial_trigger_tokens)
            else:
                self.trigger_tokens = self.init_triggers(
                    self.trigger_token_length,
                    init_trigger="",
                    user_prefix=self.user_prefix,
                )
            print(
                f"restart={restart_index}/{self.num_restarts - 1} "
                f"init_triggers={self.decode_triggers()!r}"
            )

            target_lengths = [
                len(self._encode_completion_target(text, self.trigger_tokens)[2])
                for text in target_texts
            ]
            if any(target_len == 0 for target_len in target_lengths):
                raise ValueError("each target must contain at least one target token")
            effective_max_len = max(
                self.get_effective_max_len(target_len)
                for target_len in target_lengths
            )
            self.max_len = effective_max_len
            final_loss = float("inf")
            if self.loss_mode == "self_conditioned_frontier":
                stage_ranges = iter_stage_ranges(
                    init_step=self.anchor_window,
                    step=self.frontier_window,
                    effective_max_len=effective_max_len,
                )
            else:
                stage_ranges = (
                    (0, stage_end)
                    for stage_end in iter_stage_ends(
                        init_step=self.init_step,
                        step=self.step,
                        effective_max_len=effective_max_len,
                    )
                )

            for idx_loss, (stage_start, stage_end) in enumerate(stage_ranges):
                rollout_state = None
                if self.loss_mode == "self_conditioned_frontier":
                    rollout_state = self._refresh_self_conditioned_rollouts(
                        target_texts=target_texts,
                        trigger_tokens=self.trigger_tokens,
                        stage_index=idx_loss,
                        stage_start=stage_start,
                        stage_end=stage_end,
                        reason="stage_start",
                    )

                token_flipped = True
                while token_flipped:
                    token_flipped = False
                    with torch.set_grad_enabled(True):
                        self.model.zero_grad()
                        best_loss = self.compute_loss(
                            target_texts,
                            self.trigger_tokens,
                            stage_end,
                            require_grad=True,
                            stage_index=idx_loss,
                            stage_start=stage_start,
                            rollout_state=rollout_state,
                        )
                    previous_actual_loss = best_loss
                    print(
                        f"current loss:{best_loss}, "
                        f"triggers:{self.decode_triggers()}"
                    )

                    candidates = self.hotflip_attack(
                        self.get_triggers_grad(),
                        num_candidates=self.hotflip_top_k,
                    )
                    best_trigger_tokens = deepcopy(self.trigger_tokens)
                    fixed_rollout_candidates = []
                    for i, token_to_flip in enumerate(self.trigger_tokens):
                        for cand in candidates[i]:
                            cand_id = int(cand)
                            cand_text = self.tokenizer.decode([cand_id])
                            if re.search(r"[^a-zA-Z0-9s\s]", cand_text):
                                continue

                            candidate_trigger_tokens = deepcopy(self.trigger_tokens)
                            candidate_trigger_tokens[i] = cand_id
                            try:
                                self._decode_trigger_tokens(
                                    candidate_trigger_tokens
                                )
                            except ValueError:
                                continue

                            with torch.no_grad():
                                loss = self.compute_loss(
                                    target_texts,
                                    candidate_trigger_tokens,
                                    stage_end,
                                    require_grad=False,
                                    stage_index=idx_loss,
                                    stage_start=stage_start,
                                    rollout_state=rollout_state,
                                )
                            if self.loss_mode == "self_conditioned_frontier":
                                if loss < previous_actual_loss:
                                    fixed_rollout_candidates.append(
                                        {
                                            "loss": loss,
                                            "trigger_tokens": deepcopy(
                                                candidate_trigger_tokens
                                            ),
                                        }
                                    )
                                continue
                            if best_loss <= loss:
                                continue
                            token_flipped = True
                            best_loss = loss
                            best_trigger_tokens = deepcopy(
                                candidate_trigger_tokens
                            )

                    if self.loss_mode == "self_conditioned_frontier":
                        ranked_fixed_candidates = sorted(
                            fixed_rollout_candidates,
                            key=lambda candidate: candidate["loss"],
                        )
                        refresh_candidates = ranked_fixed_candidates[
                            :self.max_refresh_candidates
                        ]
                        print(
                            "candidate_refresh_queue "
                            f"fixed_improvement_count={len(ranked_fixed_candidates)} "
                            f"verification_count={len(refresh_candidates)}"
                        )
                        for fixed_candidate in refresh_candidates:
                            accepted, best_loss, rollout_state = (
                                self._evaluate_self_conditioned_candidate(
                                    target_texts=target_texts,
                                    candidate_trigger_tokens=(
                                        fixed_candidate["trigger_tokens"]
                                    ),
                                    stage_index=idx_loss,
                                    stage_start=stage_start,
                                    stage_end=stage_end,
                                    fixed_rollout_candidate_loss=(
                                        fixed_candidate["loss"]
                                    ),
                                    previous_actual_loss=previous_actual_loss,
                                    rollout_state=rollout_state,
                                )
                            )
                            if accepted:
                                token_flipped = True
                                break
                    elif token_flipped:
                        self.trigger_tokens = deepcopy(best_trigger_tokens)

                    if token_flipped:
                        print(
                            f"Loss: {best_loss}, "
                            f"triggers:{self.decode_triggers()}"
                        )
                        if self.loss_mode == "self_conditioned_frontier":
                            print(
                                "accepted_flip "
                                f"stage={idx_loss} "
                                f"rollout_refreshed=True "
                                f"refresh_id={rollout_state['refresh_id']}"
                            )
                    else:
                        print("\nNo improvement, ending iteration")

                final_loss = best_loss
                self._print_stage_summary(
                    stage_index=idx_loss,
                    stage_start=stage_start,
                    stage_end=stage_end,
                    effective_max_len=effective_max_len,
                    target_lengths=target_lengths,
                    loss=best_loss,
                )
                if (
                    self.loss_mode == "self_conditioned_frontier"
                    and idx_loss == 0
                    and not self._validate_stage_zero_generation(
                        target_texts=target_texts,
                        trigger_tokens=self.trigger_tokens,
                        stage_end=stage_end,
                    )
                ):
                    print(
                        "stage0_generation_rejected "
                        "later_frontier_skipped=True"
                    )
                    break

            print(
                f"restart_summary restart={restart_index} "
                f"final_loss={final_loss} "
                f"trigger={self.decode_triggers()!r}"
            )
            if final_loss < best_restart_loss:
                best_restart_loss = final_loss
                best_restart_tokens = deepcopy(self.trigger_tokens)

        self.trigger_tokens = deepcopy(best_restart_tokens)
        print(
            f"best_restart_loss={best_restart_loss} "
            f"best_trigger={self.decode_triggers()!r}"
        )
