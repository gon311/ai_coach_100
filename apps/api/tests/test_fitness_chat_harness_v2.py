import json
import unittest

from fitness_chat_harness_v2 import answer, _exercise_lookup_queries, _exact_exercise_sources, _deterministic_exact_response, _source_from_runtime_record, _explicit_exercise_lookup, _requested_exercise_match, _compact_match_text, _sqlite_exact_exercise_sources, _fetch_scan_exact_exercise_sources, _source_factor, _weakest_measurement_factor, _active_measurement_for_question, _measurement_assertion_status, _source_matches_explicit_constraints, _exact_miss_diagnostics, _normalize_full_record_result, _factor_facet_sources, _source_age_compatible, _user_life_stage, _source_life_stage, _last_recommended_exercise


RESULTS = [
    {
        "id": "doc-1",
        "dataset": "video_content",
        "title": "허리 스트레칭",
        "text": "유연성 향상을 위해 허리를 천천히 움직입니다.",
        "score": 0.82,
    },
    {
        "id": "doc-2",
        "dataset": "general_prescription",
        "title": "기초 운동",
        "text": "통증이 있으면 동작을 중단합니다.",
        "score": 0.71,
    },
]

FORBIDDEN = [
    "체력 인증등급", "1등급", "2등급", "3등급", "성별: M", "성별: F",
    "대상 연령군", "RAG_DOCUMENT", "measurement_prescription",
    "general_prescription", "video_content", "document_id",
    "레코드", "청력",
]


class FakeClient:
    def complete_json(self, *_args, **_kwargs):
        return json.dumps({"answer": "허리를 천천히 움직여 보세요. [E1]", "used_evidence": ["E1"]}, ensure_ascii=False)


class MismatchedCitationClient:
    def complete_json(self, *_args, **_kwargs):
        return json.dumps(
            {"answer": "허리를 천천히 움직여 보세요. [E1]", "used_evidence": ["E2"]},
            ensure_ascii=False,
        )


class BrokenCjkClient:
    def complete_json(self, *_args, **_kwargs):
        return json.dumps(
            {"answer": "그 운然是 허리 스트레칭입니다. [E1]", "used_evidence": ["E1"]},
            ensure_ascii=False,
        )


class FakeRuntime:
    qwen3_client = FakeClient()

    def semantic_search(self, *_args, **_kwargs):
        return [dict(item) for item in RESULTS]


