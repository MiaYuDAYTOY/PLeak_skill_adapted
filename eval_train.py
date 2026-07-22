import csv

from DataFactory import DataFactory
from Sampler import Sampler


DATASET = "Samples"
TOKEN_LENGTH = 12
SHADOW_MODEL = "llama"
TARGET_MODEL = "llama"
TRAIN_NUM = 3

result_stem = (
    f"{DATASET}_{TOKEN_LENGTH}_{SHADOW_MODEL}_"
    f"{TARGET_MODEL}_{TRAIN_NUM}"
)
result_path = f"results/{result_stem}.csv"

with open(result_path, newline="", encoding="utf-8") as file:
    header = next(csv.reader(file))
    trigger = header[1]

print(f"Loaded trigger from: {result_path}")
print(f"Trigger repr: {trigger!r}")

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
)

output_path = f"results/{result_stem}_train.csv"
Sampler.save_to_csv(output_path, results, trigger)

for level in ["substring", "em", "edit", "semantic"]:
    sampler.evaluate(results, level=level)

print(f"Training evaluation saved to: {output_path}")
