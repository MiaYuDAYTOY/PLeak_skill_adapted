import torch
import numpy as np
from copy import deepcopy
import math
from contextlib import contextmanager
from util.template import TextTemplate
from util.attack_diagnostics import diagnostics_enabled, print_cuda_memory, require_finite
from util.trigger_tokens import allowed_trigger_token_ids
from ModelFactory import ModelFactory

class HotFlip:
    def __init__(self, trigger_token_length=6, shadow_model='gpt2', step=100, template=None, init_triggers='', init_step=None, prefix_length=8, compute_dtype=None, gradient_checkpointing=True):
        self.target_model = shadow_model
        self.template = TextTemplate(prefix_1='') if template is None else template
        modelFactory = ModelFactory()
        model_options = {} if compute_dtype is None else {"compute_dtype": compute_dtype}
        self.model = modelFactory.get_model(shadow_model, **model_options)
        self.device = self.model.get_input_embeddings().weight.device
        # HotFlip differentiates the input embeddings, not the model weights.
        self.model.requires_grad_(False)
        if gradient_checkpointing:
            self.model.gradient_checkpointing_enable()
        print_cuda_memory("after model load")
        self.tokenizer = modelFactory.get_tokenizer(shadow_model)
        self.embedding_weight = self.get_embedding_weight()
        self.vocab_size = len(self.tokenizer)
        self.allowed_trigger_ids = np.asarray(allowed_trigger_token_ids(
            self.tokenizer, self.embedding_weight.shape[0],
        ), dtype=np.int64)
        self.allowed_trigger_id_set = set(self.allowed_trigger_ids.tolist())
        self.step = step
        self.init_step = init_step if init_step is not None else self.step
        self.prefix_length = prefix_length
        self.user_prefix = ''
        self.trigger_tokens = self.init_triggers(trigger_token_length, init_triggers, self.user_prefix)

    def _sample_context(self, target_texts, index):
        metadata = getattr(target_texts, "sample_metadata", None)
        path = metadata[index].get("path", "<unknown>") if metadata else "<unknown>"
        return f"sample {index} path={path}"

    @contextmanager
    def _loss_model_mode(self, require_grad):
        # Legacy Llama checkpoints only in training mode. Keep that mode
        # through backward, while candidate evaluation always uses eval.
        checkpointing = getattr(self.model, "is_gradient_checkpointing", False)
        previous_training = self.model.training
        if checkpointing:
            self.model.train(require_grad)
        try:
            yield
        finally:
            if checkpointing:
                self.model.train(previous_training)

    def init_triggers(self, trigger_token_length, init_trigger='', user_prefix=''):
        # Encode content only. BOS/EOS behavior belongs to the tokenizer used
        # for the complete prompt, never to a model-name-specific slice.
        init_tokens = self.tokenizer.encode(init_trigger, add_special_tokens=False)
        len_init = len(init_tokens)
        len_user = len(self.tokenizer.encode(user_prefix, add_special_tokens=False))
        available_length = trigger_token_length - len_user
        if available_length <= 0:
            raise ValueError("Trigger token budget must exceed the user prefix length")
        if any(token_id not in self.allowed_trigger_id_set for token_id in init_tokens):
            raise ValueError("Initial trigger contains disallowed token IDs")
        if len_init >= available_length:
            triggers = np.asarray(init_tokens[:available_length], dtype=np.int64)
            self._decode_trigger_tokens(triggers)
            return triggers
        triggers = np.empty(available_length, dtype=np.int64)
        random_start = min(len_init, len(triggers))
        triggers[:random_start] = init_tokens[:random_start]

        # Only keep IDs that survive the exact decode/concatenate/encode path
        # used later by Sampler.
        for _ in range(1000):
            for idx in range(random_start, len(triggers)):
                triggers[idx] = np.random.choice(self.allowed_trigger_ids)

            try:
                self._decode_trigger_tokens(triggers)
                return triggers
            except ValueError:
                continue

        raise RuntimeError(
            "无法初始化可在训练和测试间稳定编码的 trigger"
        )

    def get_embedding_weight(self):
        return self.model.get_input_embeddings().weight.detach()

    def _decode_trigger_tokens(self, trigger_tokens):
        """Decode IDs without changing them at the prompt boundary."""
        trigger_ids = [int(token_id) for token_id in trigger_tokens]
        if any(token_id not in self.allowed_trigger_id_set for token_id in trigger_ids):
            raise ValueError("Trigger contains undefined, special or disallowed token IDs")
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

        # The template's trailing newline can merge with the last trigger
        # token (especially in byte-level BPE). Check it before candidate use.
        prompt_ids = self.tokenizer.encode(context + trigger_text + '\n',
                                           add_special_tokens=False)
        if prompt_ids[:len(roundtrip_ids)] != roundtrip_ids:
            raise ValueError("Trigger token IDs change at the trailing newline")

        return trigger_text

    def decode_triggers(self):
        trigger_text = self._decode_trigger_tokens(self.trigger_tokens)
        return self.user_prefix + trigger_text

    def make_target(self, index, idx_loss, target_text, triggers):
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
        trigger_end = trigger_start + len(trigger_ids)
        actual_trigger_ids = prompt_ids[
            trigger_start:trigger_end
        ]
        if actual_trigger_ids != trigger_ids:
            raise ValueError(
                "训练输入中的 trigger token IDs 与待优化 IDs 不一致"
            )
        #a
            encoded_target = full_ids[len(prompt_ids):]
            len_non_label = len(prompt_ids)
            max_len = len(encoded_target)
            if max_len > self.max_len: self.max_len = max_len

            label_slice = self.init_step + idx_loss * self.step

            if label_slice > self.max_len:
                encoded_label = [-100]*len_non_label + encoded_target
            else:
                encoded_label = [-100]*len_non_label + encoded_target[:label_slice]

        encoded_target = full_ids[len(prompt_ids):]
        len_non_label = len(prompt_ids)

        # 只对目标的前 prefix_length 个 token 计算损失
        target_prefix = encoded_target[:self.prefix_length]

        encoded_label = (
            [-100] * len_non_label
            + target_prefix
        )

        encoded_text = full_ids[:len(encoded_label)]
        label = torch.tensor([encoded_label], device=self.device, dtype=torch.long)
        lm_input= torch.tensor([encoded_text], device=self.device, dtype=torch.long)
        if diagnostics_enabled():
            print(
                f"[input] sample {index} chars={len(target_text)}",
                f"target_tokens={len(self.tokenizer.encode(target_text, add_special_tokens=False))}",
                f"continuation_tokens={len(encoded_target)} trigger_tokens={len(triggers)}",
                f"prompt_tokens={len_non_label} full_tokens_before_slice={len(full_ids)}",
                f"supervised_tokens={len(target_prefix)} trigger_span=[{trigger_start}, {trigger_end})",
                flush=True,
            )
            print("input shape:", lm_input.shape, "label shape:", label.shape,
                  "seq_len:", lm_input.shape[1], flush=True)
        return lm_input, label, trigger_start, trigger_end

    #def make_target_chat(self, index, idx_loss, target_text, triggers):
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

    #def make_adaptive_chat(self, index, idx_loss, target_text, triggers):
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

    def _forward_loss(self, model_input, labels):
        """Keep the full context, but project only supervised Qwen positions.

        ignore_index=-100 masks loss terms, not the allocation of full-sequence
        logits or cross-entropy intermediates. Qwen3's logits_to_keep selects
        hidden states BEFORE the vocabulary projection. A label at position t
        is predicted by the hidden state at t-1 (causal shift).
        """
        options = dict(use_cache=False, output_attentions=False,
                       output_hidden_states=False, return_dict=True)
        if self.model.config.model_type != 'qwen3':
            return self.model(**model_input, labels=labels, **options).loss

        shifted_labels = labels[:, 1:]
        positions = shifted_labels.ne(-100).any(dim=0).nonzero(as_tuple=True)[0]
        if positions.numel() == 0:
            raise ValueError("No supervised tokens after causal label shift")
        outputs = self.model(**model_input, logits_to_keep=positions, **options)
        targets = shifted_labels.index_select(1, positions).to(outputs.logits.device)
        # Match Transformers' ordinary causal LM loss: FP32 CE, mean over
        # non-ignored labels. Do not let the model apply a second causal shift.
        return torch.nn.functional.cross_entropy(
            outputs.logits.float().reshape(-1, outputs.logits.shape[-1]),
            targets.reshape(-1), ignore_index=-100,
        )

    def compute_loss(self, target_texts, trigger_tokens, idx_loss,  require_grad=False):
        if not len(target_texts):
            raise ValueError("compute_loss requires at least one sample")
        total_loss = 0
        trigger_grad = None
        for index, text in enumerate(target_texts):
            context = self._sample_context(target_texts, index)
            if diagnostics_enabled():
                raw_dataset = getattr(target_texts, "dataset", None)
                raw_chars = len(raw_dataset[index]["content"]) if raw_dataset is not None else None
                print(f"[sample] {context} raw_chars={raw_chars} require_grad={require_grad}", flush=True)
            lm_input, label, trigger_start, trigger_end = self.make_target(
                index,
                idx_loss,
                text,
                trigger_tokens,
            )
            print_cuda_memory(f"{context} after make_target")
            if lm_input.shape != label.shape:
                raise ValueError(f"{context}: input/label shapes differ")
            supervised = int(label[:, 1:].ne(-100).sum().item())
            if supervised == 0:
                raise ValueError(f"{context}: no supervised tokens after causal label shift")
            stage = "embedding"
            try:
                with self._loss_model_mode(require_grad), torch.set_grad_enabled(require_grad):
                    if require_grad:
                        inputs_embeds = self.model.get_input_embeddings()(lm_input).detach()
                        inputs_embeds.requires_grad_(True)
                        require_finite(inputs_embeds, "input embeddings", context)
                        model_input = {"inputs_embeds": inputs_embeds}
                    else:
                        model_input = {"input_ids": lm_input}
                    stage = "forward"
                    if diagnostics_enabled() and require_grad:
                        print(f"[forward] {context} inputs_embeds_dtype={inputs_embeds.dtype} "
                              f"training={self.model.training}", flush=True)
                    print_cuda_memory(f"{context} before forward")
                    loss = self._forward_loss(model_input, label) / len(target_texts)
                    print_cuda_memory(f"{context} after forward")
                    require_finite(loss, "forward loss (before backward)", context)
                    loss_value = loss.item()
                    if diagnostics_enabled():
                        print(f"[loss] {context} before_backward={loss_value} "
                              f"supervised_tokens={supervised}", flush=True)
                    if require_grad:
                        stage = "backward"
                        print_cuda_memory(f"{context} before backward")
                        loss.backward()
                        print_cuda_memory(f"{context} after backward")
                        if inputs_embeds.grad is None:
                            raise RuntimeError(f"{context}: missing input embedding gradient")
                        sample_trigger_grad = inputs_embeds.grad[
                            0, trigger_start:trigger_end, :,
                        ].detach().clone()
                        require_finite(sample_trigger_grad, "trigger gradient", context)
                        if trigger_grad is None:
                            trigger_grad = sample_trigger_grad
                        else:
                            trigger_grad += sample_trigger_grad
                        require_finite(trigger_grad, "accumulated trigger gradient", context)
                        del inputs_embeds, sample_trigger_grad
                    total_loss += loss_value
                    if not math.isfinite(total_loss):
                        raise FloatingPointError(f"{context}: non-finite accumulated loss")
                    del loss, model_input
            except torch.cuda.OutOfMemoryError:
                print_cuda_memory(
                    f"OOM {context} stage={stage} seq_len={lm_input.shape[1]}", enabled=True,
                )
                raise
            del lm_input, label
            print_cuda_memory(f"{context} sample complete")
        return total_loss, trigger_grad

    def hotflip_attack(self, averaged_grad, increase_loss=False, num_candidates=30):
        require_finite(averaged_grad, "trigger gradient", "HotFlip candidate scoring")
        averaged_grad = averaged_grad
        candidate_ids = torch.as_tensor(self.allowed_trigger_ids,
                                        device=self.embedding_weight.device)
        embedding_matrix = self.embedding_weight.index_select(0, candidate_ids)
        averaged_grad = averaged_grad.unsqueeze(0)
        gradient_dot_embedding_matrix = torch.einsum("bij,kj->bik",
                (averaged_grad, embedding_matrix))        
        gradient_dot_embedding_matrix *= -1 
        require_finite(gradient_dot_embedding_matrix, "candidate scores", "HotFlip candidate scoring")
        if num_candidates <= 0:
            raise ValueError("num_candidates must be positive")
        _, best_k_ids = torch.topk(gradient_dot_embedding_matrix,
                                  min(num_candidates, len(self.allowed_trigger_ids)), dim=2)
        return candidate_ids[best_k_ids].detach().squeeze(0).cpu().numpy()

    def replace_triggers(self, target_texts):
        print(f"init_triggers:{self.decode_triggers()}")
        #self.max_len = self.step+10
        #idx_loss = 0
        #while idx_loss <= self.max_len//self.step:
        self.max_len = self.prefix_length
        idx_loss = 0
        while idx_loss < 1:
            token_flipped = True
            while token_flipped:
                token_flipped = False
                with torch.set_grad_enabled(True):
                    self.model.zero_grad(set_to_none=True)
                    best_loss, trigger_grad = self.compute_loss(
                        target_texts,
                        self.trigger_tokens,
                        idx_loss,
                        require_grad=True,
                    )
                print(f"current loss:{best_loss}, triggers:{self.decode_triggers()}")
                
                
                candidates = self.hotflip_attack(trigger_grad, num_candidates=30)
                best_trigger_tokens = deepcopy(self.trigger_tokens)
                for i, token_to_flip in enumerate(self.trigger_tokens):
                    for cand in candidates[i]:
                        cand_id = int(cand)
                        candidate_trigger_tokens = deepcopy(self.trigger_tokens)
                        candidate_trigger_tokens[i] = cand_id
                        try:
                            self._decode_trigger_tokens(
                                candidate_trigger_tokens
                            )
                        except ValueError:
                            continue

                        self.model.zero_grad(set_to_none=True)
                        with torch.no_grad():
                            loss, _ = self.compute_loss(
                                target_texts,
                                candidate_trigger_tokens,
                                idx_loss,
                                require_grad=False,
                            )
                        if not math.isfinite(best_loss) or not math.isfinite(loss):
                            raise FloatingPointError(
                                f"candidate position={i} token={cand_id}: non-finite loss; stopping before trigger update"
                            )
                        if best_loss <= loss: continue
                        token_flipped = True
                        best_loss = loss
                        best_trigger_tokens = deepcopy(candidate_trigger_tokens)
                self.trigger_tokens = deepcopy(best_trigger_tokens)
                if token_flipped: print(f"Loss: {best_loss}, triggers:{self.decode_triggers()}")
                else: print(f"\nNo improvement, ending iteration")
            idx_loss += 1
            print(f"Enter next iteration :{idx_loss}")
