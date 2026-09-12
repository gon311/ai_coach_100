import json
import unittest
from unittest.mock import Mock

from coach_dialogue import respond, render
from coaching_interpretation import validate, generate
from qwen3_grounded_harness import ABSTENTION, GroundedQwen3Harness

EVIDENCE = [{"evidence_id": "E1", "text": "운동명: 목 돌리기\n설명: 목 유연성 운동\n운동 장소: 수영장"}]
PROFILE = {"target_area": "목", "exercise_type": "유연성", "location": "수영장"}
GOOD = {"coaching": ["목 주변의 편안한 움직임을 살펴보려는 목적에 연결해 볼 수 있어요."],
        "follow_up": "일상에서 어떤 상황의 움직임을 편하게 하고 싶으세요?", "guidance_ids": ["G1"]}


class CoachingTests(unittest.TestCase):
    def test_fact_and_inference_have_distinct_attribution(self):
        client = Mock()
        client.complete_json.side_effect = [json.dumps({"topics": ["reason"]}), json.dumps(GOOD)]
        state = {}
        answer = respond(client, "intent", "왜 추천한거야?", [], PROFILE,
            "목 돌리기", EVIDENCE, ABSTENTION, state, "coaching")
        self.assertIn("[E1]", answer.split("코치의 해석:")[0])
        self.assertNotIn("[E1]", answer.split("코치의 해석:")[1])
        self.assertNotIn("수영장", answer)
        self.assertTrue(state["trace"]["coaching"]["used"])
        self.assertTrue(state["guidance_sources"])

    def test_why_prioritizes_exercise_over_venue_without_model(self):
        answer, _ = render("왜?", ["reason"], PROFILE, "목 돌리기", EVIDENCE, ABSTENTION)
        self.assertIn("목", answer)
        self.assertNotIn("수영장", answer)
        self.assertNotIn("조건 일치만으로", answer)

    def test_prescriptions_diagnoses_and_invented_citations_rejected(self):
        for line in ("매일 20회 하면 좋아요.", "목 디스크를 치료할 수 있어요.",
                     "통증을 완화해요.", "누구에게나 안전해요.", "고개를 뒤로 젖히세요.",
                     "영상에서 이 자세를 안내해요.", "유연성에 좋아요 [E1]", "Flexibility에 좋아요."):
            with self.subTest(line=line):
                self.assertTrue(validate({**GOOD, "coaching": [line]}, "목 돌리기", []))

    def test_rejected_interpretation_never_reaches_user(self):
        client = Mock()
        client.complete_json.side_effect = [json.dumps({"topics": ["reason"]}), json.dumps({**GOOD, "coaching": ["30회 하면 완치돼요."]})]
        state = {}
        answer = respond(client, "intent", "왜?", [], PROFILE, "목 돌리기", EVIDENCE, ABSTENTION, state, "coaching")
        self.assertNotIn("완치", answer)
        self.assertNotIn("30", answer)
        self.assertFalse(state["guidance_sources"])

    def test_missing_dosage_stays_unknown(self):
        client = Mock()
        client.complete_json.return_value = json.dumps({"topics": ["dose"]})
        answer = respond(client, "intent", "몇 회 해야해?", [], PROFILE, "목 돌리기", EVIDENCE, ABSTENTION, {}, "coaching")
        self.assertEqual(answer, ABSTENTION)
        self.assertEqual(client.complete_json.call_count, 1)

    def test_generated_paragraph_is_bounded_to_complete_sentences(self):
        client = Mock()
        client.complete_json.return_value = json.dumps({**GOOD, "coaching": [
            "움직임을 살펴볼 수 있어요. 목표에 따라 선택 기준이 달라져요.",
            "생활 속 목적을 정할 수 있어요. 편안한 범위에서 시작해요."]})
        output, refs, trace = generate(client, "prompt", "왜?", [], PROFILE,
                                       "목 돌리기", EVIDENCE, {})
        self.assertTrue(trace["used"])
        self.assertEqual(output[0], "움직임을 살펴볼 수 있어요. 목표에 따라 선택 기준이 달라져요.")

    def test_followup_drops_an_already_displayed_sentence(self):
        client = Mock()
        client.complete_json.return_value = json.dumps({**GOOD, "coaching": [
            "목 주변의 편안한 움직임을 살펴보려는 목적에 연결해 볼 수 있어요.",
            "운동 선택 전 일상에서 확인하고 싶은 목표를 구체화해 볼 수 있어요."]})
        output, refs, trace = generate(client, "prompt", "어떤 의미야?", [], PROFILE,
                                       "목 돌리기", EVIDENCE, {"interpretations": GOOD["coaching"]})
        self.assertTrue(trace["used"])
        self.assertNotIn("목 주변의", output[0])
        self.assertIn("구체화", output[0])

    def test_pain_still_blocks_model(self):
        client = Mock(side_effect=AssertionError("must not call model"))
        answer = respond(client, "intent", "목이 아픈데 왜 추천?", [], PROFILE, "목 돌리기", EVIDENCE, ABSTENTION, {}, "coaching")
        self.assertIn("통증", answer)
        client.complete_json.assert_not_called()

    def test_repeat_repair_is_bounded(self):
        client = Mock()
        client.complete_json.return_value = json.dumps(GOOD)
        result, refs, trace = generate(client, "prompt", "다시 설명", [], PROFILE,
            "목 돌리기", EVIDENCE, {"interpretations": GOOD["coaching"]})
        self.assertIsNone(result)
        self.assertFalse(refs)
        self.assertEqual(client.complete_json.call_count, 2)

    def test_property_answer_clears_general_references(self):
        client = Mock()
        client.complete_json.return_value = json.dumps({"topics": ["name"]})
        state = {"guidance_sources": [{"url": "old"}]}
        answer = respond(client, "intent", "운동 이름", [], PROFILE, "목 돌리기", EVIDENCE, ABSTENTION, state, "coaching")
        self.assertFalse(state["guidance_sources"])
        self.assertNotIn("코치의 해석", answer)


if __name__ == "__main__":
    unittest.main()
