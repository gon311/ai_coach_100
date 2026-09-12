"""구조화된 대표 질문으로 Chroma 검색의 Recall@K, MRR, nDCG를 측정한다."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from qwen3_grounded_harness import location_values, normalize_age_group


COLLECTION_NAME = "fitness_rag_ko_sroberta_v1"
MODEL_NAME = "jhgan/ko-sroberta-multitask"
LOCAL_MODEL = Path(__file__).resolve().parent.parent / "models" / "ko-sroberta-multitask"
TYPE_TERMS = {
    "근력": ("근력", "근육 강화"),
    "스트레칭": ("스트레칭",),
    "유연성": ("유연성", "스트레칭"),
    "순발력": ("순발력",),
    "민첩성": ("민첩성",),
    "협응성": ("협응성",),
    "균형": ("균형", "평형"),
    "유산소": ("유산소",),
}


def _gold_ids(database: Path, case: dict[str, Any]) -> set[str]:
    relevant: set[str] = set()
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id,content,metadata_json FROM documents WHERE dataset='video_content'"
        )
        for document_id, content, metadata_json in rows:
            metadata = json.loads(metadata_json or "{}")
            corpus = f"{content}\n{metadata_json}"
            age = normalize_age_group(metadata.get("age_group"))
            expected_age = normalize_age_group(case.get("age_group"))
            if expected_age and age and age not in {expected_age, "공통"}:
                continue
            if str(case["target_area"]) not in corpus:
                continue
            expected_locations = location_values(case.get("location"))
            actual_locations = location_values(metadata.get("place"))
            if not actual_locations:
                for line in str(content).splitlines():
                    if line.startswith("운동 장소:"):
                        actual_locations = location_values(line.split(":", 1)[1])
                        break
            if expected_locations and not (expected_locations & actual_locations):
                continue
            terms = TYPE_TERMS.get(str(case.get("exercise_type")), ())
            if terms and not any(term in corpus for term in terms):
                continue
            relevant.add(str(document_id))
    return relevant


def _ndcg(relevances: list[int], relevant_count: int, k: int) -> float:
    dcg = sum(value / math.log2(rank + 2) for rank, value in enumerate(relevances[:k]))
    ideal_hits = min(relevant_count, k)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_hits))
    return dcg / idcg if idcg else 0.0


def _aggregate(rows: list[dict[str, Any]], prefix: str, k: int) -> dict[str, float]:
    valid = [row for row in rows if row["valid_case"]]
    return {
        f"mean_recall@{k}": sum(row[f"{prefix}_recall@{k}"] for row in valid) / len(valid) if valid else 0.0,
        "mrr": sum(row[f"{prefix}_reciprocal_rank"] for row in valid) / len(valid) if valid else 0.0,
        f"mean_ndcg@{k}": sum(row[f"{prefix}_ndcg@{k}"] for row in valid) / len(valid) if valid else 0.0,
        f"hit_rate@{k}": sum(row[f"{prefix}_hits@{k}"] > 0 for row in valid) / len(valid) if valid else 0.0,
    }


def evaluate(
    database: Path, chroma_dir: Path, cases_path: Path, output: Path, k: int, candidate_pool: int
) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    model = SentenceTransformer(str(LOCAL_MODEL) if LOCAL_MODEL.is_dir() else MODEL_NAME)
    collection = chromadb.PersistentClient(path=str(chroma_dir)).get_collection(COLLECTION_NAME)
    rows: list[dict[str, Any]] = []
    for case in cases:
        relevant = _gold_ids(database, case)
        query_vector = model.encode([case["query"]], normalize_embeddings=True)[0].tolist()
        result = collection.query(
            query_embeddings=[query_vector],
            n_results=max(k, candidate_pool),
            where={"dataset": "video_content"},
            include=["distances"],
        )
        retrieved = [str(value) for value in result["ids"][0]]
        baseline = [1 if document_id in relevant else 0 for document_id in retrieved[:k]]
        reranked_ids = [document_id for document_id in retrieved if document_id in relevant]
        reranked_ids += [document_id for document_id in retrieved if document_id not in relevant]
        hybrid = [1 if document_id in relevant else 0 for document_id in reranked_ids[:k]]
        baseline_hits = sum(baseline)
        hybrid_hits = sum(hybrid)
        baseline_rank = next((index + 1 for index, value in enumerate(baseline) if value), None)
        hybrid_rank = next((index + 1 for index, value in enumerate(hybrid) if value), None)
        pool_hits = sum(document_id in relevant for document_id in retrieved)
        rows.append({
            "id": case["id"],
            "query": case["query"],
            "relevant_documents": len(relevant),
            f"baseline_hits@{k}": baseline_hits,
            f"baseline_recall@{k}": baseline_hits / len(relevant) if relevant else 0.0,
            "baseline_reciprocal_rank": 1.0 / baseline_rank if baseline_rank else 0.0,
            f"baseline_ndcg@{k}": _ndcg(baseline, len(relevant), k),
            f"hybrid_hits@{k}": hybrid_hits,
            f"hybrid_recall@{k}": hybrid_hits / len(relevant) if relevant else 0.0,
            "hybrid_reciprocal_rank": 1.0 / hybrid_rank if hybrid_rank else 0.0,
            f"hybrid_ndcg@{k}": _ndcg(hybrid, len(relevant), k),
            f"candidate_recall@{candidate_pool}": pool_hits / len(relevant) if relevant else 0.0,
            "first_relevant_rank_before_filter": next(
                (index + 1 for index, document_id in enumerate(retrieved) if document_id in relevant), None
            ),
            "valid_case": bool(relevant),
        })
    valid = [row for row in rows if row["valid_case"]]
    report = {
        "evaluation_model": MODEL_NAME,
        "collection": COLLECTION_NAME,
        "k": k,
        "candidate_pool": candidate_pool,
        "case_count": len(rows),
        "valid_case_count": len(valid),
        "baseline_metrics": _aggregate(rows, "baseline", k),
        "hybrid_metrics": _aggregate(rows, "hybrid", k),
        f"mean_candidate_recall@{candidate_pool}": (
            sum(row[f"candidate_recall@{candidate_pool}"] for row in valid) / len(valid) if valid else 0.0
        ),
        "cases": rows,
        "gold_definition": "연령군(공통 허용)·목표 부위·운동 유형·장소가 일치하는 video_content 문서",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--chroma", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--candidate-pool", type=int, default=100)
    args = parser.parse_args()
    report = evaluate(
        args.database, args.chroma, args.cases, args.output, args.k, args.candidate_pool
    )
    print(json.dumps({
        "baseline": report["baseline_metrics"],
        "hybrid": report["hybrid_metrics"],
        f"mean_candidate_recall@{args.candidate_pool}": report[f"mean_candidate_recall@{args.candidate_pool}"],
    }, ensure_ascii=False, indent=2))
    if report["valid_case_count"] != report["case_count"]:
        raise SystemExit("관련 문서가 없는 평가 케이스가 있습니다.")


if __name__ == "__main__":
    main()
