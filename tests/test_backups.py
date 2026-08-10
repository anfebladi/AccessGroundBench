"""Tests for the copy-aside protection around destructive result writes.

The data these guard is expensive (a full evaluation run is ~1000 paid API
calls per model) and, for the schema-mismatch path, discarded by a command the
operator did not ask anything unusual of.
"""

import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import backups
import paths
from analysis.data.results import discover_result_csvs, model_name_from_path
from analysis.reports.output import write_outputs
from backups import BACKUP_DIR_NAME, BackupError, preserve
from evaluation.storage.results import CSV_COLUMNS, prepare_csv


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class PreserveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_missing_target_is_not_an_error(self):
        self.assertIsNone(preserve(self.dir / "nope.csv", reason="test"))

    def test_file_contents_survive_in_the_backup(self):
        target = self.dir / "results.csv"
        target.write_text("a,b\n1,2\n", encoding="utf-8")

        backup = preserve(target, reason="test")

        self.assertEqual("a,b\n1,2\n", backup.read_text(encoding="utf-8"))
        self.assertEqual(BACKUP_DIR_NAME, backup.parent.name)
        self.assertEqual(".csv", backup.suffix)

    def test_directories_are_copied_whole(self):
        target = self.dir / "vision_all"
        target.mkdir()
        (target / "reachability_results.csv").write_text("committed\n", encoding="utf-8")

        backup = preserve(target, reason="test")

        self.assertEqual(
            "committed\n",
            (backup / "reachability_results.csv").read_text(encoding="utf-8"),
        )

    def test_repeated_backups_accumulate_instead_of_overwriting(self):
        """The old `.bak` convention was one slot; the second run destroyed the first."""
        target = self.dir / "results.csv"
        target.write_text("first\n", encoding="utf-8")
        first = preserve(target, reason="test")
        target.write_text("second\n", encoding="utf-8")
        second = preserve(target, reason="test")

        self.assertNotEqual(first, second)
        self.assertEqual("first\n", first.read_text(encoding="utf-8"))
        self.assertEqual("second\n", second.read_text(encoding="utf-8"))

    def test_a_failed_backup_raises_so_the_caller_cannot_destroy_anything(self):
        target = self.dir / "results.csv"
        target.write_text("precious\n", encoding="utf-8")

        with mock.patch.object(backups.shutil, "copy2", side_effect=OSError("disk full")):
            with self.assertRaises(BackupError):
                preserve(target, reason="test")

        self.assertEqual("precious\n", target.read_text(encoding="utf-8"))


class PrepareCsvPreservationTests(unittest.TestCase):
    """prepare_csv has two paths that discard rows; both must copy first."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv_path = Path(self.tmp.name) / "gpt-5.4_vision.csv"

    def paid_rows(self) -> list[list[str]]:
        row = ["clock", "8:30 AM", "baseline", "co_present", "[1, 2]", "1", "2",
               "0", "0", "10", "10", "1"]
        return [row + [""] * (len(CSV_COLUMNS) - len(row))]

    def test_unresumable_schema_preserves_every_row_before_truncating(self):
        # The silent one: reached by an ordinary resume, not by --fresh.
        # A renamed leading column makes the header non-additive.
        stale_header = ["screen_name"] + CSV_COLUMNS[1:]
        write_csv(self.csv_path, stale_header, self.paid_rows())

        prepare_csv(self.csv_path, fresh=False)

        backups_made = list((self.csv_path.parent / BACKUP_DIR_NAME).glob("*.csv"))
        self.assertEqual(1, len(backups_made))
        saved = read_rows(backups_made[0])
        self.assertEqual(1, len(saved))
        self.assertEqual("8:30 AM", saved[0]["target_text"])
        # And the live file really was reset, so the backup is the only copy.
        self.assertEqual([], read_rows(self.csv_path))

    def test_fresh_preserves_the_discarded_rows(self):
        write_csv(self.csv_path, CSV_COLUMNS, self.paid_rows())

        prepare_csv(self.csv_path, fresh=True)

        backups_made = list((self.csv_path.parent / BACKUP_DIR_NAME).glob("*.csv"))
        self.assertEqual(1, len(backups_made))
        self.assertEqual(1, len(read_rows(backups_made[0])))
        self.assertEqual([], read_rows(self.csv_path))

    def test_a_resumable_file_is_not_backed_up(self):
        """No churn on the common path: resuming touches nothing."""
        write_csv(self.csv_path, CSV_COLUMNS, self.paid_rows())

        completed = prepare_csv(self.csv_path, fresh=False)

        self.assertEqual({("clock", "8:30 AM", "baseline")}, completed)
        self.assertFalse((self.csv_path.parent / BACKUP_DIR_NAME).exists())


class WriteOutputsPreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "vision_all"

    def test_existing_tables_are_preserved_before_being_replaced(self):
        self.out.mkdir(parents=True)
        committed = self.out / "reachability_results.csv"
        committed.write_text("Profile,Reachability\nold,0.99\n", encoding="utf-8")

        write_outputs(self.out, [], [], [], [])

        backup_dirs = list((self.out.parent / BACKUP_DIR_NAME).iterdir())
        self.assertEqual(1, len(backup_dirs))
        self.assertEqual(
            "Profile,Reachability\nold,0.99\n",
            (backup_dirs[0] / "reachability_results.csv").read_text(encoding="utf-8"),
        )
        # The live table is the new run's, not the old one's.
        self.assertNotIn("old,0.99", committed.read_text(encoding="utf-8"))


class BackupsAreInvisibleToDiscoveryTests(unittest.TestCase):
    """A backup must never be mistaken for another model's results.

    discover_result_csvs globs `*_<mode>.csv` in a dataset's evaluations
    directory. If backups sat beside the originals, each one would be
    discovered as an extra model and silently inflate the pooled permutation
    test's sample -- the same class of defect as pooling the vision and tree
    arms together.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch = mock.patch.object(paths, "PROJECT_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.dataset = self.root / "dataset"
        (self.dataset / "labels").mkdir(parents=True)

    def test_discovery_ignores_backed_up_copies(self):
        live = paths.evaluation_results_path("openai/gpt-4o", False, self.dataset)
        write_csv(live, CSV_COLUMNS, [])
        for _ in range(3):
            preserve(live, reason="test")

        found = discover_result_csvs(self.dataset, "vision")

        self.assertEqual([live], found)
        self.assertEqual(3, len(list((live.parent / BACKUP_DIR_NAME).glob("*.csv"))))

    def test_model_name_is_never_derived_from_a_backup(self):
        live = paths.evaluation_results_path("openai/gpt-4o", False, self.dataset)
        write_csv(live, CSV_COLUMNS, [])
        preserve(live, reason="test")

        for path in discover_result_csvs(self.dataset, "vision"):
            self.assertEqual("openai_gpt-4o", model_name_from_path(path))


if __name__ == "__main__":
    unittest.main()