class FitnessChatTraceTests(unittest.TestCase):
    def test_response_exposes_full_retrieval_and_cited_evidence(self):
        result = answer(FakeRuntime(), "허리 스트레칭 방법을 알려줘")
        self.assertEqual(
            result["retrieved_doc_ids"],
            [
                {"document_id": "doc-1", "score": 0.82, "dataset": "video_content"},
                {"document_id": "doc-2", "score": 0.71, "dataset": "general_prescription"},
            ],
        )
        self.assertEqual(result["cited_doc_ids"], ["doc-1"])
        self.assertEqual(result["evidence_text"], {"doc-1": RESULTS[0]["text"]})
        self.assertIsNone(result["routing_flag"])
        self.assertEqual(result["sources"][0]["title"], "허리 스트레칭")
        self.assertNotIn("document_id", result["sources"][0])
        self.assertNotIn("dataset", result["sources"][0])
        self.assertNotIn("excerpt", result["sources"][0])
        self.assertTrue(result["grounded"])
        self.assertEqual(result["grounding_type"], "GROUNDED")

    def test_user_context_does_not_become_a_rag_document(self):
        result = answer(
            FakeRuntime(), "내 체력에 맞는 허리 운동을 추천해줘",
            user_context="민첩성 11.2초 백분위 62",
        )
        self.assertEqual({item["document_id"] for item in result["retrieved_doc_ids"]}, {"doc-1", "doc-2"})
        self.assertTrue(result["cited_doc_ids"])
        self.assertTrue(all(doc_id in result["evidence_text"] for doc_id in result["cited_doc_ids"]))
        self.assertNotIn("민첩성 11.2초 백분위 62", " ".join(result["evidence_text"].values()))
        self.assertTrue(result["grounded"])
        self.assertEqual(result["grounding_type"], "GROUNDED")

    def test_generic_question_keeps_user_context_hidden_from_citations(self):
        result = answer(
            FakeRuntime(), "스쿼트 자세를 알려줘",
            user_context="로그인 사용자 프로필: 만 72세 SENIOR. 최근 측정기록: 레코드 206",
        )
        self.assertNotIn("레코드 206", result["answer"])
        self.assertTrue(all("dataset" not in source for source in result["sources"]))

    def test_out_of_scope_has_explicit_routing_flag(self):
        result = answer(FakeRuntime(), "오늘 날씨가 어때?")
        self.assertEqual(result["routing_flag"], "OUT_OF_SCOPE")
        self.assertEqual(result["retrieved_doc_ids"], [])
        self.assertEqual(result["cited_doc_ids"], [])
        self.assertEqual(result["sources"], [])
        self.assertFalse(result["grounded"])
        self.assertEqual(result["grounding_type"], "NONE")

    def test_mismatched_model_citation_list_uses_safe_evidence_fallback(self):
        runtime = FakeRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(runtime, "허리 스트레칭 방법을 알려줘")
        self.assertEqual(result["routing_flag"], "CONVERSATIONAL_FALLBACK")
        self.assertEqual(result["cited_doc_ids"], ["doc-1"])
        self.assertEqual(result["evidence_text"], {"doc-1": RESULTS[0]["text"]})

    def test_model_fallback_never_dumps_raw_user_measurement_context(self):
        runtime = FakeRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(
            runtime, "내 체력에 맞는 허리 운동을 추천해줘",
            user_context="로그인 사용자의 최근 측정기록: 레코드 206 심폐지구력 101.8회",
        )
        self.assertEqual(result["routing_flag"], "CONVERSATIONAL_FALLBACK")
        self.assertNotIn("레코드 206", result["answer"])
        self.assertNotIn("document_id", result["sources"][0])
        self.assertNotIn("dataset", result["sources"][0])

    def test_lifecycle_fallback_uses_relevant_source_without_crashing(self):
        runtime = FakeRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(
            runtime, "허리가 불편할 때 스트레칭 방법을 알려줘",
            user_context="로그인 사용자 프로필: 만 72세 SENIOR.",
        )
        self.assertEqual(result["routing_flag"], "CONVERSATIONAL_FALLBACK")
        self.assertIn("허리", result["answer"])

    def test_every_user_answer_hides_internal_metadata(self):
        runtime = FakeRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(
            runtime, "내 측정 결과를 반영해서 운동을 추천해줘",
            user_context=("로그인 사용자 프로필: 만 72세 SENIOR. 최근 측정기록: "
                          "레코드 206 유연성 10cm 또래 상위 82%"),
        )
        for word in FORBIDDEN:
            self.assertNotIn(word, result["answer"])
        self.assertNotIn("레코드 206", result["answer"])
        self.assertIn("최근 측정 결과", result["answer"])

    def test_followups_keep_recommended_exercise_and_alternative_excludes_it(self):
        runtime = FakeRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        first = answer(runtime, "오늘 어떤 운동을 추천해?")
        history = [
            {"role": "user", "content": "오늘 어떤 운동을 추천해?"},
            {"role": "assistant", "content": first["answer"]},
        ]
        why = answer(runtime, "왜 그 운동을 추천했어?", history)
        how = answer(runtime, "그 운동은 어떻게 해?", history)
        alternative = answer(runtime, "다른 운동도 추천해줘", history)
        recommended = _last_recommended_exercise(history)
        self.assertTrue(recommended)
        self.assertIn(recommended, why["answer"])
        self.assertIn(recommended, how["answer"])
        self.assertNotEqual(first["answer"], alternative["answer"])

    def test_unrequested_condition_specific_exercise_is_filtered(self):
        class ConditionRuntime(FakeRuntime):
            def semantic_search(self, *_args, **_kwargs):
                return [
                    {"id": "bad", "dataset": "video_content", "title": "요통 운동",
                     "text": "요통 환자를 위한 운동", "score": 0.9},
                    {"id": "safe", "dataset": "video_content", "title": "의자 일어서기",
                     "text": "하체 근력 운동", "score": 0.8},
                ]
        runtime = ConditionRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(
            runtime, "내 측정 결과를 반영해서 다시 추천해줘",
            user_context="로그인 사용자 프로필: 만 72세 SENIOR. 하지근기능 또래 상위 80%",
        )
        self.assertNotIn("요통", result["answer"])
        self.assertIn("의자 일어서기", result["answer"])

    def test_explicit_exercise_name_is_reranked_and_cited(self):
        class ExactRuntime(FakeRuntime):
            def semantic_search(self, *_args, **_kwargs):
                return [
                    {"id": "generic", "dataset": "video_content", "title": "전신 준비운동",
                     "text": "가볍게 몸을 움직입니다.", "score": 0.95},
                    {"id": "exact", "dataset": "video_content", "title": "의자 일어서기",
                     "text": "의자에서 일어섰다가 앉습니다.", "score": 0.72},
                ]
        runtime = ExactRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(runtime, "의자 일어서기 운동 방법을 알려줘")
        self.assertEqual(result["cited_doc_ids"], ["exact"])
        self.assertIn("의자 일어서기", result["answer"])

    def test_quoted_exercise_runs_precision_search_before_reranking(self):
        class QuotedRuntime(FakeRuntime):
            queries = []

            def semantic_search(self, query, **_kwargs):
                self.queries.append(query)
                if query == "의자 일어서기":
                    return [{"id": "exact", "dataset": "measurement_prescription",
                             "title": "의자 일어서기", "text": "하지 근력 본운동", "score": 0.7}]
                return [dict(item) for item in RESULTS]
        runtime = QuotedRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(runtime, "'의자 일어서기'는 어떤 운동인가요?")
        self.assertEqual(runtime.queries[-1], "의자 일어서기")
        self.assertEqual(result["cited_doc_ids"], ["exact"])


    def test_explicit_named_exercise_never_falls_back_to_unrelated_top_result(self):
        class ExactOnlyRuntime(FakeRuntime):
            def semantic_search(self, *_args, **_kwargs):
                return [
                    {"id": "wrong", "dataset": "video_content", "title": "척추 들어올리기",
                     "text": "허리 운동", "score": 0.95},
                    {"id": "exact", "dataset": "general_prescription",
                     "title": "폼롤러 이용 유연성운동 루틴 프로그램",
                     "text": "운동명: 폼롤러 이용 유연성운동 루틴 프로그램\n운동 단계: 본운동",
                     "score": 0.71},
                ]
        runtime = ExactOnlyRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(runtime, "그 결과를 고려하면 폼롤러 이용 유연성운동 루틴 프로그램도 제 유연성을 관리하는 운동 후보에 들어가나요?")
        self.assertEqual(result["cited_doc_ids"], ["exact"])
        self.assertIn("폼롤러 이용 유연성운동 루틴 프로그램", result["answer"])
        self.assertNotIn("척추 들어올리기", result["answer"])

    def test_explicit_named_exercise_without_exact_match_abstains_instead_of_substitution(self):
        class NoExactRuntime(FakeRuntime):
            def semantic_search(self, *_args, **_kwargs):
                return [
                    {"id": "wrong", "dataset": "video_content", "title": "탄력밴드 어깨 가쪽 돌림",
                     "text": "어깨 운동", "score": 0.95},
                ]
        result = answer(NoExactRuntime(), "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?")
        self.assertEqual(result["routing_flag"], "NO_EXACT_EXERCISE_EVIDENCE")
        self.assertEqual(result["cited_doc_ids"], [])
        self.assertNotIn("탄력밴드 어깨 가쪽 돌림", result["answer"])
        self.assertIn("직접 일치하는 근거", result["answer"])

    def test_parenthetical_storage_suffix_still_matches_korean_exercise_name(self):
        class AliasRuntime(FakeRuntime):
            def semantic_search(self, *_args, **_kwargs):
                return [
                    {"id": "exact", "dataset": "video_content",
                     "title": "앞/옆으로 팔 들어올리기(Front/Side lateral raise)",
                     "text": "운동명: 앞/옆으로 팔 들어올리기(Front/Side lateral raise)",
                     "score": 0.75},
                    {"id": "wrong", "dataset": "general_prescription", "title": "뒤로 팔 뻗기",
                     "text": "운동명: 뒤로 팔 뻗기", "score": 0.90},
                ]
        runtime = AliasRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(runtime, "제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요.")
        self.assertEqual(result["cited_doc_ids"], ["exact"])
        self.assertIn("앞/옆으로 팔 들어올리기", result["answer"])
        self.assertNotIn("뒤로 팔 뻗기", result["answer"])


    def test_exact_lookup_runs_subject_search_for_complex_personal_question(self):
        class SubjectSearchRuntime(FakeRuntime):
            queries = []
            def semantic_search(self, query, **_kwargs):
                self.queries.append(query)
                if "앞/옆으로 팔 들어올리기" in query and len(query) < 80:
                    return [{
                        "id": "exact-arm", "dataset": "video_content",
                        "title": "앞/옆으로 팔 들어올리기(Front/Side lateral raise)",
                        "text": "운동명: 앞/옆으로 팔 들어올리기(Front/Side lateral raise)",
                        "score": 0.74,
                    }]
                return [{
                    "id": "wrong-arm", "dataset": "general_prescription",
                    "title": "뒤로 팔 뻗기", "text": "운동명: 뒤로 팔 뻗기", "score": 0.92,
                }]
        runtime = SubjectSearchRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(
            runtime,
            "앞에서는 다른 사람 기록 얘기가 오갔는데 지금은 제 계정이에요. 제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요.",
            user_context="로그인 사용자 프로필: 성인 남성.",
        )
        self.assertEqual(result["cited_doc_ids"], ["exact-arm"])
        self.assertIn("앞/옆으로 팔 들어올리기", result["answer"])
        self.assertNotIn("뒤로 팔 뻗기", result["answer"])
        self.assertTrue(any("앞/옆으로 팔 들어올리기" in q for q in runtime.queries[1:]))

    def test_bilingual_named_exercise_gets_precision_search_even_when_broad_search_misses(self):
        class BilingualSearchRuntime(FakeRuntime):
            def semantic_search(self, query, **_kwargs):
                if "Knee up/Shoulder press" in query and len(query) < 120:
                    return [{
                        "id": "knee-up", "dataset": "video_content",
                        "title": "무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)",
                        "text": "운동명: 무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)\n대상 연령군: 성인\n4주차 표준운동프로그램",
                        "score": 0.70,
                    }]
                return [{
                    "id": "wrong", "dataset": "measurement_prescription",
                    "title": "무릎 굽혀 엉덩이 들어올리기",
                    "text": "운동명: 무릎 굽혀 엉덩이 들어올리기", "score": 0.90,
                }]
        runtime = BilingualSearchRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        result = answer(
            runtime,
            "근력 쪽 운동을 찾고 있는데 무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)는 어느 연령군을 위한 어떤 프로그램인가요?",
        )
        self.assertEqual(result["cited_doc_ids"], ["knee-up"])
        self.assertNotEqual(result["routing_flag"], "NO_EXACT_EXERCISE_EVIDENCE")

    def test_broken_cjk_model_output_is_replaced_by_safe_conversation(self):
        runtime = FakeRuntime()
        runtime.qwen3_client = BrokenCjkClient()
        history = [{"role": "assistant", "content": "오늘은 허리 스트레칭을 추천해요."}]
        result = answer(runtime, "그 운동은 어떻게 해?", history)
        self.assertNotRegex(result["answer"], r"[\u4e00-\u9fff]")
        self.assertIn("허리 스트레칭", result["answer"])
        self.assertEqual(result["routing_flag"], "CONVERSATIONAL_FALLBACK")


    def test_bilingual_slash_lookup_queries_include_individual_english_parts(self):
        queries = _exercise_lookup_queries(
            "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
        )
        compact = [q.casefold() for q in queries]
        self.assertTrue(any("dead lift" == q for q in compact))
        self.assertTrue(any("bent over row" == q for q in compact))

    def test_followup_fallback_preserves_prior_measurement_context(self):
        class ExactRuntime(FakeRuntime):
            def semantic_search(self, *_args, **_kwargs):
                return [{
                    "id": "foam", "dataset": "general_prescription",
                    "title": "폼롤러 이용 유연성운동 루틴 프로그램",
                    "text": "운동명: 폼롤러 이용 유연성운동 루틴 프로그램",
                    "score": 0.8,
                }]
        runtime = ExactRuntime()
        runtime.qwen3_client = MismatchedCitationClient()
        history = [
            {"role": "user", "content": "앉아윗몸앞으로굽히기 결과 알려줘"},
            {"role": "assistant", "content": "2026-09-19 집 측정의 앉아윗몸앞으로굽히기 결과는 10cm입니다."},
        ]
        result = answer(
            runtime,
            "그 수치를 고려하면 폼롤러 이용 유연성운동 루틴 프로그램도 제 유연성을 관리하는 운동 후보에 들어가나요?",
            history=history,
        )
        self.assertIn("앞서 확인한 측정 결과", result["answer"])
        self.assertIn("폼롤러 이용 유연성운동 루틴 프로그램", result["answer"])

