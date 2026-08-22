import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


class ModelFactory():
    def __init__(self):
        self.MODEL_CONF = {}

        self._register_model_config('gptj', 'EleutherAI/gpt-j-6b', 50400)
        self._register_model_config('opt', 'facebook/opt-6.7B', 50272)

        
        self._register_model_config(
            'llama',
            '/root/autodl-tmp/Llama-2-7b-hf',
            32000
        )

        self._register_model_config(
            'llama-70b',
            'meta-llama/Llama-2-70b-chat-hf',
            32000
        )

        self._register_model_config(
            'llama-chat',
            'meta-llama/Llama-2-7b-chat-hf',
            32000
        )

        self._register_model_config('falcon', 'tiiuae/falcon-7b', 65024)
        self._register_model_config('vicuna', 'lmsys/vicuna-7b-v1.5', 32000)


    def _register_model_config(self, name, alias, vocab_size):
        self.MODEL_CONF[name] = {
            'alias': alias,
            'vocab_size': vocab_size
        }


    def get_vocab_size(self, name):
        return self.MODEL_CONF[name]['vocab_size']


    def get_tokenizer(self, name):
        tokenizer = AutoTokenizer.from_pretrained(
            self.MODEL_CONF[name]["alias"],
            use_fast=True,
            local_files_only=(name == "llama"),
        )

        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token

        return tokenizer


    def get_model(self, name):
        model = AutoModelForCausalLM.from_pretrained(
            self.MODEL_CONF[name]['alias'],
            device_map="auto",
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            local_files_only=(name == "llama"),
        )

        model.config.use_cache = False

        return model.eval()
