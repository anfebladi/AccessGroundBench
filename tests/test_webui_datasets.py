import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
from webui.backend.services import registry as registry_mod


def make_dataset_dir(root: Path, name: str, screens: list[str]) -> Path:
    """Build one run on disk. Every run has the same shape, including `experiment`."""
    ds = root / paths.COLLECTIONS_DIR_NAME / name / "dataset"
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
            self.assertEqual([], registry_mod.discover_datasets())

    def test_a_run_is_named_after_its_folder(self):
        make_dataset_dir(self.root, "experiment", ["clock"])
        with self.patch_root():
            found = registry_mod.discover_datasets()

        self.assertEqual(1, len(found))
        info = found[0]
        # The shipped data used to be registered under the literal name
        # "dataset" by a special case. It is now named like anything else.
        self.assertEqual("experiment", info.name)
        self.assertEqual(1, info.screen_count)
        self.assertEqual(1, info.image_count)

    def test_a_subdirectory_that_is_not_dataset_is_not_discovered(self):
        """Discovery looks only at collections/<name>/dataset/.

        Anything else a run happens to contain -- outputs/, a leftover folder --
        is not a candidate, which is what keeps the scan to one rule.
        """
        make_dataset_dir(self.root, "experiment", ["clock"])
        stray = self.root / "collections" / "experiment" / "leftover"
        (stray / "images").mkdir(parents=True)
        (stray / "labels").mkdir(parents=True)
        (stray / "labels" / "clock_baseline.json").write_text("[]", encoding="utf-8")

        with self.patch_root():
            found = {d.name: d for d in registry_mod.discover_datasets()}

        self.assertEqual(["experiment"], list(found))

    def test_a_collected_run_is_discovered_like_any_other(self):
        make_dataset_dir(self.root, "experiment", ["clock"])
        collection = make_dataset_dir(self.root, "my_app", ["home"])

        with self.patch_root():
            found = {d.name: d for d in registry_mod.discover_datasets()}

        self.assertIn("my_app", found)
        # Registered under the run's folder, pointing at the dataset/ inside it.
        self.assertEqual(collection, found["my_app"].path)

    def test_collection_without_a_dataset_subdir_is_skipped(self):
        """A cancelled collection or hand-made folder is not an empty dataset."""
        make_dataset_dir(self.root, "experiment", ["clock"])
        (self.root / "collections" / "half_done").mkdir(parents=True)

        with self.patch_root():
            found = {d.name: d for d in registry_mod.discover_datasets()}

        self.assertEqual(["experiment"], list(found))

    def test_every_run_is_listed_once_with_no_privileged_entry(self):
        """One uniform scan: no default, no duplicate, no reserved name.

        The shipped run used to be added explicitly *and* reached by the loop
        over collections/, so it needed a skip to avoid appearing twice -- once
        as "dataset" and once as "experiment". A single loop cannot do that.
        """
        make_dataset_dir(self.root, "experiment", ["clock"])
        make_dataset_dir(self.root, "my_app", ["home"])

        with self.patch_root():
            found = registry_mod.discover_datasets()

        names = [d.name for d in found]
        self.assertEqual(["experiment", "my_app"], sorted(names))
        self.assertNotIn("dataset", names)
        for info in found:
            self.assertFalse(hasattr(info, "is_default"))
            self.assertFalse(hasattr(info, "is_archived"))

    def test_incomplete_directory_missing_labels_is_not_a_dataset(self):
        (self.root / "collections" / "half_built" / "dataset" / "images").mkdir(parents=True)
        # No labels/ dir.
        with self.patch_root():
            self.assertEqual([], registry_mod.discover_datasets())

    def test_resolve_dataset_path_returns_none_for_unknown_name(self):
        make_dataset_dir(self.root, "experiment", ["clock"])
        with self.patch_root():
            self.assertIsNone(registry_mod.resolve_dataset_path("nonexistent"))
            self.assertEqual(
                self.root / "collections" / "experiment" / "dataset",
                registry_mod.resolve_dataset_path("experiment"),
            )


if __name__ == "__main__":
    unittest.main()
