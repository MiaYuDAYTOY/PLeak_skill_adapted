from torch.utils.data import Dataset
from datasets import load_dataset
from util.template import TextTemplate
import random
import hashlib
from copy import copy

from pathlib import Path

class Samples(Dataset):
    def __init__(self, train, num=16, data_dir="data/samples"):
        files = sorted(Path(data_dir).rglob("SKILL.md"))

        rng = random.Random(0)
        rng.shuffle(files)

        split = int(len(files) * 0.8)
        files = files[:split] if train else files[split:]
        files = files[:num]

        self.dataset = [
            {"content": path.read_text(encoding="utf-8")}
            for path in files
        ]

        self.template = TextTemplate(prefix_1="", prefix_2="")

    def __getitem__(self, idx):
        content = self.dataset[idx]["content"]
        return content if content.endswith("\n") else content + "\n"

    def __len__(self):
        return len(self.dataset)


class SkillDataset(Samples):
    """A single skill category with a fixed 30/70 train/test split."""

    def __init__(self, train, num=16, *, data_dir, seed=None):
        files = sorted(Path(data_dir).rglob("SKILL.md"))

        rng = random.Random(0)
        rng.shuffle(files)

        split = int(len(files) * 0.3)
        files = files[:split] if train else files[split:]
        self.train = train
        self.pool_size = len(files)
        pool_name = "train" if train else "test"
        if not self.pool_size:
            raise ValueError(f"The {pool_name} pool is empty: {data_dir}.")
        if num is not None:
            if isinstance(num, bool) or not isinstance(num, int) or num <= 0:
                raise ValueError(f"{pool_name}_num must be a positive integer or None.")
            if num > self.pool_size:
                raise ValueError(
                    f"{pool_name}_num={num} exceeds the available {pool_name} pool "
                    f"({self.pool_size} samples)."
                )
        if seed is None:
            # Keep the original deterministic prefix selection; None loads the pool.
            files = files[:num]

        self.dataset = [
            {"content": path.read_text(encoding="utf-8")}
            for path in files
        ]
        self.sample_metadata = [
            {
                "path": str(path.resolve()),
                "pool_index": index,
                "content_sha256": hashlib.sha256(self[index].encode("utf-8")).hexdigest(),
            }
            for index, path in enumerate(files)
        ]

        self.template = TextTemplate(prefix_1="", prefix_2="")
        if seed is not None:
            selected = self.sample(num=num, seed=seed)
            self.dataset = selected.dataset
            self.sample_metadata = selected.sample_metadata

    def sample(self, num, seed):
        """Sample a loaded training pool without replacement using a local RNG."""
        if not self.train:
            raise ValueError("Random sampling is only supported for the train pool.")
        if isinstance(num, bool) or not isinstance(num, int) or num <= 0:
            raise ValueError("train_num must be a positive integer.")
        if num > len(self):
            raise ValueError(
                f"train_num={num} exceeds the available train pool ({len(self)} samples)."
            )
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer.")
        indices = random.Random(seed).sample(range(len(self)), num)
        selected = copy(self)
        selected.dataset = [self.dataset[index].copy() for index in indices]
        selected.sample_metadata = [self.sample_metadata[index].copy() for index in indices]
        return selected

class WebTesting(SkillDataset):
    def __init__(self, train, num=16, seed=None):
        super().__init__(train=train, num=num, data_dir="data/webapp", seed=seed)

class Financial(Dataset):
    def __init__(self, train, num=16, num_shots=1, prefix_1='text:', prefix_2='label:',with_instruction=True):
        dataset = load_dataset("financial_phrasebank","sentences_allagree")
        self.dataset = random.choices(dataset["train"], k=num*num_shots)
        self.num_shots = num_shots
        self.label = ['Negative', 'Neutral', 'Positive']
        self.template = TextTemplate(prefix_1 = prefix_1, prefix_2=prefix_2)
        self.with_instruction = with_instruction
        self.instruction_prefix = "instruction:"
        instruction_files = "util/instruction.csv" if train else "util/instruction_attack.csv"
        self.instructions = random.choices(load_dataset("csv", data_files=instruction_files)['train']['prompts'], k=num)
        self.num_shots = num_shots

    def __getitem__(self, idx):
        ret = self.instruction_prefix + self.instructions[idx] + "\n\n" if self.with_instruction else ''
        # instruction = random.choices(self.instructions, k=1)
        # ret = self.instruction_prefix + instruction[0] + "\n\n" if self.with_instruction else ''
        for i in range(self.num_shots):
            ret += self.template(self.dataset[idx*self.num_shots+i]['sentence'], self.label[self.dataset[idx*self.num_shots+i]['label']])

        return ret

    def __len__(self):
        return len(self.dataset)


