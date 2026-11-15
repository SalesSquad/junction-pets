"""Focused public-shield and provenance parser regression checks for V11 R audit."""
import unittest

from rokoko_r_v11_extract import valid_public_step


class PublicStepTests(unittest.TestCase):
    def good(self):
        return {
            "observation": [0.0] * 18,
            "next_observation": [0.1] * 18,
            "mask": [1, 1, 1, 1, 1, 1, 1],
            "action": 4,
        }

    def test_original_legal_public_step(self):
        self.assertIsNone(valid_public_step(self.good()))

    def test_illegal_masked_action_rejected(self):
        row = self.good()
        row["mask"][4] = 0
        with self.assertRaisesRegex(ValueError, "legal action"):
            valid_public_step(row)

    def test_nonfinite_observation_rejected(self):
        row = self.good()
        row["observation"][1] = float("nan")
        with self.assertRaisesRegex(ValueError, "public 18D"):
            valid_public_step(row)

    def test_infinite_next_observation_rejected(self):
        row = self.good()
        row["next_observation"][1] = float("inf")
        with self.assertRaisesRegex(ValueError, "public 18D"):
            valid_public_step(row)

    def test_wrong_dimension_rejected(self):
        row = self.good()
        row["observation"] = [0.0] * 17
        with self.assertRaisesRegex(ValueError, "public 18D"):
            valid_public_step(row)

    def test_malformed_mask_rejected(self):
        row = self.good()
        row["mask"] = [1] * 6 + [2]
        with self.assertRaisesRegex(ValueError, "original 7-mask"):
            valid_public_step(row)

    def test_action_out_of_range_rejected(self):
        row = self.good()
        row["action"] = 7
        with self.assertRaisesRegex(ValueError, "legal action"):
            valid_public_step(row)


if __name__ == "__main__":
    unittest.main()
