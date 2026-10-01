from __future__ import annotations

import unittest
from threading import Lock
from unittest.mock import Mock, patch
from video_audit_groups import organize
from exercise_labels import display_name, exercise_stages
from pathlib import Path
from tempfile import TemporaryDirectory

from center_percentile import RESULT_LABEL, age_band, available_input_measures, ensure_percentile_database, lookup_percentiles, status as percentile_status
from rag_data_roles import classify_document, health_categories, display_locations
from qwen3_grounded_harness import GroundedQwen3Harness
from fitness_web_server import (
    CoachRequest, HTML_PAGE, RagRuntime, _detail_notice, _facet_equipment_values,
    _friendly_result_copy, _is_chat_recommendation_request, _rag_detail, _target_focus_notice, _video_player_page,
    PERCENTILE_DATABASE, PercentileRequest, age_group_from_age, recommendation_datasets,
)


class CoachRequestTests(unittest.TestCase):
    def test_vector_index_probe_verifies_a_real_hnsw_query(self) -> None:
        class Collection:
            def get(self, **_kwargs):
                return {"ids": ["doc-1"], "embeddings": [[1.0, 0.0]]}

            def query(self, **_kwargs):
                return {"ids": [["doc-1", "doc-2"]], "distances": [[0.0, 0.2]]}

        runtime = RagRuntime.__new__(RagRuntime)
        runtime.collection = Collection()
        runtime.chroma_documents = 2
        self.assertEqual(runtime._probe_vector_index()["status"], "healthy")

    def test_stage_request_is_not_a_bmi_rank_request(self) -> None:
        runtime = RagRuntime.__new__(RagRuntime)
        context = {"age_bmi_recommendation": {"bmi": {"available": True, "bmi": 22.5, "bmi_grade": "정상"}}}
        self.assertIsNone(runtime._chat_age_bmi_recommendation("도구 없이 본운동 허리 스트레칭 추천해줘", context))

    def test_chat_property_questions_do_not_select_another_exercise(self) -> None:
        for message in ("영상 있어?", "이 운동은 실내에서 해?", "운동 이름과 영상이 있는지 알려줘", "장비 없어도 돼?"):
            self.assertFalse(_is_chat_recommendation_request(message))
        self.assertTrue(_is_chat_recommendation_request("도구 없이 본운동 추천해줘"))

    def test_chat_recommendation_updates_followup_context(self) -> None:
        from fitness_web_server import ChatRequest
        runtime = RagRuntime.__new__(RagRuntime)
        runtime.answer_lock = Lock()
        old = {"selected_name": "이전 운동"}
        new = {"selected_name": "새 운동"}
        runtime.chat_contexts = {"test": old}
        runtime._chat_age_bmi_recommendation = Mock(return_value=None)
        runtime._chat_recommendation = Mock(return_value={"answer": "새 운동", "_next_context": new})
        result = runtime.chat(ChatRequest(user_id="test", message="다른 운동 추천"))
        self.assertEqual(runtime.chat_contexts["test"], new)
        self.assertNotIn("_next_context", result)

    def test_exercise_stage_labels_preserve_source_stages(self) -> None:
        self.assertEqual(display_name("준비운동-두발모아 걷기 (본운동)"), "두발모아 걷기")
        self.assertEqual(exercise_stages("준비운동-두발모아 걷기", "운동 단계: 본운동"), {"준비운동", "본운동"})
        self.assertEqual(exercise_stages("운동", "운동 단계: 마무리운동"), {"정리운동"})
        self.assertEqual(exercise_stages("운동", "운동 단계: 사전운동"), {"준비운동"})
        self.assertEqual(exercise_stages("골반 스트레칭", ""), {"본운동"})
        self.assertEqual(exercise_stages("골반 스트레칭", "운동 단계: 단계 미상"), {"본운동"})
        self.assertEqual(exercise_stages("준비운동-골반 스트레칭", "운동 단계: 단계 미상"), {"준비운동"})
        record = {"_audience": "general", "exercise_stage": {"준비운동", "정리운동"}, "health_information": set()}
        self.assertTrue(RagRuntime._facet_record_matches(record, {"exercise_stage": "준비운동"}, "__none__"))
        self.assertTrue(RagRuntime._facet_record_matches(record, {"exercise_stage": "정리운동"}, "__none__"))
        self.assertFalse(RagRuntime._facet_record_matches(record, {"exercise_stage": "본운동"}, "__none__"))

    def test_related_video_merges_missing_equipment_rows_for_same_url(self) -> None:
        content = "설명: 유연성 운동 중, 골반 스트레칭운동을 설명한 영상\n대상 연령군: 어르신\n영상 URL: http://openapi.kspo.or.kr/web/video/a.mp4"
        videos = [("골반 스트레칭2", content), ("골반 스트레칭2", content + "\n운동 도구: 짐볼")]
        refs = organize([{"exercise_name": "골반 스트레칭"}], videos)[0]["related_videos"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["equipment"], "짐볼")
        self.assertTrue(refs[0]["missing_equipment_rows"])

    def test_video_groups_require_explicit_description_not_similar_name(self) -> None:
        items = [{"exercise_name": "골반 스트레칭", "target_areas": ["골반"], "exercise_types": ["스트레칭"]}, {"exercise_name": "물통으로 양팔 들어올리기", "target_areas": ["팔"], "exercise_types": ["근력"]}]
        videos = [("골반 스트레칭1", "설명: 유연성 운동 중, 골반 스트레칭운동을 설명한 동영상\n영상 URL: http://openapi.kspo.or.kr/web/video/a.mp4\n대상 연령군: 어르신"), ("물통으로 양팔 들어올리기1", "영상 URL: http://openapi.kspo.or.kr/web/video/b.mp4")]
        result = organize(items, videos)
        self.assertEqual(result[0]["link_status"], "description_reference")
        self.assertEqual(result[0]["related_videos"][0]["age_group"], "어르신")
        self.assertEqual(result[1]["link_status"], "unverified")
        self.assertEqual(result[1]["display_group"], "근력운동")

    def test_verified_video_aliases_do_not_use_generic_fuzzy_matching(self) -> None:
        items = [
            {"exercise_name": "물통으로 양팔 들어올리기"},
            {"exercise_name": "팔굽혀펴기(무릎대고 실시)"},
            {"exercise_name": "두발모아 걷기"},
        ]
        videos = [
            ("물병 양팔 들어올리기", "설명: 근력 운동 중, 물병 양팔 들어올리기운동을 설명한 영상\n운동 도구: 물병\n영상 URL: http://openapi.kspo.or.kr/web/video/water.mp4"),
            ("무릎대고 팔 굽혀 펴기(Kneeling push up)", "설명: 주간 표준운동프로그램\n영상 URL: http://openapi.kspo.or.kr/web/video/knee.mp4"),
            ("두발 모아 점프하기", "설명: 협응성 운동 중, 앞/뒤로 선 넘기운동을 설명한 영상\n영상 URL: http://openapi.kspo.or.kr/web/video/jump.mp4"),
        ]
        result = organize(items, videos)
        self.assertEqual(result[0]["link_status"], "description_reference")
        self.assertTrue(result[0]["alias_evidence"])
        self.assertEqual(result[1]["link_status"], "description_reference")
        self.assertEqual(result[2]["link_status"], "unverified")

    def test_user_approved_similar_walking_videos_are_labelled_similar(self) -> None:
        items = [
            {"exercise_name": "두발모아 걷기"},
            {"exercise_name": "앞뒤로 한발씩 걷기"},
        ]
        videos = [
            ("균형 걷기", "설명: 평형성 운동 중, 균형 걷기운동을 설명한 영상\n대상 연령군: 공통\n영상 URL: http://openapi.kspo.or.kr/web/video/balance.mp4"),
            ("한발 따라가기", "설명: 협응성 운동 중, 앞/뒤로 선 넘기운동을 설명한 영상\n대상 연령군: 어르신\n영상 URL: http://openapi.kspo.or.kr/web/video/follow.mp4"),
        ]
        result = organize(items, videos)
        self.assertTrue(all(item["link_status"] == "description_reference" for item in result))
        self.assertTrue(all(item["similar_evidence"] for item in result))
        self.assertTrue(all(item["related_videos"][0]["match_type"] == "similar" for item in result))
        self.assertEqual(result[0]["related_videos"][0]["title"], "균형 걷기")
        self.assertEqual(result[1]["related_videos"][0]["title"], "한발 따라가기")

    def test_quick_filter_is_hidden_but_frontend_handlers_remain(self) -> None:
        self.assertIn('id="quick-filter" class="sources" hidden', HTML_PAGE)
        self.assertIn('id="quick-filter-to-chat"', HTML_PAGE)
        self.assertIn('/api/options', HTML_PAGE)
        self.assertIn('/api/coach', HTML_PAGE)

    def test_user_equipment_location_grouping(self) -> None:
        for equipment in ({"헬스기구"}, {"머신"}, {"헬스기구", "물통"}):
            self.assertEqual(display_locations(equipment, {"실외"}), {"헬스장"})
        for equipment in (set(), {"없음"}, {"물병"}, {"물통"}, {"물병", "물통"}):
            self.assertEqual(display_locations(equipment, {"실외"}), {"실내"})
        self.assertEqual(display_locations({"매트"}, {"실외"}), {"실외"})
        self.assertEqual(display_locations(set(), {"수영장"}), {"수영장"})
        self.assertEqual(display_locations({"물병", "밴드"}, {"실외"}), {"실내"})

    def test_abstention_does_not_attach_unselected_videos(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.answer_lock = Lock()
        runtime.chat_contexts = {}
        runtime.harness = Mock()
        runtime.harness.run.return_value = {"운동명": "근거 부족", "추천이유": "근거 부족"}
        runtime.harness.last_trace = {"selected_name": None, "sources": [], "available_alternatives": [{"title": "다른 운동"}]}
        runtime._video_options = Mock(return_value=[{"url": "unselected"}])
        runtime._best_detail_source = Mock(return_value=({}, None))
        runtime._age_bmi_recommendation = Mock(return_value={})
        result = runtime.answer(CoachRequest(question="허리 운동", pain_level=8))
        self.assertEqual(result["trace"]["video_options"], [])
        self.assertEqual(result["trace"]["available_alternatives"], [])
        runtime._video_options.assert_not_called()

    def test_manual_level_is_used_in_search_question(self) -> None:
        request = CoachRequest(
            selection_mode=True, age_group="성인", sex="M", fitness_level="고급",
            exercise_type="근력", location="실내", equipment="없음",
        )
        question = request.effective_question({**request.profile(), "fitness_level": "초급"})
        self.assertIn("초급", question)
        self.assertNotIn("고급", question)

    def test_home_measurement_controls_are_absent(self) -> None:
        for field in (
            "waist_cm", "flexibility_cm", "adult_endurance_reps",
            "adult_step_recovery_hr", "senior_chair_stand_reps",
            "senior_march_knee_lifts", "body_fat_pct",
        ):
            self.assertNotIn(f'id="{field}"', HTML_PAGE)
        self.assertNotIn('<details class="measurement-box" open>', HTML_PAGE)
        self.assertNotIn("홈 자가측정 결과", HTML_PAGE)
        self.assertIn("운동·스트레칭 추천 결과", HTML_PAGE)
        self.assertIn('methodTitle.textContent="운동 방법"', HTML_PAGE)
        self.assertNotIn('id="disability_type"', HTML_PAGE)
        self.assertNotIn('id="pain_level"', HTML_PAGE)
        self.assertIn("else select.value=items[0].value", HTML_PAGE)
        self.assertIn("attempt<6", HTML_PAGE)
        self.assertNotIn("홈 체력 측정 조건", HTML_PAGE)
        self.assertIn("운동·스트레칭 추천 조건", HTML_PAGE)
        self.assertNotIn('id="assess-home"', HTML_PAGE)
        self.assertNotIn("/api/home-assessment", HTML_PAGE)
        self.assertNotIn("홈 체력 측정 결과 보기", HTML_PAGE)
        self.assertIn("운동·스트레칭 추천 검색", HTML_PAGE)
        self.assertIn("건강 목적", HTML_PAGE)
        self.assertIn("센터 인증등급과 영상 난이도는 합치지 않습니다", HTML_PAGE)
        self.assertIn("1~2는 초급, 3은 중급, 4~5는 고급", HTML_PAGE)
        self.assertIn('const ageInput=document.getElementById("age")', HTML_PAGE)
        self.assertIn('value=measurementGroupForAge(Number(ageInput.value))', HTML_PAGE)
        self.assertNotIn("syncHomeMeasurementFields", HTML_PAGE)
        self.assertIn('const cascadeFields=["health_information","target_area"', HTML_PAGE)
        ordered_controls = [
            'id="pain_area"', 'id="health_information"', 'id="target_area"',
            'id="exercise_type"', 'id="fitness_level"', 'id="location"',
            'id="equipment"',
        ]
        positions = [HTML_PAGE.index(control) for control in ordered_controls]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('id="chat-form"', HTML_PAGE)
        self.assertIn("/api/chat", HTML_PAGE)
        self.assertNotIn('summary.textContent="출처 보기"', HTML_PAGE)
        self.assertIn('sourceLine.textContent=`출처:', HTML_PAGE)
        self.assertNotIn("신뢰도 ${m.source_grade}", HTML_PAGE)
        self.assertNotIn("agility_reps", HTML_PAGE)
        self.assertNotIn("반복옆뛰기", HTML_PAGE)
        self.assertNotIn("grip_strength_kg", HTML_PAGE)
        self.assertNotIn("power_jump_cm", HTML_PAGE)
        self.assertNotIn("RAG 난이도에 자동 반영", HTML_PAGE)
        self.assertNotIn('id="exercise_experience"', HTML_PAGE)
        self.assertIn("운동 경험은 원본 6종에 독립 필드가 없어", HTML_PAGE)
        self.assertIn("공식 영상 바로 보기", HTML_PAGE)
        self.assertIn("/video-player?url=", HTML_PAGE)
        self.assertNotIn('id="award_group"', HTML_PAGE)
        self.assertIn("국내 성인 BMI 정보", HTML_PAGE)
        self.assertIn("appendAgeBmiRecommendation", HTML_PAGE)

    def test_selected_pain_area_is_kept_without_a_severity_input(self) -> None:
        request = CoachRequest(selection_mode=True, pain_area="허리", pain_level=0)
        self.assertEqual(request.profile()["pain_area"], "허리")

    def test_official_video_player_embeds_only_kspo_mp4(self) -> None:
        page = _video_player_page(
            "http://openapi.kspo.or.kr/web/video/example.mp4", "허리 스트레칭"
        )
        self.assertIn("<video controls autoplay", page)
        self.assertIn("허리 스트레칭", page)
        with self.assertRaises(ValueError):
            _video_player_page("https://example.com/not-official.mp4", "외부 영상")

    def test_age_determines_consistent_rag_age_group(self) -> None:
        self.assertEqual(age_group_from_age(12), "유소년")
        self.assertEqual(age_group_from_age(18), "청소년")
        self.assertEqual(age_group_from_age(64), "성인")
        self.assertEqual(age_group_from_age(65), "어르신")
        self.assertEqual(CoachRequest(age=70, age_group="성인").profile()["age_group"], "어르신")

    def test_adult_bmi_is_added_to_profile_without_reclassifying_teenagers(self) -> None:
        adult = CoachRequest(age=30, height_cm=170, weight_kg=65).profile()
        self.assertTrue(adult["bmi_available"])
        self.assertEqual(adult["bmi_value"], 22.5)
        self.assertEqual(adult["bmi_grade"], "정상")
        teenager = CoachRequest(age=18, height_cm=170, weight_kg=65).profile()
        self.assertFalse(teenager["bmi_available"])
        self.assertNotIn("bmi_grade", teenager)

    def test_recommendation_prompt_requests_a_warm_respectful_tone(self) -> None:
        prompt = GroundedQwen3Harness._final_system_prompt()
        self.assertIn("따뜻한 어조", prompt)
        self.assertIn("자연스러운 존댓말", prompt)
        self.assertIn("국내 성인 BMI", prompt)
        chat_prompt = GroundedQwen3Harness._chat_system_prompt()
        self.assertIn("국민연령별추천운동정보의 순위", chat_prompt)

    def test_percentile_preview_keeps_home_input_and_center_norms_separate(self) -> None:
        self.assertIn("홈 체력측정", HTML_PAGE)
        self.assertIn(RESULT_LABEL, HTML_PAGE)
        self.assertIn("국민체력100 인증등급이나 공식 백분위가 아닙니다.", HTML_PAGE)
        self.assertIn("/api/center-percentile-status", HTML_PAGE)
        self.assertIn("/api/center-percentiles", HTML_PAGE)
        self.assertIn('id="percentile-form"', HTML_PAGE)
        self.assertIn('id="measurement-age-group"', HTML_PAGE)
        self.assertIn('<label for="measurement-age-group">연령군</label>', HTML_PAGE)
        self.assertIn('<label for="age">만 나이</label><input id="age"', HTML_PAGE)
        self.assertLess(HTML_PAGE.index('id="profile-inputs"'), HTML_PAGE.index('<details class="percentile-preview"'))
        self.assertNotIn('measurement-age-hint', HTML_PAGE)
        self.assertIn("유소년 (만 11~12세)", HTML_PAGE)
        self.assertNotIn("만 10세 이하 (현재 규준 없음)", HTML_PAGE)
        self.assertIn("청소년 (만 13~18세)", HTML_PAGE)
        self.assertIn("어르신 (만 65세 이상)", HTML_PAGE)
        self.assertIn("백분위 확인", HTML_PAGE)
        self.assertIn("성인 홈 체력측정 (만 19~64세)", HTML_PAGE)
        self.assertIn("어르신 홈 체력측정 (만 65세 이상)", HTML_PAGE)
        self.assertIn("청소년 홈 체력측정 (만 13~18세)", HTML_PAGE)
        self.assertIn("유소년 홈 체력측정 (만 11~12세)", HTML_PAGE)
        self.assertIn("만 10세 이하 홈 체력측정", HTML_PAGE)
        self.assertIn("상위 ${topRate(item)}%", HTML_PAGE)
        self.assertIn("좋은 기록일수록 상위 0%에", HTML_PAGE)
        self.assertIn("기본 홈 체력측정 5종", HTML_PAGE)
        self.assertIn("홈체력측정 입력값 · 만 ${measuredAge}세", HTML_PAGE)
        prompt = GroundedQwen3Harness._final_system_prompt()
        self.assertIn("홈체력측정 입력값", prompt)
        self.assertIn(RESULT_LABEL, prompt)
        self.assertIn("유소년·청소년 입력값을 성인·어르신 기준으로", prompt)
        chat_prompt = GroundedQwen3Harness._chat_system_prompt()
        self.assertIn("유소년·청소년·성인·어르신의 측정 항목과 상위 비율은 서로 결합", chat_prompt)

    def test_chat_can_request_another_grounded_exercise_and_hides_network_jargon(self) -> None:
        self.assertTrue(_is_chat_recommendation_request("그다음은?"))
        self.assertTrue(_is_chat_recommendation_request("팔 근력 운동 추천해줘."))
        self.assertIn("다른 부위 운동", HTML_PAGE)
        self.assertIn("챗봇 서버에 연결하지 못했습니다.", HTML_PAGE)

    def test_percentile_database_registers_only_unverified_measures(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "center_percentile_norms.sqlite"
            ensure_percentile_database(database)
            report = percentile_status(database)
        self.assertEqual(report["label"], RESULT_LABEL)
        self.assertEqual(report["norm_row_count"], 0)
        self.assertEqual(len(report["measures"]), 13)
        self.assertTrue(all(item["status"] == "mapping_unverified" for item in report["measures"]))
        self.assertEqual(
            {item["direction"] for item in report["measures"] if item["code"] in {"AGILITY_10M_SHUTTLE", "REACTION_TIME", "FIGURE_8_WALK"}},
            {"lower_is_better"},
        )

    def test_center_norms_expose_age_specific_input_fields(self) -> None:
        adult = {item["code"] for item in percentile_status(PERCENTILE_DATABASE)["measures"] if item["status"] == "ready"}
        self.assertTrue({"FLEX_SIT_REACH", "MUSC_END_SITUP", "POWER_LONGJUMP"}.issubset(adult))

    def test_center_norms_expose_teenager_fields_from_center_raw_records(self) -> None:
        youth = {item["code"] for item in available_input_measures(PERCENTILE_DATABASE, 11)}
        self.assertEqual(youth, {"FLEX_SIT_REACH", "POWER_LONGJUMP"})
        teenager = {item["code"] for item in available_input_measures(PERCENTILE_DATABASE, 15)}
        self.assertEqual(teenager, {"FLEX_SIT_REACH", "POWER_LONGJUMP"})
        self.assertEqual(age_band(11), "11-12")
        self.assertEqual(age_band(13), "13-14")
        self.assertEqual(age_band(18), "15-18")

    def test_center_norms_calculate_a_percentile_for_home_input(self) -> None:
        results = lookup_percentiles(PERCENTILE_DATABASE, 30, "M", {"FLEX_SIT_REACH": 10.0})
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["available"])
        self.assertGreaterEqual(results[0]["percentile"], 0)
        self.assertLessEqual(results[0]["percentile"], 100)
        self.assertAlmostEqual(results[0]["top_percent"] + results[0]["percentile"], 100.0)

    def test_center_norms_calculate_a_percentile_for_teenager_input(self) -> None:
        youth_request = PercentileRequest(age=11, sex="F", measurements={"FLEX_SIT_REACH": 10.0})
        self.assertEqual(youth_request.age, 11)
        request = PercentileRequest(age=15, sex="F", measurements={"FLEX_SIT_REACH": 10.0})
        self.assertEqual(request.age, 15)
        results = lookup_percentiles(PERCENTILE_DATABASE, 15, "F", {"FLEX_SIT_REACH": 10.0})
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["available"])

    def test_disability_selection_uses_only_disability_prescriptions(self) -> None:
        self.assertEqual(recommendation_datasets("시각장애"), ("disability_prescription",))
        self.assertNotIn("video_content", recommendation_datasets("시각장애"))
        self.assertIn("video_content", recommendation_datasets("없음"))

    def test_disability_screen_rejects_general_video_and_other_disability(self) -> None:
        harness = object.__new__(GroundedQwen3Harness)
        profile = {"disability_type": "시각장애"}
        results = [
            {"dataset": "video_content", "metadata": {}, "text": "운동명: 일반 운동"},
            {"dataset": "disability_prescription", "metadata": {"disability_type": "지체장애"}, "text": "운동명: 다른 처방"},
            {"dataset": "disability_prescription", "metadata": {"disability_type": "시각장애"}, "text": "운동명: 맞춤 처방"},
        ]
        screened = harness._screen_profile(results, profile, "운동 추천")
        self.assertEqual([item["text"] for item in screened], ["운동명: 맞춤 처방"])

    def test_disability_title_provides_data_based_body_part_and_type_facets(self) -> None:
        facets = classify_document(
            "disability_prescription", "허리 좌우로 돌리기 (본운동)",
            "운동명: 허리 좌우로 돌리기",
            {"age_group": "성인", "sex": "M", "disability_type": "지적장애"},
        )
        self.assertEqual(facets["audience"], "disability")
        self.assertIn("허리", facets["target_area"])
        self.assertIn("유연성", facets["exercise_type"])
        self.assertIn("target_area:title", facets["derived_fields"])

    def test_body_part_title_matching_does_not_confuse_neck_with_compound_words(self) -> None:
        wrist = classify_document(
            "disability_prescription", "손목 펴기 (본운동)", "운동명: 손목 펴기",
            {"disability_type": "지적장애"},
        )
        ankle = classify_document(
            "disability_prescription", "발목 돌리기", "운동명: 발목 돌리기",
            {"disability_type": "지적장애"},
        )
        purpose = classify_document(
            "video_content", "냄비를 활용한 목적별루틴운동",
            "설명: 냄비를 활용한 목적별루틴운동", {},
        )
        neck = classify_document(
            "disability_prescription", "목 스트레칭", "운동명: 목 스트레칭",
            {"disability_type": "지적장애"},
        )
        self.assertEqual(wrist["target_area"], ["손목"])
        self.assertEqual(ankle["target_area"], ["발목"])
        self.assertNotIn("목", purpose["target_area"])
        self.assertEqual(neck["target_area"], ["목"])

    def test_exercise_name_body_part_is_kept_when_source_body_list_is_incomplete(self) -> None:
        facets = classify_document(
            "video_content", "허리 스트레칭",
            "운동명: 허리 스트레칭\n운동 부위: 앞쪽 골반,엉덩이",
            {"exercise_name": "허리 스트레칭", "age_group": "공통"},
        )
        self.assertEqual(facets["target_area"], ["앞쪽 골반", "엉덩이", "허리"])
        self.assertIn("target_area:title", facets["derived_fields"])

    def test_ranged_video_difficulty_is_fully_classified(self) -> None:
        facets = classify_document(
            "video_content", "물당기기/밀기",
            "운동명: 물당기기/밀기\n난이도: 2~5\n운동 장소: 수영장",
            {"age_group": "공통", "difficulty": "2~5", "place": "수영장"},
        )
        self.assertEqual(facets["fitness_level"], ["고급", "중급", "초급"])
        self.assertEqual(facets["location"], ["수영장"])

    def test_health_condition_removes_unrelated_exercise_candidate(self) -> None:
        harness = object.__new__(GroundedQwen3Harness)
        item = {
            "dataset": "video_content", "title": "허리 스트레칭",
            "text": "운동명: 허리 스트레칭\n운동 부위: 허리\n운동 유형: 유연성",
            "metadata": {},
        }
        screened = harness._screen_profile(
            [item], {"target_area": "허리", "exercise_type": "유연성", "health_information": "고혈압"},
            "허리 유연성 운동",
        )
        self.assertEqual(len(screened), 0)

    def test_health_taxonomy_uses_actual_source_phrases(self) -> None:
        self.assertEqual(health_categories("당뇨병을 예방하기 위한 운동"), {"당뇨"})
        self.assertEqual(health_categories("허리관련 질환자를 위한 단계별 표준운동"), {"허리 관련 질환"})
        self.assertEqual(health_categories("낙상을 예방하기 위한 운동프로그램"), {"낙상 예방"})
        self.assertEqual(health_categories("비만 관리 운동"), set())

    def test_new_health_categories_are_stored_as_facets(self) -> None:
        facets = classify_document(
            "video_content", "치매 예방 근력운동",
            "설명: 치매 예방을 위한 운동\n운동 부위: 전신",
            {"age_group": "공통"},
        )
        self.assertEqual(facets["health_information"], ["치매"])


