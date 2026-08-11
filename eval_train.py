import csv
import json

from DataFactory import DataFactory
from Sampler import Sampler


DATASET = "webtesting"
TOKEN_LENGTH = 12
SHADOW_MODEL = "llama"
TARGET_MODEL = "llama"
TRAIN_NUM = 3

result_stem = (
    f'{DATASET}_{TOKEN_LENGTH}_{SHADOW_MODEL}_{TARGET_MODEL}_{TRAIN_NUM}_target_prefix8'
)
result_path = f"results/{result_stem}.csv"
trigger_ids_path = f"results/{result_stem}.trigger_ids.json"

def load_trigger(result_path, trigger_ids_path):
    with open(result_path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        first_result = next(reader, None)

        if "trigger" in fieldnames:
            if first_result is None:
                raise ValueError(f"结果 CSV 没有数据行: {result_path}")
            trigger = first_result["trigger"]
        elif len(fieldnames) >= 2:
            # The old format stored trigger text as the second column name.
            trigger = fieldnames[1]
        else:
            raise ValueError(f"结果 CSV 中找不到 trigger: {result_path}")

    with open(trigger_ids_path, encoding="utf-8") as file:
        trigger_token_ids = [
            int(token_id)
            for token_id in json.load(file)
        ]

    return trigger, trigger_token_ids


trigger, trigger_token_ids = load_trigger(
    result_path,
    trigger_ids_path,
)

print(f"Loaded trigger from: {result_path}")
print(f"Trigger repr: {trigger!r}")
print(f"Trigger token IDs: {trigger_token_ids}")

data_factory = DataFactory()
trainset = data_factory.get_dataset(
    DATASET,
    train=True,
    num=TRAIN_NUM,
)

print(f"Training samples: {len(trainset)}")

sampler = Sampler(
    target_model=TARGET_MODEL,
    template=trainset.template,
)

results = sampler.sample_sequence(
    trainset,
    triggers=trigger,
    trigger_token_ids=trigger_token_ids,
)

output_path = f"results/{result_stem}_train.csv"
Sampler.save_to_csv(output_path, results, trigger)

sampler.evaluate_skill_leakage(results)

print(f"Training evaluation saved to: {output_path}")
