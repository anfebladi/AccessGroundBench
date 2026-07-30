import io
import contextlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import screenshot_pipeline as sp


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

    def test_unknown_mode_raises_instead_of_saving_untransformed_pixels(self):
        # Previously this warned and returned, which would save a "colorblind"
        # capture identical to baseline and quietly turn the profile into a
        # duplicate of the control condition.
        original = (123, 45, 67)
        path = self._make_png([original])
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError) as ctx:
                sp.apply_color_transform(path, "not_a_mode")
        self.assertIn("not_a_mode", str(ctx.exception))
        self.assertEqual(original, Image.open(path).convert("RGB").getpixel((0, 0)))

    def test_transform_reports_the_magnitude_of_the_change(self):
        path = self._make_png([(255, 0, 0)])
        with contextlib.redirect_stdout(io.StringIO()):
            delta = sp.apply_color_transform(path, "deuteranomaly")
        self.assertGreater(delta, 0.0)

    def test_transform_that_changes_nothing_is_rejected(self):
        # A pure grey pixel is a fixed point of the monochromacy matrix, so the
        # transform leaves it untouched -- the pipeline must refuse to record
        # that as a successfully filtered capture.
        path = self._make_png([(128, 128, 128)])
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError) as ctx:
                sp.apply_color_transform(path, "monochromacy")
        self.assertIn("changed nothing", str(ctx.exception))

    def test_all_declared_modes_are_12_convertible(self):
        # Every matrix must be a valid 3x3 (9 coefficients) so the pipeline can
        # build its 12-tuple without shape errors.
        for mode, matrix in sp.COLOR_TRANSFORMS.items():
            self.assertEqual(9, len(matrix), f"{mode} is not a 3x3 matrix")


if __name__ == "__main__":
    unittest.main()