if __name__ == "__main__":
    unittest.main()


def test_exercise_lookup_queries_keep_bilingual_components_and_slash_title():
    q1 = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    qs1 = _exercise_lookup_queries(q1)
    folded1 = " | ".join(qs1).casefold()
    assert "dead lift" in folded1
    assert "bent over row" in folded1

    q2 = "제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요."
    qs2 = _exercise_lookup_queries(q2)
    assert any("앞/옆으로 팔 들어올리기" in x for x in qs2)

class _ExactRuntime:
    def __init__(self):
        self.facet_records = [
            {"_id": "doc-dead", "_dataset": "video_content", "_exercise_name": "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)"},
            {"_id": "doc-band", "_dataset": "video_content", "_exercise_name": "탄력밴드 후방으로 당기기"},
            {"_id": "doc-knee", "_dataset": "general_prescription", "_exercise_name": "무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)"},
            {"_id": "doc-arm", "_dataset": "general_prescription", "_exercise_name": "앞/옆으로 팔 들어올리기"},
        ]
        self._records = {
            "doc-dead": {"dataset":"video_content","title":"앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)","content":"운동명: 앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)\n영상 URL: http://example.test/dead.mp4","metadata_json":"{}","occurrence_count":1},
            "doc-band": {"dataset":"video_content","title":"탄력밴드 후방으로 당기기 (본운동)","content":"운동 단계: 본운동\n운동명: 탄력밴드 후방으로 당기기","metadata_json":"{}","occurrence_count":1},
            "doc-knee": {"dataset":"general_prescription","title":"무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)","content":"운동명: 무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)\n대상 연령군: 성인\n운동 단계: 본운동","metadata_json":"{}","occurrence_count":1},
            "doc-arm": {"dataset":"general_prescription","title":"앞/옆으로 팔 들어올리기", "content":"운동명: 앞/옆으로 팔 들어올리기\n체력요인: 근력", "metadata_json":"{}","occurrence_count":1},
        }
    def _fetch_full_records(self, ids):
        return {i:self._records[i] for i in ids if i in self._records}
    def semantic_search(self, *args, **kwargs):
        return []


