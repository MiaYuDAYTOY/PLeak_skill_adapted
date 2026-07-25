from __future__ import annotations

from typing import Sequence


class SkillChatPromptBuilder:
    """
    为 Attack 和 Sampler 构造完全一致的 Skill Chat 输入。

    结构：

    system:
        SKILL.md

    user:
        trigger token IDs

    assistant:
        训练时为 SKILL.md
        推理时为空，等待模型生成
    """

    # 先用一个普通文本占位符生成完整 chat template，
    # 再在 token 层面把它替换成真正的 trigger token IDs。
    TRIGGER_SLOT = "PLEAK_TRIGGER_SLOT_7F3A91"

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

        if tokenizer.chat_template is None:
            raise ValueError(
                "当前 tokenizer 没有 chat_template。"
                "请使用 chat/instruct 模型，例如 llama-chat。"
            )

        # 后面需要 offset_mapping 定位 trigger 占位符。
        if not getattr(tokenizer, "is_fast", False):
            raise ValueError(
                "SkillChatPromptBuilder 需要 fast tokenizer，"
                "因为需要 return_offsets_mapping 定位 trigger。"
            )

    def _replace_trigger_slot(
        self,
        messages: list[dict[str, str]],
        trigger_token_ids: Sequence[int],
        *,
        add_generation_prompt: bool,
    ) -> list[int]:
        """
        1. 用占位符渲染 chat template
        2. 找到占位符对应的 token 范围；
        3. 直接替换成 HotFlip 的 trigger token IDs。

        这样不会发生：
            trigger IDs -> decode -> encode -> 新 IDs
        """

        rendered_text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
        )

        if rendered_text.count(self.TRIGGER_SLOT) != 1:
            raise ValueError(
                "chat template 中 trigger 占位符出现次数不是 1。"
            )

        slot_char_start = rendered_text.index(self.TRIGGER_SLOT)
        slot_char_end = slot_char_start + len(self.TRIGGER_SLOT)

        # apply_chat_template 已经添加了模型需要的特殊 token，
        # 因此这里不能再次 add_special_tokens=True。
        encoded = self.tokenizer(
            rendered_text,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )

        input_ids = list(encoded["input_ids"])
        offsets = list(encoded["offset_mapping"])

        slot_token_positions = []

        for token_index, (char_start, char_end) in enumerate(offsets):
            overlaps_slot = (
                char_start < slot_char_end
                and char_end > slot_char_start
            )

            if overlaps_slot:
                slot_token_positions.append(token_index)

        if not slot_token_positions:
            raise ValueError(
                "无法在 tokenized chat prompt 中定位 trigger 占位符。"
            )

        left = slot_token_positions[0]
        right = slot_token_positions[-1] + 1

        trigger_ids = [
            int(token_id)
            for token_id in trigger_token_ids
        ]

        prompt_ids = (
            input_ids[:left]
            + trigger_ids
            + input_ids[right:]
        )

        # 确保插入后的序列中确实存在完整 trigger IDs。
        inserted_ids = prompt_ids[left:left + len(trigger_ids)]

        if inserted_ids != trigger_ids:
            raise ValueError(
                "插入 Chat prompt 后的 trigger IDs 发生变化。"
            )

        return prompt_ids

    def build_prompt_ids(
        self,
        skill_text: str,
        trigger_token_ids: Sequence[int],
    ) -> list[int]:
        """
        推理输入：

        system: SKILL.md
        user: trigger
        assistant:
        """

        messages = [
            {
                "role": "system",
                "content": skill_text,
            },
            {
                "role": "user",
                "content": self.TRIGGER_SLOT,
            },
        ]

        return self._replace_trigger_slot(
            messages,
            trigger_token_ids,
            add_generation_prompt=True,
        )

    def build_training_ids(
        self,
        skill_text: str,
        trigger_token_ids: Sequence[int],
    ) -> tuple[list[int], list[int]]:
        """
        返回：

        prompt_ids:
            system + Skill + user + trigger + assistant header

        full_ids:
            prompt_ids + assistant Skill target
        """

        prompt_ids = self.build_prompt_ids(
            skill_text,
            trigger_token_ids,
        )

        messages = [
            {
                "role": "system",
                "content": skill_text,
            },
            {
                "role": "user",
                "content": self.TRIGGER_SLOT,
            },
            {
                "role": "assistant",
                "content": skill_text,
            },
        ]

        full_ids = self._replace_trigger_slot(
            messages,
            trigger_token_ids,
            add_generation_prompt=False,
        )

        # 训练输入和推理输入必须具有完全相同的 prompt 前缀。
        if full_ids[:len(prompt_ids)] != prompt_ids:
            raise ValueError(
                "训练 Chat 和推理 Chat 的 prompt 前缀不一致。\n"
                "请检查模型的 chat_template。"
            )

        return prompt_ids, full_ids
