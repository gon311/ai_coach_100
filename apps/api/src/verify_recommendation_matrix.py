"""실행 중인 로컬 서버의 일반/장애/건강 추천 분리 계약을 검증한다."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from urllib.request import Request, urlopen

from rag_data_roles import health_categories


BASE = {
    "selection_mode": True,
    "age": 30,
    "age_group": "성인",
    "sex": "M",
    "height_cm": 170,
    "weight_kg": 65,
    "fitness_level": "초급",
    "location": "실내",
    "pain_area": "없음",
    "pain_level": 0,
    "equipment": "없음",
    "available_time": "30분",
}


def post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=240) as response:
        return json.loads(response.read().decode("utf-8"))


def check_case(
    base_url: str, name: str, payload: dict, mode: str, expect_candidate: bool = True
) -> dict:
    response = post_json(f"{base_url.rstrip('/')}/api/coach", payload)
    retrieval = response["retrieval"]
    sources = response.get("sources", [])
    source_datasets = sorted({source.get("dataset") for source in sources})
    checks = {
        "status_ok": response.get("status") == "ok",
        "mode": retrieval.get("recommendation_mode") == mode,
        "candidate_expectation": (
            int(retrieval.get("screened_candidates") or 0) > 0
        ) == expect_candidate,
    }
    if mode == "disability":
        disability = payload["disability_type"]
        if expect_candidate:
            checks.update({
                "only_disability_dataset": bool(sources) and source_datasets == ["disability_prescription"],
                "exact_disability_in_every_source": bool(sources) and all(
                    f"장애유형: {disability}" in str(source.get("text") or "")
                    for source in sources
                ),
                "no_general_video": "영상 URL" not in response.get("exercise_details", {}),
            })
        else:
            checks.update({
                "no_substitute_exercise_sources": not sources,
                "no_general_video": not response.get("video_options"),
            })
    else:
        checks["no_disability_dataset"] = "disability_prescription" not in source_datasets
    if payload.get("health_information") not in {"", "없음", None}:
        condition = payload["health_information"]
        checks["health_not_separately_combined"] = not bool(
            retrieval.get("health_context_separated")
        )
        if expect_candidate:
            checks.update({
                "health_reference_found": bool(retrieval.get("health_reference_found")),
                "health_sources_present": bool(response.get("health_sources")),
                "health_in_every_recommendation_source": bool(sources) and all(
                    condition in health_categories(source.get("text") or "")
                    for source in sources
                ),
            })
    return {
        "name": name,
        "passed": all(checks.values()),
        "checks": checks,
        "mode": retrieval.get("recommendation_mode"),
        "screened_candidates": retrieval.get("screened_candidates"),
        "exercise": response.get("answer", {}).get("운동명"),
        "source_datasets": source_datasets,
        "health_source_datasets": sorted({
            source.get("dataset") for source in response.get("health_sources", [])
        }),
        "ignored_conditions": retrieval.get("ignored_conditions", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8501")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    cases = [
        (
            "general",
            {**BASE, "target_area": "가슴", "exercise_type": "스트레칭", "disability_type": "없음", "health_information": "없음"},
            "general",
        ),
        (
            "general_with_health",
            {
                **BASE, "target_area": "허리", "exercise_type": "근력",
                "fitness_level": "", "location": "", "equipment": "매트",
                "disability_type": "없음", "health_information": "허리 관련 질환",
            },
            "general",
        ),
        (
            "intellectual_disability",
            {**BASE, "target_area": "허리", "exercise_type": "유연성", "disability_type": "지적장애", "health_information": "없음"},
            "disability",
        ),
        (
            "intellectual_disability_with_health",
            {**BASE, "target_area": "허리", "exercise_type": "유연성", "disability_type": "지적장애", "health_information": "고혈압"},
            "disability",
            False,
        ),
    ]
    results = [check_case(args.base_url, *case) for case in cases]
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "passed": all(item["passed"] for item in results),
        "cases": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
