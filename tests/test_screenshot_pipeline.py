import io
import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from collection.capture import screenshot_pipeline as sp


class OutputDirectoryTests(unittest.TestCase):
    def test_default_output_directory_is_project_root_outputs(self):
        expected = Path(sp.__file__).resolve().parents[3] / "outputs"
        self.assertEqual(expected, sp.OUTPUT_DIR)

    def test_custom_image_and_xml_directories_are_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_dir = root / "images"
            xml_dir = root / "xml"

            with patch.object(sp, "run_adb_with_retries") as pull:
                xml_path, png_path = sp.pull_files(
                    "adb",
                    "serial",
                    "sample_capture",
                    image_dir=image_dir,
                    xml_dir=xml_dir,
                )

            self.assertEqual(xml_dir / "sample_capture.xml", xml_path)
            self.assertEqual(image_dir / "sample_capture.png", png_path)
            self.assertTrue(image_dir.is_dir())
            self.assertTrue(xml_dir.is_dir())
            self.assertEqual(2, pull.call_count)


class ApplyColorTransformTests(unittest.TestCase):
    def _make_png(self, pixels: list[tuple[int, int, int]]) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        path = Path(tmp.name)
        self.addCleanup(path.unlink)
        img = Image.new("RGB", (len(pixels), 1))
        for x, px in enumerate(pixels):
            img.putpixel((x, 0), px)
        img.save(path)
        return path

    def test_deuteranomaly_collapses_red_toward_yellow(self):
        # Pure red under a red-green deficiency loses its red dominance and
        # gains green, shifting toward a dark yellow/olive.
        path = self._make_png([(255, 0, 0)])
        with contextlib.redirect_stdout(io.StringIO()):
            sp.apply_color_transform(path, "deuteranomaly")
        r, g, b = Image.open(path).convert("RGB").getpixel((0, 0))
        self.assertLess(r, 255)          # red no longer maxed
        self.assertGreater(g, 40)        # green channel now present
        self.assertGreater(r, b)         # warm, not blue

    def test_monochromacy_yields_equal_channels(self):
        path = self._make_png([(200, 50, 25)])
        with contextlib.redirect_stdout(io.StringIO()):
            sp.apply_color_transform(path, "monochromacy")
        r, g, b = Image.open(path).convert("RGB").getpixel((0, 0))
        self.assertEqual(r, g)
        self.assertEqual(g, b)

    def test_unknown_mode_leaves_image_unchanged(self):
        original = (123, 45, 67)
        path = self._make_png([original])
        with contextlib.redirect_stdout(io.StringIO()):
            sp.apply_color_transform(path, "not_a_mode")
        self.assertEqual(original, Image.open(path).convert("RGB").getpixel((0, 0)))

    def test_all_declared_modes_are_12_convertible(self):
        # Every matrix must be a valid 3x3 (9 coefficients) so the pipeline can
        # build its 12-tuple without shape errors.
        for mode, matrix in sp.COLOR_TRANSFORMS.items():
            self.assertEqual(9, len(matrix), f"{mode} is not a 3x3 matrix")


if __name__ == "__main__":
    unittest.main()
