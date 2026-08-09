import torch
import numpy as np
from copy import deepcopy
import re
from util.template import TextTemplate
from torchmetrics import ExtendedEditDistance, CatMetric
from util.data import Harmful
from ModelFactory import ModelFactory

class HotFlip:
    def __init__(self, trigger_token_length=6, shadow_model='gpt2', step=100, template=None, init_triggers='', init_step=None):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.target_model = shadow_model
        self.template = TextTemplate(prefix_1='') if template is None else template
        modelFactory = ModelFactory()
        self.model = modelFactory.get_model(shadow_model)
        self.tokenizer = modelFactory.get_tokenizer(shadow_model)
        self.vocab_size = modelFactory.get_vocab_size(shadow_model)
        self.embedding_weight = self.get_embedding_weight()
        self.step = step
        self.init_step = init_step if init_step is not None else self.step
        self.user_prefix = ''
        self.trigger_tokens = self.init_triggers(trigger_token_length, init_triggers, self.user_prefix)

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

    def get_embedding_weight(self):
        return self.model.get_input_embeddings().weight.detach()

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

        #只对前 8 个 token
        target_prefix = encoded_target[:8]

        encoded_label = (
            [-100] * len_non_label
            + target_prefix
        )

        encoded_text = full_ids[:len(encoded_label)]
        label = torch.tensor([encoded_label], device=self.device, dtype=torch.long)
        lm_input= torch.tensor([encoded_text], device=self.device, dtype=torch.long)
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

    def compute_loss(self, target_texts, trigger_tokens, idx_loss,  require_grad=False):
        total_loss = 0
        trigger_grad = None
        for index, text in enumerate(target_texts):
            lm_input, label, trigger_start, trigger_end = self.make_target(
                index,
                idx_loss,
                text,
                trigger_tokens,
            )
            if require_grad:
                inputs_embeds = self.model.get_input_embeddings()(lm_input).detach()
                inputs_embeds.requires_grad_(True)
                loss = self.model(
                    inputs_embeds=inputs_embeds,
                    labels=label,
                )[0]/len(target_texts)
                loss.backward()
                sample_trigger_grad = inputs_embeds.grad[
                    0,
                    trigger_start:trigger_end,
                    :,
                ].detach()
                if trigger_grad is None:
                    trigger_grad = sample_trigger_grad
                else:
                    trigger_grad += sample_trigger_grad
            else:
                loss = self.model(lm_input, labels=label)[0]/len(target_texts)
            total_loss += loss.item()
        return total_loss, trigger_grad

    def hotflip_attack(self, averaged_grad, increase_loss=False, num_candidates=30):
        averaged_grad = averaged_grad
        embedding_matrix = self.embedding_weight
        averaged_grad = averaged_grad.unsqueeze(0)
        gradient_dot_embedding_matrix = torch.einsum("bij,kj->bik",
                (averaged_grad, embedding_matrix))        
        gradient_dot_embedding_matrix *= -1 
        _, best_k_ids = torch.topk(gradient_dot_embedding_matrix, num_candidates, dim=2)
        return best_k_ids.detach().squeeze().cpu().numpy()

    def replace_triggers(self, target_texts):
        print(f"init_triggers:{self.decode_triggers()}")
        #self.max_len = self.step+10
        #idx_loss = 0
        #while idx_loss <= self.max_len//self.step:
        self.max_len = 8
        idx_loss = 0
        while idx_loss < 1:
            token_flipped = True
            while token_flipped:
                token_flipped = False
                with torch.set_grad_enabled(True):
                    self.model.zero_grad()
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

                        self.model.zero_grad()
                        with torch.no_grad():
                            loss, _ = self.compute_loss(
                                target_texts,
                                candidate_trigger_tokens,
                                idx_loss,
                                require_grad=False,
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