def test_exact_runtime_index_resolves_bilingual_video_before_vector():
    rt = _ExactRuntime()
    sources = _exact_exercise_sources(rt, "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?", ["video_content"])
    assert sources and sources[0]["id"] == "doc-dead"
    result = _deterministic_exact_response("앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?", sources, sources, [])
    assert "http://example.test/dead.mp4" in result["answer"]
    assert result["routing_flag"] == "EXACT_FIELD_VIDEO"


def test_exact_runtime_equipment_does_not_invent_properties():
    rt = _ExactRuntime()
    sources = _exact_exercise_sources(rt, "탄력밴드 후방으로 당기기 운동에는 어떤 운동 도구가 필요한가요?", ["video_content"])
    result = _deterministic_exact_response("탄력밴드 후방으로 당기기 운동에는 어떤 운동 도구가 필요한가요?", sources, sources, [])
    assert "탄력밴드를 사용하는 운동" in result["answer"]
    assert "부드러운" not in result["answer"]
    assert "가장 적합" not in result["answer"]


def test_exact_runtime_age_program_fields():
    rt = _ExactRuntime()
    q="무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)는 어느 연령군을 위한 어떤 프로그램인가요?"
    sources = _exact_exercise_sources(rt, q, ["general_prescription"])
    result = _deterministic_exact_response(q, sources, sources, [])
    assert "성인" in result["answer"] and "본운동" in result["answer"]


def test_exact_runtime_slash_korean_title_factor():
    rt = _ExactRuntime()
    q="제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요."
    sources = _exact_exercise_sources(rt, q, ["general_prescription"])
    assert sources and sources[0]["id"] == "doc-arm"
    result = _deterministic_exact_response(q, sources, sources, [])
    assert "근력" in result["answer"]


def test_source_from_runtime_record_accepts_sqlite_row(tmp_path):
    import sqlite3

    db = tmp_path / "row.db"
    with sqlite3.connect(db) as con:
        con.execute(
            """
            CREATE TABLE documents(
                id TEXT,
                dataset TEXT,
                title TEXT,
                content TEXT,
                metadata_json TEXT,
                occurrence_count INTEGER
            )
            """
        )
        con.execute(
            "INSERT INTO documents VALUES(?,?,?,?,?,?)",
            (
                "doc-row-1",
                "video_content",
                "Dead lift",
                "운동명 : Dead lift\n영상 URL : http://example.test/deadlift.mp4",
                '{"exercise_name":"Dead lift","video_url":"http://example.test/deadlift.mp4"}',
                1,
            ),
        )
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM documents").fetchone()

    class Runtime:
        def _metadata_with_facets(self, document_id, metadata):
            return metadata

    source = _source_from_runtime_record(Runtime(), "doc-row-1", row)
    assert source["id"] == "doc-row-1"
    assert source["dataset"] == "video_content"
    assert source["url"] == "http://example.test/deadlift.mp4"
    assert source["metadata"]["exercise_name"] == "Dead lift"


def test_descriptive_what_is_exercise_uses_normalized_exact_lookup():
    q = "일반 측정 장소의 성인 여성 운동처방 본운동 중 밴드로 어깨를 뒤로 들어올리는 운동은 무엇인가요?"
    assert _explicit_exercise_lookup(q) is True
    queries = _exercise_lookup_queries(q)
    assert any(
        _compact_match_text(value).endswith(_compact_match_text("밴드 어깨 뒤로 들어올리기"))
        for value in queries
    )


def test_composite_exact_response_prefers_full_title_over_component_alias():
    q = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    partial = {
        "id": "partial", "dataset": "video_content", "title": "Deadlift",
        "text": "운동명: Deadlift\n영상 URL: http://example.test/wrong.mp4",
        "url": "http://example.test/wrong.mp4", "metadata": {}, "score": 1.0,
    }
    full = {
        "id": "full", "dataset": "video_content",
        "title": "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)",
        "text": "운동명: 앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)\n영상 URL: http://example.test/right.mp4",
        "url": "http://example.test/right.mp4", "metadata": {}, "score": 0.9,
    }
    result = _deterministic_exact_response(q, [partial, full], [partial, full], [])
    assert result["cited_doc_ids"] == ["full"]
    assert "right.mp4" in result["answer"]


def test_requested_exercise_match_can_use_source_title_or_text_when_facet_name_missing():
    source = {
        "title": "Dead lift 운동 영상",
        "text": "운동명 : Dead lift\n영상 URL : http://example.test/dead.mp4",
        "metadata": {},
    }
    q = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    assert _requested_exercise_match(source, q) is True


def test_korean_shared_suffix_slash_title_expands_both_public_names():
    q = "제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요."
    qs = _exercise_lookup_queries(q)
    assert any(_compact_match_text(x) == _compact_match_text("앞으로 팔 들어올리기") for x in qs)
    assert any(_compact_match_text(x) == _compact_match_text("옆으로 팔 들어올리기") for x in qs)


