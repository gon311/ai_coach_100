import unittest
from unittest.mock import patch

import fitness_mvp as mvp


def records(changes):
    rows = []
    for session_id, measured_at, values in (
        (2, "2026-09-16T09:00:00+09:00", {code: old + delta for code, (old, delta, _name) in changes.items()}),
        (1, "2026-09-01T09:00:00+09:00", {code: old for code, (old, _delta, _name) in changes.items()}),
    ):
        for index, (code, value) in enumerate(values.items(), 1):
            rows.append({
                "record_id": session_id * 10 + index, "session_id": session_id,
                "measured_at": measured_at, "source": "HOME", "age": 44,
                "sex": "M", "life_stage": "ADULT", "item_code": code,
                "item_name": changes[code][2], "factor_name": changes[code][2],
                "unit": "회", "input_value": value, "average_value": 30,
                "percentile": value, "age_band": "40-44", "norm_version": "test",
                "protocol_match": "EXACT", "equipment_verified": 1,
                "percentile_eligible": 1,
            })
    return rows


class MeasurementHistoryAnswerTests(unittest.TestCase):
    def answer(self, changes):
        with patch.object(mvp, "_user_measurement_records", return_value=records(changes)):
            return mvp._measurement_history_answer("test-user", "기록이 좋아지고 있어?")[0]

    def test_all_declined_never_claims_improvement(self):
        answer = self.answer({"A": (60, -8, "유연성"), "B": (55, -5, "근지구력")})
        self.assertIn("뚜렷하게 좋아진 항목은 없었어요", answer)
        self.assertIn("8%p 내려가", answer)
        self.assertNotIn("8%p 좋아졌어요", answer)

    def test_small_changes_are_reported_as_steady(self):
        answer = self.answer({"A": (60, 2, "유연성"), "B": (55, -1, "근지구력")})
        self.assertIn("대체로 유지", answer)
        self.assertIn("비슷하게 유지", answer)
        self.assertNotIn("%p 좋아졌어요", answer)
        self.assertNotIn("%p 내려가", answer)

    def test_mixed_changes_keep_correct_signs(self):
        answer = self.answer({"A": (50, 7, "유연성"), "B": (60, -6, "근지구력")})
        self.assertIn("7%p 좋아졌어요", answer)
        self.assertIn("6%p 내려가", answer)


if __name__ == "__main__":
    unittest.main()
