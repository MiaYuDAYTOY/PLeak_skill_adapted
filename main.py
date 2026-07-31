import argparse
import gc
import json
from Attack import HotFlip
from Sampler import Sampler
import random
from datasets import load_dataset
import numpy as np
import torch
from datetime import datetime
from collections import OrderedDict
import os
from DataFactory import DataFactory
from util.loss_modes import VALID_LOSS_MODES


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def non_negative_int(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return parsed


def non_negative_float(value):
    parsed = float(value)
    if not np.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must be a finite non-negative number"
        )
    return parsed


def refresh_candidate_limit(value):
    parsed = positive_int(value)
    if parsed > 5:
        raise argparse.ArgumentTypeError("value must be at most 5")
    return parsed


def optional_positive_int(value):
    if value.lower() == "none":
        return None
    return positive_int(value)


parser = argparse.ArgumentParser(
    description="Run completion-style PLeak HotFlip optimization."
)
parser.add_argument("dataset")
parser.add_argument("token_length", type=positive_int)
parser.add_argument("shadow_model")
parser.add_argument("target_model")
parser.add_argument("train_num", type=positive_int)
parser.add_argument(
    "loss_mode",
    nargs="?",
    default="baseline",
    choices=sorted(VALID_LOSS_MODES),
)
parser.add_argument("--max-loss-tokens", type=positive_int, default=300)
parser.add_argument("--anchor-len", type=non_negative_int, default=64)
parser.add_argument("--frontier-window", type=non_negative_int, default=64)
parser.add_argument(
    "--improvement-epsilon",
    type=non_negative_float,
    default=1e-6,
)
parser.add_argument(
    "--max-refresh-candidates",
    type=refresh_candidate_limit,
    default=5,
)
parser.add_argument(
    "--max-frontier-tokens",
    type=optional_positive_int,
    default=1000,
    help="positive integer, or 'none' to optimize the complete target",
)
args = parser.parse_args()

random.seed(0)
np.random.seed(0)
torch.random.manual_seed(0)
torch.cuda.manual_seed(0)

dataset = args.dataset
token_length = args.token_length
shadow_model = args.shadow_model
target_model = args.target_model
train_num = args.train_num
loss_mode = args.loss_mode
test_num = 10

print(
    "Attack config: "
    f"loss_mode={loss_mode}, "
    f"max_loss_tokens={args.max_loss_tokens}, "
    f"anchor_len={args.anchor_len}, "
    f"frontier_window={args.frontier_window}, "
    f"max_frontier_tokens={args.max_frontier_tokens}, "
    f"improvement_epsilon={args.improvement_epsilon}, "
    f"max_refresh_candidates={args.max_refresh_candidates}"
)

dataFactory = DataFactory()
trainset = dataFactory.get_dataset(dataset, train=True, num=train_num)
testset = dataFactory.get_dataset(dataset, train=False, num=test_num)
attack = HotFlip(
    trigger_token_length=token_length,
    shadow_model=shadow_model,
    template=trainset.template,
    loss_mode=loss_mode,
    max_loss_tokens=args.max_loss_tokens,
    anchor_len=args.anchor_len,
    frontier_window=args.frontier_window,
    max_frontier_tokens=args.max_frontier_tokens,
    improvement_epsilon=args.improvement_epsilon,
    max_refresh_candidates=args.max_refresh_candidates,
)
attack.replace_triggers(trainset)

triggers = attack.decode_triggers()
trigger_token_ids = [int(token_id) for token_id in attack.trigger_tokens]

os.makedirs('results', exist_ok=True)
result_stem = (
    f'{dataset}_{token_length}_{shadow_model}_'
    f'{target_model}_{train_num}_{loss_mode}'
)
trigger_ids_path = f'results/{result_stem}.trigger_ids.json'
with open(trigger_ids_path, 'w', encoding='utf-8') as file:
    json.dump(trigger_token_ids, file)

print(f'Trigger token IDs saved to: {trigger_ids_path}')

# 释放攻击阶段的梯度和模型
attack.model.zero_grad(set_to_none=True)
del attack

gc.collect()
torch.cuda.empty_cache()

if torch.cuda.is_available():
    torch.cuda.ipc_collect()

print("GPU memory released; loading target model...")

sampler = Sampler(
    target_model=target_model,
    template=testset.template
)
results = sampler.sample_sequence(
    testset,
    triggers=triggers,
    trigger_token_ids=(
        trigger_token_ids
        if shadow_model == target_model
        else None
    ),
)
Sampler.save_to_csv(f'results/{result_stem}.csv', results, triggers)

sampler.evaluate_skill_leakage(results)