def test_sqlite_exact_fallback_finds_title_when_facet_exercise_name_is_missing(tmp_path):
    import sqlite3

    db_path = tmp_path / "rag_documents.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE documents(
                id TEXT PRIMARY KEY,
                dataset TEXT,
                title TEXT,
                content TEXT,
                metadata_json TEXT,
                occurrence_count INTEGER
            )
            """
        )
        db.execute(
            "INSERT INTO documents VALUES(?,?,?,?,?,?)",
            (
                "doc-dead-real",
                "video_content",
                "Dead lift 운동 영상",
                "운동명 : Dead lift\n영상 URL : http://example.test/dead.mp4",
                '{"video_url":"http://example.test/dead.mp4"}',
                1,
            ),
        )

    class Runtime:
        def __init__(self):
            self.db_path = str(db_path)
            self.facet_records = [{"_id": "doc-dead-real", "_dataset": "video_content", "_exercise_name": ""}]

        def _metadata_with_facets(self, document_id, metadata):
            return metadata

        def _fetch_full_records(self, ids):
            with sqlite3.connect(self.db_path) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "SELECT * FROM documents WHERE id IN (" + ",".join("?" for _ in ids) + ")",
                    ids,
                ).fetchall()
            return {row["id"]: row for row in rows}

    q = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    hits = _exact_exercise_sources(Runtime(), q, datasets=["video_content"])
    assert hits
    assert hits[0]["id"] == "doc-dead-real"
    assert hits[0]["url"] == "http://example.test/dead.mp4"


def test_sqlite_exact_fallback_finds_shared_suffix_korean_title(tmp_path):
    import sqlite3

    db_path = tmp_path / "rag_documents.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE documents(
                id TEXT PRIMARY KEY,
                dataset TEXT,
                title TEXT,
                content TEXT,
                metadata_json TEXT,
                occurrence_count INTEGER
            )
            """
        )
        db.execute(
            "INSERT INTO documents VALUES(?,?,?,?,?,?)",
            (
                "doc-arm-real",
                "general_prescription",
                "앞으로 팔 들어올리기 (본운동)",
                "운동 단계 : 본운동\n운동명 : 앞으로 팔 들어올리기",
                '{}',
                1,
            ),
        )

    class Runtime:
        def __init__(self):
            self.sqlite_db_path = str(db_path)
            self.facet_records = [{"_id": "doc-arm-real", "_dataset": "general_prescription", "_exercise_name": ""}]

        def _metadata_with_facets(self, document_id, metadata):
            return metadata

        def _fetch_full_records(self, ids):
            with sqlite3.connect(self.sqlite_db_path) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "SELECT * FROM documents WHERE id IN (" + ",".join("?" for _ in ids) + ")",
                    ids,
                ).fetchall()
            return {row["id"]: row for row in rows}

    q = "제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요."
    hits = _exact_exercise_sources(Runtime(), q, datasets=["general_prescription"])
    assert hits
    assert hits[0]["id"] == "doc-arm-real"


def test_fetch_scan_exact_fallback_works_without_sqlite_path():
    rows = {
        "v1": {
            "id": "v1",
            "dataset": "video_content",
            "title": "Dead lift 운동 영상",
            "content": "운동명 : Dead lift\n영상 URL : http://example.test/dead.mp4",
            "metadata_json": '{"video_url":"http://example.test/dead.mp4"}',
            "occurrence_count": 1,
        },
        "v2": {
            "id": "v2",
            "dataset": "video_content",
            "title": "전혀 다른 운동",
            "content": "무관",
            "metadata_json": '{}',
            "occurrence_count": 1,
        },
    }

    class Runtime:
        def __init__(self):
            self.facet_records = [
                {"_id": "v2", "_dataset": "video_content", "_exercise_name": ""},
                {"_id": "v1", "_dataset": "video_content", "_exercise_name": ""},
            ]

        def _fetch_full_records(self, ids):
            return {i: rows[i] for i in ids if i in rows}

        def _metadata_with_facets(self, document_id, metadata):
            return metadata

    q = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    hits = _fetch_scan_exact_exercise_sources(Runtime(), q, datasets=["video_content"])
    assert hits
    assert hits[0]["id"] == "v1"
    assert hits[0]["url"] == "http://example.test/dead.mp4"


def test_fetch_scan_exact_fallback_respects_dataset_filter():
    rows = {
        "g1": {
            "id": "g1",
            "dataset": "general_prescription",
            "title": "앞으로 팔 들어올리기 (본운동)",
            "content": "운동명 : 앞으로 팔 들어올리기",
            "metadata_json": '{}',
            "occurrence_count": 1,
        },
        "x1": {
            "id": "x1",
            "dataset": "other_dataset",
            "title": "앞으로 팔 들어올리기",
            "content": "운동명 : 앞으로 팔 들어올리기",
            "metadata_json": '{}',
            "occurrence_count": 1,
        },
    }

    class Runtime:
        def __init__(self):
            self.facet_records = [
                {"_id": "x1", "_dataset": "other_dataset", "_exercise_name": ""},
                {"_id": "g1", "_dataset": "general_prescription", "_exercise_name": ""},
            ]

        def _fetch_full_records(self, ids):
            return {i: rows[i] for i in ids if i in rows}

        def _metadata_with_facets(self, document_id, metadata):
            return metadata

    q = "제 상대악력 47% 결과만 놓고 볼 때 앞/옆으로 팔 들어올리기가 근력 쪽 운동 후보가 되는지 알려주세요."
    hits = _fetch_scan_exact_exercise_sources(Runtime(), q, datasets=["general_prescription"])
    assert hits
    assert [h["id"] for h in hits] == ["g1"]


def test_requested_exercise_match_searches_metadata_aliases():
    source = {
        "title": "운동처방 동영상",
        "text": "영상 자료",
        "metadata": {"exercise_name_en": "Dead lift", "public_name": "Dead lift/Bent over row"},
    }
    q = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    assert _requested_exercise_match(source, q) is True


def test_source_factor_uses_literal_program_factor_only():
    flex = {
        "title": "폼롤러 이용 유연성운동 루틴 프로그램 (본운동)",
        "text": "운동명: 폼롤러 이용 유연성운동 루틴 프로그램",
        "metadata": {},
    }
    generic = {
        "title": "엎드려 양팔 및 다리 들어올리기",
        "text": "운동명: 엎드려 양팔 및 다리 들어올리기",
        "metadata": {},
    }
    assert _source_factor(flex) == "유연성"
    assert _source_factor(generic) == ""


def test_exact_factor_match_is_deterministic_for_flexibility():
    src = {
        "id": "flex-1",
        "dataset": "general_prescription",
        "title": "폼롤러 이용 유연성운동 루틴 프로그램 (본운동)",
        "text": "운동명: 폼롤러 이용 유연성운동 루틴 프로그램",
        "metadata": {},
        "score": 1.0,
    }
    history = [
        {"role": "assistant", "content": "2026-09-19 집 측정의 앉아윗몸앞으로굽히기 결과는 10cm입니다."}
    ]
    r = _deterministic_exact_response(
        "그 수치를 고려하면 폼롤러 이용 유연성운동 루틴 프로그램도 제 유연성을 관리하는 운동 후보에 들어가나요?",
        [src], [src], history, ""
    )
    assert r is not None
    assert r["routing_flag"] == "EXACT_FIELD_FACTOR_MATCH"
    assert "유연성" in r["answer"]


