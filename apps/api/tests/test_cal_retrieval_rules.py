import unittest

import fitness_web_server as server


class ExplicitExerciseRetrievalRulesTests(unittest.TestCase):
    def _runtime(self):
        runtime = server.RagRuntime.__new__(server.RagRuntime)
        runtime.explicit_exercise_groups = [
            (
                ("앉았다들어올리기", "상체숙여서뒤로당기기"),
                [
                    {"_id": "adult-composite", "_dataset": "video_content", "age_group": {"성인"}, "sex": set()},
                ],
            ),
            (
                ("밴드어깨뒤로들어올리기",),
                [
                    {"_id": "adult-f", "_dataset": "general_prescription", "age_group": {"성인"}, "sex": {"F"}},
                    {"_id": "adult-m", "_dataset": "general_prescription", "age_group": {"성인"}, "sex": {"M"}},
                    {"_id": "youth-f", "_dataset": "general_prescription", "age_group": {"유소년"}, "sex": {"F"}},
                ],
            ),
        ]
        return runtime

    def test_composite_name_matches_sentence_connector(self):
        runtime = self._runtime()
        ids = runtime._explicit_exercise_matches(
            "성인에게 앉았다 들어올리기와 상체 숙여서 뒤로 당기기 운동을 알려줘",
            ["video_content"],
            5,
        )
        self.assertEqual(ids, ["adult-composite"])

    def test_explicit_population_filters_incompatible_rows(self):
        runtime = self._runtime()
        ids = runtime._explicit_exercise_matches(
            "성인 여성의 밴드 어깨 뒤로 들어올리기 방법을 알려줘",
            ["general_prescription"],
            5,
        )
        self.assertEqual(ids, ["adult-f"])

    def test_dataset_scope_is_preserved(self):
        runtime = self._runtime()
        ids = runtime._explicit_exercise_matches(
            "성인 여성의 밴드 어깨 뒤로 들어올리기 방법을 알려줘",
            ["video_content"],
            5,
        )
        self.assertEqual(ids, [])


if __name__ == "__main__":
    unittest.main()
