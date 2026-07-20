import os

from DataFactory import DataFactory
from Sampler import Sampler


DATASET = "Financial"
TARGET_MODEL = "llama"
TEST_NUM = 20

# 把你从终端复制的完整 trigger 粘贴到这里
TRIGGER = """
sentimentlearning sind origin sindbibliothek prima partially dieser instruction somewhat dup
""".strip()


def main():
    if not TRIGGER:
        raise ValueError("TRIGGER 不能为空")

    print(f"Using trigger: {TRIGGER}")

    data_factory = DataFactory()
    testset = data_factory.get_dataset(
        DATASET,
        train=False,
        num=TEST_NUM,
    )

    # 这里只加载一份 target LLaMA
    sampler = Sampler(
        target_model=TARGET_MODEL,
        template=testset.template,
    )

    results = sampler.sample_sequence(
        testset,
        triggers=TRIGGER,
    )

    os.makedirs("results", exist_ok=True)
    output_path = (
        f"results/{DATASET}_12_llama_manual_trigger_16.csv"
    )

    Sampler.save_to_csv(
        output_path,
        results,
        TRIGGER,
    )

    if results:
        sampler.evaluate(results, level="substring")
        sampler.evaluate(results, level="em")
        sampler.evaluate(results, level="edit")
        sampler.evaluate(results, level="semantic")

    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()