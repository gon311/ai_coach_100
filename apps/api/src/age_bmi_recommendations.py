"""국민연령별추천운동정보의 조건 조회와 국내 성인 BMI 분류.

CSV는 설명형 RAG 문서가 아니라 정확한 조건·순위 조회용 원문이다. 따라서
벡터 검색에 넣지 않고 별도 SQLite 테이블로 유지한다.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


SOURCE_DATASET = "국민연령별추천운동정보"
SOURCE_FILE = "KS_MRFN_AGE_ACCTO_RECOMMEND_SPORTS_INFO_202607.csv"
BMI_SOURCE_TITLE = "질병관리청 국가건강정보포털 · 대한비만학회 기준(2022)"
BMI_SOURCE_URL = (
    "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/"
    "gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=6774"
)
BMI_SOURCE_NOTE = "성인 BMI 분류에만 사용하며, 청소년·유소년에는 적용하지 않습니다."
REQUIRED_COLUMNS = (
    "AGRDE_FLAG_NM", "BMI_IDEX_GRAD_NM", "MBER_SEXDSTN_FLAG_CD",
    "COAW_FLAG_NM", "SPORTS_STEP_NM", "FLAG_ACCTO_RECOMEND_MVM_RANK_CO",
    "RECOMEND_MVM_NM",
)
AGE_BANDS = ("10대", "20대", "30대", "40대", "50대", "60대", "70대 이상")
BMI_GRADES = ("저체중", "정상", "비만전단계비만", "1단계비만", "2단계비만", "3단계비만")
AWARD_GROUPS = ("1등급", "2등급", "3등급", "참가증")
SPORTS_STEPS = ("준비운동", "본운동", "마무리운동")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def adult_bmi_profile(
    age: int | None, height_cm: float | None, weight_kg: float | None,
) -> dict[str, Any]:
    """국내 성인 기준을 적용할 수 있을 때만 BMI와 원문 등급을 계산한다."""
    if age is None or height_cm is None or weight_kg is None:
        return {
            "available": False,
            "reason": "BMI 계산에는 만 나이, 키, 체중이 모두 필요합니다.",
        }
    if age < 20:
        return {
            "available": False,
            "reason": "만 20세 미만은 성인 BMI 고정 구간으로 자동 분류하지 않습니다.",
        }
    height_m = float(height_cm) / 100.0
    if height_m <= 0 or float(weight_kg) <= 0:
        return {"available": False, "reason": "키와 체중은 0보다 커야 합니다."}
    bmi = float(weight_kg) / (height_m * height_m)
    if bmi < 18.5:
        grade = "저체중"
    elif bmi < 23.0:
        grade = "정상"
    elif bmi < 25.0:
        grade = "비만전단계비만"
    elif bmi < 30.0:
        grade = "1단계비만"
    elif bmi < 35.0:
        grade = "2단계비만"
    else:
        grade = "3단계비만"
    if age < 30:
        age_band = "20대"
    elif age < 40:
        age_band = "30대"
    elif age < 50:
        age_band = "40대"
    elif age < 60:
        age_band = "50대"
    elif age < 70:
        age_band = "60대"
    else:
        age_band = "70대 이상"
    return {
        "available": True,
        "bmi": round(bmi, 1),
        "bmi_grade": grade,
        "age_band": age_band,
        "source_title": BMI_SOURCE_TITLE,
        "source_url": BMI_SOURCE_URL,
        "source_note": BMI_SOURCE_NOTE,
    }


def build_rule_database(source_csv: Path, database: Path) -> dict[str, Any]:
    """검증한 원문 CSV를 조건 조회 전용 SQLite DB로 재구축한다."""
    source_csv = Path(source_csv)
    database = Path(database)
    with source_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or tuple(rows[0].keys()) != REQUIRED_COLUMNS:
        raise ValueError("국민연령별추천운동정보 CSV 컬럼이 원본 정의와 다릅니다.")
    normalized: list[tuple[str, str, str, str, str, int, str, int]] = []
    for row_number, row in enumerate(rows, start=2):
        values = tuple(str(row[column] or "").strip() for column in REQUIRED_COLUMNS)
        if not all(values):
            raise ValueError(f"원본 {row_number}행에 빈 필수값이 있습니다.")
        age_band, bmi_grade, sex, award_group, sports_step, rank_raw, exercise_name = values
        try:
            rank = int(rank_raw)
        except ValueError as exc:
            raise ValueError(f"원본 {row_number}행의 추천 순위가 정수가 아닙니다.") from exc
        if age_band not in AGE_BANDS or bmi_grade not in BMI_GRADES or sex not in {"M", "F"}:
            raise ValueError(f"원본 {row_number}행의 연령대·BMI 등급·성별 값이 허용 범위를 벗어났습니다.")
        if award_group not in AWARD_GROUPS or sports_step not in SPORTS_STEPS or rank not in range(1, 6):
            raise ValueError(f"원본 {row_number}행의 상장·운동 단계·순위 값이 허용 범위를 벗어났습니다.")
        normalized.append((age_band, bmi_grade, sex, award_group, sports_step, rank, exercise_name, row_number))
    expected_count = len(AGE_BANDS) * len(BMI_GRADES) * 2 * len(AWARD_GROUPS) * len(SPORTS_STEPS) * 5
    if len(normalized) != expected_count:
        raise ValueError(f"원문 행 수가 완전 조건표 크기와 다릅니다: {len(normalized)} != {expected_count}")
    keys = [item[:6] for item in normalized]
    if len(set(keys)) != len(keys):
        raise ValueError("원문 조건·순위 복합키가 중복됩니다.")

    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("DROP TABLE IF EXISTS recommendation_rules")
        connection.execute("DROP TABLE IF EXISTS rule_meta")
        connection.execute(
            "CREATE TABLE rule_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            """CREATE TABLE recommendation_rules(
                age_band TEXT NOT NULL,
                bmi_grade TEXT NOT NULL,
                sex TEXT NOT NULL,
                award_group TEXT NOT NULL,
                sports_step TEXT NOT NULL,
                rank INTEGER NOT NULL,
                exercise_name TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                PRIMARY KEY(age_band,bmi_grade,sex,award_group,sports_step,rank)
            )"""
        )
        connection.executemany(
            "INSERT INTO recommendation_rules VALUES (?,?,?,?,?,?,?,?)", normalized
        )
        connection.execute(
            "CREATE INDEX idx_recommendation_rules_lookup ON recommendation_rules("
            "age_band,bmi_grade,sex,award_group,sports_step,rank)"
        )
        meta = {
            "dataset": SOURCE_DATASET,
            "source_file": source_csv.name,
            "source_sha256": _sha256(source_csv),
            "row_count": str(len(normalized)),
            "bmi_source_title": BMI_SOURCE_TITLE,
            "bmi_source_url": BMI_SOURCE_URL,
            "bmi_source_note": BMI_SOURCE_NOTE,
        }
        connection.executemany(
            "INSERT INTO rule_meta VALUES (?,?)", sorted(meta.items())
        )
    return {"row_count": len(normalized), "source_sha256": _sha256(source_csv)}


def rule_status(database: Path) -> dict[str, Any]:
    database = Path(database)
    if not database.is_file():
        return {"available": False, "reason": "국민연령별 추천운동 규칙 DB가 없습니다."}
    try:
        with sqlite3.connect(database) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            meta = dict(connection.execute("SELECT key,value FROM rule_meta"))
            row_count = int(connection.execute("SELECT count(*) FROM recommendation_rules").fetchone()[0])
    except sqlite3.DatabaseError as exc:
        return {"available": False, "reason": f"규칙 DB를 읽을 수 없습니다: {exc}"}
    expected_count = len(AGE_BANDS) * len(BMI_GRADES) * 2 * len(AWARD_GROUPS) * len(SPORTS_STEPS) * 5
    return {
        "available": integrity == "ok" and row_count == expected_count,
        "integrity": integrity,
        "row_count": row_count,
        "expected_row_count": expected_count,
        "award_groups": list(AWARD_GROUPS),
        "sports_steps": list(SPORTS_STEPS),
        "meta": meta,
    }


def lookup_rules(
    database: Path,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """성인 BMI와 사용자가 직접 고른 원문 상장 구분으로만 순위를 조회한다."""
    bmi = adult_bmi_profile(
        profile.get("age"), profile.get("height_cm"), profile.get("weight_kg"),
    )
    result: dict[str, Any] = {
        "bmi": bmi,
        "available": False,
        "rules": [],
        "source": {
            "dataset": SOURCE_DATASET,
            "source_file": SOURCE_FILE,
            "bmi_source_title": BMI_SOURCE_TITLE,
            "bmi_source_url": BMI_SOURCE_URL,
            "bmi_source_note": BMI_SOURCE_NOTE,
        },
    }
    if not bmi.get("available"):
        result["reason"] = str(bmi.get("reason") or "BMI 분류를 계산할 수 없습니다.")
        return result
    award_group = str(profile.get("award_group") or "").strip()
    if award_group not in AWARD_GROUPS:
        result["reason"] = "원문 상장 구분을 직접 선택하면 추천운동 순위를 조회할 수 있습니다."
        return result
    sex = str(profile.get("sex") or "").strip().upper()
    if sex not in {"M", "F"}:
        result["reason"] = "성별을 선택하면 추천운동 순위를 조회할 수 있습니다."
        return result
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT sports_step,rank,exercise_name,source_row FROM recommendation_rules "
            "WHERE age_band=? AND bmi_grade=? AND sex=? AND award_group=? "
            "ORDER BY CASE sports_step WHEN '준비운동' THEN 1 WHEN '본운동' THEN 2 ELSE 3 END,rank",
            (bmi["age_band"], bmi["bmi_grade"], sex, award_group),
        ).fetchall()
        meta = dict(connection.execute("SELECT key,value FROM rule_meta"))
    result.update({
        "available": len(rows) == len(SPORTS_STEPS) * 5,
        "reason": "" if len(rows) == len(SPORTS_STEPS) * 5 else "선택 조건의 완전한 추천 순위표를 찾지 못했습니다.",
        "age_band": bmi["age_band"], "bmi_grade": bmi["bmi_grade"],
        "sex": sex, "award_group": award_group,
        "rules": [
            {"sports_step": row[0], "rank": row[1], "exercise_name": row[2], "source_row": row[3]}
            for row in rows
        ],
        "source": {
            "dataset": meta.get("dataset", SOURCE_DATASET),
            "source_file": meta.get("source_file", SOURCE_FILE),
            "source_sha256": meta.get("source_sha256", ""),
            "bmi_source_title": meta.get("bmi_source_title", BMI_SOURCE_TITLE),
            "bmi_source_url": meta.get("bmi_source_url", BMI_SOURCE_URL),
            "bmi_source_note": meta.get("bmi_source_note", BMI_SOURCE_NOTE),
        },
    })
    return result


def grouped_rules(rules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = {step: [] for step in SPORTS_STEPS}
    for rule in rules:
        grouped.setdefault(str(rule["sports_step"]), []).append(dict(rule))
    return [
        {"sports_step": step, "recommendations": sorted(grouped.get(step, []), key=lambda item: int(item["rank"]))}
        for step in SPORTS_STEPS
    ]
