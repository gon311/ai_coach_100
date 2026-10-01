import json
import os
from contextlib import closing
import sqlite3
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import fitness_evaluation_harness as evaluation


class FitnessEvaluationHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not evaluation.NORM_DB.is_file() or not evaluation.RAG_DB.is_file():
            raise unittest.SkipTest("External percentile and RAG databases are required")
        cls.profiles = evaluation.build_profiles(evaluation.NORM_DB)
        cls.cases = evaluation.build_v6_non_normal_cases(cls.profiles) + evaluation.build_general_cases(evaluation.RAG_DB)

    def test_profile_and_path_counts_match_contract(self):
        self.assertEqual(len(self.profiles), 8)
        self.assertEqual(len(self.cases), 145)
        self.assertEqual(
            {path: sum(case["expected_path"] == path for case in self.cases) for path in "ABC"},
            {"A": 25, "B": 45, "C": 75},
        )
        self.assertEqual(
            {category: sum(case["category"] == category for case in self.cases)
             for category in evaluation.CATEGORY_TARGETS},
            evaluation.CATEGORY_TARGETS,
        )

    def test_profile_values_are_norm_derived(self):
        for profile in self.profiles:
            for snapshot in profile["measurement_snapshots"]:
                self.assertEqual(set(snapshot["measurements"]), set(snapshot["provenance"]))
                for code, value in snapshot["measurements"].items():
                    provenance = snapshot["provenance"][code]
                    self.assertEqual(provenance["source_table"], "fitness_norm")
                    self.assertEqual(value, provenance["value"])

    def test_senior_profiles_have_no_standing_long_jump(self):
        seniors = [profile for profile in self.profiles if profile["life_stage"] == "SENIOR"]
        self.assertTrue(seniors)
        for profile in seniors:
            self.assertNotIn("STANDING_LONG_JUMP", profile["previous_snapshot"]["measurements"])
            self.assertNotIn("STANDING_LONG_JUMP", profile["current_snapshot"]["measurements"])

    def test_general_candidate_population_excludes_disability_and_is_not_goldset(self):
        general = [case for case in self.cases if case["category"] == "normal"]
        self.assertEqual(len(general), 45)
        self.assertEqual(
            {dataset: sum(case.get("generation_source_dataset") == dataset for case in general)
             for dataset in evaluation.ALLOWED_RAG_DATASETS},
            {"video_content": 15, "general_prescription": 15, "measurement_prescription": 15},
        )
        self.assertNotIn(
            "disability_prescription",
            {case.get("generation_source_dataset") for case in general},
        )
        self.assertTrue(all(case["goldset_status"] == "candidate_unreviewed" for case in general))
        self.assertTrue(all(case["gold_document_ids"] == [case["generation_source_document_id"]] for case in general))
        self.assertTrue(all("reference_text" not in case for case in general))

    def test_contract_verification_passes(self):
        verification = evaluation.verify_evaluation_contract(self.profiles, self.cases)
        self.assertTrue(verification["passed"])
        self.assertEqual(verification["goldset_status"], "draft_45_normal_cases_unreviewed")
        self.assertEqual(verification["rule_case_counts"]["R12-a"], 5)
        self.assertEqual(verification["rule_case_counts"]["R12-b"], 5)

    def test_official_goldset_preflight_matches_fixed_contract(self):
        source = Path(os.environ.get("AI_FITNESS_EVAL_GOLDSET", str(evaluation.GOLDSET_ROOT / "goldset_official_145.jsonl")))
        if not source.is_file():
            self.skipTest("Official goldset is not included in the public repository")
        cases, verification = evaluation.load_official_goldset(source)
        self.assertEqual(len(cases), 145)
        self.assertTrue(verification["passed"])
        self.assertEqual(verification["case_id_duplicate_count"], 0)
        self.assertEqual(verification["path_counts"], {"A": 25, "B": 45, "C": 75})
        self.assertEqual(verification["expected_rag_search_true_count"], 80)
        self.assertEqual(verification["human_verified_true_count"], 145)
        self.assertEqual(verification["goldset_status_verified_count"], 145)
        self.assertEqual(verification["sha256"], evaluation.OFFICIAL_GOLDSET_SHA256)
        self.assertEqual(verification["rule_case_counts"], evaluation.OFFICIAL_RULE_COUNTS)
        self.assertEqual(verification["rule_case_counts"]["R10"], 0)

    def test_r1_and_r14_respect_negative_context(self):
        checks = {"r3_no_disability_retrieval": True, "r3_no_disability_citation": True}
        with closing(sqlite3.connect(":memory:")) as connection:
            negative = evaluation._official_rule_results(
                connection, {"applicable_rules": ["R1", "R14"]},
                {"answer": "공식 인증등급을 발급할 수 없습니다. 자체 상위/중위/하위 등급으로 분류하지 않습니다."},
                checks, {"passed": True},
            )
            positive = evaluation._official_rule_results(
                connection, {"applicable_rules": ["R1", "R14"]},
                {"answer": "당신은 공식 인증 1등급입니다. 당신의 체력은 상위 등급입니다."},
                checks, {"passed": True},
            )
        self.assertTrue(negative["R1"]["passed"])
        self.assertTrue(negative["R14"]["passed"])
        self.assertFalse(positive["R1"]["passed"])
        self.assertFalse(positive["R14"]["passed"])
        self.assertTrue(all(negative[rule]["status"] == "not_applicable"
                            for rule in evaluation.RULE_SPECS if rule not in {"R1", "R14"}))

    def test_official_goldset_hash_mismatch_stops_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / "tampered.jsonl"
            tampered.write_text('{"case_id":"changed"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256 불일치"):
                evaluation.load_official_goldset(tampered)

    def test_official_goldset_prepare_skips_internal_case_generators(self):
        source = Path(os.environ.get("AI_FITNESS_EVAL_GOLDSET", str(evaluation.GOLDSET_ROOT / "goldset_official_145.jsonl")))
        if not source.is_file():
            self.skipTest("Official goldset is not included in the public repository")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(evaluation, "build_v6_non_normal_cases", side_effect=AssertionError("must not run")), \
             mock.patch.object(evaluation, "build_general_cases", side_effect=AssertionError("must not run")):
            prepared = evaluation.prepare(Path(directory), goldset_jsonl=source)
        self.assertEqual(len(prepared["cases"]), 145)
        self.assertEqual(prepared["metadata"]["goldset_status"], "verified")

    def test_collection_summary_reports_path_and_retrieval_contract(self):
        rows = [
            {"case_id": "rag-ok", "http_status": 200, "path_match": True,
             "expected_rag_search": True, "actual_rag_search": True,
             "retrieval_backend": ["chroma_vector"]},
            {"case_id": "rag-fallback", "http_status": 200, "path_match": True,
             "expected_rag_search": True, "actual_rag_search": True,
             "retrieval_backend": ["sqlite_keyword_fallback"]},
            {"case_id": "unexpected", "http_status": 200, "path_match": False,
             "expected_rag_search": False, "actual_rag_search": True,
             "retrieval_backend": ["chroma_vector"]},
        ]
        summary = evaluation.summarize_collection(rows)
        self.assertEqual(summary["http_success_count"], 3)
        self.assertEqual(summary["path_match_rate"], 2 / 3)
        self.assertEqual(summary["rag_target_chroma_vector_count"], 1)
        self.assertEqual(summary["rag_target_sqlite_keyword_fallback_count"], 1)
        self.assertEqual(summary["unexpected_actual_search_count"], 1)
        self.assertEqual(summary["failed_case_ids"], ["unexpected"])

    def test_reference_free_ragas_is_ready_but_retrieval_metrics_need_verified_goldset(self):
        rows = []
        for case in self.cases:
            is_general = case["category"] == "normal"
            document_id = case.get("generation_source_document_id") if is_general else None
            injected = {} if case["expected_path"] != "B" else {"TEST": {"value": 1}}
            rows.append({
                **case,
                "response": {
                    "answer": "평가용 답변",
                    "answer_path": case["expected_path"],
                    "retrieved_doc_ids": ([{
                        "document_id": document_id,
                        "score": 1.0,
                        "dataset": case.get("generation_source_dataset"),
                    }] if is_general else []),
                    "cited_doc_ids": [document_id] if is_general else [],
                    "evidence_text": ({document_id: case["candidate_reference_text"][:700]} if is_general else {}),
                    "queried_record_ids": [],
                    "injected_values": injected,
                    "routing_flag": None,
                },
            })
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ragas_input.jsonl"
            count = evaluation.build_ragas_input(rows, output)
            samples = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            report = evaluation.score(rows, evaluation.NORM_DB)
        self.assertEqual(count, 45)
        self.assertEqual(len(samples), 45)
        self.assertTrue(all("reference" not in sample for sample in samples))
        self.assertTrue(all(sample["retrieved_contexts"] for sample in samples))
        self.assertEqual(report["retrieval_eligible_count"], 0)
        self.assertIsNone(report["hit_rate_at_5"])
        self.assertIsNone(report["mrr_at_5"])
        self.assertEqual(report["official_retrieval_metrics_status"], "not_run_no_verified_goldset")

    def test_human_verified_goldset_row_can_enter_ragas_later(self):
        case = dict(next(case for case in self.cases if case["category"] == "normal"))
        document_id = case["generation_source_document_id"]
        case.update({
            "goldset_status": "verified",
            "gold_document_ids": [document_id],
            "reference_text": case["candidate_reference_text"],
            "response": {
                "answer": "검증 답변", "answer_path": "C",
                "retrieved_doc_ids": [{
                    "document_id": document_id, "score": 1.0,
                    "dataset": case["generation_source_dataset"], "backend": "chroma_vector",
                }],
                "cited_doc_ids": [document_id],
                "evidence_text": {document_id: case["candidate_reference_text"][:700]},
                "queried_record_ids": [], "injected_values": {}, "routing_flag": None,
            },
        })
        samples = evaluation.build_ragas_samples([case])
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["reference"], case["reference_text"])

    def test_c_response_contract_verifies_top5_dataset_and_exact_evidence(self):
        with closing(sqlite3.connect(evaluation.RAG_DB)) as connection:
            documents = connection.execute(
                """SELECT id,dataset,content FROM documents
                   WHERE dataset IN ('video_content','general_prescription','measurement_prescription')
                   ORDER BY id LIMIT 5"""
            ).fetchall()
        retrieved = [
            {
                "document_id": document_id, "score": 0.9 - index * 0.1,
                "dataset": dataset, "backend": "chroma_vector",
            }
            for index, (document_id, dataset, _content) in enumerate(documents)
        ]
        cited_id, cited_dataset, cited_content = documents[0]
        row = {
            "case_id": "C-contract", "category": "normal", "expected_path": "C", "question": "운동 방법",
            "expected_rag_search": True, "applicable_rules": ["R3", "R5", "R14"],
            "goldset_status": "candidate_unreviewed", "gold_document_ids": [],
            "generation_source_document_id": cited_id,
            "response": {
                "answer": "근거 기반 답변", "answer_path": "C",
                "retrieved_doc_ids": retrieved, "cited_doc_ids": [cited_id],
                "evidence_text": {cited_id: cited_content[:700]},
                "queried_record_ids": [], "injected_values": {}, "routing_flag": None,
                "sources": [{"document_id": cited_id, "dataset": cited_dataset}],
            },
        }
        non_rag_c = {
            "case_id": "C-no-rag", "category": "out_of_scope", "expected_path": "C",
            "question": "오늘 날씨", "expected_rag_search": False,
            "applicable_rules": ["R3", "R4", "R14"],
            "response": {
                "answer": "체력 코칭 범위 밖의 요청입니다.", "answer_path": "C",
                "retrieved_doc_ids": [], "cited_doc_ids": [], "evidence_text": {},
                "queried_record_ids": [], "injected_values": {}, "routing_flag": None,
            },
        }
        report = evaluation.score([row, non_rag_c], evaluation.NORM_DB)
        self.assertTrue(report["cases"][0]["passed"])
        self.assertEqual(report["C_rag_evaluated_count"], 1)
        self.assertEqual(report["C_full_top_5_rate"], 1.0)
        self.assertEqual(report["C_vector_index_rate"], 1.0)
        self.assertEqual(report["C_citation_integrity_rate"], 1.0)

    def test_environment_status_never_contains_api_key_value(self):
        status = evaluation.evaluation_environment_status()
        self.assertIn("openai_api_key_present", status)
        self.assertNotIn("api_key", status)

    def test_eval_user_db_contains_only_eight_seeded_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            database, token_map = evaluation.build_eval_user_db(Path(directory), self.profiles)
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute("SELECT count(*) FROM users").fetchone()[0], 8)
                self.assertEqual(connection.execute("SELECT count(*) FROM auth_sessions").fetchone()[0], 8)
                self.assertEqual(connection.execute("SELECT count(*) FROM measurement_sessions").fetchone()[0], 10)
                self.assertEqual(connection.execute("SELECT count(*) FROM user_screening WHERE parq_passed=0").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM measurement_sessions WHERE username='eval_p6'").fetchone()[0], 0)
                senior_long_jump = connection.execute(
                    """SELECT count(*) FROM measurement_results r
                       JOIN measurement_sessions s ON s.id=r.session_id
                       WHERE s.life_stage='SENIOR' AND r.item_code='STANDING_LONG_JUMP'"""
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(senior_long_jump, 0)
            self.assertEqual(set(token_map), {f"P{index}" for index in range(1, 9)})

    def test_prepare_consolidates_preflight_into_one_bundle_database(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            prepared = evaluation.prepare(output_dir)
            bundle = output_dir / evaluation.BUNDLE_FILENAME
            self.assertEqual(prepared["bundle_db"], bundle)
            self.assertEqual([path.name for path in output_dir.iterdir()], [bundle.name])
            with closing(sqlite3.connect(bundle)) as connection:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertTrue({"fitness_norm", "users", "evaluation_artifacts"} <= tables)
            self.assertEqual(len(evaluation.load_bundle_artifact(bundle, "virtual_profiles_8")), 8)
            self.assertEqual(len(evaluation.load_bundle_artifact(bundle, "evaluation_cases_145")), 145)
            self.assertTrue(evaluation.load_bundle_artifact(bundle, "contract_verification")["passed"])
            evaluation.load_prepared(output_dir)
            refreshed = evaluation.load_bundle_artifact(bundle, "evaluation_metadata")
            self.assertIn("last_run_at", refreshed)
            with closing(sqlite3.connect(bundle)) as connection:
                sessions = connection.execute(
                    "SELECT username,created_at FROM auth_sessions ORDER BY username"
                ).fetchall()
            self.assertEqual(len(sessions), 8)
            self.assertEqual({row[0] for row in sessions}, {f"eval_p{i}" for i in range(1, 9)})
            self.assertTrue(all(row[1] == refreshed["last_run_at"] for row in sessions))
            self.assertEqual(
                refreshed["last_run_module_log"][str(Path(evaluation.__file__).resolve())],
                evaluation._sha256(Path(evaluation.__file__)),
            )

    def test_visual_report_distinguishes_path_success_from_model_fallback(self):
        rows = [{
            "case_id": "P1-B-01", "expected_path": "B", "question": "개인화 질문",
            "response": {
                "answer": "근거 기반 대체 답변", "answer_path": "B",
                "queried_record_ids": [1], "injected_values": {"TEST": {"value": 1}},
                "retrieved_doc_ids": [{
                    "document_id": "doc-1", "score": 0.4,
                    "dataset": "general_prescription", "backend": "sqlite_keyword_fallback",
                }],
                "routing_flag": "MODEL_FALLBACK",
            },
        }]
        report = {
            "cases": [{"case_id": "P1-B-01", "passed": False}],
            "contract_pass_rate": 0.0, "path_match_rate": 1.0,
            "B_model_response_accept_rate": 0.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.html"
            evaluation.write_visual_report({"improved": rows}, {"improved": report}, target)
            content = target.read_text(encoding="utf-8")
        self.assertIn("경로 정확도", content)
        self.assertIn("MODEL_FALLBACK", content)
        self.assertIn("SQLite 검색 폴백", content)


if __name__ == "__main__":
    unittest.main()
