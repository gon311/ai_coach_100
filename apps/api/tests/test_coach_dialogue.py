import json
import unittest
from threading import Lock
from unittest.mock import Mock, patch

from coach_dialogue import CONTINUE, INTENT_SCHEMA, is_recommendation, render, respond, safety_update
from qwen3_grounded_harness import ABSTENTION, GroundedQwen3Harness, Qwen3Client

EVIDENCE = [{"evidence_id": "E7", "text": "운동명: 의자에서 일어나기\n운동 부위: 허벅지\n운동 유형: 근력\n대상 연령군: 성인\n운동 도구: 의자\n운동 장소: 실내\n운동 단계: 본운동\n난이도: 초급"}]
PROFILE = {"target_area": "허벅지", "exercise_type": "근력", "age_group": "성인"}


class DialogueTests(unittest.TestCase):
    def test_reason_does_not_replace_exercise(self):
        for question in ("그 운동을 왜 추천하는거야?", "이 운동 추천 이유가 뭐야", "추천해 준 이유 알려줘", "추천한 근거가 있어?"):
            with self.subTest(question=question):
                self.assertFalse(is_recommendation(question))

    def test_actual_recommendation_and_properties(self):
        for question in ("다른 본운동 추천해줘", "팔 근력 운동 추천해줘", "그다음은?", "대신 다른 운동 알려줘"):
            self.assertTrue(is_recommendation(question))
        for question in ("장비 없어도 돼?", "이어서 작성해줘", "영상 있어?", "난이도는?"):
            self.assertFalse(is_recommendation(question))

    def test_pain_before_all_routes_and_persists(self):
        from fitness_web_server import RagRuntime, ChatRequest
        runtime = RagRuntime.__new__(RagRuntime)
        runtime.answer_lock = Lock()
        runtime.chat_contexts = {"test": {"profile": dict(PROFILE)}}
        runtime._chat_recommendation = Mock(side_effect=AssertionError("unsafe recommendation"))
        first = runtime.chat(ChatRequest(user_id="test", message="무릎이 아픈데 제자리달리기 추천해줘"))
        second = runtime.chat(ChatRequest(user_id="test", message="그럼 다른 운동 추천해줘"))
        self.assertFalse(first["sources"])
        self.assertFalse(second["sources"])
        self.assertTrue(runtime.chat_contexts["test"]["safety_pending"])

    def test_pain_negation_and_severe_profile(self):
        self.assertIsNone(safety_update("무릎 통증이 없어요", {}))
        self.assertIsNone(safety_update("무릎이 아프지 않아요", {}))
        self.assertIsNotNone(safety_update("무릎 통증이 없어요. 어깨가 아파요", {}))
        self.assertIsNotNone(safety_update("다른 운동 추천", {"pain_level": 8}))

    def test_reason_uses_matches_without_safety_inference(self):
        answer, _ = render("왜 추천?", ["reason"], PROFILE, "의자에서 일어나기", EVIDENCE, ABSTENTION)
        self.assertIn("조건이 이 운동의 원문과 일치", answer)
        self.assertNotIn("안전해요", answer)
        self.assertNotIn("조건 일치만으로", answer)
        self.assertEqual(answer.count("[E7]"), 2)

    def test_composite_reports_missing_method_without_dropping_equipment(self):
        answer, _ = render("도구와 방법", ["equipment", "method"], PROFILE, "의자에서 일어나기", EVIDENCE, ABSTENTION)
        self.assertIn("의자", answer)
        self.assertIn("충분한 정보가 없어요", answer)
        self.assertNotIn("본운동", answer)  # stage is NOT a method

    def test_each_fact_keeps_its_own_source(self):
        sources = [{"evidence_id": "E1", "text": "운동 도구: 의자"}, {"evidence_id": "E2", "text": "운동 장소: 실내"}]
        answer, _ = render("도구와 장소", ["equipment", "location"], {}, "운동", sources, ABSTENTION)
        self.assertIn("의자’예요 [E1]", answer)
        self.assertIn("실내’예요 [E2]", answer)

    def test_conflicting_fact_does_not_hide_other_answerable_fact(self):
        sources = [*EVIDENCE, {"evidence_id": "E8", "text": "운동 도구: 덤벨"}]
        answer, _ = render("도구와 장소", ["equipment", "location"], {}, "운동", sources, ABSTENTION)
        self.assertIn("원문끼리 달라", answer)
        self.assertIn("실내", answer)
        self.assertNotIn("덤벨", answer)

    def test_model_facts_and_unknown_topics_never_reach_output(self):
        client = Mock()
        client.complete_json.return_value = '{"답변":"100회 하면 완치됩니다 [E99]"}'
        state = {}
        answer = respond(client, "prompt", "도구는?", [], {}, "운동", EVIDENCE, ABSTENTION, state)
        self.assertIn("의자", answer)
        self.assertNotIn("100", answer)
        self.assertNotIn("E99", answer)
        self.assertTrue(state["trace"]["errors"])

    def test_semantic_question_uses_model_topic(self):
        client = Mock()
        client.complete_json.return_value = '{"topics":["equipment"]}'
        state = {}
        answer = respond(client, "prompt", "뭘 챙겨야 해?", [], {}, "운동", EVIDENCE, ABSTENTION, state)
        self.assertIn("의자", answer)
        self.assertEqual(state["trace"]["intent_source"], "model")

    def test_explicit_topics_cannot_be_dropped(self):
        client = Mock()
        client.complete_json.return_value = '{"topics":["name"]}'
        answer = respond(client, "prompt", "도구와 방법", [], {}, "운동", EVIDENCE, ABSTENTION, {})
        self.assertIn("의자", answer)
        self.assertIn("충분한 정보가 없어요", answer)

    def test_semantic_part_of_composite_is_not_dropped(self):
        client = Mock()
        client.complete_json.return_value = '{"topics":["equipment","dose"]}'
        answer = respond(client, "prompt", "준비물은 뭐고 몇 번씩 해야 해?", [], {}, "운동", EVIDENCE, ABSTENTION, {})
        self.assertIn("의자", answer)
        self.assertIn("횟수", answer)

    def test_foreign_title_translation_does_not_hide_korean_name(self):
        sources = [{"evidence_id": "E9", "text": "운동명: 허리 스트레칭(Trunk stretch)"}]
        answer, _ = render("이름", ["name"], {}, "운동", sources, ABSTENTION)
        self.assertIn("허리 스트레칭", answer)
        self.assertNotIn("Trunk", answer)

    def test_reason_can_explain_title_match_without_inventing_body_label(self):
        sources = [{"evidence_id": "E1", "text": "운동명: 허리 스트레칭"}]
        answer, _ = render("이유", ["reason"], {"target_area": "허리"}, "허리 스트레칭", sources, ABSTENTION)
        self.assertIn("원문 운동명에 포함", answer)
        self.assertIn("[E1]", answer)

    def test_video_recommendation_is_about_current_exercise(self):
        self.assertFalse(is_recommendation("이 운동 영상 추천해줘"))

    def test_continuation_never_repeats_facts_or_calls_model(self):
        client = Mock()
        client.complete_json.return_value = '{"topics":["equipment","location"]}'
        state = {}
        first = respond(client, "prompt", "도구와 장소", [], {}, "운동", EVIDENCE, ABSTENTION, state)
        second = respond(client, "prompt", "이어서 작성해줘", [], {}, "운동", EVIDENCE, ABSTENTION, state)
        self.assertIn("의자", first)
        self.assertNotIn("의자", second)
        self.assertIn("새로운 원문 정보가 없어요", second)
        self.assertEqual(client.complete_json.call_count, 1)

    def test_long_source_is_not_cut_mid_fact(self):
        sources = [{"evidence_id": "E1", "text": "설명: " + "긴설명" * 200}]
        answer, _ = render("길게 설명", ["description"], {}, "운동", sources, ABSTENTION)
        self.assertEqual(answer, ABSTENTION)

    def test_source_language_drift_is_not_shown(self):
        sources = [{"evidence_id": "E1", "text": "설명: 健康 exercise 운동"}]
        answer, _ = render("설명", ["description"], {}, "운동", sources, ABSTENTION)
        self.assertEqual(answer, ABSTENTION)

    def test_five_sentence_limit_and_cursor(self):
        topics = ["name", "area", "equipment", "location", "difficulty", "stage", "age"]
        first, seen = render("모두", topics, PROFILE, "운동", EVIDENCE, ABSTENTION)
        self.assertEqual(len(seen), 5)
        second, other = render("이어서", topics, PROFILE, "운동", EVIDENCE, ABSTENTION, seen)
        self.assertTrue(other)
        self.assertFalse(set(seen) & set(other))

    def test_transport_disables_thinking_and_rejects_truncation(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"choices": [{"finish_reason": "length", "message": {"content": '{"topics":["area"]}'}}]}).encode()
        with patch("qwen3_grounded_harness.urllib.request.urlopen", return_value=response) as send:
            with self.assertRaises(ValueError):
                Qwen3Client().complete_json("system", "user", max_tokens=128, response_schema=INTENT_SCHEMA)
        payload = json.loads(send.call_args.args[0].data)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(payload["max_tokens"], 128)
        self.assertFalse(payload["response_format"]["schema"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
