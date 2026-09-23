from functools import partial
from pathlib import Path

from util.data import SkillDataset


SKILL_CATEGORIES = (
    "documents",
    "data_analysis",
    "software_development",
    "information_retrieval",
    "workflow",
    "content_creation",
    "scientific_research",
    "security",
    "cloud",
    "marketing",
    "product_management",
)

class DataFactory:
    def __init__(self):
        data_root = Path(__file__).resolve().parent / "data/skill_expansion_20260922/samples"
        self._creator = {}
        for category in SKILL_CATEGORIES:
            self._creator[category] = partial(
                SkillDataset,
                data_dir=data_root / category,
            )

    def get_dataset(self, name, **kwargs):
        creator = self._creator.get(name)
        if creator is None:
            raise ValueError(f"Unknown dataset: {name!r}.")
        return creator(**kwargs)

    @staticmethod
    def validate_split(train_pool, testset):
        """Reject duplicate paths/content and overlap before starting an experiment."""
        if not isinstance(train_pool, SkillDataset) or not isinstance(testset, SkillDataset):
            raise ValueError("Split validation only supports expanded skill categories.")
        if not train_pool.train or testset.train:
            raise ValueError("Expected a train pool and a test set from their respective splits.")

        identities = {}
        for label, dataset in (("train pool", train_pool), ("test set", testset)):
            identities[label] = {}
            for key in ("path", "content_sha256"):
                seen = {}
                for metadata in dataset.sample_metadata:
                    value = metadata[key]
                    if value in seen:
                        raise ValueError(
                            f"Duplicate {key} in {label}: {seen[value]} and {metadata['path']}."
                        )
                    seen[value] = metadata["path"]
                identities[label][key] = seen

        for key in ("path", "content_sha256"):
            overlap = identities["train pool"][key].keys() & identities["test set"][key].keys()
            if overlap:
                value = sorted(overlap)[0]
                raise ValueError(
                    f"Train/test data leakage ({key}): "
                    f"{identities['train pool'][key][value]} and "
                    f"{identities['test set'][key][value]}."
                )