def test_exact_followup_no_record_does_not_fake_personalization():
    src = {
        "id": "balance-1",
        "dataset": "general_prescription",
        "title": "의자잡고 서기 평형성운동 루틴 프로그램 (본운동)",
        "text": "운동명: 의자잡고 서기 평형성운동 루틴 프로그램",
        "metadata": {},
        "score": 1.0,
    }
    history = [
        {"role": "assistant", "content": "현재 로그인 계정에는 의자에앉아 3m 표적돌아오기 기록이 저장되어 있지 않아요."}
    ]
    r = _deterministic_exact_response(
        "그 결과를 생각하면 의자잡고 서기 평형성운동 루틴 프로그램도 제 균형을 관리·보완하는 운동 후보가 될까요?",
        [src], [src], history, ""
    )
    assert r is not None
    assert r["routing_flag"] == "EXACT_FACTOR_NO_MEASUREMENT_RECORD"
    assert "개인화해 연결할 수는 없어요" in r["answer"]


def test_weakest_measurement_factor_uses_first_latest_value_per_factor():
    context = (
        "최근 측정기록: "
        "레코드 1 2026-09-19 민첩성 10초 또래 상위 5% / "
        "레코드 2 2026-09-19 유연성 10cm 또래 상위 49% / "
        "레코드 3 2026-09-19 근지구력 30회 또래 상위 77% / "
        "레코드 4 2026-09-19 순발력 200cm 또래 상위 57% / "
        "레코드 5 2026-09-18 유연성 1cm 또래 상위 82%"
    )
    factor, band = _weakest_measurement_factor(context)
    assert factor == "근지구력"
    assert "77" in band


def test_context_measurement_parser_and_source_exclusion():
    context = (
        "로그인 사용자 프로필: 성인 남성. 최근 측정기록: "
        "레코드 10 2026-09-19 [CENTER] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 11cm / 또래 상위 40% / "
        "레코드 11 2026-09-19 [HOME] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 10cm / 또래 상위 49% "
        " 측정 범위: 유연성."
    )
    row = _active_measurement_for_question(
        "센터 기록은 빼고 제 앉아윗몸앞으로굽히기 11cm 기록을 기준으로 봐주세요.",
        context,
    )
    assert row is not None
    assert row["source"] == "HOME"
    assert row["value"] == 10.0
    status, active, claimed, unit = _measurement_assertion_status(
        "센터 기록은 빼고 제 앉아윗몸앞으로굽히기 11cm 기록을 기준으로 봐주세요.",
        context,
    )
    assert status == "VALUE_MISMATCH"
    assert active["value"] == 10.0
    assert claimed == 11.0
    assert unit == "cm"


def test_explicit_constraints_reject_known_demographic_contradiction():
    src = {
        "title": "탄력밴드 어깨 가쪽 돌림 (본운동)",
        "text": "운동 단계: 본운동\n대상 연령군: 어르신\n성별: M\n측정 장소: 일반",
        "metadata": {},
    }
    q = "일반 측정 장소의 성인 여성 운동처방 본운동 중 밴드로 어깨를 뒤로 들어올리는 운동은 무엇인가요?"
    assert _source_matches_explicit_constraints(src, q) is False


def test_explicit_constraints_accept_matching_demographic():
    src = {
        "title": "탄력밴드 어깨 가쪽 돌림 (본운동)",
        "text": "운동 단계: 본운동\n대상 연령군: 성인\n성별: F\n측정 장소: 일반",
        "metadata": {},
    }
    q = "일반 측정 장소의 성인 여성 운동처방 본운동 중 밴드로 어깨를 뒤로 들어올리는 운동은 무엇인가요?"
    assert _source_matches_explicit_constraints(src, q) is True


def test_measurement_assertion_mismatch_short_circuits_personalized_factor_claim():
    src = {
        "id": "flex-x",
        "dataset": "general_prescription",
        "title": "폼롤러 이용 유연성운동 루틴 프로그램 (본운동)",
        "text": "운동명: 폼롤러 이용 유연성운동 루틴 프로그램",
        "metadata": {},
        "score": 1.0,
    }
    context = (
        "로그인 사용자 프로필: 성인 남성. 최근 측정기록: "
        "레코드 11 2026-09-19 [HOME] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 10cm / 또래 상위 49% "
        " 측정 범위: 유연성."
    )
    r = _deterministic_exact_response(
        "센터 기록은 빼고 봐주세요. 제 앉아윗몸앞으로굽히기 11cm 기록을 기준으로 "
        "폼롤러 이용 유연성운동 루틴 프로그램이 관련 있는 운동인지 궁금합니다.",
        [src], [src], [], context
    )
    assert r["routing_flag"] == "MEASUREMENT_ASSERTION_MISMATCH"
    assert "10cm" in r["answer"]
    assert "11cm" in r["answer"]


def test_exact_miss_diagnostics_surfaces_near_facet_names():
    class Runtime:
        facet_records = [
            {"_id": "a", "_dataset": "video_content", "_exercise_name": "Deadlift"},
            {"_id": "b", "_dataset": "video_content", "_exercise_name": "Bent-over row"},
            {"_id": "c", "_dataset": "general_prescription", "_exercise_name": "스쿼트"},
        ]
    d = _exact_miss_diagnostics(
        Runtime(),
        "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?",
    )
    names = [x["exercise_name"] for x in d["near_facet_matches"]]
    assert "Bent-over row" in names or "Deadlift" in names


def test_exact_sources_accept_list_return_shape_from_runtime_fetch():
    row = {
        "id": "doc-list-1",
        "dataset": "video_content",
        "title": "Dead lift/Bent over row",
        "content": "운동명: Dead lift/Bent over row\n영상 URL: http://example.test/x.mp4",
        "metadata_json": '{"video_url":"http://example.test/x.mp4"}',
        "occurrence_count": 1,
    }
    class Runtime:
        facet_records = [{
            "_id": "doc-list-1",
            "_dataset": "video_content",
            "_exercise_name": "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)",
        }]
        def _fetch_full_records(self, ids):
            return [row]  # production-compatible alternate shape
        def _metadata_with_facets(self, document_id, metadata):
            return metadata

    q = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    hits = _exact_exercise_sources(Runtime(), q, datasets=["video_content"])
    assert hits
    assert hits[0]["id"] == "doc-list-1"
    assert hits[0]["url"] == "http://example.test/x.mp4"


def test_exact_sources_preserve_facet_when_full_record_materialization_is_empty():
    class Runtime:
        facet_records = [{
            "_id": "doc-facet-1",
            "_dataset": "video_content",
            "_exercise_name": "무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)",
            "_life_stage": "성인",
            "_program": "근력 프로그램",
        }]
        def _fetch_full_records(self, ids):
            return {}
    q = "무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)는 어느 연령군을 위한 어떤 프로그램인가요?"
    hits = _exact_exercise_sources(Runtime(), q, datasets=["video_content"])
    assert hits
    assert hits[0]["id"] == "doc-facet-1"
    assert hits[0]["retrieval_backend"] == "exact_exercise_facet"


