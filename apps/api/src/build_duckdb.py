from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import duckdb


EXPECTED_FOLDERS = {
    "video_content": "국민체력100 동영상 정보",
    "fitness_measurements": "국민체력측정결과",
    "center_statistics": "센터별 통계정보",
    "disability_prescriptions": "장애인 체력 측정별 운동처방 데이터",
    "general_prescriptions": "체력 측정별 운동처방 데이터",
    "center_measurements": "체력인증센터 측정건수",
}


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def file_glob(root: Path, folder: str, pattern: str) -> str:
    return sql_path(root / folder / pattern)


def create_csv_table(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    pattern: str,
) -> None:
    connection.execute(
        f"""
        CREATE TABLE {table} AS
        SELECT
            * EXCLUDE (filename),
            regexp_extract(filename, '[^/\\\\]+$', 0) AS source_file
        FROM read_csv_auto(
            '{pattern}',
            header = true,
            all_varchar = true,
            union_by_name = true,
            filename = true,
            null_padding = true
        )
        """
    )


def create_struct_array_table(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    pattern: str,
) -> None:
    connection.execute(
        f"""
        CREATE TABLE {table} AS
        SELECT
            item.*,
            regexp_extract(src.filename, '[^/\\\\]+$', 0) AS source_file,
            src.name AS source_dataset_name
        FROM read_json_auto(
            '{pattern}',
            union_by_name = true,
            filename = true
        ) AS src,
        UNNEST(src.items) AS expanded(item)
        """
    )


def build(source_root: Path, target: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    target = target.resolve()
    missing = [folder for folder in EXPECTED_FOLDERS.values() if not (source_root / folder).is_dir()]
    if missing:
        raise FileNotFoundError(f"원본 데이터 폴더 누락: {missing}")

    target.parent.mkdir(parents=True, exist_ok=True)
    building = target.with_suffix(target.suffix + ".building")
    if building.exists():
        building.unlink()

    print(f"[DuckDB] 원본: {source_root}", flush=True)
    print(f"[DuckDB] 생성: {target}", flush=True)
    connection = duckdb.connect(str(building))
    connection.execute("PRAGMA disable_progress_bar")
    connection.execute(f"SET threads = {max(1, min(8, os.cpu_count() or 4))}")
    connection.execute("SET preserve_insertion_order = false")

    try:
        print("[1/6] 일반 운동처방 CSV 적재", flush=True)
        create_csv_table(
            connection,
            "general_prescriptions",
            file_glob(source_root, EXPECTED_FOLDERS["general_prescriptions"], "*.csv"),
        )

        print("[2/6] 장애인 운동처방 CSV 적재", flush=True)
        create_csv_table(
            connection,
            "disability_prescriptions",
            file_glob(source_root, EXPECTED_FOLDERS["disability_prescriptions"], "*.csv"),
        )

        print("[3/6] 센터별 통계 CSV 적재", flush=True)
        create_csv_table(
            connection,
            "center_statistics",
            file_glob(source_root, EXPECTED_FOLDERS["center_statistics"], "*.csv"),
        )

        print("[4/6] 국민체력측정결과 대용량 JSON 적재", flush=True)
        measurement_json = file_glob(
            source_root,
            EXPECTED_FOLDERS["fitness_measurements"],
            "*.json",
        )
        connection.execute(
            f"""
            CREATE TABLE fitness_measurements AS
            SELECT
                * EXCLUDE (filename),
                regexp_extract(filename, '[^/\\\\]+$', 0) AS source_file
            FROM read_json_auto(
                '{measurement_json}',
                format = 'array',
                union_by_name = true,
                filename = true
            )
            """
        )

        print("[5/6] 동영상 콘텐츠 JSON 적재", flush=True)
        create_struct_array_table(
            connection,
            "video_content",
            file_glob(source_root, EXPECTED_FOLDERS["video_content"], "*.json"),
        )

        print("[6/6] 체력인증센터 측정건수 JSON 적재", flush=True)
        create_struct_array_table(
            connection,
            "center_measurements",
            file_glob(source_root, EXPECTED_FOLDERS["center_measurements"], "*.json"),
        )

        print("[DuckDB] 분석용 형변환 뷰 생성", flush=True)
        connection.execute(
            """
            CREATE VIEW general_prescriptions_analysis AS
            SELECT *,
                   try_cast(MESURE_AGE_CO AS INTEGER) AS age,
                   try_strptime(MESURE_DE, '%Y%m%d')::DATE AS measurement_date,
                   upper(SEXDSTN_FLAG_CD) AS sex
            FROM general_prescriptions;

            CREATE VIEW disability_prescriptions_analysis AS
            SELECT *,
                   try_cast(MESURE_AGE_CO AS INTEGER) AS age,
                   try_strptime(MESURE_DE, '%Y%m%d')::DATE AS measurement_date,
                   upper(SEXDSTN_FLAG_CD) AS sex
            FROM disability_prescriptions;

            CREATE VIEW fitness_measurements_analysis AS
            SELECT *,
                   try_cast(age_degree AS INTEGER) AS age,
                   try_cast(age_class AS INTEGER) AS age_class_numeric,
                   try_strptime(test_ym, '%Y%m')::DATE AS test_month,
                   upper(test_sex) AS sex
            FROM fitness_measurements;

            CREATE VIEW center_measurements_analysis AS
            SELECT *,
                   try_strptime(test_ym, '%Y%m')::DATE AS test_month,
                   try_cast(test_cnt AS BIGINT) AS measurement_count
            FROM center_measurements;

            CREATE VIEW center_statistics_analysis AS
            SELECT *,
                   try_cast(MESURE_YEAR AS INTEGER) AS measurement_year,
                   try_cast(ALL_MESURE_CAS_CO AS BIGINT) AS total_measurements,
                   try_cast(MALE_MBER_CO AS BIGINT) AS male_members,
                   try_cast(FEMALE_MBER_CO AS BIGINT) AS female_members
            FROM center_statistics;
            """
        )

        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        connection.execute(
            """
            CREATE TABLE build_info(
                key VARCHAR PRIMARY KEY,
                value VARCHAR NOT NULL
            )
            """
        )
        build_info = {
            "bundle_version": "2.0.0",
            "generated_at": generated_at,
            "source_root": str(source_root),
            "duckdb_version": duckdb.__version__,
            "description": "국민체력100 6개 원본 폴더 통계 분석용 통합 DB",
        }
        connection.executemany("INSERT INTO build_info VALUES (?, ?)", build_info.items())

        row_counts: dict[str, int] = {}
        for table in EXPECTED_FOLDERS:
            count = int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            row_counts[table] = count
            print(f"  - {table}: {count:,}행", flush=True)

        connection.execute(
            """
            CREATE TABLE dataset_catalog(
                dataset VARCHAR PRIMARY KEY,
                source_folder VARCHAR NOT NULL,
                row_count BIGINT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO dataset_catalog VALUES (?, ?, ?)",
            [(name, EXPECTED_FOLDERS[name], count) for name, count in row_counts.items()],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    if target.exists():
        target.unlink()
    building.replace(target)
    size_bytes = target.stat().st_size
    result = {
        "database": str(target),
        "size_bytes": size_bytes,
        "row_counts": row_counts,
        "total_rows": sum(row_counts.values()),
    }
    print("[DuckDB] 완료", json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    build(args.source_root, args.target)


if __name__ == "__main__":
    main()
