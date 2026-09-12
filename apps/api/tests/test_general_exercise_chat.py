import json
import unittest
from threading import Lock
from unittest.mock import Mock
from general_exercise_chat import use_general, answer
from fitness_web_server import RagRuntime, ChatRequest


class GeneralExerciseTests(unittest.TestCase):
    def setUp(self):
        self.context = {"selected_name": "허리 돌리기", "profile": {"target_area": "허리"}}

    def test_body_change_and_general_topics_escape_selected_card(self):
        for q in ("다리운동 추천해줘", "다리 운동", "스쿼트 방법", "스쿼트 몇 세트 해?", "걷기 추천해줘", "팔 운동 방법", "유산소와 근력 운동 차이", "초보 루틴 알려줘", "운동 후 회복은 어떻게 해?", "걷기와 달리기 비교"):
            with self.subTest(q=q):
                self.assertTrue(use_general(q, self.context))
        self.assertFalse(use_general("이 운동 왜 추천한거야?", self.context))
        self.assertFalse(use_general("준비물이 뭐야?", self.context))

    def test_general_followup_does_not_jump_back_to_old_card(self):
        self.context["chat_mode"] = "general"
        self.assertTrue(use_general("이 운동은 어떻게 해?", self.context))
        self.assertTrue(use_general("그럼 몇 번 해?", self.context))
        self.assertFalse(use_general("선택한 카드의 영상 알려줘", self.context))

    def test_general_knowledge_has_no_invented_rag_attribution(self):
        client = Mock()
        client.complete_json.return_value = json.dumps({"paragraphs": ["다리 운동의 예로 스쿼트가 있어요.", "집에서 할 운동을 찾고 계세요?"]})
        result = answer(client, "다리 운동", [], self.context)
        self.assertEqual(result["answer_kind"], "general_exercise_knowledge")
        self.assertFalse(result["sources"])
        self.assertNotIn("허리", client.complete_json.call_args.args[1])
        self.assertEqual(self.context["chat_mode"], "general")

    def test_no_recommendation_required_for_first_question(self):
        runtime = RagRuntime.__new__(RagRuntime)
        runtime.answer_lock = Lock()
        runtime.chat_contexts = {}
        runtime._chat_age_bmi_recommendation = Mock(return_value=None)
        runtime._chat_recommendation = Mock(side_effect=AssertionError("no stale recommendation"))
        runtime.harness = Mock()
        runtime.harness.client.complete_json.return_value = json.dumps({"paragraphs": ["유산소 운동과 근력 운동은 목적이 달라요."]})
        result = runtime.chat(ChatRequest(user_id="new", message="유산소와 근력의 차이"))
        self.assertTrue(result["context_ready"])
        self.assertEqual(result["answer_kind"], "general_exercise_knowledge")

    def test_unsafe_or_foreign_generated_answer_not_displayed(self):
        client = Mock()
        for line in ("Squat 운동입니다.", "통증을 참고 운동해요."):
            client.complete_json.return_value = json.dumps({"paragraphs": [line]})
            self.assertEqual(answer(client, "운동 추천", [], {})["answer_kind"], "generation_error")

    def test_ambiguous_method_is_clarified_then_sourced(self):
        client = Mock(side_effect=AssertionError("verified method must not be invented"))
        context = {"general_history": [{"role": "assistant", "content": "미니 스쿼트와 뒤꿈치 들기가 있어요."}]}
        result = answer(client, "그 운동 어떻게 해?", [], context)
        self.assertEqual(result["answer_kind"], "clarification")
        result = answer(client, "미니 스쿼트", [], context)
        self.assertEqual(result["answer_kind"], "verified_general_guidance")
        self.assertIn("천천히", result["answer"])
        self.assertTrue(result["guidance_sources"])
        client.complete_json.assert_not_called()

    def test_incomplete_sentence_is_retried_once(self):
        client = Mock()
        client.complete_json.return_value = json.dumps({"paragraphs": ["운동을 하는 방"]})
        result = answer(client, "운동 설명", [], {})
        self.assertEqual(result["answer_kind"], "generation_error")
        self.assertEqual(client.complete_json.call_count, 2)

    def test_known_exercise_intro_does_not_invent_movement(self):
        client = Mock()
        client.complete_json.return_value = json.dumps({"paragraphs": ["옆으로 다리 들기는 앞으로 다리를 움직이는 운동이에요."]})
        result = answer(client, "다리 운동", [], {})
        self.assertNotIn("앞으로", result["answer"])
        self.assertIn("옆으로 다리 들기", result["answer"])
        self.assertTrue(result["guidance_sources"])

    def test_new_body_request_never_calls_old_body_recommendation(self):
        runtime = RagRuntime.__new__(RagRuntime)
        runtime.answer_lock = Lock()
        runtime.chat_contexts = {"test": self.context}
        runtime._chat_age_bmi_recommendation = Mock(return_value=None)
        runtime._chat_recommendation = Mock(side_effect=AssertionError("stale body"))
        runtime.harness = Mock()
        runtime.harness.client.complete_json.return_value = json.dumps({"paragraphs": ["다리 운동으로 스쿼트를 살펴볼 수 있어요."]})
        result = runtime.chat(ChatRequest(user_id="test", message="다리운동 추천해줘"))
        self.assertIn("다리", result["answer"])
        runtime._chat_recommendation.assert_not_called()