def test_weakest_measurement_factor_parses_structured_v57_context():
    context = (
        "최근 측정기록: "
        "레코드 1 2026-09-19 [HOME] 10m 4회 왕복달리기 / 체력요인 민첩성 / 값 10초 / 또래 상위 5% / "
        "레코드 2 2026-09-19 [HOME] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 10cm / 또래 상위 49% / "
        "레코드 3 2026-09-19 [HOME] 교차윗몸일으키기 / 체력요인 근지구력 / 값 30회 / 또래 상위 77% / "
        "레코드 4 2026-09-19 [HOME] 제자리멀리뛰기 / 체력요인 순발력 / 값 200cm / 또래 상위 57% "
        " 측정 범위: 민첩성, 유연성, 근지구력, 순발력."
    )
    factor, band = _weakest_measurement_factor(context)
    assert factor == "근지구력"
    assert band == "또래 상위 77%"


def test_precise_semantic_batches_cannot_evict_exact_source_from_top80():
    class Runtime:
        def __init__(self):
            self.facet_records = [{
                "_id": "exact-deadlift",
                "_dataset": "video_content",
                "_exercise_name": "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)",
            }]
            self.qwen3_client = None

        def _fetch_full_records(self, ids):
            if "exact-deadlift" in ids:
                return {
                    "exact-deadlift": {
                        "id": "exact-deadlift",
                        "dataset": "video_content",
                        "title": "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row)",
                        "content": (
                            "운동명: 앉았다 들어올리기/상체 숙여서 뒤로 당기기"
                            "(Dead lift/Bent over row)\n"
                            "영상 URL: http://example.test/deadlift.mp4"
                        ),
                        "metadata_json": '{"video_url":"http://example.test/deadlift.mp4"}',
                        "occurrence_count": 1,
                    }
                }
            return {}

        def _metadata_with_facets(self, document_id, metadata):
            return metadata

        def semantic_search(self, query, k=20, **kwargs):
            # Simulate many high-volume precise semantic results that used to
            # push the exact source beyond the [:80] truncation boundary.
            return [
                {
                    "id": f"semantic-{query[:8]}-{i}",
                    "dataset": "video_content",
                    "title": f"다른 운동 {i}",
                    "text": f"운동명: 다른 운동 {i}",
                    "score": 0.95 - i * 0.001,
                    "metadata": {},
                    "retrieval_backend": "chroma_vector",
                }
                for i in range(30)
            ]

    q = "앉았다 들어올리기/상체 숙여서 뒤로 당기기(Dead lift/Bent over row) 운동 영상은 어디에서 볼 수 있나요?"
    result = answer(Runtime(), q)
    assert result["routing_flag"] in {"EXACT_FIELD_VIDEO", "VIDEO_RESULTS"}
    assert result["cited_doc_ids"] == ["exact-deadlift"]
    assert result["sources"][0]["url"] == "http://example.test/deadlift.mp4"
    assert result["retrieved_doc_ids"][0]["document_id"] == "exact-deadlift"


def test_audience_program_answer_uses_description_when_program_field_missing():
    src = {
        "id": "knee-up-1",
        "dataset": "video_content",
        "title": "Knee Up",
        "text": (
            "운동명: Knee Up\n"
            "설명: 초보자를 위한 전신근력운동 중, 루프밴드를 활용한 홈트레이닝 및 "
            "홈필라테스운동을 설명한 운동처방 가이드 동영상\n"
            "대상 연령군: 공통"
        ),
        "metadata": {},
        "score": 1.0,
    }
    q = "근력 쪽 운동을 찾고 있는데 무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)는 어느 연령군을 위한 어떤 프로그램인가요?"
    result = _deterministic_exact_response(q, [src], [src], [], "")
    assert result is not None
    assert result["routing_flag"] == "EXACT_FIELD_AUDIENCE"
    assert "공통" in result["answer"]
    assert "초보자를 위한 전신근력운동" in result["answer"]


def test_weakest_factor_runs_focused_search_when_first_pass_has_no_matching_factor():
    class Runtime:
        def semantic_search(self, query, **kwargs):
            if "근지구력" in query:
                return [{
                    "id": "endur-1",
                    "dataset": "general_prescription",
                    "title": "근지구력운동 루틴 프로그램",
                    "text": "운동명: 근지구력운동 루틴 프로그램\n체력요인: 근지구력",
                    "metadata": {},
                    "score": 0.8,
                    "retrieval_backend": "chroma_vector",
                }]
            return []

    context = (
        "최근 측정기록: "
        "레코드 1 2026-09-19 [HOME] 교차윗몸일으키기 / 체력요인 근지구력 / 값 30회 / 또래 상위 77% / "
        "레코드 2 2026-09-19 [HOME] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 10cm / 또래 상위 49% "
        " 측정 범위: 근지구력, 유연성."
    )
    result = answer(
        Runtime(),
        "제 체력요인 중에 제일 떨어지는 걸 하나 골라서 거기에 맞는 운동을 정해 주세요.",
        user_context=context,
    )
    assert result["routing_flag"] == "WEAKEST_FACTOR_DETERMINISTIC"
    assert "근지구력" in result["answer"]
    assert "근지구력운동 루틴 프로그램" in result["answer"]
    assert result["cited_doc_ids"] == ["endur-1"]


def test_factor_facet_sources_find_literal_factor_without_vector_search():
    class Runtime:
        def __init__(self):
            self.facet_records = [
                {
                    "_id": "endur-1",
                    "_dataset": "general_prescription",
                    "_exercise_name": "근지구력운동 루틴 프로그램",
                    "_exercise_type": "근지구력",
                },
                {
                    "_id": "flex-1",
                    "_dataset": "general_prescription",
                    "_exercise_name": "유연성운동 루틴 프로그램",
                    "_exercise_type": "유연성",
                },
            ]
        def _fetch_full_records(self, ids):
            return {}

    hits = _factor_facet_sources(
        Runtime(),
        "근지구력",
        datasets=["general_prescription"],
    )
    assert hits
    assert hits[0]["id"] == "endur-1"
    assert _source_factor(hits[0]) == "근지구력"


