import os

import torch
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig


class ModelFactory():
    def __init__(self):
        self.MODEL_CONF = {}

        self._register_model_config('gptj', 'EleutherAI/gpt-j-6b')
        self._register_model_config('opt', 'facebook/opt-6.7B')

        
        self._register_model_config(
            'llama',
            '/root/autodl-tmp/Llama-2-7b-hf',
            local_files_only=True,
        )

        self._register_model_config(
            'llama-70b',
            'meta-llama/Llama-2-70b-chat-hf',
        )

        self._register_model_config(
            'llama-chat',
            'meta-llama/Llama-2-7b-chat-hf',
        )

        self._register_model_config('falcon', 'tiiuae/falcon-7b')
        self._register_model_config('vicuna', 'lmsys/vicuna-7b-v1.5')
        qwen_path = os.environ.get('PLEAK_QWEN3_MODEL_PATH')
        self._register_model_config(
            'qwen3', qwen_path or 'Qwen/Qwen3-0.6B-Base',
            load_in_4bit=False, local_files_only=bool(qwen_path),
        )


    def _register_model_config(self, name, alias, *, load_in_4bit=True, local_files_only=False):
        self.MODEL_CONF[name] = {
            'alias': alias,
            'load_in_4bit': load_in_4bit,
            'local_files_only': local_files_only,
        }


    def get_vocab_size(self, name):
        # Includes added tokens, but never includes unused embedding padding rows.
        return len(self.get_tokenizer(name))

    def get_generation_kwargs(self, name):
        kwargs = {
            'num_beams': 3,
            'remove_invalid_values': True,
            'renormalize_logits': True,
        }
        if 'llama' in name or name == 'qwen3':
            kwargs.update(do_sample=True, temperature=0.9, top_p=0.6)
        if name == 'qwen3':
            # Match the existing Llama experiment's sampling settings explicitly.
            # These are experiment settings, not Qwen Instruct/thinking defaults.
            kwargs.update(top_k=50, repetition_penalty=1.0, length_penalty=1.0,
                          num_return_sequences=1, early_stopping=False, use_cache=True)
        return kwargs

    def get_runtime_config(self, name):
        config = self.MODEL_CONF[name]
        return {
            'model_path': config['alias'],
            'quantization': '4bit' if config['load_in_4bit'] else 'none',
            'prompt_format': 'plain_text',
            'attack_loss': ('supervised_qwen_logits_v1' if name == 'qwen3'
                            else 'full_causal_lm'),
            'generation': self.get_generation_kwargs(name),
        }

    def get_context_limit(self, name):
        """Read the context limit without loading model weights."""
        config = AutoConfig.from_pretrained(
            self.MODEL_CONF[name]["alias"],
            local_files_only=self.MODEL_CONF[name]['local_files_only'],
        )
        limit = getattr(config, "max_position_embeddings", None)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError(f"No valid max_position_embeddings for {name!r}")
        return limit


    def get_tokenizer(self, name):
        tokenizer = AutoTokenizer.from_pretrained(
            self.MODEL_CONF[name]["alias"],
            use_fast=True,
            local_files_only=self.MODEL_CONF[name]['local_files_only'],
        )

        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token

        return tokenizer


    def get_model(self, name, compute_dtype=None):
        # Qwen3 Base defaults to full BF16 weights; legacy models keep 4-bit.
        if compute_dtype not in (None, torch.float16, torch.bfloat16):
            raise ValueError("compute_dtype must be float16 or bfloat16")
        compute_dtype = torch.bfloat16 if compute_dtype is None else compute_dtype
        config = self.MODEL_CONF[name]
        options = dict(device_map="auto", torch_dtype=compute_dtype,
                       local_files_only=config['local_files_only'])
        if config['load_in_4bit']:
            options['quantization_config'] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=compute_dtype,
            )
        model = AutoModelForCausalLM.from_pretrained(config['alias'], **options)

        model.config.use_cache = False

        return model.eval()