class RagSourceUiTests(unittest.TestCase):
    def test_chat_uses_deterministic_bmi_rule_context_before_model_generation(self) -> None:
        runtime = object.__new__(RagRuntime)
        context = {
            "age_bmi_recommendation": {
                "available": True,
                "bmi": {"available": True, "bmi": 22.5, "bmi_grade": "정상"},
                "age_band": "30대", "sex": "M", "award_group": "1등급",
                "source": {"source_file": "rules.csv"},
                "steps": [{"sports_step": "본운동", "recommendations": [
                    {"rank": 1, "exercise_name": "걷기"},
                ]}],
                "rules": [{"sports_step": "본운동", "rank": 1, "exercise_name": "걷기"}],
            },
        }
        response = runtime._chat_age_bmi_recommendation("BMI와 본운동 순위 알려줘", context)
        self.assertIsNotNone(response)
        self.assertIn("22.5", response["answer"])
        self.assertIn("1위 걷기", response["answer"])
        self.assertEqual(response["sources"][0]["evidence_id"], "B1")

    def test_equipment_none_and_hidden_equipment_are_normalized(self) -> None:
        self.assertEqual(_facet_equipment_values("운동 도구: 없음"), set())
        self.assertEqual(_facet_equipment_values("설명: 밴드를 활용한 운동"), {"밴드"})

    def test_rag_detail_exposes_only_source_fields(self) -> None:
        detail = _rag_detail({
            "title": "누워서 가슴 밀기",
            "text": (
                "운동명: 누워서 가슴 밀기\n"
                "설명: 가슴 근력 운동\n"
                "운동 단계: 본운동\n"
                "운동 부위: 가슴\n"
                "운동 도구: 없음\n"
                "안전수칙: 이 라벨은 화면 계약에 없음"
            ),
        })
        self.assertEqual(detail["운동명"], "누워서 가슴 밀기")
        self.assertEqual(detail["설명"], "가슴 근력 운동")
        self.assertEqual(detail["운동 단계"], "본운동")
        self.assertNotIn("안전수칙", detail)
        self.assertNotIn("수행방법", detail)

    def test_facets_are_conditioned_on_previous_selection(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "age_group": {"성인"}, "sex": {"M"}, "target_area": {"가슴"},
                "exercise_type": {"근력"}, "fitness_level": {"초급"},
                "location": {"실내"}, "equipment": set(),
                "disability_type": set(), "health_information": set(),
                "_audience": "general", "_applicable_fields": set(),
            },
            {
                "age_group": {"어르신"}, "sex": {"F"}, "target_area": {"허벅지"},
                "exercise_type": {"균형"}, "fitness_level": {"초급"},
                "location": {"실내"}, "equipment": {"의자"},
                "disability_type": set(), "health_information": {"관절염"},
                "_audience": "general", "_applicable_fields": set(),
            },
        ]
        options = runtime._faceted_rag_options({"age_group": "성인"})
        self.assertEqual([item["value"] for item in options["sex"]], ["M"])
        self.assertEqual([item["value"] for item in options["target_area"]], ["가슴"])
        self.assertEqual([item["value"] for item in options["exercise_type"]], ["근력"])

    def test_common_age_and_unspecified_sex_keep_user_lists_visible(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [{
            "_id": "common", "_dataset": "video_content", "_audience": "general",
            "_applicable_fields": set(), "age_group": {"공통"}, "sex": set(),
            "target_area": {"등"}, "exercise_type": {"스트레칭"},
            "fitness_level": {"중급"}, "location": {"실내"}, "equipment": set(),
            "disability_type": set(), "health_information": set(),
        }]
        options = runtime._faceted_rag_options({
            "age_group": "성인", "sex": "M", "exercise_type": "스트레칭",
            "fitness_level": "중급", "equipment": "없음", "disability_type": "없음",
        })
        self.assertIn("성인", [item["value"] for item in options["age_group"]])
        self.assertEqual([item["value"] for item in options["sex"]], ["M", "F"])

    def test_cascading_choices_use_only_previous_fields(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": "indoor", "_dataset": "video_content", "_audience": "general",
                "_applicable_fields": set(), "age_group": {"성인"}, "sex": set(),
                "target_area": {"등"}, "exercise_type": {"근력"},
                "fitness_level": {"중급"}, "location": {"실내"}, "equipment": set(),
                "disability_type": set(), "health_information": set(),
            },
            {
                "_id": "outdoor", "_dataset": "video_content", "_audience": "general",
                "_applicable_fields": set(), "age_group": {"성인"}, "sex": set(),
                "target_area": {"가슴"}, "exercise_type": {"유산소"},
                "fitness_level": {"초급"}, "location": {"실외"}, "equipment": {"밴드"},
                "disability_type": set(), "health_information": set(),
            },
        ]
        options = runtime._faceted_rag_options({
            "age_group": "성인", "sex": "M", "target_area": "등",
            "exercise_type": "근력", "fitness_level": "중급",
            "location": "실내", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual(
            [item["value"] for item in options["target_area"]], ["등", "가슴"]
        )
        self.assertEqual([item["value"] for item in options["exercise_type"]], ["근력"])
        self.assertEqual([item["value"] for item in options["fitness_level"]], ["중급"])
        self.assertEqual([item["value"] for item in options["location"]], ["실내"])
        self.assertEqual([item["value"] for item in options["equipment"]], ["없음"])

    def test_video_link_audit_lists_only_exercises_without_exact_official_url(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": "video", "_dataset": "video_content", "_audience": "general",
                "_variant_key": "video:https://official.test/neck.mp4",
                "_exercise_name": "목 스트레칭", "_link_key": "목스트레칭",
                "target_area": {"목"}, "exercise_type": {"스트레칭"},
            },
            {
                "_id": "linked", "_dataset": "general_prescription", "_audience": "general",
                "_variant_key": "document:linked", "_exercise_name": "목 스트레칭",
                "_link_key": "목스트레칭", "target_area": {"목"},
                "exercise_type": {"스트레칭"},
            },
            {
                "_id": "unlinked", "_dataset": "general_prescription", "_audience": "general",
                "_variant_key": "document:unlinked", "_exercise_name": "허리 스트레칭",
                "_link_key": "허리스트레칭", "target_area": {"허리"},
                "exercise_type": {"스트레칭"},
            },
            {
                "_id": "no-url", "_dataset": "video_content", "_audience": "general",
                "_variant_key": "document:no-url", "_exercise_name": "등 펴기",
                "_link_key": "등펴기", "target_area": {"등"},
                "exercise_type": {"유연성"},
            },
        ]
        with patch("fitness_web_server.sqlite3.connect") as connection:
            connection.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            audit = runtime.video_link_audit()
        self.assertEqual(audit["unlinked_count"], 2)
        self.assertEqual(
            [(item["exercise_name"], item["reason"]) for item in audit["items"]],
            [
                ("등 펴기", "보유 자료에서 영상 연결 근거 미확인"),
                ("허리 스트레칭", "보유 자료에서 영상 연결 근거 미확인"),
            ],
        )

    def test_cascading_counts_deduplicate_the_same_exercise_name(self) -> None:
        runtime = object.__new__(RagRuntime)
        base = {
            "_dataset": "video_content", "_audience": "general",
            "_applicable_fields": set(), "age_group": {"성인"}, "sex": set(),
            "target_area": {"목"}, "exercise_type": {"스트레칭"},
            "fitness_level": {"초급"}, "location": {"실내"}, "equipment": set(),
            "disability_type": set(), "health_information": set(),
            "_exercise_key": "목스트레칭",
        }
        runtime.facet_records = [
            {**base, "_id": "copy-1"}, {**base, "_id": "copy-2"},
        ]
        options = runtime._faceted_rag_options({
            "age_group": "성인", "sex": "M", "target_area": "목",
            "exercise_type": "스트레칭", "fitness_level": "초급",
            "location": "실내", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual(options["target_area"][0]["count"], 1)
        self.assertEqual(options["exercise_type"][0]["count"], 1)
        self.assertEqual(runtime._matching_exercise_count({
            "age_group": "성인", "sex": "M", "target_area": "목",
            "exercise_type": "스트레칭", "fitness_level": "초급",
            "location": "실내", "equipment": "없음", "disability_type": "없음",
        }), 1)

    def test_equipment_options_hide_impossible_no_equipment_choice(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [{
            "_id": "chair-neck", "_exercise_key": "의자목스트레칭",
            "_dataset": "video_content", "_audience": "general",
            "_applicable_fields": set(), "age_group": {"성인"}, "sex": set(),
            "target_area": {"목"}, "exercise_type": {"스트레칭"},
            "fitness_level": {"초급"}, "location": {"실내"},
            "equipment": {"의자"}, "disability_type": set(),
            "health_information": set(),
        }]
        options = runtime._faceted_rag_options({
            "age_group": "성인", "sex": "M", "target_area": "목",
            "exercise_type": "스트레칭", "fitness_level": "초급",
            "location": "실내", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual([item["value"] for item in options["equipment"]], ["의자"])

    def test_structured_search_never_relaxes_location(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [{
            "_id": "indoor", "_dataset": "video_content", "_audience": "general",
            "_applicable_fields": set(), "age_group": {"성인"}, "sex": {"M"},
            "target_area": {"전신"}, "exercise_type": {"근력"},
            "fitness_level": {"중급"}, "location": {"실내"}, "equipment": set(),
            "disability_type": set(), "health_information": set(),
        }]
        runtime._fetch_full_records = lambda ids: {}
        results = runtime.structured_search({
            "age_group": "성인", "sex": "M", "target_area": "전신",
            "exercise_type": "근력", "fitness_level": "중급",
            "location": "수영장", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual(results, [])

    def test_richer_exact_source_is_used_for_display(self) -> None:
        detail, source = RagRuntime._best_detail_source("", [
            {"document_id": "1", "dataset": "general_prescription", "title": "가슴 밀기", "text": "운동명: 가슴 밀기"},
            {"document_id": "2", "dataset": "video_content", "title": "가슴 밀기", "text": "운동명: 가슴 밀기\n설명: 가슴 운동\n운동 부위: 가슴\n영상 URL: https://example.test/video"},
        ])
        self.assertEqual(source["document_id"], "2")
        self.assertEqual(detail["설명"], "가슴 운동")
        self.assertEqual(detail["운동 부위"], "가슴")

    def test_detail_source_does_not_mix_other_user_profile(self) -> None:
        detail, source = RagRuntime._best_detail_source("", [
            {"document_id": "adult", "dataset": "measurement_prescription", "title": "운동", "text": "운동명: 운동\n대상 연령군: 성인\n성별: M"},
            {"document_id": "youth", "dataset": "measurement_prescription", "title": "운동", "text": "운동명: 운동\n대상 연령군: 청소년\n성별: F\n체력 인증등급: 3등급"},
        ], {"age_group": "성인", "sex": "M"})
        self.assertEqual(source["document_id"], "adult")
        self.assertEqual(detail["대상 연령군"], "성인")
        self.assertEqual(detail["성별"], "M")

    def test_detail_source_does_not_mix_other_disability_type(self) -> None:
        detail, source = RagRuntime._best_detail_source("", [
            {"document_id": "intellectual", "dataset": "disability_prescription", "title": "허리 스트레칭", "text": "운동명: 허리 스트레칭\n대상 연령군: 성인\n장애유형: 지적장애"},
            {"document_id": "brain", "dataset": "disability_prescription", "title": "허리 스트레칭", "text": "운동명: 허리 스트레칭\n대상 연령군: 성인\n설명: 더 긴 기록\n장애유형: 뇌병변장애"},
        ], {"age_group": "성인", "disability_type": "지적장애"})
        self.assertEqual(source["document_id"], "intellectual")
        self.assertEqual(detail["장애유형"], "지적장애")

    def test_detail_source_does_not_mix_an_explicit_level_into_composite_level(self) -> None:
        detail, source = RagRuntime._best_detail_source("", [
            {
                "document_id": "missing", "dataset": "video_content",
                "title": "앉아서 다리 밀기",
                "text": "운동명: 앉아서 다리 밀기\n운동 장소: 헬스장\n운동 도구: 헬스기구",
            },
            {
                "document_id": "labelled", "dataset": "video_content",
                "title": "앉아서 다리 밀기",
                "text": "운동명: 앉아서 다리 밀기\n설명: 더 긴 상세\n난이도: 3~5\n운동 장소: 헬스장\n운동 도구: 헬스기구",
            },
        ], {
            "age_group": "성인", "sex": "M", "fitness_level": "종합",
            "location": "헬스장", "equipment": "헬스기구",
        })
        self.assertEqual(source["document_id"], "missing")
        self.assertNotIn("난이도", detail)

    def test_video_options_keep_distinct_weekly_urls_and_level_basis(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": "week1", "_dataset": "video_content", "_audience": "general",
                "age_group": {"성인"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"스트레칭"}, "fitness_level": set(),
                "location": {"실내"}, "equipment": set(),
            },
            {
                "_id": "week2", "_dataset": "video_content", "_audience": "general",
                "age_group": {"성인"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"스트레칭"}, "fitness_level": set(),
                "location": {"실내"}, "equipment": set(),
            },
            {
                "_id": "all-levels", "_dataset": "video_content", "_audience": "general",
                "age_group": {"공통"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"스트레칭"},
                "fitness_level": {"초급", "중급", "고급"},
                "location": {"실내"}, "equipment": set(),
            },
        ]
        records = {
            "week1": {"title": "전신 늘리기", "content": "운동명: 전신 늘리기\n설명: 성인 1주차 프로그램\n영상 URL: https://example.test/week1.mp4", "metadata_json": '{"video_url":"https://example.test/week1.mp4","source_file":"05_생애주기별표준운동.json","row_num":17}'},
            "week2": {"title": "전신 늘리기", "content": "운동명: 전신 늘리기\n설명: 성인 2주차 프로그램\n영상 URL: https://example.test/week2.mp4", "metadata_json": '{"video_url":"https://example.test/week2.mp4"}'},
            "all-levels": {"title": "전신 루틴", "content": "운동명: 전신 루틴\n난이도: 1~5\n영상 URL: https://example.test/all.mp4", "metadata_json": '{"video_url":"https://example.test/all.mp4"}'},
        }
        runtime._fetch_full_records = lambda ids: {key: records[key] for key in ids}
        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "전신",
            "exercise_type": "스트레칭", "fitness_level": "중급",
            "location": "실내", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual(options, [])

        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "전신",
            "exercise_type": "스트레칭", "fitness_level": "종합",
            "location": "실내", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual([item["url"] for item in options], [
            "https://example.test/week1.mp4", "https://example.test/week2.mp4",
            "https://example.test/all.mp4",
        ])
        self.assertTrue(all(item["fitness_level"] == "종합" for item in options))

    def test_video_options_keep_an_unlabelled_variant_of_a_shared_url(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": "unlabelled", "_dataset": "video_content", "_audience": "general",
                "age_group": {"공통"}, "sex": set(), "target_area": {"허리"},
                "exercise_type": {"스트레칭"}, "fitness_level": set(),
                "location": set(), "equipment": set(),
            },
            {
                "_id": "labelled", "_dataset": "video_content", "_audience": "general",
                "age_group": {"공통"}, "sex": set(), "target_area": {"허리"},
                "exercise_type": {"스트레칭"}, "fitness_level": {"초급"},
                "location": {"실내"}, "equipment": {"매트"},
            },
        ]
        runtime._fetch_full_records = lambda ids: {
            "unlabelled": {"title": "허리 스트레칭", "content": "운동명: 허리 스트레칭", "metadata_json": '{"video_url":"https://example.test/shared.mp4"}'},
            "labelled": {"title": "허리 스트레칭", "content": "운동명: 허리 스트레칭\n난이도: 1~2\n운동 장소: 실내\n운동 도구: 매트", "metadata_json": '{"video_url":"https://example.test/shared.mp4"}'},
        }
        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "허리",
            "exercise_type": "스트레칭", "fitness_level": "종합",
            "location": "", "equipment": "없음", "disability_type": "없음",
        }, "허리 스트레칭")
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["fitness_level"], "종합")
        self.assertEqual(options[0]["equipment"], "장비 없음/미표기")

    def test_video_options_only_return_the_selected_exercise(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": document_id, "_dataset": "video_content", "_audience": "general",
                "age_group": {"성인"}, "sex": set(), "target_area": {"엉덩이"},
                "exercise_type": {"스트레칭"}, "fitness_level": {"중급"},
                "location": {"실내"}, "equipment": {"매트"},
            }
            for document_id in ("selected", "other")
        ]
        runtime._fetch_full_records = lambda ids: {
            "selected": {"title": "엉덩이 스트레칭(매트)", "content": "운동명: 엉덩이 스트레칭(매트)", "metadata_json": '{"video_url":"https://example.test/selected.mp4"}'},
            "other": {"title": "허리 스트레칭(매트)", "content": "운동명: 허리 스트레칭(매트)", "metadata_json": '{"video_url":"https://example.test/other.mp4"}'},
        }
        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "엉덩이",
            "exercise_type": "스트레칭", "fitness_level": "중급",
            "location": "실내", "equipment": "매트", "disability_type": "없음",
        }, "엉덩이 스트레칭(매트)")
        self.assertEqual([option["url"] for option in options], ["https://example.test/selected.mp4"])

    def test_video_options_merge_source_metadata_for_the_same_url(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": document_id, "_dataset": "video_content", "_audience": "general",
                "age_group": {"성인"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"스트레칭"}, "fitness_level": {"중급"},
                "location": {"실내"}, "equipment": set(),
            }
            for document_id in ("source-a", "source-b")
        ]
        records = {
            "source-a": {
                "title": "전신 늘리기", "content": "운동명: 전신 늘리기",
                "metadata_json": '{"video_url":"https://example.test/shared.mp4","source_file":"03_운동처방동영상.json","row_num":5}',
            },
            "source-b": {
                "title": "전신 늘리기", "content": "운동명: 전신 늘리기",
                "metadata_json": '{"video_url":"https://example.test/shared.mp4","source_file":"07_동영상전체목록.json","row_num":9}',
            },
        }
        runtime._fetch_full_records = lambda ids: {key: records[key] for key in ids}
        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "전신",
            "exercise_type": "스트레칭", "fitness_level": "중급",
            "location": "실내", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual(len(options), 1)
        self.assertEqual(
            [source["source_file"] for source in options[0]["sources"]],
            ["03_운동처방동영상.json", "07_동영상전체목록.json"],
        )
        self.assertEqual([source["row_num"] for source in options[0]["sources"]], [5, 9])

    def test_video_options_exclude_explicitly_different_level(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": "beginner", "_dataset": "video_content", "_audience": "general",
                "age_group": {"공통"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"근력"}, "fitness_level": {"초급"},
                "location": {"실내"}, "equipment": {"밴드"},
            },
            {
                "_id": "beginner-copy", "_dataset": "video_content", "_audience": "general",
                "age_group": {"공통"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"근력"}, "fitness_level": set(),
                "location": set(), "equipment": {"밴드"},
            },
        ]
        runtime._fetch_full_records = lambda ids: {
            key: {"title": "초급 전신 근력", "content": "운동명: 초급 전신 근력\n영상 URL: https://example.test/beginner.mp4", "metadata_json": '{"video_url":"https://example.test/beginner.mp4"}'}
            for key in ids
        }
        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "전신",
            "exercise_type": "근력", "fitness_level": "중급",
            "location": "실내", "equipment": "밴드", "disability_type": "없음",
        })
        self.assertEqual(options, [])

    def test_video_options_require_explicit_location_and_compatible_equipment(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": "missing-place", "_dataset": "video_content", "_audience": "general",
                "age_group": {"성인"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"근력"}, "fitness_level": {"중급"},
                "location": set(), "equipment": set(),
            },
            {
                "_id": "pool-with-pot", "_dataset": "video_content", "_audience": "general",
                "age_group": {"성인"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"근력"}, "fitness_level": {"중급"},
                "location": {"수영장"}, "equipment": {"냄비"},
            },
            {
                "_id": "pool-bodyweight", "_dataset": "video_content", "_audience": "general",
                "age_group": {"성인"}, "sex": set(), "target_area": {"전신"},
                "exercise_type": {"근력"}, "fitness_level": {"중급"},
                "location": {"수영장"}, "equipment": set(),
            },
        ]
        records = {
            key: {
                "title": key, "content": f"운동명: {key}\n영상 URL: https://example.test/{key}",
                "metadata_json": f'{{"video_url":"https://example.test/{key}"}}',
            }
            for key in ("missing-place", "pool-with-pot", "pool-bodyweight")
        }
        runtime._fetch_full_records = lambda ids: {key: records[key] for key in ids}
        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "전신",
            "exercise_type": "근력", "fitness_level": "중급",
            "location": "수영장", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual([item["title"] for item in options], ["pool-bodyweight"])

    def test_video_options_prioritize_the_selected_body_part_in_title(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [
            {
                "_id": "thigh", "_dataset": "video_content", "_audience": "general",
                "age_group": {"공통"}, "sex": set(),
                "target_area": {"허리", "안쪽 넓적다리"},
                "exercise_type": {"스트레칭"}, "fitness_level": {"초급"},
                "location": {"실내"}, "equipment": {"매트"},
            },
            {
                "_id": "waist", "_dataset": "video_content", "_audience": "general",
                "age_group": {"공통"}, "sex": set(), "target_area": {"허리"},
                "exercise_type": {"스트레칭"}, "fitness_level": {"초급"},
                "location": {"실내"}, "equipment": {"매트"},
            },
        ]
        records = {
            "thigh": {
                "title": "넙다리 안쪽 스트레칭",
                "content": "운동명: 넙다리 안쪽 스트레칭\n영상 URL: https://example.test/thigh",
                "metadata_json": '{"video_url":"https://example.test/thigh"}',
            },
            "waist": {
                "title": "허리 스트레칭-1",
                "content": "운동명: 허리 스트레칭-1\n영상 URL: https://example.test/waist",
                "metadata_json": '{"video_url":"https://example.test/waist"}',
            },
        }
        runtime._fetch_full_records = lambda ids: {key: records[key] for key in ids}
        options = runtime._video_options({
            "age_group": "성인", "sex": "M", "target_area": "허리",
            "exercise_type": "스트레칭", "fitness_level": "초급",
            "location": "실내", "equipment": "매트", "disability_type": "없음",
        })
        self.assertEqual([item["title"] for item in options], ["허리 스트레칭-1"])

    def test_detail_source_cannot_come_from_a_different_location(self) -> None:
        detail, source = RagRuntime._best_detail_source("", [
            {
                "document_id": "indoor", "dataset": "video_content", "title": "냄비 운동",
                "text": "운동명: 냄비 운동\n운동 장소: 실내\n운동 도구: 냄비",
            },
            {
                "document_id": "pool", "dataset": "video_content", "title": "아쿠아 걷기",
                "text": "운동명: 아쿠아 걷기\n운동 장소: 수영장",
            },
        ], {"age_group": "성인", "sex": "M", "location": "수영장", "equipment": "없음"})
        self.assertEqual(source["document_id"], "pool")
        self.assertEqual(detail["운동 장소"], "수영장")

    def test_structured_search_never_relaxes_exercise_type(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [{
            "_id": "stretch", "_dataset": "video_content", "_audience": "general",
            "_applicable_fields": set(), "age_group": {"성인"}, "sex": set(),
            "target_area": {"전신"}, "exercise_type": {"스트레칭"},
            "fitness_level": {"초급"}, "location": {"실내"}, "equipment": set(),
            "disability_type": set(), "health_information": set(),
        }]
        runtime._fetch_full_records = lambda ids: {}
        results = runtime.structured_search({
            "age_group": "성인", "sex": "M", "target_area": "전신",
            "exercise_type": "근력", "fitness_level": "고급",
            "location": "실외", "equipment": "없음", "disability_type": "없음",
        })
        self.assertEqual(results, [])

    def test_friendly_copy_explains_weekly_videos_in_narrative_form(self) -> None:
        copy = _friendly_result_copy(
            {
                "age_group": "성인", "fitness_level": "중급",
                "target_area": "전신", "exercise_type": "스트레칭",
                "equipment": "없음",
            },
            {
                "selected_name": "전신 루틴 스트레칭",
                "selected_detail": {"설명": "전신 루틴을 설명한 공식 영상"},
                "video_options": [
                    {
                        "title": "전신 루틴 스트레칭", "week": "",
                        "fitness_level": "초급/중급/고급",
                        "condition_note": "선택 난이도 명시",
                        "condition_compatible": True, "equipment": "장비 없음/미표기",
                        "description": "전신 루틴을 설명한 공식 영상",
                    },
                    {
                        "title": "전신 늘리기", "week": "1주차",
                        "fitness_level": "난이도 미표기", "condition_note": "난이도 미표기",
                        "condition_compatible": True, "equipment": "장비 없음/미표기",
                        "description": "성인 1주차 프로그램",
                    },
                    {
                        "title": "전신 늘리기", "week": "2주차",
                        "fitness_level": "난이도 미표기", "condition_note": "난이도 미표기",
                        "condition_compatible": True, "equipment": "장비 없음/미표기",
                        "description": "성인 2주차 프로그램",
                    },
                ],
            },
        )
        self.assertIn("공식 영상도 3개 있어요", copy["recommendation_guide"])
        self.assertIn("1주차부터 2주차", copy["exercise_method"])
        self.assertIn("별도 등급을 붙이지 않았어요", copy["exercise_method"])
        self.assertNotIn("1주차", copy["exercise_intro"])

    def test_friendly_copy_explains_equipment_mismatch(self) -> None:
        copy = _friendly_result_copy(
            {
                "age_group": "성인", "fitness_level": "중급",
                "target_area": "전신", "exercise_type": "근력", "equipment": "없음",
            },
            {
                "selected_name": None, "selected_detail": {},
                "video_options": [{
                    "title": "물병 전신 근력", "week": "",
                    "fitness_level": "난이도 미표기", "condition_note": "추가 장비 필요: 물병",
                    "condition_compatible": False, "equipment": "물병",
                    "description": "물병을 활용한 전신 근력운동",
                }],
            },
        )
        self.assertIn("장소와 장비(없음)에 모두 맞는 영상은", copy["recommendation_guide"])
        self.assertEqual(copy["exercise_method"], "")

    def test_recommendation_intro_and_method_have_distinct_roles(self) -> None:
        copy = _friendly_result_copy(
            {
                "age_group": "성인", "fitness_level": "초급",
                "target_area": "허리", "exercise_type": "스트레칭",
                "equipment": "매트",
            },
            {
                "selected_name": "허리 스트레칭",
                "selected_detail": {
                    "설명": "허리 스트레칭을 설명한 공식 운동처방 가이드",
                    "운동 부위": "허리", "주요 근육": "허리근",
                },
                "video_options": [{
                    "title": "허리 스트레칭", "description": "허리 스트레칭 안내",
                    "condition_note": "선택 난이도 명시", "condition_compatible": True,
                    "equipment": "매트", "week": "",
                }],
            },
        )
        self.assertIn("잘 맞아요", copy["recommendation_guide"])
        self.assertNotIn("허리근", copy["recommendation_guide"])
        self.assertIn("허리근", copy["exercise_intro"])
        self.assertNotIn("RAG", copy["recommendation_guide"])
        self.assertEqual(copy["exercise_method"], "")

    def test_sparse_and_inconsistent_prescription_is_explained(self) -> None:
        notice = _detail_notice({
            "운동명": "정리운동:엉덩이 늘리기", "운동 단계": "본운동",
            "대상 연령군": "성인", "성별": "M",
        })
        self.assertIn("개인 처방 분류 기록", notice)
        self.assertIn("다른 연령군의 상세 자료는 섞지 않았습니다", notice)
        self.assertIn("서로 달라", notice)

    def test_title_body_part_mismatch_is_explained_without_rewriting_source(self) -> None:
        notice = _target_focus_notice(
            {"target_area": "허리"},
            {
                "selected_name": "허리 스트레칭",
                "selected_detail": {
                    "운동명": "허리 스트레칭",
                    "설명": "허리 스트레칭운동 안내",
                    "운동 부위": "엉덩이,앞쪽 골반,등",
                },
            },
        )
        self.assertIn("허리 중심 자료로 우선 선택", notice)
        self.assertIn("원문 값을 수정하지 않고", notice)

    def test_structured_search_uses_same_conditions_as_visible_facets(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [{
            "_id": "shin-1", "_dataset": "video_content",
            "_audience": "general", "_applicable_fields": set(),
            "age_group": {"성인"}, "sex": {"M"}, "target_area": {"정강이"},
            "exercise_type": {"스트레칭"}, "fitness_level": {"초급"},
            "location": {"실내"}, "equipment": set(),
            "disability_type": set(), "health_information": set(),
        }]
        runtime.exercise_detail_index = {}
        runtime._fetch_full_records = lambda ids: {
            "shin-1": {
                "id": "shin-1", "dataset": "video_content", "title": "정강이 스트레칭",
                "content": "운동명: 정강이 스트레칭\n운동 부위: 정강이\n운동 도구: 없음",
                "metadata_json": '{"age_group":"성인","sex":"M"}',
                "occurrence_count": 1,
            }
        }
        results = runtime.structured_search({
            "age_group": "성인", "sex": "M", "target_area": "정강이",
            "exercise_type": "스트레칭", "fitness_level": "초급",
            "location": "실내", "equipment": "없음",
        })
        self.assertEqual([item["id"] for item in results], ["shin-1"])

    def test_disability_matching_ignores_fields_missing_from_source_schema(self) -> None:
        record = {
            "_id": "d1", "_dataset": "disability_prescription", "_audience": "disability",
            "_applicable_fields": {"age_group", "sex", "target_area", "exercise_type", "location", "disability_type"},
            "age_group": {"성인"}, "sex": {"M"}, "target_area": {"허리"},
            "exercise_type": {"유연성"}, "fitness_level": set(), "location": set(),
            "equipment": set(), "disability_type": {"지적장애"}, "health_information": set(),
        }
        selection = {
            "age_group": "성인", "sex": "M", "target_area": "허리",
            "exercise_type": "유연성", "fitness_level": "초급", "location": "실내",
            "equipment": "", "disability_type": "지적장애", "health_information": "고혈압",
        }
        self.assertFalse(RagRuntime._facet_record_matches(record, selection, "__none__"))
        selection["health_information"] = "없음"
        self.assertTrue(RagRuntime._facet_record_matches(record, selection, "__none__"))
        selection["disability_type"] = "시각장애"
        self.assertFalse(RagRuntime._facet_record_matches(record, selection, "__none__"))

    def test_pain_area_cannot_remain_the_selected_target(self) -> None:
        record = {
            "_audience": "general", "age_group": {"성인"}, "sex": {"M"},
            "target_area": {"허리"}, "exercise_type": {"근력"},
            "fitness_level": set(), "location": set(), "equipment": set(),
            "disability_type": set(), "health_information": set(),
        }
        selection = {
            "age_group": "성인", "sex": "M", "pain_area": "허리", "pain_level": "3",
            "target_area": "허리", "disability_type": "없음", "health_information": "없음",
        }
        self.assertFalse(RagRuntime._facet_record_matches(record, selection, "__none__"))
        selection["pain_level"] = "0"
        self.assertFalse(RagRuntime._facet_record_matches(record, selection, "__none__"))
        selection["pain_area"] = "없음"
        self.assertTrue(RagRuntime._facet_record_matches(record, selection, "__none__"))

    def test_severe_pain_makes_matching_count_zero(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = []
        self.assertEqual(runtime._matching_exercise_count({"pain_level": "7"}), 0)

    def test_pain_area_is_removed_from_following_target_options(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = []
        for index, target in enumerate(("허리", "어깨"), start=1):
            runtime.facet_records.append({
                "_id": str(index), "_exercise_key": str(index),
                "_audience": "general", "age_group": {"성인"}, "sex": {"M"},
                "target_area": {target}, "exercise_type": {"근력"},
                "fitness_level": set(), "location": set(), "equipment": set(),
                "disability_type": set(), "health_information": set(),
            })
        options = runtime._faceted_rag_options({
            "age_group": "성인", "sex": "M", "pain_area": "허리",
            "pain_level": "0", "disability_type": "없음",
        })
        self.assertEqual([item["value"] for item in options["target_area"]], ["어깨"])

    def test_missing_difficulty_is_grouped_as_composite_without_inventing_a_level(self) -> None:
        runtime = object.__new__(RagRuntime)
        runtime.facet_records = [{
            "_id": "gym-1", "_exercise_key": "gym-1", "_audience": "general",
            "age_group": {"성인"}, "sex": {"M"}, "target_area": {"엉덩이"},
            "exercise_type": {"근력"}, "fitness_level": set(),
            "location": {"헬스장"}, "equipment": {"헬스기구"},
            "disability_type": set(), "health_information": set(),
        }]
        selection = {
            "age_group": "성인", "sex": "M", "pain_area": "없음",
            "health_information": "없음", "target_area": "엉덩이",
            "exercise_type": "근력", "disability_type": "없음",
        }
        options = runtime._faceted_rag_options(selection)
        self.assertEqual(
            [item["value"] for item in options["fitness_level"]], ["종합"],
        )
        selection["fitness_level"] = "종합"
        self.assertTrue(
            RagRuntime._facet_record_matches(runtime.facet_records[0], selection, "__none__")
        )

    def test_measurement_place_is_not_treated_as_exercise_location(self) -> None:
        facets = classify_document(
            "disability_prescription", "허리 스트레칭", "측정 장소: 출장",
            {"place": "출장", "disability_type": "지적장애"},
        )
        self.assertEqual(facets["location"], [])

    def test_equipment_named_in_disability_exercise_is_derived(self) -> None:
        facets = classify_document(
            "disability_prescription", "허리 굽혀 덤벨 들기", "운동명: 허리 굽혀 덤벨 들기",
            {"disability_type": "지적장애"},
        )
        self.assertIn("덤벨", facets["equipment"])
        self.assertIn("equipment:title", facets["derived_fields"])


if __name__ == "__main__":
    unittest.main()
