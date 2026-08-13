import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
from webui.backend import datasets as datasets_mod


def make_dataset_dir(root: Path, name: str, screens: list[str]) -> Path:
    ds = root / name if name == "dataset" else root / "datasets" / name
    (ds / "images").mkdir(parents=True, exist_ok=True)
    (ds / "labels").mkdir(parents=True, exist_ok=True)
    for screen in screens:
        (ds / "labels" / f"{screen}_baseline.json").write_text("[]", encoding="utf-8")
        (ds / "images" / f"{screen}_baseline.png").write_bytes(b"\x89PNG")
    return ds


class DiscoverDatasetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.addCleanup(self.tmp_dir.cleanup)

    def patch_root(self):
        return mock.patch.object(paths, "PROJECT_ROOT", self.root)

    def test_no_dataset_dir_yields_empty_registry(self):
        with self.patch_root():
            self.assertEqual([], datasets_mod.discover_datasets())

    def test_default_dataset_is_flagged_default_and_not_archived(self):
        make_dataset_dir(self.root, "dataset", ["clock"])
        with self.patch_root():
            found = datasets_mod.discover_datasets()

        self.assertEqual(1, len(found))
        info = found[0]
        self.assertEqual("dataset", info.name)
        self.assertTrue(info.is_default)
        self.assertFalse(info.is_archived)
        self.assertEqual(1, info.screen_count)
        self.assertEqual(1, info.image_count)

    def test_archived_experiments_are_flagged_read_only(self):
        make_dataset_dir(self.root, "dataset", ["clock"])
        exp1 = self.root / "dataset" / "experiment_1"
        (exp1 / "images").mkdir(parents=True)
        (exp1 / "labels").mkdir(parents=True)
        (exp1 / "labels" / "clock_baseline.json").write_text("[]", encoding="utf-8")

        with self.patch_root():
            found = {d.name: d for d in datasets_mod.discover_datasets()}

        self.assertIn("experiment_1", found)
        self.assertTrue(found["experiment_1"].is_archived)
        self.assertFalse(found["experiment_1"].is_default)

    def test_user_datasets_directory_is_discovered_and_writable(self):
        make_dataset_dir(self.root, "dataset", ["clock"])
        (self.root / "datasets" / "my_app" / "images").mkdir(parents=True)
        (self.root / "datasets" / "my_app" / "labels").mkdir(parents=True)
        (self.root / "datasets" / "my_app" / "labels" / "home_baseline.json").write_text(
            "[]", encoding="utf-8"
        )

        with self.patch_root():
            found = {d.name: d for d in datasets_mod.discover_datasets()}

        self.assertIn("my_app", found)
        self.assertFalse(found["my_app"].is_archived)
        self.assertFalse(found["my_app"].is_default)

    def test_incomplete_directory_missing_labels_is_not_a_dataset(self):
        (self.root / "dataset" / "images").mkdir(parents=True)
        # No labels/ dir.
        with self.patch_root():
            self.assertEqual([], datasets_mod.discover_datasets())

    def test_resolve_dataset_path_returns_none_for_unknown_name(self):
        make_dataset_dir(self.root, "dataset", ["clock"])
        with self.patch_root():
            self.assertIsNone(datasets_mod.resolve_dataset_path("nonexistent"))
            self.assertEqual(
                self.root / "dataset", datasets_mod.resolve_dataset_path("dataset")
            )


if __name__ == "__main__":
    unittest.main()
