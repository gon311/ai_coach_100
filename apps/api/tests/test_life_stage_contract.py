import unittest
from unittest.mock import patch

from fastapi import HTTPException

import fitness_mvp as mvp


class LifeStageContractTests(unittest.TestCase):
    def test_age_and_life_stage_must_match(self):
        with self.assertRaisesRegex(ValueError, "일치하지 않습니다"):
            mvp._evaluate(mvp.EvaluateBody(
                age=70, life_stage="ADULT", sex="F", source="HOME", measurements={}
            ))

    def test_under_19_is_rejected_by_api_contract(self):
        body = mvp.EvaluateBody(
            age=16, life_stage="TEEN", sex="M", source="HOME",
            measurements={"SIT_AND_REACH": 12, "CURL_UP": 30},
        )
        with self.assertRaisesRegex(ValueError, "만 19세 이상"):
            mvp._evaluate(body)

    def test_relative_grip_requires_weight(self):
        body = mvp.EvaluateBody(
            age=44, life_stage="ADULT", sex="M", source="HOME",
            measurements={"RELATIVE_GRIP": 50},
        )
        with self.assertRaisesRegex(ValueError, "체중"):
            mvp._evaluate(body)

    def test_video_selection_excludes_other_life_stages(self):
        result = mvp._training_videos("CHAIR_STAND_30S", 70, 50)
        self.assertTrue(all(video["age_group"] in {"어르신", "공통", ""} for video in result["videos"]))
        self.assertEqual(result["life_stage"], "SENIOR")

    def test_top_percent_is_inverted_and_advances_one_level(self):
        self.assertEqual(mvp._next_exercise_level(95), (1, 2))
        self.assertEqual(mvp._next_exercise_level(55), (2, 3))
        self.assertEqual(mvp._next_exercise_level(20), (3, 4))
        weak = mvp._training_videos("RELATIVE_GRIP", 40, 95)
        strong = mvp._training_videos("RELATIVE_GRIP", 40, 20)
        self.assertEqual(weak["target_week"], "2주차")
        self.assertEqual(strong["target_week"], "4주차")
        self.assertNotEqual(weak["videos"][1]["exercise_name"], strong["videos"][1]["exercise_name"])

    def test_each_supported_factor_returns_three_phase_videos(self):
        for code in ("CURL_UP", "SIT_AND_REACH", "STANDING_LONG_JUMP", "RELATIVE_GRIP",
                     "SIDE_STEP", "SHUTTLE_RUN_20M", "CHAIR_3M_TURN", "CHAIR_STAND_30S"):
            with self.subTest(code=code):
                age = 70 if code.startswith("CHAIR_") else 40
                result = mvp._training_videos(code, age, 55)
                self.assertEqual([v["phase"] for v in result["videos"]],
                                 ["준비운동", "본운동", "마무리운동"])

    def test_video_endpoint_rejects_mismatch(self):
        with self.assertRaises(HTTPException) as caught:
            mvp.recommendation_videos("CHAIR_STAND_30S", 70, "ADULT", 50)
        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
