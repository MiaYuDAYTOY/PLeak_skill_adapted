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

TRAIN_NUMS = [3]
PREFIX_LENGTHS = [8]
test_num = 20

dataFactory = DataFactory()
testset = dataFactory.get_dataset(dataset, train=False, num=test_num)
os.makedirs('results', exist_ok=True)

for train_num in TRAIN_NUMS:
    for prefix_length in PREFIX_LENGTHS:
        print(
            f'Running train_num={train_num}, '
            f'prefix_length={prefix_length}'
        )

        trainset = dataFactory.get_dataset(dataset,train=True,num=train_num,
        )
        random.seed(0)
        np.random.seed(0)
        torch.manual_seed(0)
        torch.cuda.manual_seed_all(0)
     
        attack = HotFlip(
            trigger_token_length=token_length,
            shadow_model=shadow_model,
            template=trainset.template,
            prefix_length=prefix_length,
        )
        attack.replace_triggers(trainset)

        triggers = attack.decode_triggers()
        trigger_token_ids = [
            int(token_id) for token_id in attack.trigger_tokens
        ]
        SEED = 0
        result_stem = (
            f'{dataset}_{token_length}_{shadow_model}_{target_model}_{train_num}_target_prefix{prefix_length}_seed{SEED}'
        )
        trigger_ids_path = f'results/{result_stem}.trigger_ids.json'
        with open(trigger_ids_path, 'w', encoding='utf-8') as file:
            json.dump(trigger_token_ids, file)

        print(f'Trigger token IDs saved to: {trigger_ids_path}')

        attack.model.zero_grad(set_to_none=True)
        del attack
        gc.collect()
        torch.cuda.empty_cache()

        if torch.cuda.is_available():
            torch.cuda.ipc_collect()

        print("GPU memory released; loading target model...")

        sampler = Sampler(
            target_model=target_model,
            template=testset.template,
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
        Sampler.save_to_csv(f'results/{result_stem}.csv',results,triggers,
        )
        sampler.evaluate_skill_leakage(results)

        del sampler
        gc.collect()
        torch.cuda.empty_cache()