class Tomatoes(Dataset):
    def __init__(self, train, num=16, num_shots=1, prefix_1='text:', prefix_2='label:', with_instruction=True):
        dataset = load_dataset("rotten_tomatoes")
        self.dataset = random.choices(dataset["train"], k=num*num_shots)
        self.label = ['Negative', 'Positive']
        self.template = TextTemplate(prefix_1 = prefix_1, prefix_2=prefix_2)
        self.with_instruction = with_instruction
        self.instruction_prefix = "instruction:"
        instruction_files = "util/instruction.csv" if train else "util/instruction_attack.csv"
        self.num_shots = num_shots
        self.instructions = random.choices(load_dataset("csv", data_files=instruction_files)['train']['prompts'], k=num)
        self.num_shots = num_shots
    def __getitem__(self, idx):
        ret = self.instruction_prefix + self.instructions[idx] + "\n\n" if self.with_instruction else ''
        for i in range(self.num_shots):
            ret += self.template(self.dataset[idx*self.num_shots+i]['text'], self.label[self.dataset[idx*self.num_shots+i]['label']])

        return ret
    
    def __len__(self):
        return len(self.dataset)


class SQuAD(Dataset):
    def __init__(self, train, num=16, prefix_1='context:'):
        dataset = load_dataset("squad")
        self.dataset = random.choices(dataset["train"], k=num)
        self.prefix_1 = prefix_1
        self.template = TextTemplate(prefix_1 = prefix_1)

    def __getitem__(self, idx):
        return self.template(self.dataset[idx]['context'])

    def __len__(self):
        return len(self.dataset)


class SIQA(Dataset):
    def __init__(self, train, num=16, prefix_1='context:'):
        dataset = load_dataset("social_i_qa")
        self.dataset = random.choices(dataset['train']['context'], k=num)
        self.template = TextTemplate(prefix_1 = prefix_1)

    def __getitem__(self, idx):
        return self.template(self.dataset[idx])

    def __len__(self):
        return len(self.dataset)


class Roles(Dataset):
    def __init__(self, train, num=16, prefix_1=''):
        dataset = load_dataset("csv", data_files="util/roles.csv")
        num = num if num < len(dataset['train']['instruction']) else len(dataset['train']['instruction'])
        self.dataset = random.choices(dataset['train']['instruction'], k=num)
        self.template = TextTemplate(prefix_1 = '', prefix_2='')
        self.prefix_1 = prefix_1

    def __getitem__(self, idx):
        return self.prefix_1 + self.dataset[idx] + '\n'

    def __len__(self):
        return len(self.dataset)


class Harmful(Dataset):
    def __init__(self, train, num=16, prefix_1=''):
        dataset = load_dataset("csv", data_files="util/harmful_behaviors.csv")
        self.dataset = random.choices(dataset['train']['goal'], k=num)

    def __getitem__(self, idx):
        return self.dataset[idx]

    def __len__(self):
        return len(self.dataset)


class Mol(Dataset):
    def __init__(self, train, num=16, prefix_1='instruction:'):
        dataset = load_dataset("zjunlp/Mol-Instructions", 'Molecule-oriented Instructions')
        self.dataset = random.choices(dataset['description_guided_molecule_design']['instruction'], k=num)
        self.prefix_1 = prefix_1

    def __getitem__(self, idx):
        ret = self.prefix_1 + self.dataset[idx] + '\n'
        return ret

    def __len__(self):
        return len(self.dataset)


class Alpaca(Dataset):
    def __init__(self, train, num=16, prefix_1='instruction:'):
        dataset = load_dataset("tatsu-lab/alpaca")
        self.dataset = random.choices(dataset['train']['instruction'], k=num)
        self.prefix_1 = prefix_1

    def __getitem__(self, idx):
        ret = self.prefix_1 + self.dataset[idx] + '\n'
        return ret

    def __len__(self):
        return len(self.dataset)


class Articles(Dataset):
    def __init__(self, train, num=16, prefix_1='instruction:'):
        dataset = load_dataset("nisaar/Articles_Constitution_3300_Instruction_Set")
        self.dataset = random.choices(dataset['train']['instruction'], k=num)
        self.prefix_1 = prefix_1

    def __getitem__(self, idx):
        ret = self.prefix_1 + self.dataset[idx] + '\n'
        return ret

    def __len__(self):
        return len(self.dataset)


class SST(Dataset):
    def __init__(self, train, num=16, prefix_1='sentence:', prefix_2='label:', with_instruction=False):
        dataset = load_dataset("sst2")
        self.dataset = random.choices(dataset["train"], k=num)
        self.label = ['Negative', 'Positive']
        self.template = TextTemplate(prefix_1 = prefix_1, prefix_2=prefix_2)
        self.instruction_prefix = "instruction:"
        self.instruction = (self.instruction_prefix+"Please analyze the sentiment of following sentences.\n\n") if with_instruction else ''
    
    def __getitem__(self, idx):
        return self.instruction + self.template(self.dataset[idx]['sentence'], self.label[self.dataset[idx]['label']])
    
    def __len__(self):
        return len(self.dataset)


class Awesome(Dataset):
    def __init__(self, train, num=16, prefix_1='context:'):
        dataset = load_dataset("fka/awesome-chatgpt-prompts")
        num = num if num < len(dataset['train']['prompt']) else len(dataset['train']['prompt'])
        self.dataset = random.choices(dataset['train']['prompt'], k=num)
        self.template = TextTemplate(prefix_1 = '', prefix_2='')
        self.prefix_1 = prefix_1

    def __getitem__(self, idx):
        return self.prefix_1 + self.dataset[idx] + '\n'

    def __len__(self):
        return len(self.dataset)
