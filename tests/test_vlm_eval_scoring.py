import unittest

from vlm_eval.scoring import (
    PARSE_BRACKET,
    PARSE_FAILED,
    PARSE_LOOSE,
    TOLERANCE,
    hit_test,
    parse_coordinates,
    parse_coordinates_detailed,
    to_pixel_space,
)


class ParseCoordinatesTests(unittest.TestCase):
    def test_parse_coordinates_extracts_bracketed_pair(self):
        self.assertEqual((123, 456), parse_coordinates("[123, 456]"))

    def test_parse_coordinates_falls_back_to_bare_pair(self):
        self.assertEqual((12, 34), parse_coordinates("click at 12,34 please"))

    def test_parse_coordinates_preserves_negative_values(self):
        self.assertEqual((-5, 34), parse_coordinates("[-5, 34]"))

    def test_parse_coordinates_returns_negative_sentinel_on_failure(self):
        self.assertEqual((-1, -1), parse_coordinates("no coordinate here"))

    def test_bracketed_answer_wins_over_earlier_incidental_pair(self):
        # A loose first-match scan would score (3, 2) from the prose.
        text = "It sits at row 3, column 2 of the grid, so the centre is [540, 300]"
        self.assertEqual((540, 300), parse_coordinates(text))

    def test_parenthesised_pair_is_also_anchored(self):
        self.assertEqual((540, 300), parse_coordinates("the point is (540, 300)"))

    def test_detailed_reports_which_pattern_matched(self):
        self.assertEqual(PARSE_BRACKET, parse_coordinates_detailed("[1, 2]")[2])
        self.assertEqual(PARSE_LOOSE, parse_coordinates_detailed("1, 2")[2])
        self.assertEqual(PARSE_FAILED, parse_coordinates_detailed("nope")[2])


class HitTestTests(unittest.TestCase):
    BOX = [10, 20, 30, 40]

    def test_hit_test_scores_inside_and_edge_points(self):
        self.assertEqual(1, hit_test(20, 30, self.BOX))
        self.assertEqual(1, hit_test(10, 20, self.BOX))
        self.assertEqual(1, hit_test(30, 40, self.BOX))

    def test_hit_test_accepts_points_within_touch_tolerance(self):
        # TOLERANCE simulates the minimum tap-target guidance, so points just
        # outside the drawn bounds still count as a hit.
        self.assertEqual(1, hit_test(self.BOX[0] - TOLERANCE, 30, self.BOX))
        self.assertEqual(1, hit_test(20, self.BOX[3] + TOLERANCE, self.BOX))

    def test_hit_test_rejects_points_beyond_tolerance(self):
        self.assertEqual(0, hit_test(self.BOX[0] - TOLERANCE - 1, 30, self.BOX))
        self.assertEqual(0, hit_test(20, self.BOX[3] + TOLERANCE + 1, self.BOX))

    def test_baseline_box_keeps_strictness_constant_when_element_inflates(self):
        # An element that doubles in size must not become easier to hit: the
        # baseline dimensions are applied at the inflated element's centre.
        baseline = [0, 0, 100, 100]
        inflated = [0, 0, 300, 300]

        # Centre of the inflated element is (150, 150); baseline half-width
        # plus tolerance is 50 + 30 = 80.
        self.assertEqual(1, hit_test(150 + 79, 150, inflated, baseline))
        self.assertEqual(0, hit_test(150 + 81, 150, inflated, baseline))


class ToPixelSpaceTests(unittest.TestCase):
    # The three distinct screenshot dimensions in dataset/images. Bar heights
    # change with density, so each profile group has its own image height.
    DATASET_DIMS = ((1080, 2177), (1080, 2196), (1080, 2219))

    def test_pixel_space_passes_through_unchanged(self):
        self.assertEqual((123.0, 456.0), to_pixel_space(123.0, 456.0, 1080, 2219, "pixel"))

    def test_unknown_space_is_treated_as_pixels(self):
        # "unverified" (an unparseable reply) must not be scaled: the -1
        # sentinel and any salvaged value stay in whatever space they were.
        self.assertEqual((-1.0, -1.0), to_pixel_space(-1.0, -1.0, 1080, 2219, "unverified"))

    def test_both_normalized_spellings_convert_identically(self):
        # "norm1000" is COORD_SPACE's spelling; "normalized" is what
        # vlm_provider records per reply. They must not diverge.
        self.assertEqual(
            to_pixel_space(500, 500, 1080, 2219, "norm1000"),
            to_pixel_space(500, 500, 1080, 2219, "normalized"),
        )

    def test_centre_of_grid_maps_to_centre_of_image(self):
        self.assertEqual((540.0, 1109.5), to_pixel_space(500, 500, 1080, 2219, "norm1000"))

    def test_reproduces_legacy_provider_side_conversion_exactly(self):
        """The conversion used to happen in vlm_provider, which emitted
        f"[{cx:.1f}, {cy:.1f}]" before the runner truncated with int().

        Moving it here must not change a single already-collected x_pred or
        y_pred. Dropping the 1-decimal quantization would shift ~4% of replies
        by one pixel (267 of 3003 inputs across these dimensions), and since
        score = hit_test(x_pred, ...) that can flip a score at a box edge.
        """
        for width, height in self.DATASET_DIMS:
            for value in range(1001):
                legacy_x = float(f"{(value / 1000.0) * width:.1f}")
                legacy_y = float(f"{(value / 1000.0) * height:.1f}")
                new_x, new_y = to_pixel_space(value, value, width, height, "normalized")

                self.assertEqual(
                    (int(legacy_x), int(legacy_y)),
                    (int(new_x), int(new_y)),
                    f"x_pred/y_pred changed for reply {value} at {width}x{height}",
                )


if __name__ == "__main__":
    unittest.main()
