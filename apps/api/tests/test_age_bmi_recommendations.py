from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from age_bmi_recommendations import (
    AWARD_GROUPS, SPORTS_STEPS, adult_bmi_profile, build_rule_database,
    lookup_rules, rule_status,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CSV = PROJECT_ROOT / "source_data" / "KS_MRFN_AGE_ACCTO_RECOMMEND_SPORTS_INFO_202607.csv"
RULE_DATABASE = PROJECT_ROOT / "artifacts" / "age_bmi_recommendation_rules.sqlite"


class AdultBmiProfileTests(unittest.TestCase):
    def test_adult_bmi_uses_the_domestic_categories_in_the_csv(self) -> None:
        cases = [
            (18.4, "저체중"), (18.5, "정상"), (22.9, "정상"),
            (23.0, "비만전단계비만"), (25.0, "1단계비만"),
            (30.0, "2단계비만"), (35.0, "3단계비만"),
        ]
        for value, expected in cases:
            with self.subTest(bmi=value):
                profile = adult_bmi_profile(30, 100.0, value)
                self.assertTrue(profile["available"])
                self.assertEqual(profile["bmi_grade"], expected)
                self.assertEqual(profile["age_band"], "30대")

    def test_under_twenty_is_not_automatically_classified_as_an_adult(self) -> None:
        profile = adult_bmi_profile(19, 170.0, 65.0)
        self.assertFalse(profile["available"])
        self.assertIn("20세 미만", profile["reason"])


class AgeBmiRuleDatabaseTests(unittest.TestCase):
    def test_bundled_rule_database_is_complete_and_integral(self) -> None:
        status = rule_status(RULE_DATABASE)
        self.assertTrue(status["available"])
        self.assertEqual(status["integrity"], "ok")
        self.assertEqual(status["row_count"], 5040)
        self.assertEqual(status["award_groups"], list(AWARD_GROUPS))
        self.assertEqual(status["sports_steps"], list(SPORTS_STEPS))

    def test_exact_lookup_returns_three_steps_and_five_ranks_each(self) -> None:
        result = lookup_rules(RULE_DATABASE, {
            "age": 30, "height_cm": 170.0, "weight_kg": 65.0,
            "sex": "M", "award_group": "1등급",
        })
        self.assertTrue(result["available"])
        self.assertEqual(result["bmi"]["bmi_grade"], "정상")
        self.assertEqual(len(result["rules"]), 15)
        self.assertEqual({item["sports_step"] for item in result["rules"]}, set(SPORTS_STEPS))
        self.assertEqual({item["rank"] for item in result["rules"]}, {1, 2, 3, 4, 5})

    def test_missing_award_group_does_not_invent_a_rule(self) -> None:
        result = lookup_rules(RULE_DATABASE, {
            "age": 30, "height_cm": 170.0, "weight_kg": 65.0, "sex": "F",
        })
        self.assertFalse(result["available"])
        self.assertIn("상장 구분", result["reason"])

    def test_builder_recreates_the_same_complete_table(self) -> None:
        # Windows can retain the just-closed SQLite handle briefly.  The test
        # verifies the database contents; cleanup must not turn that verified
        # result into a platform-specific failure.
        with TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            database = Path(directory) / "rules.sqlite"
            report = build_rule_database(SOURCE_CSV, database)
            status = rule_status(database)
        self.assertEqual(report["row_count"], 5040)
        self.assertTrue(status["available"])


if __name__ == "__main__":
    unittest.main()
