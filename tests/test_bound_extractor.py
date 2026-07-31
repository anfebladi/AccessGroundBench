import tempfile
import unittest
from pathlib import Path

from bound_extractor import extract

XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
<node index="0" text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2424]">
{children}
</node>
</hierarchy>
"""


def write_xml(path: Path, children_xml: str) -> None:
    path.write_text(XML_TEMPLATE.format(children=children_xml), encoding="utf-8")


class ExtractClampingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.xml_path = Path(self.tmp.name) / "screen.xml"

    def test_node_fully_inside_content_area_is_unaffected(self):
        write_xml(
            self.xml_path,
            '<node index="1" text="Settings" class="android.widget.TextView" '
            'bounds="[100,300][500,400]" />',
        )

        results = extract(self.xml_path, y_offset=80, bottom_crop=100)

        self.assertEqual(1, len(results))
        # y shifted by y_offset only, x untouched, since fully within bounds.
        self.assertEqual([100, 220, 500, 320], results[0]["box"])

    def test_node_clipped_at_bottom_edge_is_clamped_not_kept_at_full_size(self):
        # screen_h=2424, bottom_crop=100 -> content_bottom=2324. This node
        # starts inside the visible area but extends 76px past it.
        write_xml(
            self.xml_path,
            '<node index="1" text="Claude Team" class="android.widget.TextView" '
            'bounds="[100,2200][500,2400]" />',
        )

        results = extract(self.xml_path, y_offset=80, bottom_crop=100)

        self.assertEqual(1, len(results))
        box = results[0]["box"]
        # Clamped y_max is content_bottom - y_offset = 2324 - 80 = 2244, not
        # 2400 - 80 = 2320 (which is what the old, unclamped code produced --
        # a box whose center could fall outside the final cropped image).
        self.assertEqual([100, 2120, 500, 2244], box)

    def test_clamped_box_center_never_falls_outside_cropped_image(self):
        # Regression for the exact defect found in dataset/evaluation_results:
        # a node clipped hard enough at the bottom edge that its unclamped
        # center landed below the final image height.
        write_xml(
            self.xml_path,
            '<node index="1" text="Promotions" class="android.widget.TextView" '
            'bounds="[100,2270][500,2450]" />',
        )
        y_offset, bottom_crop = 80, 100
        screen_h = 2424
        image_height = screen_h - bottom_crop - y_offset

        results = extract(self.xml_path, y_offset=y_offset, bottom_crop=bottom_crop)

        self.assertEqual(1, len(results))
        _, y1, _, y2 = results[0]["box"]
        center_y = (y1 + y2) / 2.0
        self.assertLessEqual(center_y, image_height)
        self.assertGreaterEqual(center_y, 0)

    def test_node_entirely_below_content_area_is_still_dropped(self):
        write_xml(
            self.xml_path,
            '<node index="1" text="Off screen" class="android.widget.TextView" '
            'bounds="[100,2400][500,2420]" />',
        )

        results = extract(self.xml_path, y_offset=80, bottom_crop=100)

        self.assertEqual([], results)

    def test_node_clipped_at_top_edge_is_clamped(self):
        write_xml(
            self.xml_path,
            '<node index="1" text="Status" class="android.widget.TextView" '
            'bounds="[100,20][500,150]" />',
        )

        results = extract(self.xml_path, y_offset=80, bottom_crop=100)

        self.assertEqual(1, len(results))
        # Clamped y_min is content_top (80), shifted by y_offset -> 0.
        self.assertEqual([100, 0, 500, 70], results[0]["box"])

    def test_node_clipped_past_screen_width_is_clamped(self):
        write_xml(
            self.xml_path,
            '<node index="1" text="Wide" class="android.widget.TextView" '
            'bounds="[900,300][1200,400]" />',
        )

        results = extract(self.xml_path, y_offset=0, bottom_crop=0)

        self.assertEqual(1, len(results))
        # screen_w is 1080 (from the root node's bounds); x_max clamped to it.
        self.assertEqual([900, 300, 1080, 400], results[0]["box"])


if __name__ == "__main__":
    unittest.main()
