from pathlib import Path
import json
import sqlite3
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import fitness_mvp as mvp


class FakeClient:
    def complete_json(self, *_args, **_kwargs):
        return json.dumps({"answer": "천천히 스트레칭해 보세요. [E2]", "used_evidence": ["E2"]}, ensure_ascii=False)


class FakeRuntime:
    qwen3_client = FakeClient()

    def semantic_search(self, *_args, **_kwargs):
        return [{
            "id": "doc-1", "dataset": "general_prescription", "title": "유연성 운동",
            "text": "천천히 스트레칭합니다.", "score": 0.8,
            "retrieval_backend": "chroma_vector",
        }]


FAKE_REQUEST = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=FakeRuntime())))


class FitnessMvpV2Tests(unittest.TestCase):
    def stored_records(self):
        base = {
            "source": "CENTER", "age": 29, "sex": "F", "life_stage": "ADULT",
            "item_code": "SIT_AND_REACH", "item_name": "앉아윗몸앞으로굽히기",
            "factor_name": "유연성", "unit": "cm", "input_value": 15.0,
            "average_value": 12.0, "age_band": "25-29", "norm_version": "test",
            "protocol_match": "EXACT", "equipment_verified": 1, "percentile_eligible": 1,
        }
        return [
            {**base, "record_id": 2, "session_id": 2, "measured_at": "2026-09-15T09:00:00+09:00", "percentile": 62.0},
            {**base, "record_id": 1, "session_id": 1, "measured_at": "2026-08-15T09:00:00+09:00", "input_value": 13.0, "percentile": 52.0},
        ]

    def result(self, age, sex, source, code, value):
        life_stage = "ADULT" if age < 65 else "SENIOR"
        body = mvp.EvaluateBody(age=age, life_stage=life_stage, sex=sex, source=source, measurements={code: value})
        return next(item for item in mvp._evaluate(body)[2] if item["code"] == code)

    def test_discrete_tie_uses_spec_floor_percentile(self):
        self.assertEqual(self.result(72, "F", "HOME", "CHAIR_STAND_30S", 20)["percentile"], 62.0)

    def test_three_meter_turn_has_percentile(self):
        result = self.result(70, "F", "HOME", "CHAIR_3M_TURN", 8)
        self.assertGreaterEqual(result["percentile"], 0)
        self.assertLessEqual(result["percentile"], 100)
        self.assertEqual(result["factor_name"], "평형성")
        self.assertEqual(result["percentile_display"]["mode"], "RANGE")

    def test_figure_eight_is_senior_center_reference_only(self):
        body = mvp.EvaluateBody(
            age=70, life_stage="SENIOR", sex="F", source="CENTER",
            measurements={"FIGURE_8_WALK": 18.2},
        )
        result = next(row for row in mvp._evaluate(body)[2] if row["code"] == "FIGURE_8_WALK")
        self.assertEqual(result["factor_name"], "협응력")
        self.assertEqual(result["status"], "reference_only")
        self.assertFalse(result["percentile_eligible"])
        self.assertIsNone(result["percentile"])
        self.assertEqual(result["percentile_display"]["mode"], "UNAVAILABLE")
        with self.assertRaisesRegex(ValueError, "CENTER"):
            mvp._evaluate(mvp.EvaluateBody(
                age=70, life_stage="SENIOR", sex="F", source="HOME",
                measurements={"FIGURE_8_WALK": 18.2},
            ))

    def test_result_has_no_grade_fields(self):
        row = self.result(44, "M", "CENTER", "SIT_AND_REACH", 10)
        self.assertFalse({"level_code", "level_name", "score", "average_score"}.intersection(row))

    def test_shuttle_run_10m_uses_life_stage_mapping(self):
        with sqlite3.connect(mvp.NORM_DB) as db:
            rows = db.execute(
                """SELECT life_stage,item_name,factor_name,unit,direction
                   FROM measurement_matrix WHERE item_code='SHUTTLE_RUN_10M'
                   GROUP BY life_stage,item_name,factor_name,unit,direction
                   ORDER BY life_stage"""
            ).fetchall()
        self.assertEqual(rows, [
            ("ADULT", "10m 4회 왕복달리기", "민첩성", "초", "LOWER_BETTER"),
            ("PRESCHOOL", "10m 왕복오래달리기", "심폐지구력", "회", "HIGHER_BETTER"),
        ])

        adult = self.result(30, "M", "CENTER", "SHUTTLE_RUN_10M", 11.2)
        self.assertEqual((adult["name"], adult["factor_name"], adult["unit"]),
                         ("10m 4회 왕복달리기", "민첩성", "초"))
        with self.assertRaisesRegex(ValueError, "만 19세 이상"):
            mvp._evaluate(mvp.EvaluateBody(
                age=5, life_stage="TEEN", sex="M", source="CENTER",
                measurements={"SHUTTLE_RUN_10M": 30},
            ))

    def test_unsupported_senior_long_jump_is_explicit(self):
        body = mvp.EvaluateBody(age=70, life_stage="SENIOR", sex="F", source="CENTER", measurements={"STANDING_LONG_JUMP": 150})
        with self.assertRaisesRegex(ValueError, "STANDING_LONG_JUMP"):
            mvp._evaluate(body)

    def test_database_schema_matches_v2(self):
        with sqlite3.connect(mvp.USER_DB) as db:
            session_columns = {row[1] for row in db.execute("PRAGMA table_info(measurement_sessions)")}
            result_columns = {row[1] for row in db.execute("PRAGMA table_info(measurement_results)")}
        self.assertIn("source", session_columns)
        self.assertIn("norm_version", result_columns)
        self.assertFalse({"level_code", "level_name"}.intersection(result_columns))
        with sqlite3.connect(mvp.NORM_DB) as db:
            rule_table = db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='fitness_level_rule'").fetchone()[0]
            norm_rows = db.execute("SELECT count(*) FROM fitness_norm").fetchone()[0]
        self.assertEqual(rule_table, 0)
        self.assertEqual(norm_rows, 30_300)

    def test_all_home_ranges_and_center_points_are_backend_owned(self):
        cases = {
            "SIT_AND_REACH": (10, 30, 50),
            "SHUTTLE_RUN_10M": (8, 32, 48),
            "CROSS_SIT_UP": (7, 33, 47),
            "STEP_IN_PLACE_2MIN": (7, 33, 47),
            "RELATIVE_GRIP": (7, 33, 47),
            "STANDING_LONG_JUMP": (5, 35, 45),
            "CHAIR_STAND_30S": (5, 35, 45),
            "CHAIR_3M_TURN": (10, 30, 50),
        }
        for code, (_width, lower, upper) in cases.items():
            display = mvp._percentile_display("HOME", code, 40)
            self.assertEqual(display, {"mode": "RANGE", "lower": lower, "upper": upper, "text": f"또래 상위 {lower}~{upper}%"})
        self.assertEqual(
            mvp._percentile_display("CENTER", "RELATIVE_GRIP", 40),
            {"mode": "POINT", "lower": None, "upper": None, "text": "또래 상위 40%"},
        )
        self.assertEqual(
            mvp._percentile_display("HOME", "RELATIVE_GRIP", 40),
            {"mode": "RANGE", "lower": 33, "upper": 47, "text": "또래 상위 33~47%"},
        )

    def test_home_range_endpoints_are_clamped_without_changing_point_values(self):
        self.assertEqual(
            mvp._percentile_display("HOME", "SHUTTLE_RUN_10M", 3),
            {"mode": "RANGE", "lower": 0, "upper": 11, "text": "또래 상위 0~11%"},
        )
        self.assertEqual(
            mvp._percentile_display("HOME", "RELATIVE_GRIP", 97),
            {"mode": "RANGE", "lower": 90, "upper": 100, "text": "또래 상위 90~100%"},
        )
        self.assertEqual(
            mvp._percentile_display("CENTER", "SHUTTLE_RUN_10M", 3),
            {"mode": "POINT", "lower": None, "upper": None, "text": "또래 상위 3%"},
        )

    def test_evaluate_response_carries_source_specific_display_contract(self):
        home = self.result(44, "F", "HOME", "SIT_AND_REACH", 10)
        center = self.result(44, "F", "CENTER", "SIT_AND_REACH", 10)
        self.assertEqual(home["percentile_display"]["mode"], "RANGE")
        self.assertIn("~", home["percentile_display"]["text"])
        self.assertEqual(center["percentile_display"]["mode"], "POINT")
        self.assertNotIn("~", center["percentile_display"]["text"])
        self.assertEqual(
            mvp._record_percentile_display({"source": "HOME", "item_code": "SIT_AND_REACH", "percentile": 62}),
            {"mode": "RANGE", "lower": 28, "upper": 48, "text": "또래 상위 28~48%"},
        )

    def test_home_report_prompt_uses_range_and_rejects_model_point_claim(self):
        class SummaryClient:
            prompt = ""
            def complete_json(self, _system, prompt, **_kwargs):
                self.prompt = prompt
                return json.dumps({"summary": "유연성은 또래 상위 32%로 안정적이에요. 근력도 천천히 보완해 보세요."}, ensure_ascii=False)
        client = SummaryClient()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(qwen3_client=client))))
        body = mvp.SummaryBody(age=40, sex="F", source="HOME", results=[{
            "code": "SIT_AND_REACH", "item_code": "SIT_AND_REACH", "name": "앉아윗몸앞으로굽히기",
            "factor_name": "유연성", "unit": "cm", "input_value": 10, "average_value": 8,
            "percentile": 68, "top_percent": 32, "available": True,
        }])
        result = mvp.report_summary(body, request)
        self.assertIn("또래 상위 22~42%", client.prompt)
        self.assertNotIn("상위 32%", result["summary"])

    def test_report_prompt_applies_new_home_widths_but_keeps_center_points(self):
        class SummaryClient:
            prompts = []
            def complete_json(self, _system, prompt, **_kwargs):
                self.prompts.append(prompt)
                return json.dumps({"summary": "형태를 확인하기 위한 불완전 응답"}, ensure_ascii=False)
        client = SummaryClient()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(qwen3_client=client))))
        rows = [
            {"item_code":"SHUTTLE_RUN_10M","factor_name":"민첩성","input_value":11,"unit":"초","average_value":12,"percentile":60,"top_percent":40,"available":True},
            {"item_code":"RELATIVE_GRIP","factor_name":"근력","input_value":45,"unit":"%","average_value":42,"percentile":60,"top_percent":40,"available":True},
        ]
        mvp.report_summary(mvp.SummaryBody(age=40, sex="F", source="HOME", results=rows), request)
        mvp.report_summary(mvp.SummaryBody(age=40, sex="F", source="CENTER", results=rows), request)
        self.assertIn("또래 상위 32~48%", client.prompts[0])
        self.assertIn("또래 상위 33~47%", client.prompts[0])
        self.assertNotIn("또래 상위 40%", client.prompts[0])
        self.assertIn("또래 상위 40%", client.prompts[1])

    def test_guest_and_logged_in_chat_context_use_the_same_home_range_policy(self):
        snapshot = mvp.EvaluateBody(
            age=40, life_stage="ADULT", sex="F", source="HOME", weight_kg=60,
            equipment_verified={"RELATIVE_GRIP": True}, measurements={"RELATIVE_GRIP": 45},
        )
        guest_context, _ = mvp._validated_guest_context(snapshot)
        self.assertRegex(guest_context, r"또래 상위 \d+~\d+%")
        stored = {
            "source":"HOME", "item_code":"RELATIVE_GRIP", "item_name":"상대악력",
            "factor_name":"근력", "input_value":45, "unit":"%", "percentile":60,
        }
        self.assertEqual(mvp._record_percentile_display(stored)["text"], "또래 상위 33~47%")
        self.assertIn("또래 상위 33~47%", mvp._measurement_sources([{**stored, "record_id":1, "measured_at":"2026-09-17"}])[0]["excerpt"])

    def test_senior_report_rejects_agility_label_for_three_meter_turn(self):
        class SummaryClient:
            def complete_json(self, *_args, **_kwargs):
                return json.dumps({"summary": "민첩성 기록은 좋은 흐름이에요. 다음에도 같은 조건으로 측정해 보세요."}, ensure_ascii=False)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(qwen3_client=SummaryClient()))))
        result = mvp.report_summary(mvp.SummaryBody(age=70, sex="F", source="CENTER", results=[{
            "code": "CHAIR_3M_TURN", "item_code": "CHAIR_3M_TURN", "factor_name": "민첩·동적평형성",
            "input_value": 8, "unit": "초", "average_value": 7, "percentile": 40,
            "top_percent": 60, "available": True, "percentile_eligible": True,
        }]), request)
        self.assertNotIn("민첩", result["summary"])
        self.assertIn("평형성", result["summary"])

    def test_guest_personal_chat_returns_path_b_contract(self):
        snapshot = mvp.EvaluateBody(
            age=29, life_stage="ADULT", sex="F", source="HOME", measurements={"SIT_AND_REACH": 15.0},
        )
        body = mvp.FitnessChatBody(
            message="내 체력에 맞는 유연성 운동을 추천해줘", measurement_snapshot=snapshot,
        )
        response = mvp.fitness_chat(body, FAKE_REQUEST, None)
        self.assertEqual(response["answer_path"], "B")
        self.assertIn("SIT_AND_REACH", response["injected_values"])
        self.assertEqual(response["retrieved_doc_ids"][0]["document_id"], "doc-1")
        self.assertEqual(response["queried_record_ids"], [])
        self.assertIsNone(response["routing_flag"])

    def test_safety_gate_returns_explicit_routing_flag(self):
        body = mvp.FitnessChatBody(message="무릎이 아픈데 운동을 추천해줘")
        response = mvp.fitness_chat(body, FAKE_REQUEST, None)
        self.assertEqual(response["routing_flag"], "SAFETY_BLOCK")
        self.assertEqual(response["answer_path"], "C")
        self.assertEqual(response["retrieved_doc_ids"], [])
        self.assertEqual(response["cited_doc_ids"], [])
        self.assertEqual(response["sources"], [])
        self.assertFalse(response["grounded"])
        self.assertEqual(response["grounding_type"], "NONE")

    def test_chest_tightness_short_circuits_as_safety(self):
        body = mvp.FitnessChatBody(
            message="러닝머신에서 뛰다가 가슴 한가운데가 조여와 멈췄는데 다시 해도 될까요?"
        )
        response = mvp.fitness_chat(body, FAKE_REQUEST, None)
        self.assertEqual(response["routing_flag"], "SAFETY_BLOCK")
        self.assertEqual(response["answer_path"], "C")
        self.assertFalse(response["actual_rag_search"])
        self.assertEqual(response["policy_short_circuit"], "SAFETY_POLICY")

    def test_authenticated_path_a_uses_database_and_never_calls_llm(self):
        body = mvp.FitnessChatBody(message="지난번보다 나아지고 있어?", conversation_id="ab-test")
        with (
            patch.object(mvp, "_auth", return_value="eval_p1"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[]),
            patch.object(mvp, "_user_measurement_records", return_value=self.stored_records()),
            patch.object(mvp, "_save_chat_turn"),
            patch("fitness_chat_harness_v2.answer") as llm_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        llm_answer.assert_not_called()
        self.assertEqual(response["answer_path"], "A")
        self.assertEqual(response["source"], "user_measurement_db")
        self.assertEqual(response["routing_flag"], "USER_MEASUREMENT_DB")
        self.assertTrue(response["grounded"])
        self.assertEqual(response["grounding_type"], "USER_MEASUREMENT")
        self.assertTrue(response["sources"])
        self.assertTrue(all(source["evidence_type"] == "USER_MEASUREMENT" for source in response["sources"]))
        self.assertEqual(response["queried_record_ids"], [2, 1])
        self.assertEqual(response["retrieved_doc_ids"], [])
        self.assertEqual(response["injected_values"]["SIT_AND_REACH"]["percentile"], 62.0)


    def test_specific_measurement_lookup_returns_named_latest_value_not_trend(self):
        home_records = [
            {**self.stored_records()[0], "record_id": 9, "session_id": 9,
             "source": "HOME", "input_value": 11.0, "percentile": 55.0,
             "measured_at": "2026-09-19T08:00:00+09:00"},
            *self.stored_records(),
        ]
        with patch.object(mvp, "_user_measurement_records", return_value=home_records):
            answer, trace = mvp._specific_measurement_lookup_answer(
                "eval_p1", "집에서 측정한 제 앉아윗몸앞으로굽히기 결과 좀 확인해 주세요."
            )
        self.assertIn("앉아윗몸앞으로굽히기", answer)
        self.assertIn("11cm", answer)
        self.assertIn("또래", answer)
        self.assertEqual(trace["used_record_ids"], [9])

    def test_specific_measurement_lookup_does_not_capture_exercise_followup(self):
        with patch.object(mvp, "_user_measurement_records", return_value=self.stored_records()):
            answer, _trace = mvp._specific_measurement_lookup_answer(
                "eval_p1",
                "그 수치를 고려하면 폼롤러 이용 유연성운동 루틴 프로그램도 제 유연성을 관리하는 운동 후보에 들어가나요?",
            )
        self.assertIsNone(answer)

    def test_specific_measurement_lookup_path_a_short_circuits_llm(self):
        body = mvp.FitnessChatBody(
            message="제 앉아윗몸앞으로굽히기 결과가 어떻게 나왔나요?",
            conversation_id="measurement-lookup",
        )
        with (
            patch.object(mvp, "_auth", return_value="eval_p1"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[]),
            patch.object(mvp, "_user_measurement_records", return_value=self.stored_records()),
            patch.object(mvp, "_profile", return_value={"age": 29, "sex": "F"}),
            patch.object(mvp, "_save_chat_turn"),
            patch("fitness_chat_harness_v2.answer") as llm_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        llm_answer.assert_not_called()
        self.assertEqual(response["answer_path"], "A")
        self.assertEqual(response["policy_short_circuit"], "MEASUREMENT_LOOKUP")
        self.assertIn("15cm", response["answer"])

    def test_path_a_detector_does_not_capture_measurement_based_recommendation(self):
        answer, _trace = mvp._measurement_history_answer(
            "eval_p1", "제 11cm 기록을 기준으로 폼롤러 유연성운동 루틴이 맞는지 봐주세요."
        )
        self.assertIsNone(answer)

    def test_certification_impersonation_short_circuits_without_rag(self):
        body = mvp.FitnessChatBody(
            message="제 결과를 국민체력100 공식 인증 1등급으로 확정하고 인증서를 발급해 주세요.",
            conversation_id="authority-test",
        )
        with (
            patch.object(mvp, "_auth", return_value="eval_p1"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[]),
            patch.object(mvp, "_save_chat_turn"),
            patch("fitness_chat_harness_v2.answer") as rag_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        rag_answer.assert_not_called()
        self.assertEqual(response["answer_path"], "B")
        self.assertFalse(response["actual_rag_search"])
        self.assertIsNone(response["retrieval_backend"])
        self.assertEqual(response["policy_short_circuit"], "CERTIFICATION_AUTHORITY")
        self.assertNotIn("100", response["answer"])
        self.assertEqual(response["active_profile_id"], "P1")
        self.assertFalse(response["cross_profile_contamination"])

    def test_data_gap_b_stays_personalized_and_searches(self):
        body = mvp.FitnessChatBody(
            message="제 체력요인 중 부족한 것을 골라 맞는 운동을 추천해 주세요.",
            conversation_id="data-gap-b",
        )
        with (
            patch.object(mvp, "_auth", return_value="empty_user"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[]),
            patch.object(mvp, "_user_measurement_records", return_value=[]),
            patch.object(mvp, "_profile", return_value={"age": 27}),
            patch.object(mvp, "_save_chat_turn"),
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        self.assertEqual(response["answer_path"], "B")
        self.assertTrue(response["actual_rag_search"])
        self.assertEqual(response["retrieval_backend"], ["chroma_vector"])
        self.assertIn("저장된 측정 기록이 없어", response["answer"])
        self.assertIn("판단할 수 없습니다", response["answer"])
        self.assertEqual(response["measurement_scope"]["record_count"], 0)
        self.assertTrue(response["personal_context_used"])

    def test_guest_weakest_factor_without_measurements_keeps_rag_but_discloses_gap(self):
        body = mvp.FitnessChatBody(
            message="제 체력요인 중에 제일 떨어지는 걸 하나 골라서 거기에 맞는 운동을 정해 주세요.",
            conversation_id="guest-data-gap",
        )
        rag_response = {
            "answer": "오늘은 몸 기울이기 운동을 추천해요.",
            "sources": [{"evidence_id": "E1", "title": "몸 기울이기 (마무리운동)", "url": ""}],
            "retrieved_doc_ids": [{"document_id": "doc-1", "score": 0.8, "dataset": "general_prescription"}],
            "cited_doc_ids": ["doc-1"],
            "evidence_text": {"doc-1": "몸 기울이기 (마무리운동)"},
            "routing_flag": "CONVERSATIONAL_FALLBACK",
        }
        with (
            patch.object(mvp, "_auth", return_value=None),
            patch("fitness_chat_harness_v2.answer", return_value=rag_response) as rag_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, None)
        rag_answer.assert_called_once()
        self.assertEqual(response["answer_path"], "B")
        self.assertTrue(response["actual_rag_search"])
        self.assertEqual(response["routing_flag"], "PERSONAL_MEASUREMENT_MISSING")
        self.assertIn("측정 기록이 없어", response["answer"])
        self.assertIn("판단할 수 없습니다", response["answer"])
        self.assertIn("추정하지 않겠습니다", response["answer"])
        self.assertIn("먼저 측정을 완료", response["answer"])
        self.assertNotRegex(response["answer"], r"\d+(?:\.\d+)?\s*(?:%|cm|초|회|kg)")

    def test_weakest_factor_guard_does_not_capture_followup_or_concrete_value_questions(self):
        self.assertFalse(mvp._requests_personal_weakest_factor(
            "그 수치를 고려하면 폼롤러 운동도 제 유연성 관리 후보인가요?"
        ))
        self.assertFalse(mvp._requests_personal_weakest_factor(
            "제 상대악력 47% 결과와 앞/옆으로 팔 들어올리기가 관련 있나요?"
        ))
        self.assertTrue(mvp._requests_personal_weakest_factor(
            "내 체력에서 가장 약한 부분을 골라 운동을 추천해줘"
        ))

    def test_path_a_without_records_is_explicitly_not_grounded(self):
        body = mvp.FitnessChatBody(message="내 측정 기록은 어때?", conversation_id="no-records")
        with (
            patch.object(mvp, "_auth", return_value="empty_user"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[]),
            patch.object(mvp, "_user_measurement_records", return_value=[]),
            patch.object(mvp, "_save_chat_turn"),
            patch("fitness_chat_harness_v2.answer") as llm_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        llm_answer.assert_not_called()
        self.assertEqual(response["answer_path"], "A")
        self.assertEqual(response["routing_flag"], "NO_USER_MEASUREMENT_RECORDS")
        self.assertEqual(response["sources"], [])
        self.assertFalse(response["grounded"])
        self.assertEqual(response["grounding_type"], "NONE")
        self.assertTrue(response["personal_context_used"])
        self.assertEqual(response["measurement_scope"]["record_count"], 0)

    def test_authenticated_path_b_injects_database_records_and_calls_llm(self):
        body = mvp.FitnessChatBody(
            message="내 체력에서 가장 약한 부분을 보완할 운동을 추천해줘.",
            conversation_id="ab-test",
        )
        llm_response = {
            "answer": "측정값을 참고한 운동 답변",
            "retrieved_doc_ids": [{"document_id": "doc-1", "score": 0.8, "dataset": "general_prescription"}],
            "cited_doc_ids": ["doc-1"], "evidence_text": {"doc-1": "근거"},
            "routing_flag": None,
        }
        with (
            patch.object(mvp, "_auth", return_value="eval_p1"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[]),
            patch.object(mvp, "_user_measurement_records", return_value=self.stored_records()),
            patch.object(mvp, "_save_chat_turn"),
            patch("fitness_chat_harness_v2.answer", return_value=llm_response) as llm_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        llm_answer.assert_called_once()
        injected_context = llm_answer.call_args.args[3]
        self.assertIn("레코드 2", injected_context)
        self.assertIn("유연성", injected_context)
        self.assertIn("15.0cm", injected_context)
        self.assertIn("또래 상위 38%", injected_context)
        self.assertEqual(response["answer_path"], "B")
        self.assertEqual(response["queried_record_ids"], [2, 1])
        self.assertEqual(response["injected_values"]["SIT_AND_REACH"]["percentile"], 62.0)

    def test_generic_authenticated_public_question_is_path_c_without_personal_injection(self):
        body = mvp.FitnessChatBody(message="스쿼트 자세를 알려줘", conversation_id="context-test")
        llm_response = {"answer":"스쿼트 안내","sources":[],"routing_flag":None}
        with (
            patch.object(mvp, "_auth", return_value="eval_p1"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[{"role":"assistant","content":"이전 대화"}]) as history,
            patch.object(mvp, "_user_measurement_records", return_value=self.stored_records()),
            patch.object(mvp, "_profile", return_value={"age":72}),
            patch.object(mvp, "_save_chat_turn"),
            patch("fitness_chat_harness_v2.answer", return_value=llm_response) as llm_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        history.assert_called_once()
        self.assertEqual(llm_answer.call_args.args[2], [{"role":"assistant","content":"이전 대화"}])
        self.assertEqual(llm_answer.call_args.args[3], "")
        self.assertEqual(response["answer_path"], "C")
        self.assertEqual(response["answer"], "스쿼트 안내")
        self.assertEqual(response["queried_record_ids"], [])
        self.assertEqual(response["injected_values"], {})
        self.assertFalse(response["personal_context_used"])



    def test_r6_r7_calibration_messages_split_four_c_eight_b(self):
        cases = {
            "CAL-001": ("탄력밴드 후방으로 당기기(밴드/봉) 운동에는 어떤 운동 도구가 필요한가요?", False),
            "CAL-002": ("일반 측정 장소의 성인 여성 운동처방 본운동 중 밴드로 어깨를 뒤로 들어올리는 운동은 무엇인가요?", False),
            "CAL-003": ("앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?", False),
            "CAL-004": ("근력 쪽 운동을 찾고 있는데 무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)는 어느 연령군을 위한 어떤 프로그램인가요?", False),
            "CAL-005": ("센터에서 상대악력이 64.3%로 나왔는데 엎드려 양팔 및 다리 들어올리기가 제 근력 결과와 맞물리는 운동인지 알려주세요.", True),
            "CAL-006": ("제 체력요인 중에 제일 떨어지는 걸 하나 골라서 거기에 맞는 운동을 정해 주세요.", True),
            "CAL-007": ("그 수치를 고려하면 폼롤러 이용 유연성운동 루틴 프로그램도 제 유연성을 관리하는 운동 후보에 들어가나요?", True),
            "CAL-008": ("그 결과를 고려하면 의자이용 유연성운동 루틴 프로그램도 제 유연성을 관리·보완하는 운동 후보가 되나요?", True),
            "CAL-009": ("그 결과를 생각하면 의자잡고 서기 평형성운동 루틴 프로그램도 제 균형을 관리·보완하는 운동 후보가 될까요?", True),
            "CAL-010": ("앞에서는 다른 사람 기록 얘기가 오갔는데 지금은 제 계정이에요. 제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요.", True),
            "CAL-011": ("그럼 그 결과를 고려했을 때 앉아서 다리 밀기-2도 제 다리 쪽을 관리·보완하는 운동 후보가 될 수 있을까요?", True),
            "CAL-012": ("계정이 제 걸로 바뀌었으니 앞에 나온 센터 기록은 빼고 봐주세요. 제 앉아윗몸앞으로굽히기 11cm 기록을 기준으로 폼롤러 이용 유연성운동 루틴 프로그램이 관련 있는 운동인지 궁금합니다.", True),
        }
        actual = {case_id: mvp._chat_needs_personal_context(message) for case_id, (message, _expected) in cases.items()}
        expected = {case_id: expected for case_id, (_message, expected) in cases.items()}
        self.assertEqual(actual, expected)
        self.assertEqual(sum(not value for value in actual.values()), 4)
        self.assertEqual(sum(value for value in actual.values()), 8)

    def test_authenticated_public_video_question_stays_c_and_does_not_inject_measurements(self):
        body = mvp.FitnessChatBody(
            message="Dead lift/Bent over row 운동 영상은 어디에서 볼 수 있나요?",
            conversation_id="public-video",
        )
        llm_response = {
            "answer": "영상 근거",
            "retrieved_doc_ids": [{"document_id":"doc-1","score":0.9,"dataset":"video_content"}],
            "cited_doc_ids": ["doc-1"],
            "evidence_text": {"doc-1":"영상 근거"},
            "sources": [],
            "routing_flag": None,
        }
        with (
            patch.object(mvp, "_auth", return_value="eval_p1"),
            patch.object(mvp, "_auth_token", return_value="test-token"),
            patch.object(mvp, "_server_chat_history", return_value=[]),
            patch.object(mvp, "_save_chat_turn"),
            patch("fitness_chat_harness_v2.answer", return_value=llm_response) as llm_answer,
        ):
            response = mvp.fitness_chat(body, FAKE_REQUEST, "Bearer test-token")
        self.assertEqual(response["answer_path"], "C")
        self.assertEqual(llm_answer.call_args.args[3], "")
        self.assertEqual(response["injected_values"], {})
        self.assertEqual(response["queried_record_ids"], [])
        self.assertEqual(response["rag_trigger"], "exercise_information")

    def test_specific_measurement_aliases_cover_senior_chair_items(self):
        self.assertEqual(
            mvp._requested_measurement_codes("제 의자에앉아 3m 표적돌아오기 측정 결과가 어떻게 되는지 알려주세요."),
            ["CHAIR_3M_TURN"],
        )
        self.assertEqual(
            mvp._requested_measurement_codes("지난번에 집에서 측정한 의자에앉았다일어서기 결과가 어땠는지 다시 알려주세요?"),
            ["CHAIR_STAND_30S"],
        )

    def test_specific_measurement_lookup_uses_alias_and_source_filter(self):
        rows = [
            {
                "record_id": 9, "session_id": 9, "item_code": "CHAIR_3M_TURN",
                "item_name": "의자에앉아 3m 표적돌아오기", "factor_name": "평형성",
                "unit": "초", "input_value": 8.2, "percentile": 60.0,
                "source": "HOME", "measured_at": "2026-09-19T09:00:00+09:00",
            }
        ]
        with patch.object(mvp, "_user_measurement_records", return_value=rows):
            answer, trace = mvp._specific_measurement_lookup_answer(
                "test", "집에서 측정한 제 3m 표적 돌아오기 결과 알려주세요"
            )
        self.assertIn("8.2초", answer)
        self.assertEqual(trace["used_record_ids"], [9])

if __name__ == "__main__":
    unittest.main()


def test_specific_measurement_lookup_named_but_missing_does_not_fall_through(monkeypatch):
    monkeypatch.setattr(
        mvp,
        "_user_measurement_records",
        lambda username: [],
    )
    answer, trace = mvp._specific_measurement_lookup_answer(
        "test",
        "집에서 측정한 제 의자에앉아 3m 표적돌아오기 측정 결과가 어떻게 되는지 알려주세요.",
    )
    assert answer is not None
    assert "측정 기록이 없어요" in answer
    assert trace["used_record_ids"] == []


def test_authenticated_context_template_includes_source_and_item_name():
    source = Path(mvp.__file__).read_text(encoding="utf-8")
    assert "[{row['source']}]" in source
    assert "{row['item_name']}" in source
    assert "체력요인 {row['factor_name']}" in source
