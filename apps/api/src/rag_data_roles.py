"""RAG 문서의 대상·역할·검색 가능 필드를 일관되게 분류한다.

원문을 수정하지 않고 파생 분류만 ``document_facets`` 표에 저장한다. 장애인
처방처럼 일반 영상과 필드 구성이 다른 자료를 같은 필터로 탈락시키지 않기 위한
런타임/DB 공용 규칙이다.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping


CLASSIFICATION_VERSION = "1.3.0"
# 화면 값은 원본에 실제 존재하는 건강 목적만 사용한다. 각 별칭은 원문 표현을
# 표준 선택값으로 묶기 위한 것이며, 의학적 동의어를 추정해 확장하지 않는다.
HEALTH_CATEGORIES = {
    "고혈압": (r"고혈압",),
    "당뇨": (r"당뇨(?:병)?",),
    "골다공증": (r"골다공증",),
    "관절염": (r"관절염",),
    "요통": (r"요통",),
    "치매": (r"치매",),
    "우울증": (r"우울증",),
    "인지노쇠": (r"인지\s*노쇠",),
    "낙상 예방": (r"낙상(?:을)?\s*예방",),
    "허리 관련 질환": (r"허리\s*관련\s*질환", r"허리\s*질환"),
    "무릎 관련 질환": (r"무릎\s*관련\s*질환", r"무릎\s*질환"),
    "어깨 관련 질환": (r"어깨\s*관련\s*질환", r"어깨\s*질환"),
}
HEALTH_TERMS = tuple(HEALTH_CATEGORIES)
HEALTH_CATEGORY_GROUPS = {
    "고혈압": "질환별 운동", "당뇨": "질환별 운동",
    "골다공증": "질환별 운동", "관절염": "질환별 운동",
    "요통": "질환별 운동", "치매": "질환별 운동",
    "우울증": "질환별 운동",
    "인지노쇠": "예방 목적 운동", "낙상 예방": "예방 목적 운동",
    "허리 관련 질환": "부위 질환 단계별 운동",
    "무릎 관련 질환": "부위 질환 단계별 운동",
    "어깨 관련 질환": "부위 질환 단계별 운동",
}
DATASET_ROLES = {
    "video_content": ("general", "exercise_instruction"),
    "general_prescription": ("general", "center_prescription_record"),
    "measurement_prescription": ("general", "measurement_prescription_note"),
    "disability_prescription": ("disability", "disability_prescription_record"),
}
BODY_PART_ALIASES = {
    "전신": "전신", "상체": "상체", "하체": "하체", "머리": "머리",
    "목": "목", "어깨": "어깨", "가슴": "가슴", "등": "등", "허리": "허리",
    "척추": "척추", "복부": "복부", "배": "복부", "코어": "복부",
    "골반": "골반", "엉덩이": "엉덩이", "고관절": "고관절",
    "팔": "팔", "위팔": "위팔", "아래팔": "아래팔", "팔꿈치": "팔꿈치",
    "손목": "손목", "손": "손", "허벅지": "허벅지", "넓적다리": "넓적다리",
    "대퇴": "허벅지", "무릎": "무릎", "종아리": "종아리",
    "발목": "발목", "발": "발",
}


def _title_body_parts(title: str) -> set[str]:
    """운동명에서 겹치는 신체 부위를 가장 긴 용어 기준으로 찾는다.

    단순 포함 검색은 ``손목``과 ``발목``을 ``목`` 운동으로, ``목적별``을
    목 운동으로 잘못 분류한다. 같은 위치에서 겹치면 손목·발목처럼 더 구체적인
    용어를 우선하고, 운동 부위가 아닌 대표적인 ``목`` 합성어는 제외한다.
    """
    candidates: list[tuple[int, int, str, str]] = []
    for term, normalized in BODY_PART_ALIASES.items():
        for match in re.finditer(re.escape(term), title):
            start, end = match.span()
            if term == "목" and title[end:end + 1] in {"적", "표", "록", "차", "봉"}:
                continue
            if term == "등" and title[end:end + 1] == "척":
                continue
            candidates.append((start, end, term, normalized))

    occupied: set[int] = set()
    found: set[str] = set()
    for start, end, _term, normalized in sorted(
        candidates, key=lambda item: (-(item[1] - item[0]), item[0])
    ):
        span = set(range(start, end))
        if span & occupied:
            continue
        occupied.update(span)
        found.add(normalized)
    return found
TYPE_PATTERNS = {
    "스트레칭": ("스트레칭", "늘리기", "이완"),
    "유연성": ("유연성", "스트레칭", "늘리기", "이완", "굽히기", "돌리기"),
    "근력": (
        "근력", "근육 강화", "강화", "스쿼트", "런지", "팔굽혀펴기",
        "윗몸일으키기", "복근", "밀기", "당기기", "들어올리기", "버티기",
    ),
    "유산소": ("유산소", "걷기", "달리기", "자전거", "트레드밀"),
    "균형": ("균형", "평형", "한발", "외발"),
    "민첩성": ("민첩", "사이드스텝", "반복옆뛰기"),
    "순발력": ("순발", "점프", "뛰기", "멀리뛰기"),
    "협응성": ("협응", "협응성"),
}
KNOWN_EQUIPMENT = (
    "덤벨", "바벨", "짐볼", "밴드", "튜빙", "케틀벨", "메디신볼", "스텝박스",
    "헬스기구", "머신", "트레드밀", "러닝머신", "고정식 자전거", "실내 자전거",
    "의자", "매트", "계단", "폼롤러", "품롤러", "테니스공", "보슈",
    "테이블", "물병", "물통", "봉",
)
GENERAL_FIELDS = {
    "age_group", "sex", "target_area", "exercise_type", "exercise_stage", "fitness_level",
    "location", "equipment", "health_information",
}
DISABILITY_FIELDS = {
    "age_group", "sex", "target_area", "exercise_type", "exercise_stage", "equipment",
    "disability_type",
}


def _values(text: str, label: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(rf"(?m)^{re.escape(label)}\s*:\s*([^\n]+)", text):
        found.update(
            value.strip() for value in re.split(r"\s*[/,|]\s*", match.group(1))
            if value.strip() and value.strip() not in {"정보 없음", "단계 미상"}
        )
    return found


def _difficulty(value: Any) -> set[str]:
    text = str(value or "").strip().replace(" ", "")
    if not text:
        return set()
    levels: set[str] = set()
    for part in re.split(r"[,/|]", text):
        if not part or part in {"정보없음", "단계미상"}:
            continue
        if part in {"초급", "중급", "고급"}:
            levels.add(part)
            continue
        numbers = [int(number) for number in re.findall(r"[1-5]", part)]
        if not numbers:
            levels.add(part)
            continue
        for number in range(min(numbers), max(numbers) + 1):
            levels.add("초급" if number <= 2 else "중급" if number == 3 else "고급")
    return levels


def _locations(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text or text in {"정보 없음", "일반"}:
        return set()
    return {part.strip() for part in re.split(r"\s*[/,|]\s*", text) if part.strip()}


def health_categories(text: Any) -> set[str]:
    """원문에 직접 표시된 건강 목적을 표준 선택값으로 반환한다."""
    source = str(text or "")
    return {
        category
        for category, patterns in HEALTH_CATEGORIES.items()
        if any(re.search(pattern, source) for pattern in patterns)
    }


def display_locations(equipment: Any, original: Any) -> set[str]:
    """사용자 지정 테스트 분류. 원문 장소를 수정하지 않는다."""
    tools = _locations(equipment) if isinstance(equipment, str) else set(equipment or [])
    tools -= {"없음", "맨몸", "무장비", "정보 없음"}
    places = _locations(original) if isinstance(original, str) else set(original or [])
    if tools & {"헬스기구", "헬스 기구", "머신"}:
        return {"헬스장"}
    if places - {"실내", "실외", "헬스장"}:
        return places  # 수영장 등 전용 장소를 일반 실내 운동으로 바꾸지 않는다.
    if not tools or tools & {"물병", "물통", "생수병", "페트병"}:
        return {"실내"}
    return places


def classify_document(
    dataset: str, title: str, content: str, metadata: Mapping[str, Any]
) -> dict[str, Any]:
    """원문 필드와 운동명에서만 파생한 검색 분류를 반환한다."""
    audience, source_role = DATASET_ROLES.get(dataset, ("reference", "reference"))
    title_text = str(metadata.get("exercise_name") or title or "")
    text = str(content or "")
    searchable = f"{title_text}\n{text}"

    target_areas = _values(text, "운동 부위")
    derived_fields: set[str] = set()
    # 일부 공식 영상은 운동명이 '허리 스트레칭'인데 운동 부위에는 골반·엉덩이만
    # 적힌 것처럼 제목과 상세 부위가 불완전하게 어긋난다. 사용자가 고른 부위를
    # 운동명 기준으로도 찾을 수 있도록 제목에서 확인된 부위를 원문 부위와 합친다.
    title_target_areas = _title_body_parts(title_text)
    if title_target_areas - target_areas:
        target_areas.update(title_target_areas)
        derived_fields.add("target_area:title")

    exercise_types = _values(text, "운동 유형") | _values(text, "체력요인")
    if not exercise_types:
        exercise_types = {
            label for label, terms in TYPE_PATTERNS.items()
            if any(term in title_text for term in terms)
        }
        if exercise_types:
            derived_fields.add("exercise_type:title")

    difficulty = _difficulty(metadata.get("difficulty"))
    difficulty |= _difficulty(next(iter(_values(text, "난이도")), ""))
    equipment = _values(text, "운동 도구") | _values(text, "필요 장비")
    equipment -= {"없음", "맨몸", "무장비"}
    if not equipment:
        equipment = {tool for tool in KNOWN_EQUIPMENT if tool in title_text}
        if equipment:
            derived_fields.add("equipment:title")
    # 처방 CSV의 MESURE_PLACE_FLAG_NM은 운동 장소가 아니라 측정 장소다.
    # 실제 운동 장소 필드가 있는 공식 영상 데이터에서만 장소를 분류한다.
    locations = (
        _locations(metadata.get("place")) | _values(text, "운동 장소")
        if dataset == "video_content" else set()
    )
    health_terms = health_categories(searchable)
    disability = str(metadata.get("disability_type") or "").strip()
    age = str(metadata.get("age_group") or "").strip()
    sex = str(metadata.get("sex") or "").strip().upper()

    return {
        "audience": audience,
        "source_role": source_role,
        "age_group": sorted({age} if age else set()),
        "sex": sorted({sex} if sex in {"M", "F"} else set()),
        "target_area": sorted(target_areas),
        "exercise_type": sorted(exercise_types),
        "fitness_level": sorted(difficulty),
        "location": sorted(locations),
        "equipment": sorted(equipment),
        "disability_type": sorted({disability} if disability else set()),
        "health_information": sorted(health_terms),
        "derived_fields": sorted(derived_fields),
        "applicable_fields": sorted(
            DISABILITY_FIELDS if audience == "disability" else GENERAL_FIELDS
        ),
    }


def has_facet_table(connection: sqlite3.Connection) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_facets'"
    ).fetchone() is not None


def rebuild_facets(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    try:
        integrity = connection.execute("PRAGMA quick_check(1)").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite 무결성 검사 실패: {integrity}")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE IF EXISTS document_facets_building")
        connection.execute(
            """
            CREATE TABLE document_facets_building(
                document_id TEXT PRIMARY KEY,
                audience TEXT NOT NULL,
                source_role TEXT NOT NULL,
                age_group_json TEXT NOT NULL,
                sex_json TEXT NOT NULL,
                target_area_json TEXT NOT NULL,
                exercise_type_json TEXT NOT NULL,
                fitness_level_json TEXT NOT NULL,
                location_json TEXT NOT NULL,
                equipment_json TEXT NOT NULL,
                disability_type_json TEXT NOT NULL,
                health_information_json TEXT NOT NULL,
                derived_fields_json TEXT NOT NULL,
                applicable_fields_json TEXT NOT NULL,
                classification_version TEXT NOT NULL
            )
            """
        )
        batch: list[tuple[Any, ...]] = []
        audience_counts: Counter[str] = Counter()
        role_counts: Counter[str] = Counter()
        for document_id, dataset, title, content, metadata_json in connection.execute(
            "SELECT id,dataset,title,content,metadata_json FROM documents ORDER BY id"
        ):
            facets = classify_document(
                str(dataset), str(title), str(content), json.loads(metadata_json or "{}")
            )
            audience_counts[facets["audience"]] += 1
            role_counts[facets["source_role"]] += 1
            columns = (
                "age_group", "sex", "target_area", "exercise_type", "fitness_level",
                "location", "equipment", "disability_type", "health_information",
                "derived_fields", "applicable_fields",
            )
            batch.append((
                str(document_id), facets["audience"], facets["source_role"],
                *(json.dumps(facets[column], ensure_ascii=False) for column in columns),
                CLASSIFICATION_VERSION,
            ))
            if len(batch) >= 2000:
                connection.executemany(
                    "INSERT INTO document_facets_building VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    batch,
                )
                batch.clear()
        if batch:
            connection.executemany(
                "INSERT INTO document_facets_building VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
        expected = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
        actual = connection.execute("SELECT count(*) FROM document_facets_building").fetchone()[0]
        if actual != expected:
            raise RuntimeError(f"분류 건수 불일치: expected={expected}, actual={actual}")
        connection.execute("DROP TABLE IF EXISTS document_facets")
        connection.execute("ALTER TABLE document_facets_building RENAME TO document_facets")
        connection.execute("CREATE INDEX idx_document_facets_audience ON document_facets(audience)")
        connection.execute("CREATE INDEX idx_document_facets_role ON document_facets(source_role)")
        connection.commit()
        connection.execute("VACUUM")
        return {
            "classification_version": CLASSIFICATION_VERSION,
            "documents": actual,
            "audiences": dict(audience_counts),
            "roles": dict(role_counts),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def audit(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA quick_check(1)").fetchone()[0]
        dataset_counts = {}
        coverage: dict[str, Counter[str]] = defaultdict(Counter)
        values: dict[str, Counter[str]] = defaultdict(Counter)
        disability_coverage: dict[str, Counter[str]] = defaultdict(Counter)
        for dataset, title, content, metadata_json, occurrence_count in connection.execute(
            "SELECT dataset,title,content,metadata_json,occurrence_count FROM documents"
        ):
            metadata = json.loads(metadata_json or "{}")
            facets = classify_document(str(dataset), str(title), str(content), metadata)
            counter = coverage[str(dataset)]
            counter["documents"] += 1
            counter["occurrence_sum"] += int(occurrence_count or 1)
            for field in (
                "age_group", "sex", "target_area", "exercise_type", "fitness_level",
                "location", "equipment", "disability_type", "health_information",
            ):
                if facets[field]:
                    counter[f"with_{field}"] += 1
            for disability in facets["disability_type"]:
                values["disability_type"][disability] += 1
                item = disability_coverage[disability]
                item["documents"] += 1
                if facets["target_area"]:
                    item["with_target_area"] += 1
                if facets["exercise_type"]:
                    item["with_exercise_type"] += 1
                if facets["target_area"] and facets["exercise_type"]:
                    item["with_target_and_type"] += 1
            for health in facets["health_information"]:
                values["health_information"][health] += 1
        for dataset, counter in coverage.items():
            dataset_counts[dataset] = dict(counter)
        return {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "classification_version": CLASSIFICATION_VERSION,
            "sqlite_integrity": integrity,
            "document_facets_present": has_facet_table(connection),
            "stored_classification_rows": (
                int(connection.execute("SELECT count(*) FROM document_facets").fetchone()[0])
                if has_facet_table(connection) else 0
            ),
            "dataset_coverage": dataset_counts,
            "disability_type_coverage": {
                key: dict(counter) for key, counter in sorted(
                    disability_coverage.items(), key=lambda item: item[1]["documents"], reverse=True
                )
            },
            "top_values": {
                key: dict(counter.most_common(40)) for key, counter in values.items()
            },
            "six_source_roles": {
                "fitness_measurements": "분석·센터 측정 및 처방 기록; 홈 측정 등급 산정 근거로 직접 사용하지 않음",
                "general_prescriptions": "일반인 센터 운동처방 기록",
                "disability_prescriptions": "장애 유형별 센터 운동처방 기록",
                "video_content": "일반 운동 방법·공식 영상 상세",
                "center_measurements": "센터 이용·측정 건수 통계",
                "center_statistics": "센터별 연도 통계",
            },
            "policy": {
                "general_recommendation": ["video_content", "general_prescription", "measurement_prescription"],
                "disability_recommendation": ["disability_prescription"],
                "health_keyword": "원문에 같은 건강 목적이 직접 표시된 운동만 추천 후보로 사용",
                "unsupported_disability_filters": ["fitness_level", "location", "available_time"],
                "removed_non_source_filters": ["exercise_experience"],
                "occurrence_count": "원본 사람 수가 아니라 한 기록에서 추출된 운동 처방 항목의 누적 출현 수",
            },
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--rebuild-facets", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result: dict[str, Any] = {}
    if args.rebuild_facets:
        result["rebuild"] = rebuild_facets(args.database)
    result["audit"] = audit(args.database)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