def test_weakest_factor_prefers_factor_facet_before_semantic_fallback():
    class Runtime:
        def __init__(self):
            self.facet_records = [{
                "_id": "endur-2",
                "_dataset": "general_prescription",
                "_exercise_name": "근지구력 강화 루틴",
                "_exercise_type": "근지구력",
            }]
            self.semantic_calls = 0

        def _fetch_full_records(self, ids):
            return {}

        def semantic_search(self, *args, **kwargs):
            self.semantic_calls += 1
            return []

    rt = Runtime()
    context = (
        "최근 측정기록: "
        "레코드 1 2026-09-19 [HOME] 교차윗몸일으키기 / 체력요인 근지구력 / 값 30회 / 또래 상위 77% / "
        "레코드 2 2026-09-19 [HOME] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 10cm / 또래 상위 49% "
        " 측정 범위: 근지구력, 유연성."
    )
    result = answer(
        rt,
        "제 체력요인 중에 제일 떨어지는 걸 하나 골라서 거기에 맞는 운동을 정해 주세요.",
        user_context=context,
    )
    assert result["routing_flag"] == "WEAKEST_FACTOR_DETERMINISTIC"
    assert "근지구력" in result["answer"]
    assert "근지구력 강화 루틴" in result["answer"]
    assert result["cited_doc_ids"] == ["endur-2"]


def test_source_age_compatible_rejects_child_for_adult():
    child = {
        "title": "유아기 응용 민첩성,근지구력",
        "text": "설명: 유아기 응용 민첩성,근지구력",
        "metadata": {},
    }
    common = {
        "title": "근지구력 운동",
        "text": "대상 연령군: 공통\n체력요인: 근지구력",
        "metadata": {},
    }
    adult = {
        "title": "성인 근지구력 운동",
        "text": "대상 연령군: 성인\n체력요인: 근지구력",
        "metadata": {},
    }
    assert _source_age_compatible(child, "성인") is False
    assert _source_age_compatible(common, "성인") is True
    assert _source_age_compatible(adult, "성인") is True


def test_factor_facet_sources_excludes_wrong_life_stage():
    class Runtime:
        def __init__(self):
            self.facet_records = [
                {
                    "_id": "child-1",
                    "_dataset": "video_content",
                    "_exercise_name": "유아기 응용 민첩성,근지구력",
                    "_exercise_type": "근지구력",
                },
                {
                    "_id": "adult-1",
                    "_dataset": "general_prescription",
                    "_exercise_name": "성인 근지구력 운동 루틴",
                    "_exercise_type": "근지구력",
                    "_life_stage": "성인",
                },
            ]
        def _fetch_full_records(self, ids):
            return {}

    hits = _factor_facet_sources(
        Runtime(),
        "근지구력",
        datasets=["video_content", "general_prescription"],
        user_life_stage="성인",
    )
    assert hits
    assert [h["id"] for h in hits] == ["adult-1"]


def test_weakest_factor_does_not_recommend_child_program_to_adult():
    class Runtime:
        def __init__(self):
            self.facet_records = [{
                "_id": "child-only",
                "_dataset": "video_content",
                "_exercise_name": "유아기 응용 민첩성,근지구력",
                "_exercise_type": "근지구력",
            }]
        def _fetch_full_records(self, ids):
            return {}
        def semantic_search(self, *args, **kwargs):
            return []

    context = (
        "로그인 사용자 프로필: 성인 남성, 만 44세. 최근 측정기록: "
        "레코드 1 2026-09-19 [HOME] 교차윗몸일으키기 / 체력요인 근지구력 / 값 30회 / 또래 상위 77% / "
        "레코드 2 2026-09-19 [HOME] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 10cm / 또래 상위 49% "
        " 측정 범위: 근지구력, 유연성."
    )
    result = answer(
        Runtime(),
        "제 체력요인 중에 제일 떨어지는 걸 하나 골라서 거기에 맞는 운동을 정해 주세요.",
        user_context=context,
    )
    assert result["routing_flag"] == "WEAKEST_FACTOR_EVIDENCE_MISSING"
    assert "유아기" not in result["answer"]


def test_user_life_stage_reads_runtime_enum_values():
    assert _user_life_stage("로그인 사용자 프로필: ADULT 남성. 최근 측정기록: x") == "성인"
    assert _user_life_stage("로그인 사용자 프로필: SENIOR 여성. 최근 측정기록: x") == "어르신"
    assert _user_life_stage("로그인 사용자 프로필: 성인 남성. 최근 측정기록: x") == "성인"


def test_source_life_stage_reads_runtime_enum_metadata():
    src = {
        "title": "근지구력 운동",
        "text": "체력요인: 근지구력",
        "metadata": {"life_stage": "PRESCHOOL"},
    }
    assert _source_life_stage(src) == "유아기"
    assert _source_age_compatible(src, "성인") is False


def test_adult_runtime_context_filters_preschool_factor_source():
    class Runtime:
        def __init__(self):
            self.facet_records = [
                {
                    "_id": "preschool-1",
                    "_dataset": "video_content",
                    "_exercise_name": "유아기 응용 민첩성,근지구력",
                    "_exercise_type": "근지구력",
                    "_life_stage": "PRESCHOOL",
                },
                {
                    "_id": "adult-1",
                    "_dataset": "general_prescription",
                    "_exercise_name": "성인 근지구력 운동 루틴",
                    "_exercise_type": "근지구력",
                    "_life_stage": "ADULT",
                },
            ]
        def _fetch_full_records(self, ids):
            return {}
        def semantic_search(self, *args, **kwargs):
            return []

    context = (
        "로그인 사용자 프로필: ADULT 남성. 최근 측정기록: "
        "레코드 1 2026-09-19 [HOME] 교차윗몸일으키기 / 체력요인 근지구력 / 값 30회 / 또래 상위 77% / "
        "레코드 2 2026-09-19 [HOME] 앉아윗몸앞으로굽히기 / 체력요인 유연성 / 값 10cm / 또래 상위 49% "
        " 측정 범위: 근지구력, 유연성."
    )
    result = answer(
        Runtime(),
        "제 체력요인 중에 제일 떨어지는 걸 하나 골라서 거기에 맞는 운동을 정해 주세요.",
        user_context=context,
    )
    assert result["routing_flag"] == "WEAKEST_FACTOR_DETERMINISTIC"
    assert "성인 근지구력 운동 루틴" in result["answer"]
    assert "유아기 응용" not in result["answer"]
