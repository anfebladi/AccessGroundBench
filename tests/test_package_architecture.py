import ast
import importlib.util
import io
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import cli
import paths
from collection import cli as collection_cli
from evaluation.storage import locking, results
from evaluation.providers import config as provider_config
from evaluation.providers import coord_prompting as prompting
from evaluation.providers import ferret, hosted, retry


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"


class UnifiedCliTests(unittest.TestCase):
    def test_help_lists_every_supported_subcommand(self):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.main([])

        for command in cli.COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, output.getvalue())

    def test_dispatch_forwards_command_arguments_verbatim(self):
        command = mock.Mock(return_value=17)
        with mock.patch.object(cli, "_load_command", return_value=command) as load:
            result = cli.main(["evaluate", "--fresh", "--force-unlock"])

        load.assert_called_once_with("evaluate")
        command.assert_called_once_with(["--fresh", "--force-unlock"])
        self.assertEqual(17, result)

    def test_packaging_exposes_unified_and_compatibility_commands(self):
        with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
            scripts = tomllib.load(handle)["project"]["scripts"]

        expected = {
            "agb",
            "orchestrator",
            "vlm_evaluator",
            "mcnemar_analysis",
            "canonicalize_results",
            "rescore_coords",
            "layout_modifier",
            "screenshot_pipeline",
            "bound_extractor",
        }
        self.assertLessEqual(expected, scripts.keys())

    def test_built_wheel_contains_reorganized_packages_and_no_retired_modules(self):
        if importlib.util.find_spec("pip") is None:
            self.skipTest("wheel builder unavailable in this test interpreter")
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    tmp,
                    str(REPO_ROOT),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            wheels = list(Path(tmp).glob("accessgroundbench-*.whl"))
            self.assertEqual(1, len(wheels))
            with zipfile.ZipFile(wheels[0]) as wheel:
                contents = set(wheel.namelist())

        expected = {
            "cli.py",
            "paths.py",
            "collection/__init__.py",
            "evaluation/__init__.py",
            "analysis/__init__.py",
            "evaluation/providers/__init__.py",
            "analysis/data/results.py",
            "analysis/data/samples.py",
            "analysis/reports/comparison.py",
            "collection/runtime/device.py",
            "collection/pipeline/capture.py",
            "collection/artifacts/manifest.py",
            "evaluation/grounding/scoring.py",
            "evaluation/grounding/targets.py",
            "evaluation/storage/results.py",
            "evaluation/providers/coord_prompting.py",
        }
        for path in expected:
            with self.subTest(path=path):
                self.assertIn(path, contents)
        for retired in (
            "analysis/data.py", "analysis/samples.py", "analysis/comparison.py",
            "collection/device.py", "collection/capture.py", "collection/manifest.py",
            "evaluation/results.py", "evaluation/scoring.py", "evaluation/targets.py",
            "evaluation/prompting.py",
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, contents)

    def test_setuptools_explicitly_discovers_flat_src_packages(self):
        with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
            config = tomllib.load(handle)

        setuptools = config["tool"]["setuptools"]
        finder = setuptools["packages"]["find"]
        self.assertEqual({"": "src"}, setuptools["package-dir"])
        self.assertEqual(["cli", "paths"], setuptools["py-modules"])
        self.assertEqual("src", finder["where"][0])
        self.assertEqual(
            {
                "analysis",
                "analysis.*",
                "collection",
                "collection.*",
                "evaluation",
                "evaluation.*",
            },
            set(finder["include"]),
        )

    def test_extract_without_xml_path_exits_one(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            collection_cli.extract_main([])

        self.assertEqual(1, raised.exception.code)

    def test_profile_name_is_lowercased_before_application(self):
        with mock.patch.object(collection_cli.profiles, "apply_profile") as apply:
            collection_cli.profile_main(["  ELDER_COMBO_MAX  "])

        apply.assert_called_once_with("elder_combo_max")

    def test_profile_help_flags_exit_zero_and_show_usage(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                output = io.StringIO()
                with redirect_stdout(output), mock.patch.object(
                    collection_cli.profiles, "apply_profile"
                ) as apply:
                    result = collection_cli.profile_main([flag])

                self.assertIsNone(result)
                self.assertIn("Usage:", output.getvalue())
                self.assertIn("layout_modifier <profile_name>", output.getvalue())
                apply.assert_not_called()

    def test_profile_without_arguments_matches_help_and_applies_nothing(self):
        no_args_output = io.StringIO()
        help_output = io.StringIO()
        with mock.patch.object(collection_cli.profiles, "apply_profile") as apply, \
             mock.patch.object(collection_cli.profiles, "reset_all") as reset:
            with redirect_stdout(no_args_output):
                result = collection_cli.profile_main([])
            with redirect_stdout(help_output):
                help_result = collection_cli.profile_main(["--help"])

        self.assertIsNone(result)
        self.assertIsNone(help_result)
        self.assertEqual(help_output.getvalue(), no_args_output.getvalue())
        self.assertIn("Available profiles:", no_args_output.getvalue())
        apply.assert_not_called()
        reset.assert_not_called()

    def test_invalid_profile_exits_one(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            collection_cli.profile_main(["not-a-profile"])

        self.assertEqual(1, raised.exception.code)

    def test_extra_profile_argument_exits_one(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            collection_cli.profile_main(["baseline", "extra"])

        self.assertEqual(1, raised.exception.code)


class PackageBoundaryTests(unittest.TestCase):
    def test_find_project_root_walks_up_from_nested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "one" / "two"
            nested.mkdir(parents=True)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "accessgroundbench"\n', encoding="utf-8"
            )

            self.assertEqual(root.resolve(), paths.find_project_root(nested))

    def test_dataset_path_uses_the_central_dataset_root(self):
        self.assertEqual(paths.DATASET_DIR / "labels" / "clock.json", paths.dataset_path("labels", "clock.json"))

    def test_domain_dependencies_do_not_cross_forbidden_directions(self):
        violations = []
        for domain in ("collection", "evaluation"):
            for source_path in (SOURCE_ROOT / domain).rglob("*.py"):
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        if domain == "collection" and node.module.startswith(
                            ("evaluation", "analysis")
                        ):
                            violations.append((source_path.name, node.module))
                        if domain == "evaluation" and node.module.startswith(
                            "analysis"
                        ):
                            violations.append((source_path.name, node.module))

        self.assertEqual([], violations)

    def test_collection_modules_follow_concrete_dependency_direction(self):
        workflow_source = (SOURCE_ROOT / "collection" / "workflow.py").read_text(encoding="utf-8")
        manifest_source = (SOURCE_ROOT / "collection" / "artifacts" / "manifest.py").read_text(encoding="utf-8")
        capture_source = (SOURCE_ROOT / "collection" / "pipeline" / "capture.py").read_text(encoding="utf-8")

        self.assertIn("from .artifacts import labels, manifest", workflow_source)
        self.assertIn("from .pipeline import capture", workflow_source)
        self.assertIn("from .runtime import navigation, profiles", workflow_source)
        self.assertIn("from . import diagnostics", manifest_source)
        self.assertNotIn("workflow", manifest_source)
        self.assertIn("from .imaging import", capture_source)
        self.assertNotIn("from .capture import", (SOURCE_ROOT / "collection" / "pipeline" / "imaging.py").read_text(encoding="utf-8"))

    def test_collection_runtime_does_not_depend_on_pipeline_or_artifacts(self):
        violations = []
        for source_path in (SOURCE_ROOT / "collection" / "runtime").glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                relative = node.level >= 2 and node.module.split(".", 1)[0] in {
                    "pipeline", "artifacts"
                }
                absolute = node.level == 0 and node.module.startswith(
                    "collection.pipeline"
                ) or node.level == 0 and node.module.startswith("collection.artifacts")
                if relative or absolute:
                    violations.append((source_path.name, node.module, node.level))
        self.assertEqual([], violations)

    def test_collection_domain_modules_do_not_parse_cli_or_define_main_blocks(self):
        violations = []
        for source_path in (SOURCE_ROOT / "collection").rglob("*.py"):
            if source_path.name in {"__init__.py", "cli.py"}:
                continue
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports_argparse = any(
                isinstance(node, ast.Import)
                and any(alias.name == "argparse" for alias in node.names)
                for node in ast.walk(tree)
            )
            has_main_guard = any(
                isinstance(node, ast.If)
                and "__main__" in ast.unparse(node.test)
                for node in ast.walk(tree)
            )
            if imports_argparse or has_main_guard:
                violations.append(source_path.name)

        self.assertEqual([], violations)

    def test_screens_module_owns_screen_order_and_workflow_imports_it(self):
        screens_path = SOURCE_ROOT / "collection" / "screens.py"
        workflow_path = SOURCE_ROOT / "collection" / "workflow.py"
        screens_tree = ast.parse(screens_path.read_text(encoding="utf-8"))
        workflow_tree = ast.parse(workflow_path.read_text(encoding="utf-8"))

        def assigned_names(tree):
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names.update(target.id for target in targets if isinstance(target, ast.Name))
            return names

        self.assertIn("SCREENS", assigned_names(screens_tree))
        self.assertNotIn("SCREENS", assigned_names(workflow_tree))
        self.assertTrue(any(
            isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module == "screens"
            and any(alias.name == "SCREENS" for alias in node.names)
            for node in ast.walk(workflow_tree)
        ))

    def test_prompting_is_owned_by_grounding_and_runner_consumes_it(self):
        runner_source = (SOURCE_ROOT / "evaluation" / "runner.py").read_text(encoding="utf-8")
        prompting_source = (SOURCE_ROOT / "evaluation" / "grounding" / "task_prompting.py").read_text(encoding="utf-8")

        self.assertIn("from .grounding.task_prompting import", runner_source)
        self.assertIn("from .scoring import hit_test", prompting_source)
        self.assertNotIn("runner", prompting_source)

    def test_retired_flat_modules_are_neither_present_nor_imported(self):
        retired = {
            "adb_utils", "app_navigator", "bound_extractor", "capture_checks",
            "layout_modifier", "mcnemar_analysis", "orchestrator",
            "screenshot_pipeline", "vlm_evaluator", "vlm_provider", "vlm_eval",
        }
        self.assertFalse(any((REPO_ROOT / f"{name}.py").exists() for name in retired))

        violations = []
        for source_path in [*SOURCE_ROOT.rglob("*.py"), *Path(__file__).parent.rglob("test_*.py")]:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                if retired.intersection(names):
                    violations.append(str(source_path.relative_to(REPO_ROOT)))

        self.assertEqual([], violations)


class EvaluationBoundaryTests(unittest.TestCase):
    def test_provider_facade_routes_ferret_to_its_concrete_owner(self):
        expected = "[10.0, 20.0]"
        self.assertIs(hosted._call_ferret, ferret.call_ferret)
        with mock.patch.object(hosted, "_call_ferret", return_value=expected) as local:
            actual = hosted.call_vlm(
                hosted.FERRET_MODEL_ID, Path("unused.png"), "prompt", target_text="Alarm"
            )

        self.assertEqual(expected, actual)
        local.assert_called_once()

    def test_retry_module_owns_the_single_effective_predicate(self):
        class ReadTimeout(Exception):
            pass

        self.assertIs(hosted._is_retryable_error, retry.is_retryable_error)
        self.assertTrue(retry.is_retryable_error(ReadTimeout("timed out")))
        self.assertFalse(retry.is_retryable_error(ValueError("invalid model")))

    def test_provider_configuration_and_prompting_have_concrete_owners(self):
        self.assertIs(hosted.resolve_completion_config, provider_config.resolve_completion_config)
        self.assertIs(hosted.validate_coord_space, provider_config.validate_coord_space)
        self.assertIs(hosted.build_normalized_prompt, prompting.build_normalized_prompt)
        self.assertIs(hosted._uses_normalized_coords, prompting.uses_normalized_coords)

    def test_provider_config_has_no_sibling_imports_and_provider_graph_is_acyclic(self):
        providers_dir = SOURCE_ROOT / "evaluation" / "providers"
        module_paths = {
            path.stem: path for path in providers_dir.glob("*.py")
        }
        graph = {name: set() for name in module_paths}

        for name, source_path in module_paths.items():
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                    sibling = node.module.split(".")[0]
                    if sibling in graph:
                        graph[name].add(sibling)

        self.assertEqual(set(), graph["config"])

        visiting = set()
        visited = set()

        def visit(module):
            if module in visiting:
                self.fail(f"provider import cycle reaches {module}: {graph}")
            if module in visited:
                return
            visiting.add(module)
            for dependency in graph[module]:
                visit(dependency)
            visiting.remove(module)
            visited.add(module)

        for module in graph:
            visit(module)

    def test_provider_modules_do_not_depend_on_runner_or_storage(self):
        violations = []
        for source_path in (SOURCE_ROOT / "evaluation" / "providers").glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                relative = node.level >= 2 and node.module.split(".", 1)[0] in {
                    "runner", "storage"
                }
                absolute = node.level == 0 and node.module.startswith(
                    "evaluation.runner"
                ) or node.level == 0 and node.module.startswith("evaluation.storage")
                if relative or absolute:
                    violations.append((source_path.name, node.module, node.level))
        self.assertEqual([], violations)

    def test_workflows_are_the_cross_layer_coordinators(self):
        collection_workflow = (SOURCE_ROOT / "collection" / "workflow.py").read_text(encoding="utf-8")
        evaluation_workflow = (SOURCE_ROOT / "evaluation" / "workflow.py").read_text(encoding="utf-8")
        self.assertIn("from .pipeline", collection_workflow)
        self.assertIn("from .artifacts", collection_workflow)
        self.assertIn("from .storage", evaluation_workflow)
        self.assertIn("from .grounding", evaluation_workflow)

    def test_locking_is_separate_but_results_reuses_it(self):
        self.assertIs(results.acquire_lock, locking.acquire_lock)
        self.assertIs(results.release_lock, locking.release_lock)

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "results.csv"
            locking.acquire_lock(csv_path)
            with self.assertRaises(locking.CsvLockError):
                locking.acquire_lock(csv_path)
            locking.release_lock(csv_path)
            self.assertFalse(locking.lock_path(csv_path).exists())

    def test_result_statuses_and_prompt_modes_are_centralized(self):
        self.assertEqual(
            {"co_present", "off_screen", "api_error", "label_changed", "off_frame"},
            {
                results.STATUS_CO_PRESENT,
                results.STATUS_OFF_SCREEN,
                results.STATUS_API_ERROR,
                results.STATUS_LABEL_CHANGED,
                results.STATUS_OFF_FRAME,
            },
        )
        self.assertEqual({"vision", "tree"}, {results.PROMPT_MODE_VISION, results.PROMPT_MODE_TREE})


if __name__ == "__main__":
    unittest.main()
