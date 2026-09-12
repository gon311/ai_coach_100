"""센터 원시기록 기반 백분위 규준 테이블의 안전한 저장·조회 기반."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


RESULT_LABEL = "보유 센터 측정 원시기록 기준 상위 비율"
NORM_VERSION = "center-raw-v1"
MIN_VALID_SAMPLE = 200

# 1차 화면 입력 대상. extension 종목은 DB 카탈로그에만 보관한다.
ACTIVE_MEASURE_CODES = {
    "FLEX_SIT_REACH", "MUSC_END_SITUP", "POWER_LONGJUMP",
    "LOWER_CHAIRSTAND", "CARDIO_2MINSTEP", "AGILITY_3M",
}

# source_field는 공식 API/원본 사전으로 검증된 뒤에만 채운다.
# 추정한 item_f 번호로 백분위를 계산하지 않도록 빈 값과 상태를 함께 보관한다.
MEASURE_CATALOG: tuple[dict[str, str], ...] = (
    {"code": "FLEX_SIT_REACH", "name": "앉아 윗몸 앞으로 굽히기", "unit": "cm", "direction": "higher_is_better", "age_scope": "유소년·청소년·성인·어르신", "release": "primary"},
    {"code": "MUSC_END_SITUP", "name": "교차 윗몸 일으키기", "unit": "회", "direction": "higher_is_better", "age_scope": "성인", "release": "primary"},
    {"code": "POWER_LONGJUMP", "name": "제자리 멀리뛰기", "unit": "cm", "direction": "higher_is_better", "age_scope": "유소년·청소년·성인", "release": "primary"},
    {"code": "LOWER_CHAIRSTAND", "name": "의자에 앉았다 일어서기", "unit": "회", "direction": "higher_is_better", "age_scope": "어르신", "release": "primary"},
    {"code": "CARDIO_2MINSTEP", "name": "2분 제자리걷기", "unit": "회", "direction": "higher_is_better", "age_scope": "어르신", "release": "primary"},
    {"code": "AGILITY_3M", "name": "3m 표적 돌아오기", "unit": "초", "direction": "lower_is_better", "age_scope": "어르신", "release": "primary"},
    {"code": "GRIP_RELATIVE", "name": "상대악력", "unit": "%", "direction": "higher_is_better", "age_scope": "성인·어르신", "release": "optional"},
    {"code": "GRIP_ABSOLUTE", "name": "절대악력", "unit": "kg", "direction": "higher_is_better", "age_scope": "성인·어르신", "release": "optional"},
    {"code": "CARDIO_20M_SHUTTLE", "name": "왕복오래달리기", "unit": "회", "direction": "higher_is_better", "age_scope": "성인", "release": "expansion"},
    {"code": "CARDIO_6MIN_WALK", "name": "6분걷기", "unit": "m", "direction": "higher_is_better", "age_scope": "어르신", "release": "expansion"},
    {"code": "AGILITY_10M_SHUTTLE", "name": "10m 왕복달리기", "unit": "초", "direction": "lower_is_better", "age_scope": "성인", "release": "expansion"},
    {"code": "REACTION_TIME", "name": "반응시간", "unit": "초", "direction": "lower_is_better", "age_scope": "성인", "release": "expansion"},
    {"code": "FIGURE_8_WALK", "name": "8자보행", "unit": "초", "direction": "lower_is_better", "age_scope": "어르신", "release": "expansion"},
)


def ensure_percentile_database(path: Path) -> None:
    """항상 동일한 카탈로그와 비어 있는 규준 셀을 갖는 SQLite DB를 만든다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS percentile_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS measure_catalog (
                measure_code TEXT PRIMARY KEY,
                measure_name TEXT NOT NULL,
                unit TEXT NOT NULL,
                direction TEXT NOT NULL CHECK(direction IN ('higher_is_better', 'lower_is_better')),
                age_scope TEXT NOT NULL,
                release_stage TEXT NOT NULL CHECK(release_stage IN ('primary', 'optional', 'expansion')),
                source_field TEXT,
                mapping_status TEXT NOT NULL CHECK(mapping_status IN ('mapping_unverified', 'ready')),
                mapping_provenance TEXT
            );
            CREATE TABLE IF NOT EXISTS percentile_norms (
                norm_version TEXT NOT NULL,
                measure_code TEXT NOT NULL REFERENCES measure_catalog(measure_code),
                sex TEXT NOT NULL,
                age_band TEXT NOT NULL,
                score_value REAL NOT NULL,
                percentile REAL NOT NULL CHECK(percentile >= 0 AND percentile <= 100),
                n_valid INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ready', 'insufficient_sample')),
                source_period TEXT NOT NULL,
                PRIMARY KEY(norm_version, measure_code, sex, age_band, score_value)
            );
            CREATE INDEX IF NOT EXISTS idx_percentile_norms_lookup
                ON percentile_norms(measure_code, sex, age_band, score_value);
            """
        )
        norm_row_count = int(
            connection.execute("SELECT count(*) FROM percentile_norms").fetchone()[0]
        )
        calculation_status = (
            "1차 공개 항목 규준 산출 완료"
            if norm_row_count > 0
            else "공식 필드 매핑 확인 전: 결과 미산출"
        )
        connection.executemany(
            """
            INSERT INTO measure_catalog (
                measure_code, measure_name, unit, direction, age_scope, release_stage,
                source_field, mapping_status, mapping_provenance
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'mapping_unverified', NULL)
            ON CONFLICT(measure_code) DO UPDATE SET
                measure_name=excluded.measure_name,
                unit=excluded.unit,
                direction=excluded.direction,
                age_scope=excluded.age_scope,
                release_stage=excluded.release_stage
            WHERE measure_catalog.measure_name != excluded.measure_name
               OR measure_catalog.unit != excluded.unit
               OR measure_catalog.direction != excluded.direction
               OR measure_catalog.age_scope != excluded.age_scope
               OR measure_catalog.release_stage != excluded.release_stage
            """,
            [
                (item["code"], item["name"], item["unit"], item["direction"], item["age_scope"], item["release"])
                for item in MEASURE_CATALOG
            ],
        )
        connection.commit()
        connection.executemany(
            "INSERT INTO percentile_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE percentile_meta.value != excluded.value",
            [
                ("norm_version", NORM_VERSION),
                ("result_label", RESULT_LABEL),
                ("comparison_source", "국민체력100 센터 측정 원시기록"),
                ("minimum_valid_sample", str(MIN_VALID_SAMPLE)),
                ("calculation_status", calculation_status),
                ("norm_row_count", str(norm_row_count)),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def status(path: Path) -> dict[str, Any]:
    ensure_percentile_database(path)
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT measure_code, measure_name, unit, direction, age_scope, release_stage, source_field, mapping_status FROM measure_catalog ORDER BY rowid"
        ).fetchall()
        norm_count = int(connection.execute("SELECT count(*) FROM percentile_norms").fetchone()[0])
    finally:
        connection.close()
    measures = [
        {
            "code": row[0], "name": row[1], "unit": row[2], "direction": row[3],
            "age_scope": row[4], "stage": row[5], "source_field": row[6], "status": row[7],
        }
        for row in rows
    ]
    return {
        "label": RESULT_LABEL,
        "input_label": "홈체력측정 입력값",
        "comparison_source": "국민체력100 센터 측정 원시기록",
        "norm_version": NORM_VERSION,
        "minimum_valid_sample": MIN_VALID_SAMPLE,
        "norm_row_count": norm_count,
        "measures": measures,
    }


def age_band(age: int) -> str:
    if age < 11:
        raise ValueError("현재 홈 체력측정 상위 비율은 유소년(만 11세 이상)·청소년·성인·어르신 항목만 지원합니다.")
    if age <= 12:
        return "11-12"
    if age <= 14:
        return "13-14"
    if age <= 18:
        return "15-18"
    if age >= 85:
        return "85+"
    lower = (age // 5) * 5
    return f"{lower}-{lower + 4}"


def available_input_measures(path: Path, age: int) -> list[dict[str, Any]]:
    report = status(path)
    band = age_band(age)
    age_group = "유소년" if age < 13 else "청소년" if age < 19 else "성인" if age < 65 else "어르신"
    return [
        item for item in report["measures"]
        if item["code"] in ACTIVE_MEASURE_CODES
        and age_group in item["age_scope"]
        and item["status"] == "ready"
        and item["source_field"]
        and band
    ]


def lookup_percentiles(
    path: Path, age: int, sex: str, measurements: dict[str, float],
) -> list[dict[str, Any]]:
    """사전 계산된 성별·5세 연령대별 규준값으로 홈 입력을 비교한다."""
    band = age_band(age)
    normalized_sex = str(sex or "").upper()
    if normalized_sex not in {"M", "F"}:
        raise ValueError("성별은 M 또는 F여야 합니다.")
    catalog = {item["code"]: item for item in available_input_measures(path, age)}
    results: list[dict[str, Any]] = []
    connection = sqlite3.connect(path)
    try:
        for code, raw_value in measurements.items():
            item = catalog.get(code)
            if item is None:
                continue
            value = float(raw_value)
            row = connection.execute(
                """
                SELECT score_value, percentile, n_valid, status
                FROM percentile_norms
                WHERE norm_version=? AND measure_code=? AND sex=? AND age_band=?
                ORDER BY ABS(score_value - ?) ASC, score_value ASC LIMIT 1
                """,
                (NORM_VERSION, code, normalized_sex, band, value),
            ).fetchone()
            if not row or row[3] != "ready":
                results.append({**item, "input_value": value, "available": False})
                continue
            percentile = round(float(row[1]), 1)
            results.append({
                **item,
                "input_value": value,
                "reference_score": float(row[0]),
                # 내부 백분위는 큰 값이 좋은 기록이다. 화면에는 사용자가
                # 이해하기 쉬운 '상위 n%'로만 표시하므로 반대 방향 값을 함께 준다.
                "percentile": percentile,
                "top_percent": round(100.0 - percentile, 1),
                "sample_size": int(row[2]),
                "age_band": band,
                "available": True,
            })
    finally:
        connection.close()
    return results
