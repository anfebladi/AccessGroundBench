"""Regression tests for repository-root paths under the src layout."""

import unittest
from pathlib import Path

from collection import orchestrator
from collection.capture import screenshot_pipeline
from mcnemar import cli as mcnemar_cli
from vlm_eval import config as vlm_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectPathTests(unittest.TestCase):
    def test_collection_dataset_paths_use_repository_root(self):
        self.assertEqual(PROJECT_ROOT / "dataset", orchestrator.DATASET_DIR)
        self.assertEqual(PROJECT_ROOT / "dataset" / "images", orchestrator.IMAGES_DIR)
        self.assertEqual(PROJECT_ROOT / "dataset" / "raw_xml", orchestrator.RAW_XML_DIR)
        self.assertEqual(PROJECT_ROOT / "dataset" / "labels", orchestrator.LABELS_DIR)

    def test_evaluation_paths_use_repository_root(self):
        self.assertEqual(PROJECT_ROOT, vlm_config.PROJECT_ROOT)
        self.assertEqual(PROJECT_ROOT / "dataset", vlm_config.DATASET_DIR)
        self.assertEqual(PROJECT_ROOT / "dataset" / "images", vlm_config.IMAGES_DIR)
        self.assertEqual(PROJECT_ROOT / "dataset" / "labels", vlm_config.LABELS_DIR)
        self.assertEqual(
            PROJECT_ROOT / "outputs" / "evaluation_results",
            vlm_config.EVALUATION_RESULTS_DIR,
        )

    def test_mcnemar_paths_use_repository_root(self):
        self.assertEqual(PROJECT_ROOT, mcnemar_cli.PROJECT_ROOT)

    def test_mcnemar_output_directory_names(self):
        self.assertEqual("outputs", mcnemar_cli.OUTPUTS_DIR_NAME)
        self.assertEqual("evaluation_results", mcnemar_cli.EVALUATION_RESULTS_DIR_NAME)
        self.assertEqual("mcnemar", mcnemar_cli.MCNEMAR_RESULTS_DIR_NAME)
        self.assertEqual(
            PROJECT_ROOT / "outputs" / "evaluation_results",
            mcnemar_cli.get_evaluation_results_dir(PROJECT_ROOT),
        )
        self.assertEqual(
            PROJECT_ROOT / "outputs" / "mcnemar",
            mcnemar_cli.get_mcnemar_results_dir(PROJECT_ROOT),
        )

    def test_vlm_results_use_evaluation_output_directory(self):
        self.assertEqual(
            PROJECT_ROOT / "outputs" / "evaluation_results" /
            "evaluation_results_openai_gpt-4o-mini.csv",
            vlm_config.get_results_csv("openai/gpt-4o-mini"),
        )

    def test_standalone_capture_uses_repository_root_outputs(self):
        self.assertEqual(PROJECT_ROOT / "outputs", screenshot_pipeline.OUTPUT_DIR)
