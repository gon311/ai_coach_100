"""센터 원시기록에서 홈 입력 비교용 백분위 규준 SQLite를 1회 생성한다."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import duckdb

from center_percentile import MIN_VALID_SAMPLE, NORM_VERSION, ensure_percentile_database


# 측정값 단위·연령군·분포를 원시기록과 대조해 확정한 1차 입력 항목이다.
SOURCE_MAPPINGS = (
    ("FLEX_SIT_REACH", "item_f012", "higher_is_better", 11, 120, -50.0, 80.0),
    ("MUSC_END_SITUP", "item_f019", "higher_is_better", 19, 64, 0.0, 150.0),
    ("POWER_LONGJUMP", "item_f022", "higher_is_better", 11, 64, 50.0, 400.0),
    ("LOWER_CHAIRSTAND", "item_f023", "higher_is_better", 65, 120, 0.0, 100.0),
    ("CARDIO_2MINSTEP", "item_f025", "higher_is_better", 65, 120, 0.0, 300.0),
    ("AGILITY_3M", "item_f026", "lower_is_better", 65, 120, 1.0, 60.0),
)


def _age_band_sql() -> str:
    return "CASE WHEN age BETWEEN 11 AND 12 THEN '11-12' WHEN age BETWEEN 13 AND 14 THEN '13-14' WHEN age BETWEEN 15 AND 18 THEN '15-18' WHEN age >= 85 THEN '85+' ELSE concat(CAST(floor(age / 5) * 5 AS INTEGER), '-', CAST(floor(age / 5) * 5 + 4 AS INTEGER)) END"


def build(source_database: Path, target_database: Path) -> int:
    ensure_percentile_database(target_database)
    with sqlite3.connect(target_database) as target:
        target.execute("DELETE FROM percentile_norms WHERE norm_version=?", (NORM_VERSION,))
        target.execute("UPDATE measure_catalog SET source_field=NULL, mapping_status='mapping_unverified', mapping_provenance=NULL")
        target.commit()

    source = duckdb.connect(str(source_database), read_only=True)
    target = sqlite3.connect(target_database)
    inserted = 0
    try:
        for code, field, direction, min_age, max_age, minimum, maximum in SOURCE_MAPPINGS:
            value = f"try_cast({field} AS DOUBLE)"
            age_band = _age_band_sql()
            order = "ASC" if direction == "higher_is_better" else "DESC"
            sql = f"""
                WITH valid AS (
                    SELECT sex, {age_band} AS age_band, {value} AS score_value
                    FROM fitness_measurements_analysis
                    WHERE age BETWEEN {min_age} AND {max_age}
                      AND (
                          age >= 19
                          OR (age BETWEEN 13 AND 18 AND age_gbn = '청소년')
                          OR (age BETWEEN 11 AND 12 AND age_gbn = '유소년')
                      )
                      AND sex IN ('M', 'F')
                      AND {value} BETWEEN {minimum} AND {maximum}
                ), frequency AS (
                    SELECT sex, age_band, score_value, count(*)::BIGINT AS n_at_score
                    FROM valid GROUP BY sex, age_band, score_value
                ), ranked AS (
                    SELECT sex, age_band, score_value, n_at_score,
                           sum(n_at_score) OVER (PARTITION BY sex, age_band) AS n_valid,
                           sum(n_at_score) OVER (PARTITION BY sex, age_band ORDER BY score_value {order} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative
                    FROM frequency
                )
                SELECT sex, age_band, score_value,
                       100.0 * (cumulative - (n_at_score * 0.5)) / n_valid AS percentile,
                       n_valid,
                       CASE WHEN n_valid >= {MIN_VALID_SAMPLE} THEN 'ready' ELSE 'insufficient_sample' END AS status
                FROM ranked
            """
            rows = source.execute(sql).fetchall()
            target.executemany(
                """INSERT INTO percentile_norms(
                    norm_version, measure_code, sex, age_band, score_value, percentile,
                    n_valid, status, source_period
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(NORM_VERSION, code, *row, "2011-01~2026-08") for row in rows],
            )
            target.execute(
                """UPDATE measure_catalog
                   SET source_field=?, mapping_status='ready',
                       mapping_provenance='보유 센터 원시기록의 측정 항목 필드·단위·연령군을 대조한 1차 규준 매핑'
                   WHERE measure_code=?""",
                (field, code),
            )
            inserted += len(rows)
        target.commit()
        target.executemany(
            "INSERT INTO percentile_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [
                ("calculation_status", "1차 공개 항목 규준 산출 완료"),
                ("norm_row_count", str(inserted)),
                ("source_period", "2011-01~2026-08"),
            ],
        )
        target.commit()
    finally:
        target.close()
        source.close()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    count = build(args.source, args.target)
    print(f"백분위 규준값 {count:,}개 생성 완료: {args.target}")


if __name__ == "__main__":
    main()
