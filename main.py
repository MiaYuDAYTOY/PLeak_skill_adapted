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
import sys

random.seed(0)
np.random.seed(0)
torch.random.manual_seed(0)
torch.cuda.manual_seed(0)

dataset = sys.argv[1]
token_length = int(sys.argv[2])
shadow_model = sys.argv[3]
target_model = sys.argv[4]
train_num = int(sys.argv[5])
test_num = 10

dataFactory = DataFactory()
trainset = dataFactory.get_dataset(dataset, train=True, num=train_num)
testset = dataFactory.get_dataset(dataset, train=False, num=test_num)
attack = HotFlip(trigger_token_length=token_length, shadow_model=shadow_model, template=trainset.template)
attack.replace_triggers(trainset)

triggers = attack.decode_triggers()
trigger_token_ids = [int(token_id) for token_id in attack.trigger_tokens]

os.makedirs('results', exist_ok=True)
#result_stem = f'{dataset}_{token_length}_{shadow_model}_{target_model}_{train_num}'
result_stem = (f'{dataset}_{token_length}_{shadow_model}_{target_model}_{train_num}_target_prefix8')
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
