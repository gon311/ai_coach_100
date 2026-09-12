"""Jupyter 없이 실행하는 AI 체력 코치 로컬 웹 서버."""

from __future__ import annotations

import asyncio
from collections import Counter
from html import escape
import json
import logging
import os
import re
import sqlite3
import threading
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Mapping

import chromadb
from rag_index_contract import validate_index
from video_audit_groups import organize as organize_video_audit
from exercise_labels import display_name, exercise_stages
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

from rag_data_roles import (
    DISABILITY_FIELDS,
    GENERAL_FIELDS,
    HEALTH_CATEGORY_GROUPS,
    HEALTH_TERMS,
    classify_document,
    display_locations,
    has_facet_table,
    health_categories,
)
from coach_dialogue import is_recommendation, safety_update, SAFETY_MESSAGE
from general_exercise_chat import use_general, answer as answer_general
from qwen3_grounded_harness import (
    Qwen3Client,
    Qwen3ServerConfig,
    GroundedQwen3Harness,
    KNOWN_EQUIPMENT,
    difficulty_levels,
    location_values,
    normalize_age_group,
    target_name_focus_score,
)
from center_percentile import (
    RESULT_LABEL, available_input_measures, ensure_percentile_database,
    lookup_percentiles, status as percentile_status,
)
from age_bmi_recommendations import (
    AWARD_GROUPS, BMI_SOURCE_NOTE, BMI_SOURCE_TITLE, BMI_SOURCE_URL,
    adult_bmi_profile, grouped_rules, lookup_rules, rule_status,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_FILE = Path(
    os.environ.get(
        "AI_FITNESS_FRONTEND_FILE",
        str(PROJECT_ROOT / "frontend1" / "fit-coach-webview.html"),
    )
)
from fitness_mvp import router as fitness_mvp_router, NORM_DB as FITNESS_PACKAGE_DB, USER_DB as FITNESS_USER_DB
ARTIFACTS_DIR = Path(
    os.environ.get("AI_FITNESS_ARTIFACTS_DIR", str(PROJECT_ROOT / "artifacts"))
)
RAG_DATABASE = ARTIFACTS_DIR / "rag_documents.sqlite"
PERCENTILE_DATABASE = ARTIFACTS_DIR / "center_percentile_norms.sqlite"
AGE_BMI_RULE_DATABASE = ARTIFACTS_DIR / "age_bmi_recommendation_rules.sqlite"
MANIFEST_PATH = ARTIFACTS_DIR / "manifest.json"
# 실행 캐시 기본 위치: Windows는 C:\ai_fitness_qwen3_runtime, macOS/Linux는 ~/ai_fitness_qwen3_runtime
_DEFAULT_RUNTIME_ROOT = (
    r"C:\ai_fitness_qwen3_runtime" if os.name == "nt" else str(Path.home() / "ai_fitness_qwen3_runtime")
)
DEFAULT_RUNTIME_DIR = Path(os.environ.get("AI_FITNESS_RUNTIME_ROOT", _DEFAULT_RUNTIME_ROOT))
DEFAULT_CHROMA_DIR = DEFAULT_RUNTIME_DIR / "chroma"
CHROMA_DIR = Path(
    os.environ.get(
        "AI_FITNESS_CHROMA_DIR",
        str(DEFAULT_CHROMA_DIR),
    )
)
OUTPUT_DIR = Path(
    os.environ.get(
        "AI_FITNESS_OUTPUT_DIR",
        str(DEFAULT_RUNTIME_DIR / "outputs"),
    )
)
COLLECTION_NAME = "fitness_rag_ko_sroberta_v1"
EMBEDDING_MODEL_NAME = "jhgan/ko-sroberta-multitask"
BUNDLED_EMBEDDING_MODEL = PROJECT_ROOT / "models" / "ko-sroberta-multitask"
MIN_SIMILARITY_SCORE = 0.35
LOGGER = logging.getLogger("uvicorn.error")
EXERCISE_TYPE_TERMS = {
    "근력": ("근력", "근육 강화"), "스트레칭": ("스트레칭",),
    "유산소": ("유산소",), "균형": ("균형", "평형"),
    "유연성": ("유연성",), "민첩성": ("민첩성",),
    "순발력": ("순발력",), "협응성": ("협응성",),
}
RAG_FACET_FIELDS = (
    "age_group", "sex", "target_area", "exercise_type", "exercise_stage", "fitness_level",
    "location", "equipment", "disability_type", "health_information",
)
CASCADE_FIELDS = (
    "health_information", "target_area", "exercise_type", "exercise_stage", "fitness_level", "location", "equipment",
)
DEFAULT_FACET_SELECTION = {
    "age_group": "성인", "sex": "M", "exercise_type": "근력",
    "fitness_level": "중급", "location": "실내", "equipment": "없음",
    "disability_type": "없음", "health_information": "없음",
}
DETAIL_LABELS = (
    "설명", "운동 단계", "운동 유형", "대상 연령군", "성별", "체력 인증등급",
    "난이도", "운동 장소", "운동 부위", "주요 근육", "운동 도구",
    "반복 횟수", "권장 주기", "측정 장소", "장애유형", "장애 세부유형",
    "장애등급", "영상 URL",
)
GENERAL_RECOMMENDATION_DATASETS = (
    "video_content", "general_prescription", "measurement_prescription",
)
FITNESS_LEVELS = {"초급", "중급", "고급"}


def _is_composite_difficulty(levels: set[str]) -> bool:
    """미표기 또는 초·중·고 전체 해당 원문을 '종합'으로 묶는다."""
    return not levels or "공통" in levels or FITNESS_LEVELS.issubset(levels)


def recommendation_datasets(disability_type: str | None) -> tuple[str, ...]:
    """장애 선택 여부에 따라 일반·장애인 처방 원문을 절대 섞지 않는다."""
    if str(disability_type or "").strip() not in {"", "없음"}:
        return ("disability_prescription",)
    return GENERAL_RECOMMENDATION_DATASETS


def sqlite_readonly_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro&immutable=1"


def _validated_official_video_url(value: str) -> str:
    """공식 국민체력100 MP4만 플레이어에서 열도록 주소 범위를 제한한다."""
    url = str(value or "").strip()
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname != "openapi.kspo.or.kr"
        or parsed.username
        or parsed.password
        or not parsed.path.startswith("/web/video/")
        or not parsed.path.casefold().endswith(".mp4")
    ):
        raise ValueError("국민체력100 공식 영상 주소만 재생할 수 있습니다.")
    return url


def _video_player_page(url: str, title: str = "공식 운동 영상") -> str:
    official_url = escape(_validated_official_video_url(url), quote=True)
    safe_title = escape(str(title or "공식 운동 영상").strip(), quote=True)
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
body{{margin:0;background:#101820;color:#fff;font-family:Arial,"Malgun Gothic",sans-serif}}
main{{max-width:1100px;margin:auto;padding:24px}}h1{{font-size:22px;margin:0 0 16px}}
video{{display:block;width:100%;max-height:78vh;background:#000;border-radius:10px}}
p{{color:#d6e3ee;line-height:1.6}}a{{color:#8bc7ff}}
</style></head><body><main><h1>{safe_title}</h1>
<video controls autoplay playsinline preload="metadata"><source src="{official_url}" type="video/mp4">
이 브라우저에서는 영상 재생을 지원하지 않습니다.</video>
<p>국민체력100 공식 영상을 재생하고 있습니다. 재생이 시작되지 않으면 재생 버튼을 눌러주세요.</p>
</main></body></html>'''


def age_group_from_age(age: int | None) -> str:
    if age is None:
        return ""
    if age < 7:
        return "유아기"
    if age < 13:
        return "유소년"
    if age < 19:
        return "청소년"
    if age < 65:
        return "성인"
    return "어르신"


class CoachRequest(BaseModel):
    question: str = Field(default="", max_length=500)
    user_id: str = Field(default="local-web-user", max_length=100)
    age: int | None = Field(default=None, ge=1, le=120)
    age_group: str = Field(default="", max_length=50)
    height_cm: float | None = Field(default=None, ge=80, le=250)
    weight_kg: float | None = Field(default=None, ge=20, le=300)
    sex: str = Field(default="", max_length=20)
    award_group: str = Field(default="", max_length=30)
    goal: str = Field(default="", max_length=200)
    target_area: str = Field(default="", max_length=100)
    exercise_type: str = Field(default="", max_length=100)
    exercise_stage: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=100)
    fitness_level: str = Field(default="", max_length=100)
    pain_area: str = Field(default="없음", max_length=200)
    pain_level: int = Field(default=0, ge=0, le=10)
    equipment: str = Field(default="없음", max_length=200)
    available_time: str = Field(default="", max_length=100)
    health_information: str = Field(default="", max_length=500)
    disability_type: str = Field(default="", max_length=100)
    home_measurement_context: str = Field(default="", max_length=1500)
    selection_mode: bool = False

    def profile(self) -> dict[str, Any]:
        result = self.model_dump(exclude={"question"})
        result["age_group"] = age_group_from_age(self.age) or normalize_age_group(self.age_group)
        bmi = adult_bmi_profile(self.age, self.height_cm, self.weight_kg)
        result["bmi_available"] = bool(bmi.get("available"))
        if bmi.get("available"):
            result["bmi_value"] = bmi["bmi"]
            result["bmi_grade"] = bmi["bmi_grade"]
            result["bmi_age_band"] = bmi["age_band"]
        else:
            result["bmi_unavailable_reason"] = str(bmi.get("reason") or "")
        if self.target_area or self.exercise_type:
            result["goal"] = " ".join(
                value for value in (self.target_area, self.exercise_type) if value
            )
        return result

    def effective_question(self, profile: Mapping[str, Any] | None = None) -> str:
        if not self.selection_mode and self.question.strip():
            return self.question.strip()
        values = profile or self.profile()
        terms = [
            values.get("age_group"), values.get("sex"), values.get("fitness_level"),
            values.get("target_area"), values.get("exercise_type"), values.get("exercise_stage"), "운동",
            values.get("location"), values.get("equipment"),
        ]
        return " ".join(value for value in terms if value and value != "없음")


class OptionRequest(BaseModel):
    age_group: str = ""
    sex: str = ""
    pain_area: str = "없음"
    pain_level: int = Field(default=0, ge=0, le=10)
    target_area: str = ""
    exercise_type: str = ""
    exercise_stage: str = ""
    fitness_level: str = ""
    location: str = ""
    equipment: str = ""
    disability_type: str = ""
    health_information: str = ""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    user_id: str = Field(default="local-web-user", max_length=100)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=8)


class PercentileRequest(BaseModel):
    age: int = Field(ge=11, le=120)
    sex: str = Field(pattern="^(M|F)$")
    measurements: dict[str, float] = Field(default_factory=dict)


def _metadata_counts(connection: sqlite3.Connection, key: str) -> Counter[str]:
    path = f"$.{key}"
    rows = connection.execute(
        "SELECT json_extract(metadata_json, ?), COUNT(*) FROM documents "
        "WHERE json_extract(metadata_json, ?) IS NOT NULL "
        "AND json_extract(metadata_json, ?) != '' GROUP BY 1",
        (path, path, path),
    )
    return Counter({str(value): int(count) for value, count in rows})


def _content_label_counts(rows: list[tuple[str]], label: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    prefix = f"{label}:"
    for (content,) in rows:
        for line in str(content).splitlines():
            if not line.startswith(prefix):
                continue
            counts.update(
                value.strip() for value in line.split(":", 1)[1].split(",") if value.strip()
            )
    return counts


def _label_values(content: str, label: str) -> set[str]:
    prefix = f"{label}:"
    for line in str(content).splitlines():
        if line.startswith(prefix):
            return {
                value.strip() for value in line.split(":", 1)[1].split(",") if value.strip()
            }
    return set()


def _rag_detail(source: dict[str, Any] | None) -> dict[str, str]:
    if not source:
        return {}
    labels: dict[str, str] = {}
    for line in str(source.get("text") or "").splitlines():
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        if label.strip() in {"운동명", *DETAIL_LABELS} and value.strip():
            labels[label.strip()] = value.strip()
    labels.setdefault("운동명", str(source.get("title") or "").strip())
    return {label: labels[label] for label in ("운동명", *DETAIL_LABELS) if labels.get(label)}


CHAT_RECOMMENDATION_TERMS = (
    "추천", "다음", "그다음", "이어서", "이어", "계속", "다른 운동", "또 다른",
    "헬스장", "실내", "실외", "수영장", "운동장", "있어", "없어",
)


def _is_chat_recommendation_request(message: str) -> bool:
    return is_recommendation(message)


def _exercise_key(value: Any) -> str:
    text = re.sub(r"\s*\([^)]*\)\s*$", "", display_name(value))
    return re.sub(r"\s+", "", text).casefold()


def _rule_exercise_key(value: Any) -> str:
    """원문 운동명 연결에는 공백·문장부호만 무시하고 별칭 추측은 하지 않는다."""
    return re.sub(r"[^0-9A-Za-z가-힣]", "", display_name(value)).casefold()


def _detail_notice(detail: dict[str, str]) -> str:
    if not detail:
        return "선택된 처방 원문에 표시할 수 있는 운동 상세 정보가 없습니다."
    informative = {
        "설명", "운동 유형", "난이도", "운동 장소", "운동 부위", "주요 근육",
        "운동 도구", "반복 횟수", "권장 주기", "영상 URL",
    }
    messages: list[str] = []
    if not (informative & detail.keys()):
        messages.append(
            "이 결과는 개인 처방 분류 기록입니다. 원본에 운동 설명·주요 근육·횟수·영상 정보가 없어 존재하는 분류값만 표시합니다. 다른 연령군의 상세 자료는 섞지 않았습니다."
        )
    name = str(detail.get("운동명") or "")
    stage = str(detail.get("운동 단계") or "")
    prefix = name.split(":", 1)[0] if ":" in name else ""
    if prefix in {"준비운동", "본운동", "정리운동"} and stage and stage != "단계 미상" and prefix != stage:
        messages.append(
            f"원본 데이터의 운동명 분류({prefix})와 운동 단계({stage})가 서로 달라 원문 그대로 표시했습니다."
        )
    return " ".join(messages)


def _target_focus_notice(
    profile: Mapping[str, Any], trace: Mapping[str, Any]
) -> str:
    """운동명과 상세 부위가 어긋난 원문을 사용자에게 숨기지 않고 설명한다."""
    target = str(profile.get("target_area") or "").strip()
    selected_name = str(trace.get("selected_name") or "").strip()
    detail = trace.get("selected_detail") or {}
    if not target or target_name_focus_score(selected_name, target) < 4:
        return ""
    source_areas = {
        value.strip()
        for value in re.split(r"\s*[,/|]\s*", str(detail.get("운동 부위") or ""))
        if value.strip()
    }
    if target in source_areas or not source_areas:
        return ""
    return (
        f"선택 부위 확인: 운동명과 설명에 ‘{target}’가 직접 명시되어 있어 "
        f"{target} 중심 자료로 우선 선택했습니다. 다만 같은 원문의 운동 부위 칸에는 "
        f"{target}가 빠져 있어, 아래에는 원문 값을 수정하지 않고 그대로 표시합니다."
    )


def _friendly_result_copy(
    profile: Mapping[str, Any], trace: Mapping[str, Any]
) -> dict[str, str]:
    """검증된 원문 값은 유지하면서 대화하듯 읽히는 문장으로 바꾼다."""
    def subject_particle(value: str) -> str:
        if not value:
            return "이"
        code = ord(value[-1]) - 0xAC00
        return "이" if 0 <= code <= 11171 and code % 28 else "가"

    def readable_list(value: Any) -> str:
        return ", ".join(
            item.strip() for item in str(value or "").split(",") if item.strip()
        )

    age_group = normalize_age_group(profile.get("age_group")) or "현재 연령"
    fitness_level = str(profile.get("fitness_level") or "현재 수준").strip()
    target_area = str(profile.get("target_area") or "선택 부위").strip()
    exercise_type = str(profile.get("exercise_type") or "운동").strip()
    location = str(profile.get("location") or "").strip()
    equipment = str(profile.get("equipment") or "없음").strip()
    health_information = str(profile.get("health_information") or "").strip()
    video_options = list(trace.get("video_options") or [])
    compatible = [item for item in video_options if item.get("condition_compatible")]
    explicit = [
        item for item in video_options
        if "선택 난이도 명시" in str(item.get("condition_note") or "")
    ]
    weekly = sorted(
        [item for item in video_options if item.get("week")],
        key=lambda item: int(re.sub(r"\D", "", str(item.get("week"))) or 999),
    )
    incompatible_equipment = sorted({
        value
        for item in video_options
        if not item.get("condition_compatible")
        for value in str(item.get("equipment") or "").split("/")
        if value and value not in {"장비 없음", "미표기", "장비 없음/미표기"}
    })

    selected_name = str(trace.get("selected_name") or "").strip()
    guide_parts: list[str] = []
    if health_information not in {"", "없음"}:
        guide_parts.append(
            f"고르신 ‘{health_information}’ 목적이 공식 자료에 직접 표시된 운동만 살펴봤어요."
        )
    if selected_name:
        guide_parts.append(
            f"지금 고르신 {target_area} {exercise_type} 조건에는 "
            f"‘{selected_name}’{subject_particle(selected_name)} 잘 맞아요."
        )
        condition_text = "·".join(
            value for value in (age_group, fitness_level, location) if value
        )
        if condition_text:
            guide_parts.append(f"{condition_text} 조건도 함께 확인했어요.")
        if target_name_focus_score(selected_name, target_area) >= 4:
            guide_parts.append(
                f"운동 이름에도 ‘{target_area}’{subject_particle(target_area)} 직접 들어 있어요."
            )
    if video_options:
        guide_parts.append(
            f"바로 확인할 수 있는 공식 영상도 {len(video_options)}개 있어요."
        )
    if explicit:
        guide_parts.append(
            f"그중에는 고르신 {fitness_level} 난이도가 표시된 영상도 있어요."
        )
    if video_options and not compatible:
        guide_parts.append(
            f"다만 지금 고르신 장소와 장비({equipment})에 모두 맞는 영상은 없어서, "
            "아래 자료에서 필요한 조건을 먼저 확인해 주세요."
        )
    elif incompatible_equipment:
        guide_parts.append(
            f"일부 영상은 {', '.join(incompatible_equipment)} 장비가 필요해요. 영상 카드에서 장비를 먼저 확인해 주세요."
        )
    if not video_options:
        guide_parts.append("이 조건과 바로 연결된 공식 영상은 아직 확인되지 않았어요.")

    detail = dict(trace.get("selected_detail") or {})
    detail_description = str(detail.get("설명") or "").strip()
    lead_video = next(iter(compatible or video_options), {})
    lead_title = str(lead_video.get("title") or selected_name or f"{target_area} {exercise_type}").strip()
    lead_description = str(lead_video.get("description") or detail_description).strip()
    intro_parts = [f"이번에는 ‘{lead_title}’ 운동을 함께 볼게요."]
    source_type = str(detail.get("운동 유형") or "").strip()
    source_areas = readable_list(detail.get("운동 부위"))
    source_muscles = readable_list(detail.get("주요 근육"))
    if source_areas:
        intro_parts.append(
            f"{source_areas} 부위를 중심으로 하는 {source_type or exercise_type} 운동이에요."
        )
    elif source_type:
        intro_parts.append(f"{source_type} 운동으로 안내되어 있어요.")
    elif lead_description:
        intro_parts.append(f"공식 소개에는 ‘{lead_description.rstrip('.')}’라고 적혀 있어요.")
    if source_muscles:
        intro_parts.append(f"주로 {source_muscles}을 사용하는 동작이에요.")

    method_parts: list[str] = []
    source_stage = str(detail.get("운동 단계") or "").strip()
    repetitions = str(detail.get("반복 횟수") or "").strip()
    frequency = str(detail.get("권장 주기") or "").strip()
    if source_stage and source_stage != "단계 미상":
        method_parts.append(f"원문 운동 단계는 {source_stage}입니다.")
    if repetitions:
        method_parts.append(f"원문 반복 횟수는 {repetitions}입니다.")
    if frequency:
        method_parts.append(f"원문 권장 주기는 {frequency}입니다.")
    if weekly:
        week_labels = [str(item.get("week")) for item in weekly]
        method_parts.append(
            f"주차별 자료는 {week_labels[0]}부터 {week_labels[-1]}까지 있어요. "
            "표시된 주차 순서대로 확인할 수 있고, 난이도가 적혀 있지 않은 영상에는 별도 등급을 붙이지 않았어요."
        )
    return {
        "recommendation_guide": " ".join(guide_parts),
        "exercise_intro": " ".join(intro_parts),
        "exercise_method": " ".join(method_parts),
    }


def _options(counter: Counter[str], order: list[str] | None = None, limit: int = 40) -> list[dict[str, Any]]:
    values = order or [value for value, _ in counter.most_common(limit)]
    return [
        {"value": value, "label": value, "count": int(counter.get(value, 0)), "source": "rag"}
        for value in values
        if counter.get(value, 0) > 0
    ]


def _facet_equipment_values(text: str) -> set[str]:
    """선택 목록과 하네스가 '없음/숨은 장비'를 같은 방식으로 판정하게 한다."""
    labelled = _label_values(text, "운동 도구")
    if labelled:
        return {
            value for value in labelled
            if value not in {"없음", "맨몸", "무장비"}
        }
    hidden = next((equipment for equipment in KNOWN_EQUIPMENT if equipment in text), None)
    return {hidden} if hidden else set()


class RagRuntime:
    def __init__(self) -> None:
        if not RAG_DATABASE.is_file():
            raise FileNotFoundError(f"RAG DB가 없습니다: {RAG_DATABASE}")
        if not (CHROMA_DIR / "chroma.sqlite3").is_file():
            raise FileNotFoundError(f"ChromaDB가 없습니다: {CHROMA_DIR}")

        with sqlite3.connect(sqlite_readonly_uri(RAG_DATABASE), uri=True) as connection:
            integrity = connection.execute("PRAGMA quick_check(1)").fetchone()[0]
            self.sqlite_documents = int(
                connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            )
            self.rag_datasets = [
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT dataset FROM documents ORDER BY dataset"
                )
            ]
            self.facet_records = self._load_facet_records(connection)
            self.facet_by_id = {
                str(record["_id"]): record for record in self.facet_records
            }
            self.rag_options = self._load_options(connection)
            self.exercise_detail_index = self._load_exercise_detail_index(connection)
            self.rule_detail_index = self._load_rule_detail_index(connection)
        if integrity != "ok":
            raise RuntimeError(f"SQLite 무결성 검사 실패: {integrity}")
        self.age_bmi_rule_status = rule_status(AGE_BMI_RULE_DATABASE)
        if not self.age_bmi_rule_status.get("available"):
            raise RuntimeError(
                "국민연령별 추천운동 규칙 DB 검증 실패: "
                f"{self.age_bmi_rule_status.get('reason') or self.age_bmi_rule_status}"
            )
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.source_dataset_count = int(manifest.get("source_folder_count", 0))
        self.total_source_rows = int(manifest.get("total_source_rows", 0))

        embedding_source = (
            str(BUNDLED_EMBEDDING_MODEL)
            if BUNDLED_EMBEDDING_MODEL.is_dir()
            else EMBEDDING_MODEL_NAME
        )
        self.embedding_model = SentenceTransformer(embedding_source)
        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.chroma_client.get_collection(COLLECTION_NAME)
        self.chroma_documents = int(self.collection.count())
        validate_index(RAG_DATABASE, CHROMA_DIR, self.collection, set(self.facet_by_id))

        self.qwen3_client = Qwen3Client(
            Qwen3ServerConfig(
                base_url=os.environ.get("QWEN3_BASE_URL", "http://127.0.0.1:8080"),
                model="Qwen3-4B-Q4_K_M.gguf",
                temperature=0.0,
                seed=42,
                max_tokens=900,
            )
        )
        self.harness = GroundedQwen3Harness(
            search=self.semantic_search,
            client=self.qwen3_client,
            min_score=MIN_SIMILARITY_SCORE,
            max_regeneration_attempts=2,
            structured_search=self.structured_search,
        )
        self.answer_lock = threading.Lock()
        self.chat_contexts: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _load_options(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
        video_rows = connection.execute(
            "SELECT content FROM documents WHERE dataset='video_content'"
        ).fetchall()
        body_parts = _content_label_counts(video_rows, "운동 부위")
        equipment = _content_label_counts(video_rows, "운동 도구")
        locations = _content_label_counts(video_rows, "운동 장소")
        difficulty = _metadata_counts(connection, "difficulty")
        age_groups = _metadata_counts(connection, "age_group")
        sexes = _metadata_counts(connection, "sex")
        disabilities = _metadata_counts(connection, "disability_type")

        normalized_ages: Counter[str] = Counter()
        for raw_value, count in age_groups.items():
            normalized_ages[normalize_age_group(raw_value)] += count
        normalized_difficulty: Counter[str] = Counter()
        for raw_value, count in difficulty.items():
            for level in difficulty_levels(raw_value):
                normalized_difficulty[level] += count
        normalized_locations: Counter[str] = Counter()
        for raw_value, count in locations.items():
            for location in location_values(raw_value):
                normalized_locations[location] += count

        all_video_text = "\n".join(content for (content,) in video_rows)
        exercise_types = Counter(
            {
                label: sum(all_video_text.count(term) for term in terms)
                for label, terms in EXERCISE_TYPE_TERMS.items()
            }
        )
        health_counts = Counter({
            term: int(connection.execute(
                "SELECT COUNT(*) FROM documents WHERE content LIKE ?", (f"%{term}%",)
            ).fetchone()[0])
            for term in HEALTH_TERMS
        })

        none_constraint = {"value": "없음", "label": "없음", "count": 0, "source": "constraint"}
        return {
            "age_group": _options(
                normalized_ages,
                ["유아기", "유소년", "청소년", "성인", "어르신", "공통"],
            ),
            "sex": [
                {"value": "M", "label": "남성", "count": int(sexes.get("M", 0)), "source": "rag"},
                {"value": "F", "label": "여성", "count": int(sexes.get("F", 0)), "source": "rag"},
            ],
            "fitness_level": _options(
                normalized_difficulty,
                ["초급", "중급", "고급"],
            ),
            "target_area": _options(body_parts, limit=30),
            "exercise_type": _options(exercise_types, limit=20),
            "pain_area": [none_constraint, *_options(body_parts, limit=30)],
            "equipment": [none_constraint, *_options(equipment, limit=35)],
            "location": _options(
                normalized_locations,
                ["실내", "실외", "헬스장", "수영장", "운동장"],
            ),
            "disability_type": [none_constraint, *_options(disabilities, limit=30)],
            "health_information": [none_constraint, *_options(health_counts, limit=20)],
            "available_time": [
                {"value": value, "label": value, "count": 0, "source": "constraint"}
                for value in ("10분", "20분", "30분", "45분", "60분")
            ],
            "pain_level": [
                {"value": str(value), "label": str(value), "count": 0, "source": "constraint"}
                for value in range(11)
            ],
        }

    @staticmethod
    def _load_facet_records(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        stored_facets: dict[str, dict[str, Any]] = {}
        if has_facet_table(connection):
            facet_columns = (
                "age_group", "sex", "target_area", "exercise_type", "fitness_level",
                "location", "equipment", "disability_type", "health_information",
                "derived_fields", "applicable_fields",
            )
            for row in connection.execute(
                "SELECT document_id,audience,source_role,age_group_json,sex_json,"
                "target_area_json,exercise_type_json,fitness_level_json,location_json,"
                "equipment_json,disability_type_json,health_information_json,"
                "derived_fields_json,applicable_fields_json FROM document_facets"
            ):
                stored_facets[str(row[0])] = {
                    "audience": str(row[1]), "source_role": str(row[2]),
                    **{
                        field: json.loads(value or "[]")
                        for field, value in zip(facet_columns, row[3:])
                    },
                }
        for document_id, dataset, title, content, metadata_json in connection.execute(
            "SELECT id,dataset,title,content,metadata_json FROM documents"
        ):
            text = str(content or "")
            metadata = json.loads(metadata_json or "{}")
            video_url = str(metadata.get("video_url") or "").strip()
            if not video_url:
                match = re.search(r"(?m)^영상 URL\s*:\s*(\S+)", text)
                video_url = match.group(1).strip() if match else ""
            facets = stored_facets.get(str(document_id)) or classify_document(
                str(dataset), str(title), text, metadata
            )
            raw_difficulty = str(metadata.get("difficulty") or "").strip()
            if not raw_difficulty:
                raw_difficulty = str(
                    _rag_detail({"title": str(title), "text": text}).get("난이도") or ""
                ).strip()
            ages = {
                normalize_age_group(value) for value in facets.get("age_group", [])
                if normalize_age_group(value)
            }
            records.append({
                "_id": str(document_id),
                "_exercise_key": _exercise_key(str(title)) or str(document_id),
                "_exercise_name": _rag_detail({"title": str(title), "text": text}).get("운동명") or str(title),
                "_link_key": _rule_exercise_key(
                    _rag_detail({"title": str(title), "text": text}).get("운동명") or str(title)
                ),
                "_variant_key": (
                    f"video:{video_url}" if str(dataset) == "video_content" and video_url
                    else f"document:{document_id}"
                ),
                "_dataset": str(dataset),
                "_audience": str(facets.get("audience") or "reference"),
                "_source_role": str(facets.get("source_role") or "reference"),
                "_derived_fields": set(facets.get("derived_fields", [])),
                "_applicable_fields": set(facets.get("applicable_fields", [])),
                "_fitness_group": (
                    "종합" if _is_composite_difficulty(
                        difficulty_levels(raw_difficulty) or set(facets.get("fitness_level", []))
                    ) else ""
                ),
                "age_group": ages,
                "sex": set(facets.get("sex", [])),
                "target_area": set(facets.get("target_area", [])),
                "exercise_type": set(facets.get("exercise_type", [])),
                "exercise_stage": exercise_stages(str(title), text, metadata),
                "fitness_level": set(facets.get("fitness_level", [])),
                "location": display_locations(facets.get("equipment", []), facets.get("location", [])),
                "equipment": set(facets.get("equipment", [])),
                "disability_type": set(facets.get("disability_type", [])),
                "health_information": set(facets.get("health_information", [])),
            })
        # 같은 URL이라도 원문 행의 난이도·장소·장비 표기가 다를 수 있다.
        # 여기서 다른 행의 장비를 빈 행에 덮어쓰면 '난이도 미표기/장비 없음'
        # 선택이 실제 미표기 행을 찾지 못한다. URL 중복 제거는 조건에 맞는
        # 행만 선별한 뒤 _video_options에서 수행한다.
        return records

    @staticmethod
    def _load_exercise_detail_index(
        connection: sqlite3.Connection,
    ) -> dict[str, dict[str, str]]:
        index: dict[str, dict[str, str]] = {}
        for document_id, title, content in connection.execute(
            "SELECT id,title,content FROM documents WHERE dataset='video_content'"
        ):
            source = {
                "document_id": str(document_id), "title": str(title),
                "text": str(content), "dataset": "video_content",
            }
            detail = _rag_detail(source)
            key = _exercise_key(detail.get("운동명") or title)
            if not key:
                continue
            current = index.get(key)
            if current is None or len(_rag_detail(source)) > len(_rag_detail(current)):
                index[key] = source
        return index

    @staticmethod
    def _load_rule_detail_index(
        connection: sqlite3.Connection,
    ) -> dict[str, dict[str, str]]:
        """순위표의 운동명과 직접 표기까지 일치하는 공식 영상만 연결한다."""
        index: dict[str, dict[str, str]] = {}
        for document_id, title, content in connection.execute(
            "SELECT id,title,content FROM documents WHERE dataset='video_content'"
        ):
            source = {
                "document_id": str(document_id), "title": str(title),
                "text": str(content), "dataset": "video_content",
            }
            detail = _rag_detail(source)
            key = _rule_exercise_key(detail.get("운동명") or title)
            if not key:
                continue
            current = index.get(key)
            if current is None or len(_rag_detail(source)) > len(_rag_detail(current)):
                index[key] = source
        return index

    def _age_bmi_recommendation(self, profile: dict[str, Any]) -> dict[str, Any]:
        """성인 BMI와 사용자가 직접 고른 상장 구분으로 원문 순위만 조회한다."""
        recommendation = lookup_rules(AGE_BMI_RULE_DATABASE, profile)
        if not recommendation.get("available"):
            return recommendation
        for rule in recommendation.get("rules", []):
            linked = self.rule_detail_index.get(_rule_exercise_key(rule.get("exercise_name")))
            if not linked:
                rule["rag_linked"] = False
                continue
            detail = _rag_detail(linked)
            rule["rag_linked"] = True
            rule["rag_title"] = str(linked.get("title") or "")
            rule["video_url"] = str(detail.get("영상 URL") or "")
            rule["detail"] = {
                key: detail[key]
                for key in ("운동 부위", "운동 장소", "운동 도구", "난이도")
                if detail.get(key)
            }
        recommendation["steps"] = grouped_rules(recommendation.get("rules", []))
        return recommendation

    @staticmethod
    def _age_bmi_chat_source(recommendation: Mapping[str, Any]) -> dict[str, Any]:
        bmi = dict(recommendation.get("bmi") or {})
        source = dict(recommendation.get("source") or {})
        rule_lines = [
            f"{item.get('sports_step')} {item.get('rank')}위: {item.get('exercise_name')}"
            for item in recommendation.get("rules", [])
        ]
        context = [
            "국내 성인 BMI 분류",
            f"입력 BMI: {bmi.get('bmi')}",
            f"분류: {bmi.get('bmi_grade')}",
            str(source.get("bmi_source_title") or BMI_SOURCE_TITLE),
            str(source.get("bmi_source_url") or BMI_SOURCE_URL),
            str(source.get("bmi_source_note") or BMI_SOURCE_NOTE),
        ]
        if recommendation.get("available"):
            context.extend([
                f"원문 조건: {recommendation.get('age_band')} · {recommendation.get('sex')} · "
                f"{recommendation.get('bmi_grade')} · {recommendation.get('award_group')}",
                f"원문 파일: {source.get('source_file', '')}",
                *rule_lines,
            ])
        return {
            "evidence_id": "B1",
            "document_id": "korean-adult-bmi-and-age-recommendation-rules",
            "dataset": "age_bmi_recommendation_rules",
            "title": "국내 성인 BMI 기준 및 국민연령별추천운동정보",
            "score": 1.0,
            "text": "\n".join(value for value in context if value),
        }

    def _chat_age_bmi_recommendation(
        self, message: str, context: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """BMI·순위 질문은 모델 추측 대신 계산·원문 규칙 결과로 답한다."""
        normalized = re.sub(r"\s+", "", str(message or ""))
        terms = ("BMI", "비만", "상장", "순위")
        if not any(term in normalized.upper() for term in terms):
            return None
        recommendation = dict(context.get("age_bmi_recommendation") or {})
        bmi = dict(recommendation.get("bmi") or {})
        if not bmi.get("available"):
            return None
        source = self._age_bmi_chat_source(recommendation)
        lead = (
            f"입력 BMI는 {float(bmi['bmi']):.1f}이고, 국내 성인 BMI 기준상 "
            f"‘{bmi['bmi_grade']}’입니다. 이는 진단이나 치료 판단이 아니라 분류값입니다."
        )
        if not recommendation.get("available"):
            reason = str(recommendation.get("reason") or "")
            return {"answer": f"{lead} {reason}", "sources": [source], "context_ready": True}
        requested_steps = [
            step for step in ("준비운동", "본운동", "마무리운동") if step in normalized
        ]
        steps = requested_steps or ("준비운동", "본운동", "마무리운동")
        grouped = {item["sports_step"]: item["recommendations"] for item in recommendation.get("steps", [])}
        descriptions = []
        for step in steps:
            names = [
                f"{item['rank']}위 {item['exercise_name']}"
                for item in grouped.get(step, [])
            ]
            if names:
                descriptions.append(f"{step} 원문 순위는 {', '.join(names)}입니다.")
        condition = (
            f"원문 조회 조건은 {recommendation.get('age_band')} · "
            f"{recommendation.get('sex')} · {recommendation.get('bmi_grade')} · "
            f"{recommendation.get('award_group')}입니다."
        )
        return {
            "answer": " ".join([lead, condition, *descriptions]),
            "sources": [source], "context_ready": True,
        }

    @staticmethod
    def _facet_record_matches(
        record: dict[str, Any], selection: dict[str, str], skip: str
    ) -> bool:
        disability = str(selection.get("disability_type") or "").strip()
        mode = "disability" if disability not in {"", "없음"} else "general"
        if record.get("_audience") != mode:
            return False
        pain_area = str(selection.get("pain_area") or "").strip()
        selected_target = str(selection.get("target_area") or "").strip()
        if pain_area not in {"", "없음"} and selected_target == pain_area:
            return False
        expected_health = str(selection.get("health_information") or "").strip()
        if expected_health not in {"", "없음"} and expected_health not in record["health_information"]:
            return False
        applicable = DISABILITY_FIELDS if mode == "disability" else GENERAL_FIELDS
        for field in RAG_FACET_FIELDS:
            if field == skip:
                continue
            if field not in applicable:
                continue
            expected = str(selection.get(field) or "").strip()
            if not expected:
                continue
            values = record.get(field, set())
            if field == "health_information":
                continue
            if field == "equipment" and expected == "없음":
                if values:
                    return False
                continue
            if field == "fitness_level":
                composite = str(record.get("_fitness_group") or "") == "종합" or _is_composite_difficulty(set(values))
                if expected == "종합":
                    if not composite:
                        return False
                    continue
                if composite:
                    return False
                if expected not in values:
                    return False
                continue
            if field == "age_group":
                expected = normalize_age_group(expected)
                if values and expected not in values and "공통" not in values:
                    return False
                continue
            if field == "sex":
                if values and expected not in values:
                    return False
                continue
            if expected not in values:
                return False
        return True

    def structured_search(
        self, profile: Mapping[str, Any], k: int = 200
    ) -> list[dict[str, Any]]:
        """화면 목록을 만든 동일한 구조화 조건으로 SQLite 원문을 직접 회수한다."""
        selection = {field: str(profile.get(field) or "").strip() for field in RAG_FACET_FIELDS}
        search_selection = dict(selection)
        matched: list[dict[str, Any]] = []
        matched_ids: set[str] = set()
        tier_counts: dict[str, int] = {}
        # 체력 수준은 원문 표기가 드문 경우에만 완화한다. 운동 장소는
        # 사용자가 실제로 운동할 환경이므로 다른 장소로 절대 완화하지 않는다.
        for tier, relaxed_field in (
            ("exact", None), ("fitness_level", "fitness_level"),
        ):
            if relaxed_field:
                search_selection[relaxed_field] = ""
            tier_matches = [
                record for record in self.facet_records
                if self._facet_record_matches(record, search_selection, "__none__")
            ]
            tier_matches.sort(
                key=lambda record: record.get("_dataset") == "video_content",
                reverse=True,
            )
            tier_counts[tier] = len(tier_matches)
            for record in tier_matches:
                document_id = str(record["_id"])
                if document_id not in matched_ids:
                    matched_ids.add(document_id)
                    matched.append(record)
            if len(matched) >= max(k * 2, 200):
                break
        ids = [str(record["_id"]) for record in matched[: max(k * 2, 200)]]
        full_records = self._fetch_full_records(ids)
        results: list[dict[str, Any]] = []
        for document_id in ids:
            record = full_records.get(document_id)
            if record is None:
                continue
            result = {
                "id": document_id,
                "dataset": record["dataset"],
                "title": record["title"],
                "text": record["content"],
                "metadata": self._metadata_with_facets(
                    document_id, json.loads(record["metadata_json"])
                ),
                "occurrence_count": record["occurrence_count"],
                "score": 1.0,
            }
            # 목록을 만든 원문 자체로 먼저 검증한다. 같은 이름의 다른 상세 문서를
            # 미리 합치면 그 문서의 장비·연령 값 때문에 유효 후보가 탈락할 수 있다.
            results.append(result)
            if len(results) >= k:
                break
        LOGGER.info(
            "Structured RAG selection matched=%d returned=%d tiers=%s selection=%s",
            len(matched), len(results), tier_counts, selection,
        )
        return results

    def _faceted_rag_options(self, selection: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        normalized = {
            field: str(selection.get(field) or "").strip()
            for field in RAG_FACET_FIELDS
        }
        normalized["pain_area"] = str(selection.get("pain_area") or "없음").strip()
        try:
            normalized["pain_level"] = str(int(selection.get("pain_level") or 0))
        except (TypeError, ValueError):
            normalized["pain_level"] = "0"
        disability_mode = normalized.get("disability_type") not in {"", "없음"}
        applicable = DISABILITY_FIELDS if disability_mode else GENERAL_FIELDS
        for field in RAG_FACET_FIELDS:
            counter: Counter[str] = Counter()
            if field == "disability_type":
                # 현재 일반 모드에서도 장애 유형으로 전환할 수 있도록 목록은
                # 장애인 처방 전체에서 연령·성별만 맞춰 계산한다.
                for record in self.facet_records:
                    if record.get("_audience") != "disability":
                        continue
                    age = normalize_age_group(normalized.get("age_group"))
                    if age and record["age_group"] and age not in record["age_group"] and "공통" not in record["age_group"]:
                        continue
                    sex = normalized.get("sex")
                    if sex and record["sex"] and sex not in record["sex"]:
                        continue
                    counter.update(record[field])
            elif field == "health_information":
                if disability_mode:
                    result[field] = [{
                        "value": "", "label": "장애인 처방 원문에 질환 분류 없음",
                        "count": 0, "source": "not_applicable",
                    }]
                    continue
                # 건강 목적은 통증·연령·성별까지의 기본 조건으로 먼저 고른다.
                # 뒤쪽의 기본 선택값(난이도·장소·장비)이 건강 목적 목록을 미리
                # 비워 버리지 않도록, 화면에서 고르는 순서를 유지한다.
                display_selection = {name: "" for name in RAG_FACET_FIELDS}
                display_selection["pain_area"] = normalized["pain_area"]
                display_selection["pain_level"] = normalized["pain_level"]
                display_selection["age_group"] = normalized.get("age_group", "")
                display_selection["sex"] = normalized.get("sex", "")
                value_keys: dict[str, set[str]] = {}
                for record in self.facet_records:
                    if not self._facet_record_matches(
                        record, display_selection, "health_information"
                    ):
                        continue
                    record_key = str(
                        record.get("_exercise_key") or record.get("_id") or id(record)
                    )
                    for value in record[field]:
                        value_keys.setdefault(value, set()).add(record_key)
                counter = Counter({value: len(keys) for value, keys in value_keys.items()})
            elif field not in applicable:
                result[field] = [{
                    "value": "", "label": "장애인 처방 원문에 별도 항목 없음",
                    "count": 0, "source": "not_applicable",
                }]
                continue
            else:
                # 화면 순서대로 조건을 누적한다. 뒤쪽 기본 선택값 때문에 앞쪽
                # 목록이 사라지지 않게 하고, 사용자가 하나씩 고를수록 다음
                # 목록에서 실제 가능한 운동 범위가 좁혀지게 한다.
                display_selection = {name: "" for name in RAG_FACET_FIELDS}
                display_selection["pain_area"] = normalized["pain_area"]
                display_selection["pain_level"] = normalized["pain_level"]
                for core_field in ("age_group", "sex", "disability_type"):
                    display_selection[core_field] = normalized.get(core_field, "")
                display_selection["health_information"] = normalized.get("health_information", "")
                if field in CASCADE_FIELDS:
                    field_index = CASCADE_FIELDS.index(field)
                    for previous_field in CASCADE_FIELDS[:field_index]:
                        display_selection[previous_field] = normalized.get(previous_field, "")
                value_keys: dict[str, set[str]] = {}
                for record in self.facet_records:
                    if not self._facet_record_matches(record, display_selection, field):
                        continue
                    values = record.get(field, set())
                    record_key = str(
                        record.get("_exercise_key") or record.get("_id") or id(record)
                    )
                    if field == "sex" and not values:
                        # 성별이 없는 공식 영상·공통 자료는 남녀 모두 사용할 수 있다.
                        counter["M"] += 1
                        counter["F"] += 1
                    elif field in CASCADE_FIELDS:
                        if field == "equipment" and not values:
                            displayed_values = {"없음"}
                        elif field == "fitness_level":
                            displayed_values = (
                                {"종합"}
                                if str(record.get("_fitness_group") or "") == "종합"
                                or _is_composite_difficulty(set(values))
                                else values
                            )
                        else:
                            displayed_values = values
                        for value in displayed_values:
                            value_keys.setdefault(value, set()).add(record_key)
                    else:
                        counter.update(values)
                if field in CASCADE_FIELDS:
                    counter = Counter({value: len(keys) for value, keys in value_keys.items()})

            if field == "exercise_stage":
                options = [{"value": "", "label": "전체 단계", "count": 0, "source": "display"}] + _options(counter, ["준비운동", "본운동", "정리운동"])
            elif field == "age_group":
                age_counter = Counter(counter)
                common_count = int(counter.get("공통", 0))
                # 공통 연령 자료는 사용자의 실제 연령군에서도 선택 가능해야 한다.
                if common_count:
                    for age_label in ("유아기", "유소년", "청소년", "성인", "어르신"):
                        age_counter[age_label] += common_count
                options = _options(age_counter, ["유아기", "유소년", "청소년", "성인", "어르신", "공통"])
            elif field == "sex":
                options = [
                    option for option in (
                        {"value": "M", "label": "남성", "count": int(counter.get("M", 0)), "source": "rag"},
                        {"value": "F", "label": "여성", "count": int(counter.get("F", 0)), "source": "rag"},
                    ) if option["count"] > 0
                ]
            elif field == "target_area":
                options = _options(counter, limit=100)
                if normalized["pain_area"] not in {"", "없음"}:
                    options = [
                        item for item in options
                        if item["value"] != normalized["pain_area"]
                    ]
            elif field == "exercise_type":
                options = _options(counter, list(EXERCISE_TYPE_TERMS))
            elif field == "fitness_level":
                preferred = ["초급", "중급", "고급", "종합"]
                remaining = sorted(value for value in counter if value not in preferred)
                options = _options(counter, [*preferred, *remaining])
            elif field == "location":
                options = _options(counter, ["실내", "실외", "헬스장", "수영장", "운동장"])
            elif field == "equipment":
                none_count = int(counter.get("없음", 0))
                options = []
                if none_count > 0:
                    options.append({
                        "value": "없음", "label": "없음", "count": none_count,
                        "source": "rag",
                    })
                options.extend(
                    item for item in _options(counter, limit=40)
                    if item["value"] != "없음"
                )
            elif field == "disability_type":
                none = {"value": "없음", "label": "없음", "count": 0, "source": "constraint"}
                options = [none, *_options(counter, limit=40)]
            elif field == "health_information":
                none = {"value": "없음", "label": "건강 목적 선택 안 함", "count": 0, "source": "constraint"}
                options = [none]
                for item in _options(counter, list(HEALTH_TERMS), limit=40):
                    group = HEALTH_CATEGORY_GROUPS.get(item["value"], "건강 목적 운동")
                    item["label"] = f"{group} · {item['value']}"
                    options.append(item)
            else:
                none = {"value": "없음", "label": "없음", "count": 0, "source": "constraint"}
                options = [none, *_options(counter, limit=20)]

            result[field] = options

        return result

    def _matching_exercise_count(self, selection: dict[str, str]) -> int:
        try:
            if int(selection.get("pain_level") or 0) >= 7:
                return 0
        except (TypeError, ValueError):
            pass
        normalized = {
            field: str(selection.get(field) or "").strip()
            for field in RAG_FACET_FIELDS
        }
        normalized["pain_area"] = str(selection.get("pain_area") or "없음").strip()
        normalized["pain_level"] = str(selection.get("pain_level") or "0").strip()
        keys = {
            str(record.get("_exercise_key") or record.get("_id") or id(record))
            for record in self.facet_records
            if self._facet_record_matches(record, normalized, "__none__")
        }
        return len(keys)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = self.embedding_model.encode(
            texts,
            batch_size=64,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def _fetch_full_records(self, ids: list[str]) -> dict[str, sqlite3.Row]:
        if not ids:
            return {}
        with sqlite3.connect(sqlite_readonly_uri(RAG_DATABASE), uri=True) as connection:
            connection.row_factory = sqlite3.Row
            placeholders = ",".join("?" for _ in ids)
            rows = connection.execute(
                "SELECT id,dataset,title,content,metadata_json,occurrence_count "
                f"FROM documents WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        return {str(row["id"]): row for row in rows}

    def _metadata_with_facets(
        self, document_id: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """파생 분류를 검색 검증에만 추가하고 원문 메타데이터는 보존한다."""
        enriched = dict(metadata)
        facet = getattr(self, "facet_by_id", {}).get(str(document_id), {})
        for field in (
            "target_area", "exercise_type", "fitness_level", "location", "equipment",
            "disability_type", "health_information",
        ):
            values = sorted(facet.get(field, set()))
            if values:
                enriched[f"facet_{field}"] = values
        enriched["audience"] = facet.get("_audience", "reference")
        enriched["source_role"] = facet.get("_source_role", "reference")
        enriched["facet_basis"] = sorted(facet.get("_derived_fields", set()))
        return enriched

    def semantic_search(
        self,
        question: str,
        k: int = 5,
        datasets: list[str] | None = None,
        min_score: float = MIN_SIMILARITY_SCORE,
    ) -> list[dict[str, Any]]:
        query_vector = self.embed_texts([question])[0]
        where = {"dataset": {"$in": datasets}} if datasets else None
        raw = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(max(k * 5, 20), self.chroma_documents),
            where=where,
        )
        ids = [str(value) for value in raw["ids"][0]]
        distances = raw["distances"][0]
        full_records = self._fetch_full_records(ids)
        results = []
        for document_id, distance in zip(ids, distances):
            score = 1.0 - float(distance)
            if score < min_score:
                continue
            record = full_records.get(document_id)
            if record is None:
                continue
            result = {
                    "id": document_id,
                    "dataset": record["dataset"],
                    "title": record["title"],
                    "text": record["content"],
                    "metadata": self._metadata_with_facets(
                        document_id, json.loads(record["metadata_json"])
                    ),
                    "occurrence_count": record["occurrence_count"],
                    "score": score,
                }
            exercise_name = result["metadata"].get("exercise_name") or result["title"]
            linked = self.exercise_detail_index.get(_exercise_key(exercise_name))
            if linked and str(linked.get("document_id")) != document_id:
                result["linked_detail_id"] = linked["document_id"]
                result["linked_detail_text"] = linked["text"]
            results.append(result)
        results.sort(key=lambda item: item["score"], reverse=True)
        selected = results[:k]
        LOGGER.info(
            "RAG search query=%r requested_k=%d raw=%d above_threshold=%d datasets=%s top_score=%s",
            question,
            k,
            len(ids),
            len(results),
            datasets or "all",
            round(selected[0]["score"], 4) if selected else None,
        )
        return selected

    def health(self) -> dict[str, Any]:
        qwen3 = self.qwen3_client.healthcheck()
        return {
            "status": "ok",
            "sqlite_documents": self.sqlite_documents,
            "chroma_documents": self.chroma_documents,
            "source_dataset_count": self.source_dataset_count,
            "total_source_rows": self.total_source_rows,
            "rag_dataset_count": len(self.rag_datasets),
            "rag_datasets": self.rag_datasets,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "qwen3_ready": bool(qwen3.get("data") or qwen3.get("models")),
            "generation_model": "Qwen3-4B-Q4_K_M.gguf",
            "harness_version": "5.6.0-qwen3-general-exercise-chat",
            "chat_policy": {"thinking": False, "max_sentences": 5, "max_sentence_chars": 80,
                "facts": "source_bound_python", "model_role": "question_intent_and_labelled_interpretation"},
            "age_bmi_recommendation_rules": int(self.age_bmi_rule_status.get("row_count", 0)),
            "index_scope": "full" if self.chroma_documents == self.sqlite_documents else "sample",
            "note": (
                "전체 RAG 인덱스입니다."
                if self.chroma_documents == self.sqlite_documents
                else "현재 ChromaDB는 2,000건 표본 인덱스입니다."
            ),
        }

    def options(self, selection: dict[str, str] | None = None) -> dict[str, Any]:
        current = selection or {}
        options = dict(self.rag_options)
        options.update(self._faceted_rag_options(current))
        disability_mode = str(current.get("disability_type") or "").strip() not in {"", "없음"}
        applicable = DISABILITY_FIELDS if disability_mode else GENERAL_FIELDS
        try:
            severe_pain = int(current.get("pain_level") or 0) >= 7
        except (TypeError, ValueError):
            severe_pain = False
        return {
            "status": "ok",
            "options": options,
            "matching_exercise_count": self._matching_exercise_count(current),
            "rag_fields": [
                "age_group", "sex", "pain_area", "health_information", "target_area",
                "exercise_type", "fitness_level", "location", "equipment", "disability_type",
            ],
            "constraint_fields": [
                "height_cm", "weight_kg", "available_time",
            ],
            "recommendation_mode": "disability" if disability_mode else "general",
            "facet_policy": {
                "applied": sorted(applicable),
                "not_applicable": (
                    ["fitness_level", "location", "available_time", "health_information"]
                    if disability_mode else []
                ),
                "note": (
                    "통증 정도가 7 이상이어서 운동 추천을 중단합니다. 현재 증상은 운동 선택보다 전문가 확인이 우선입니다."
                    if severe_pain else
                    "장애 유형·연령·성별과 운동명 기반 부위·유형·장비로 검색합니다. 장애인 처방 원문에는 질환 연결 필드와 영상 URL이 없어 건강 목적이나 일반 영상을 임의로 결합하지 않습니다."
                    if disability_mode
                    else "통증이 있는 부위는 운동 목표 부위에서 제외하고, 건강 목적을 선택하면 같은 목적이 직접 표시된 운동만 남깁니다. 위에서 아래로 선택할수록 다음 목록은 앞 조건을 모두 만족하는 운동만 남깁니다. 괄호 숫자는 중복 제거 운동 수입니다."
                ),
            },
        }

    def video_link_audit(self, limit: int = 500) -> dict[str, Any]:
        """정확한 운동명 기준으로 공식 영상 URL이 없는 운동을 점검한다.

        비슷한 이름을 자동 연결하지 않는다. 이 목록은 '현재 선택 조건과 맞지
        않는 영상'이 아니라, 원문 운동명 자체가 공식 영상 URL과 연결되지 않은
        항목을 보여 준다.
        """
        video_keys = {
            str(record.get("_link_key") or "")
            for record in self.facet_records
            if record.get("_dataset") == "video_content"
            and str(record.get("_variant_key") or "").startswith("video:")
            and str(record.get("_link_key") or "")
        }
        unlinked: dict[tuple[str, str], dict[str, Any]] = {}
        for record in self.facet_records:
            if record.get("_audience") != "general":
                continue
            dataset = str(record.get("_dataset") or "")
            if dataset not in GENERAL_RECOMMENDATION_DATASETS:
                continue
            # 건강 안내·프로그램 제목처럼 화면의 목표 부위/운동 유형으로 실제
            # 선택할 수 없는 참고 문서는 제외한다. 이 목록은 추천 화면에서
            # 선택 가능한 개별 운동의 영상 연결 상태를 확인하는 용도다.
            if not record.get("target_area") or not record.get("exercise_type"):
                continue
            name = display_name(record.get("_exercise_name"))
            key = _rule_exercise_key(name)
            if not name or not key or key in video_keys:
                continue
            reason = (
                "공식 영상 원문에 영상 URL 없음"
                if dataset == "video_content"
                else "정규화 후 같은 운동명의 공식 영상 URL 없음"
            )
            item_key = (key, reason)
            item = unlinked.setdefault(item_key, {
                "exercise_name": name,
                "reason": reason,
                "datasets": set(),
                "target_areas": set(),
                "exercise_types": set(),
                "stages": set(),
            })
            item["datasets"].add(dataset)
            item["target_areas"].update(record.get("target_area") or set())
            item["exercise_types"].update(record.get("exercise_type") or set())
            item["stages"].update(record.get("exercise_stage") or {"본운동"})
        items = []
        for item in unlinked.values():
            items.append({
                "exercise_name": item["exercise_name"],
                "reason": item["reason"],
                "datasets": sorted(item["datasets"]),
                "target_areas": sorted(item["target_areas"]),
                "exercise_types": sorted(item["exercise_types"]),
                "stages": sorted(item["stages"]),
            })
        items.sort(key=lambda item: (item["exercise_name"], item["reason"]))
        with sqlite3.connect(sqlite_readonly_uri(RAG_DATABASE), uri=True) as connection:
            videos = connection.execute("SELECT DISTINCT title,content FROM documents WHERE dataset='video_content'").fetchall()
        items = organize_video_audit(items, videos)
        related_count = sum(bool(item["related_videos"]) for item in items)
        return {
            "status": "ok",
            "policy": "공식 설명문 일치, 검증된 원문 이름 대응 및 사용자가 승인한 유사 운동만 관련 자료로 묶습니다. 원문의 세부 운동명·연령·도구와 유사 연결 근거를 유지합니다. 일반적인 문자열 유사도만으로는 자동 연결하지 않습니다.",
            "reviewed_count": len(items),
            "related_count": related_count,
            "unlinked_count": len(items) - related_count,
            "items": items[:limit],
            "truncated": len(items) > limit,
        }

    def _exact_alternatives(self, profile: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
        target = str(profile.get("target_area") or "").strip()
        health = str(profile.get("health_information") or "").strip()
        if not target:
            return []
        conditions = ["d.dataset='video_content'", "d.content LIKE ?"]
        parameters: list[str | int] = [f"%{target}%"]
        if health and health != "없음":
            conditions.append("f.health_information_json LIKE ?")
            parameters.append(f"%{health}%")
        parameters.append(limit * 10)
        query = (
            "SELECT d.title,d.content,d.metadata_json FROM documents d "
            "JOIN document_facets f ON f.document_id=d.id WHERE "
            + " AND ".join(conditions)
            + " ORDER BY occurrence_count DESC LIMIT ?"
        )
        alternatives: list[dict[str, Any]] = []
        seen: set[str] = set()
        with sqlite3.connect(sqlite_readonly_uri(RAG_DATABASE), uri=True) as connection:
            for title, content, metadata_json in connection.execute(query, parameters):
                if title in seen:
                    continue
                seen.add(str(title))
                metadata = json.loads(metadata_json or "{}")
                equipment_match = re.search(r"운동 도구\s*:\s*([^\n]+)", str(content))
                alternatives.append({
                    "title": str(title),
                    "age_group": normalize_age_group(metadata.get("age_group")) or "정보 없음",
                    "fitness_levels": sorted(difficulty_levels(metadata.get("difficulty"))),
                    "location": str(metadata.get("place") or "정보 없음"),
                    "equipment": equipment_match.group(1).strip() if equipment_match else "없음/정보 없음",
                })
                if len(alternatives) >= limit:
                    break
        return alternatives

    def _video_options(
        self, profile: dict[str, Any], exercise_name: str = "", limit: int = 20
    ) -> list[dict[str, Any]]:
        """선택 조건 행의 공식 영상을 URL 기준으로 중복 제거해 반환한다.

        추천 운동명과 정규화 후 정확히 일치하는 영상만 표시한다. 난이도 1~2는
        초급, 3은 중급, 4~5는 고급으로 분류한다. 1~5와 난이도 미표기는
        초·중·고와 섞지 않고 '종합'으로 분류한다.
        URL이 같은 다른 원문 행은 먼저 섞지 않는다. 특히 난이도·장소·장비
        미표기 행이 표기 행과 합쳐져 선택 조건에서 사라지는 일을 막는다.
        """
        if str(profile.get("disability_type") or "").strip() not in {"", "없음"}:
            return []
        expected_age = normalize_age_group(profile.get("age_group"))
        expected_sex = str(profile.get("sex") or "").strip().upper()
        expected_target = str(profile.get("target_area") or "").strip()
        expected_type = str(profile.get("exercise_type") or "").strip()
        expected_level = str(profile.get("fitness_level") or "").strip()
        expected_location = str(profile.get("location") or "").strip()
        expected_equipment = str(profile.get("equipment") or "").strip()
        expected_health = str(profile.get("health_information") or "").strip()
        expected_exercise_key = _rule_exercise_key(exercise_name)
        no_equipment = expected_equipment in {"", "없음", "맨몸", "무장비"}

        matched_facets: dict[str, dict[str, Any]] = {}
        for record in self.facet_records:
            if record.get("_dataset") != "video_content" or record.get("_audience") != "general":
                continue
            ages = set(record.get("age_group") or set())
            sexes = set(record.get("sex") or set())
            targets = set(record.get("target_area") or set())
            exercise_types = set(record.get("exercise_type") or set())
            levels = set(record.get("fitness_level") or set())
            locations = set(record.get("location") or set())
            equipment = set(record.get("equipment") or set())
            health = set(record.get("health_information") or set())
            if expected_age and ages and expected_age not in ages and "공통" not in ages:
                continue
            if expected_sex in {"M", "F"} and sexes and expected_sex not in sexes:
                continue
            if expected_target and expected_target not in targets:
                continue
            if expected_type and expected_type not in exercise_types:
                continue
            if expected_health not in {"", "없음"} and expected_health not in health:
                continue
            # URL별 묶음 전에 각 원문 행의 조건을 판정한다. 1~5와 미표기는
            # '종합'에서만, 초·중·고는 전용 표기 원문에서만 사용한다.
            composite = str(record.get("_fitness_group") or "") == "종합" or _is_composite_difficulty(levels)
            if expected_level == "종합":
                if not composite:
                    continue
            elif expected_level:
                if composite or expected_level not in levels:
                    continue
            if expected_location and expected_location not in locations:
                continue
            if no_equipment:
                if equipment:
                    continue
            elif expected_equipment not in equipment:
                continue
            matched_facets[str(record["_id"])] = {
                "ages": ages, "levels": levels, "locations": locations,
                "equipment": equipment,
            }

        full_records = self._fetch_full_records(list(matched_facets))
        grouped: dict[str, dict[str, Any]] = {}
        for document_id, facets in matched_facets.items():
            source = full_records.get(document_id)
            if source is None:
                continue
            metadata = json.loads(source["metadata_json"] or "{}")
            content = str(source["content"] or "")
            detail = _rag_detail({"title": source["title"], "text": content})
            if expected_exercise_key and _rule_exercise_key(
                detail.get("운동명") or source["title"]
            ) != expected_exercise_key:
                continue
            video_url = str(metadata.get("video_url") or detail.get("영상 URL") or "").strip()
            if not video_url:
                continue
            item = grouped.setdefault(video_url, {
                "title": str(source["title"]), "url": video_url,
                "descriptions": set(), "ages": set(), "levels": set(),
                "locations": set(), "equipment": set(), "week_number": None,
                "source_refs": {},
            })
            source_file = str(metadata.get("source_file") or "").strip()
            row_num = metadata.get("row_num")
            if source_file:
                source_key = f"{source_file}\u0000{row_num if row_num is not None else ''}"
                item["source_refs"][source_key] = {
                    "source_file": source_file,
                    "row_num": row_num,
                    "document_id": str(document_id),
                }
            description = str(detail.get("설명") or "").strip()
            if description:
                item["descriptions"].add(description)
            item["ages"].update(facets["ages"])
            item["levels"].update(facets["levels"])
            item["locations"].update(facets["locations"])
            item["equipment"].update(facets["equipment"])
            week_match = re.search(r"(\d+)\s*주차", f"{source['title']} {description}")
            if week_match:
                item["week_number"] = int(week_match.group(1))

        options: list[dict[str, Any]] = []
        for item in grouped.values():
            levels = sorted(item["levels"])
            locations = sorted(item["locations"])
            equipment = sorted(item["equipment"])
            notes = [
                "종합 난이도" if expected_level == "종합"
                else "선택 난이도 명시" if expected_level and expected_level in levels
                else "난이도 정보 없음"
            ]
            options.append({
                "title": item["title"], "url": item["url"],
                "description": sorted(item["descriptions"])[0] if item["descriptions"] else "",
                "week": f"{item['week_number']}주차" if item["week_number"] else "",
                "age_group": "/".join(sorted(item["ages"])) or "연령 미표기",
                "fitness_level": "종합" if _is_composite_difficulty(set(item["levels"])) else "/".join(levels),
                "location": "/".join(locations) or "장소 미표기",
                "equipment": "/".join(equipment) or "장비 없음/미표기",
                "condition_note": " · ".join(notes),
                "condition_compatible": True,
                "sources": sorted(
                    item["source_refs"].values(),
                    key=lambda source: (
                        source["source_file"],
                        int(source["row_num"]) if str(source["row_num"] or "").isdigit() else 0,
                        source["document_id"],
                    ),
                ),
                "week_number": item["week_number"],
            })
        options.sort(key=lambda item: (
            0 if "선택 난이도 명시" in item["condition_note"] else 1,
            0 if item["condition_compatible"] else 1,
            item["week_number"] if item["week_number"] is not None else 999,
            item["title"], item["url"],
        ))
        # 같은 조건에 여러 부위가 함께 포함된 영상이 있더라도, 사용자가 고른
        # 부위가 운동명에 직접 적힌 공식 영상이 있으면 그 영상을 우선한다.
        directly_named = [
            item for item in options
            if target_name_focus_score(item["title"], expected_target) >= 4
        ]
        if directly_named:
            options = directly_named
        for item in options:
            item.pop("week_number", None)
        return options[:limit]

    @staticmethod
    def _health_reference_sources(condition: str, limit: int = 3) -> list[dict[str, Any]]:
        """선택한 건강 목적이 구조화 분류로 확인된 원문만 회수한다."""
        condition = str(condition or "").strip()
        if not condition or condition == "없음":
            return []
        with sqlite3.connect(sqlite_readonly_uri(RAG_DATABASE), uri=True) as connection:
            rows = connection.execute(
                "SELECT d.id,d.dataset,d.title,d.content FROM documents d "
                "JOIN document_facets f ON f.document_id=d.id "
                "WHERE d.dataset IN ('video_content','general_prescription','measurement_prescription') "
                "AND f.health_information_json LIKE ? "
                "ORDER BY CASE d.dataset WHEN 'video_content' THEN 0 ELSE 1 END, "
                "LENGTH(d.content) DESC LIMIT ?",
                (f"%{condition}%", limit * 10),
            ).fetchall()
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for document_id, dataset, title, content in rows:
            name = str(title)
            if name in seen:
                continue
            seen.add(name)
            result.append({
                "evidence_id": f"H{len(result) + 1}",
                "document_id": str(document_id), "dataset": str(dataset),
                "title": name, "score": 1.0, "text": str(content)[:900],
            })
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _best_detail_source(
        exercise_name: str,
        sources: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], dict[str, Any] | None]:
        candidates = [dict(source) for source in sources]
        if exercise_name:
            with sqlite3.connect(sqlite_readonly_uri(RAG_DATABASE), uri=True) as connection:
                rows = connection.execute(
                    "SELECT id,dataset,title,content FROM documents "
                    "WHERE dataset='video_content' AND title=? "
                    "ORDER BY LENGTH(content) DESC, occurrence_count DESC LIMIT 50",
                    (exercise_name,),
                ).fetchall()
                if not rows:
                    rows = connection.execute(
                        "SELECT id,dataset,title,content FROM documents "
                        "WHERE dataset='video_content' AND content LIKE ? "
                        "ORDER BY LENGTH(content) DESC, occurrence_count DESC LIMIT 50",
                        (f"%운동명: {exercise_name}%",),
                    ).fetchall()
            known_ids = {str(source.get("document_id")) for source in candidates}
            for document_id, dataset, title, content in rows:
                if str(document_id) in known_ids:
                    continue
                candidates.append({
                    "evidence_id": "D1",
                    "document_id": str(document_id),
                    "dataset": str(dataset),
                    "title": str(title),
                    "score": 1.0,
                    "text": str(content),
                })

        expected_age = normalize_age_group((profile or {}).get("age_group"))
        expected_sex = str((profile or {}).get("sex") or "").strip().upper()
        expected_fitness = str((profile or {}).get("fitness_level") or "").strip()
        expected_location = str((profile or {}).get("location") or "").strip()
        expected_equipment = str((profile or {}).get("equipment") or "").strip()
        expected_disability = str((profile or {}).get("disability_type") or "").strip()
        compatible: list[dict[str, Any]] = []
        for source in candidates:
            detail = _rag_detail(source)
            source_age = normalize_age_group(detail.get("대상 연령군"))
            source_sex = str(detail.get("성별") or "").strip().upper()
            source_levels = difficulty_levels(detail.get("난이도"))
            source_location = str(detail.get("운동 장소") or "").strip()
            source_equipment = str(detail.get("운동 도구") or "").strip()
            source_disability = str(detail.get("장애유형") or "").strip()
            if expected_age and source_age and source_age != "공통" and source_age != expected_age:
                continue
            if expected_sex in {"M", "F"} and source_sex in {"M", "F"} and source_sex != expected_sex:
                continue
            composite = _is_composite_difficulty(source_levels)
            if expected_fitness == "종합":
                if not composite:
                    continue
            elif expected_fitness:
                if composite or expected_fitness not in source_levels:
                    continue
            if expected_location and expected_location not in display_locations(source_equipment, source_location):
                continue
            if expected_equipment in {"없음", "맨몸", "무장비"} and source_equipment and source_equipment not in {"없음", "맨몸", "무장비"}:
                continue
            if expected_equipment not in {"", "없음", "맨몸", "무장비"} and source_equipment and expected_equipment not in source_equipment:
                continue
            if expected_disability not in {"", "없음"} and source_disability != expected_disability:
                continue
            compatible.append(source)

        candidates = compatible
        if not candidates:
            return {}, None
        best = max(
            candidates,
            key=lambda source: (
                len(_rag_detail(source)),
                source.get("dataset") == "video_content",
                len(str(source.get("text") or "")),
            ),
        )
        public_source = dict(best)
        public_source["text"] = str(public_source.get("text") or "")[:1600]
        return _rag_detail(best), public_source

    def answer(self, request: CoachRequest) -> dict[str, Any]:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        profile = request.profile()
        is_disability_recommendation = str(profile.get("disability_type") or "").strip() not in {"", "없음"}
        datasets = recommendation_datasets(profile.get("disability_type"))
        search_profile = dict(profile)
        ignored_conditions: list[str] = []
        if is_disability_recommendation:
            for field in ("fitness_level", "location", "available_time"):
                if search_profile.get(field) not in (None, "", "없음"):
                    ignored_conditions.append(field)
                search_profile[field] = ""
        question = request.effective_question(search_profile)
        if len(question) < 2:
            raise ValueError("RAG 검색 조건을 하나 이상 선택하세요.")
        LOGGER.info(
            "Coach request age=%s sex=%s goal=%r equipment=%r question=%r",
            request.age,
            request.sex,
            request.goal,
            request.equipment,
            question,
        )
        with self.answer_lock:
            answer = self.harness.run(
                question,
                search_profile,
                datasets=datasets,
                output_path=OUTPUT_DIR / "qwen3_grounded_answer.json",
                candidate_k=6,
            )
            trace = dict(self.harness.last_trace)
            health_condition = str(search_profile.get("health_information") or "").strip()
            if health_condition not in {"", "없음"} and not trace.get("health_sources"):
                trace["health_sources"] = self._health_reference_sources(health_condition)
                trace["health_reference_found"] = bool(trace["health_sources"])
                trace["health_source_scope"] = "separate_general_reference"
            elif health_condition not in {"", "없음"}:
                trace["health_reference_found"] = True
                trace["health_source_scope"] = "recommendation_corpus"
            if (
                trace.get("selected_name")
                and not is_disability_recommendation
                and not trace.get("screened_candidates")
                and not trace.get("available_alternatives")
            ):
                trace["available_alternatives"] = self._exact_alternatives(search_profile)
            if is_disability_recommendation:
                # 장애인 원문 자체의 분류값은 표시하되 일반 영상은 덧붙이지 않는다.
                trace["selected_detail"], trace["detail_source"] = self._best_detail_source(
                    "", trace.get("sources", []), search_profile,
                )
            elif trace.get("selected_name"):
                trace["selected_detail"], trace["detail_source"] = self._best_detail_source(
                    str(trace.get("selected_name") or ""), trace.get("sources", []),
                    profile,
                )
                trace["video_options"] = self._video_options(
                    profile, str(trace.get("selected_name") or ""),
                )
                if not trace["video_options"]:
                    with sqlite3.connect(sqlite_readonly_uri(RAG_DATABASE), uri=True) as connection:
                        video_rows = connection.execute("SELECT DISTINCT title,content FROM documents WHERE dataset='video_content'").fetchall()
                    related = organize_video_audit([{"exercise_name": display_name(trace["selected_name"])}], video_rows)
                    trace["related_video_options"] = related[0]["related_videos"]
            if not trace.get("selected_name"):
                # 중단·근거 부족 응답에 다른 운동의 영상과 대안을 붙이지 않는다.
                trace["selected_detail"], trace["detail_source"] = {}, None
                trace["video_options"] = []
                trace["available_alternatives"] = []
            trace["recommendation_mode"] = "disability" if is_disability_recommendation else "general"
            trace["age_bmi_recommendation"] = self._age_bmi_recommendation(profile)
            trace["ignored_conditions"] = ignored_conditions
            trace["facet_policy"] = {
                "mode": trace["recommendation_mode"],
                "applied": sorted(DISABILITY_FIELDS if is_disability_recommendation else GENERAL_FIELDS),
                "ignored": ignored_conditions,
            }
            if (
                (trace.get("selected_name") and trace.get("sources"))
                or trace["age_bmi_recommendation"].get("bmi", {}).get("available")
            ):
                self.chat_contexts[request.user_id] = {
                    "profile": dict(profile),
                    "selected_name": str(trace.get("selected_name") or ""),
                    "sources": [dict(item) for item in trace["sources"]],
                    "detail": dict(trace.get("selected_detail") or {}),
                    "age_bmi_recommendation": dict(trace["age_bmi_recommendation"]),
                }
            else:
                self.chat_contexts.pop(request.user_id, None)
        abstained = sum(value == "제공된 자료만으로는 안전하고 정확한 운동 안내가 어렵습니다." for value in answer.values())
        LOGGER.info("Coach answer completed abstained_fields=%d exercise=%r", abstained, answer.get("운동명"))
        return {"answer": answer, "trace": trace, "profile": profile}

    def _chat_requested_facet(self, message: str, field: str, fallback: str) -> str:
        """질문에 직접 적힌 부위·유형만 현재 조건에서 바꾼다."""
        option_values = [
            str(item.get("value") or "").strip()
            for item in self.rag_options.get(field, [])
            if str(item.get("value") or "").strip()
        ]
        # 화면에서 현재 조합 때문에 선택지에서 사라진 부위도 챗봇 요청에는
        # 들어올 수 있다. 전체 원문 facet을 함께 보아야 '팔 근력'처럼 새 부위를
        # 정확히 인식한 뒤, 아래의 동일 조건 검색으로 가능 여부를 판단할 수 있다.
        record_values = [
            str(value).strip()
            for record in self.facet_records
            for value in record.get(field, [])
            if str(value).strip()
        ]
        values = sorted(set(option_values) | set(record_values), key=len, reverse=True)
        normalized_message = re.sub(r"\s+", "", str(message or ""))
        for value in values:
            if re.sub(r"\s+", "", value) in normalized_message:
                return value
        return fallback

    def _chat_recommendation(self, message: str, context: Mapping[str, Any]) -> dict[str, Any] | None:
        """다음·다른 운동 요청에는 모델 추측 대신 같은 조건의 원문을 다시 찾는다."""
        if not _is_chat_recommendation_request(message):
            return None
        profile = dict(context["profile"])
        original_target = str(profile.get("target_area") or "").strip()
        original_type = str(profile.get("exercise_type") or "").strip()
        original_location = str(profile.get("location") or "").strip()
        target = self._chat_requested_facet(message, "target_area", original_target)
        exercise_type = self._chat_requested_facet(message, "exercise_type", original_type)
        location = self._chat_requested_facet(message, "location", original_location)
        if not target:
            return None
        profile["target_area"] = target
        profile["exercise_type"] = exercise_type
        profile["location"] = location
        for field in ("exercise_stage", "fitness_level", "equipment"):
            profile[field] = self._chat_requested_facet(
                message, field, str(profile.get(field) or "")
            )
        if re.search(r"(도구|장비)\s*(없이|없음|없는|없어)", message) or "맨몸" in message:
            profile["equipment"] = "없음"
        allowed_datasets = set(recommendation_datasets(profile.get("disability_type")))
        selection = {field: str(profile.get(field) or "").strip() for field in RAG_FACET_FIELDS}
        matched = [
            record for record in self.facet_records
            if record.get("_dataset") in allowed_datasets
            and self._facet_record_matches(record, selection, "__none__")
        ]
        ids = [str(record["_id"]) for record in matched[:200]]
        full_records = self._fetch_full_records(ids)
        selected_key = _exercise_key(context.get("selected_name"))
        candidates: list[dict[str, Any]] = []
        for document_id in ids:
            record = full_records.get(document_id)
            if record is None:
                continue
            candidate = {
                "id": document_id,
                "dataset": str(record["dataset"]),
                "title": str(record["title"]),
                "text": str(record["content"]),
                "metadata": self._metadata_with_facets(
                    document_id, json.loads(record["metadata_json"])
                ),
                "score": 1.0,
            }
            detail = _rag_detail(candidate)
            if _exercise_key(detail.get("운동명") or candidate["title"]) == selected_key:
                continue
            candidates.append(candidate)
        if not candidates:
            # 사용자가 장비 없음을 선택한 경우에는 다른 장비가 필요한 실제 자료를
            # '없다'고만 말하지 않는다. 다만 현재 조건과 일치하는 추천으로 바꾸지 않고,
            # 필요한 장비를 명시한 참고 후보로만 안내한다.
            equipment = str(profile.get("equipment") or "").strip()
            if equipment in {"없음", "맨몸", "무장비"}:
                relaxed_selection = dict(selection)
                relaxed_selection["equipment"] = ""
                relaxed_selection["fitness_level"] = ""
                relaxed_records = [
                    record for record in self.facet_records
                    if record.get("_dataset") in allowed_datasets
                    and self._facet_record_matches(record, relaxed_selection, "__none__")
                ]
                relaxed_ids = [str(record["_id"]) for record in relaxed_records[:200]]
                relaxed_full_records = self._fetch_full_records(relaxed_ids)
                relaxed_candidates: list[dict[str, Any]] = []
                for document_id in relaxed_ids:
                    record = relaxed_full_records.get(document_id)
                    if record is None:
                        continue
                    candidate = {
                        "id": document_id,
                        "dataset": str(record["dataset"]),
                        "title": str(record["title"]),
                        "text": str(record["content"]),
                        "metadata": self._metadata_with_facets(
                            document_id, json.loads(record["metadata_json"])
                        ),
                        "score": 1.0,
                    }
                    detail = _rag_detail(candidate)
                    if _exercise_key(detail.get("운동명") or candidate["title"]) != selected_key:
                        relaxed_candidates.append(candidate)
                if relaxed_candidates:
                    relaxed_candidates.sort(
                        key=lambda item: (
                            target_name_focus_score(_rag_detail(item).get("운동명") or item["title"], target),
                            item["dataset"] == "video_content",
                            len(_rag_detail(item)),
                        ),
                        reverse=True,
                    )
                    candidate = relaxed_candidates[0]
                    detail = _rag_detail(candidate)
                    name = detail.get("운동명") or str(candidate["title"])
                    required_equipment = detail.get("운동 도구") or "원문 장비 정보"
                    source_level = detail.get("난이도")
                    evidence_numbers = [
                        int(match.group(1)) for source in context.get("sources", [])
                        for match in [re.fullmatch(r"E(\d+)", str(source.get("evidence_id") or ""))]
                        if match
                    ]
                    source = {
                        "evidence_id": f"E{max(evidence_numbers, default=0) + 1}",
                        "document_id": candidate["id"],
                        "dataset": candidate["dataset"],
                        "title": str(candidate["title"]),
                        "score": 1.0,
                        "text": str(candidate["text"])[:900],
                    }
                    if source_level:
                        answer = (
                            f"현재 ‘장비 없음’과 선택 난이도 조건에는 맞지 않지만, {location} {target} {exercise_type} 자료로 "
                            f"‘{name}’가 있고 원문 장비는 {required_equipment}, 난이도 표기는 {source_level}예요 [{source['evidence_id']}]. "
                            "장비와 난이도를 이 원문 값으로 선택하면 해당 자료를 조건에 맞춰 다시 확인할 수 있어요."
                        )
                    else:
                        answer = (
                            f"현재 ‘장비 없음’ 조건에는 맞지 않지만, {location} {target} {exercise_type} 자료로 "
                            f"‘{name}’가 있고 원문 장비는 {required_equipment}예요 [{source['evidence_id']}]. "
                            "이 원문에는 난이도 표기가 없어 현재 선택 난이도와의 일치는 확인할 수 없어요."
                        )
                    return {
                        "answer": answer,
                        "sources": [source],
                        "context_ready": True,
                    }
            normalized_message = re.sub(r"\s+", "", str(message or ""))
            continuation = any(
                term.replace(" ", "") in normalized_message
                for term in ("다음", "그다음", "이어서", "이어", "계속", "다른 운동", "또 다른")
            )
            if continuation and target == original_target:
                answer = (
                    f"현재 선택 조건에는 ‘{context['selected_name']}’ 외에 다른 {target} 운동 자료가 없어요. "
                    "다음으로 보고 싶은 부위를 말씀해 주시면 그 부위의 실제 RAG 자료를 다시 찾아드릴게요."
                )
            else:
                constraints = [
                    str(profile.get(field) or "").strip()
                    for field in ("fitness_level", "location", "equipment")
                    if str(profile.get(field) or "").strip()
                ]
                suffix = f" 현재 난이도·장소·장비 조건은 {' · '.join(constraints)}입니다." if constraints else ""
                answer = f"현재 선택 조건과 모두 일치하는 {target} 운동 원문 자료를 찾지 못했어요.{suffix}"
            return {
                "answer": answer,
                "sources": [],
                "context_ready": True,
            }
        candidates.sort(
            key=lambda item: (
                target_name_focus_score(_rag_detail(item).get("운동명") or item["title"], target),
                item["dataset"] == "video_content",
                len(_rag_detail(item)),
            ),
            reverse=True,
        )
        candidate = candidates[0]
        detail = _rag_detail(candidate)
        name = detail.get("운동명") or str(candidate["title"])
        evidence_numbers = [
            int(match.group(1)) for source in context.get("sources", [])
            for match in [re.fullmatch(r"E(\d+)", str(source.get("evidence_id") or ""))]
            if match
        ]
        source = {
            "evidence_id": f"E{max(evidence_numbers, default=0) + 1}",
            "document_id": candidate["id"],
            "dataset": candidate["dataset"],
            "title": str(candidate["title"]),
            "score": 1.0,
            "text": str(candidate["text"])[:900],
        }
        changed = target != original_target or exercise_type != original_type or location != original_location
        focus = f"{location} {target} {exercise_type}".strip() if changed else f"다른 {target}".strip()
        return {
            "answer": f"현재 선택 조건에 맞는 {focus} 자료로 ‘{name}’가 있어요 [{source['evidence_id']}]",
            "sources": [source],
            "context_ready": True,
            "_next_context": {
                **context, "profile": profile, "selected_name": name,
                "sources": [source], "detail": detail, "dialogue_state": {},
            },
        }

    def chat(self, request: ChatRequest) -> dict[str, Any]:
        with self.answer_lock:
            context = self.chat_contexts.get(request.user_id)
            if not context:
                context = {"profile": {}, "selected_name": "", "sources": [], "detail": {}}
                self.chat_contexts[request.user_id] = context
            safety = safety_update(request.message, context.get("profile", {}))
            if safety:
                context["profile"] = safety["profile"]
                context["safety_pending"] = True
                context["dialogue_state"] = {}
                return {"answer": safety["answer"], "sources": [], "context_ready": True}
            if context.get("safety_pending"):
                return {"answer": SAFETY_MESSAGE, "sources": [], "context_ready": True}
            age_bmi_answer = self._chat_age_bmi_recommendation(request.message, context)
            if age_bmi_answer is not None:
                return age_bmi_answer
            if use_general(request.message, context):
                return answer_general(self.harness.client, request.message, request.history, context)
            context["chat_mode"] = "selected"
            recommendation = self._chat_recommendation(request.message, context)
            if recommendation is not None:
                next_context = recommendation.pop("_next_context", None)
                if next_context is not None:
                    self.chat_contexts[request.user_id] = next_context
                return recommendation
            try:
                answer = self.harness.chat(
                    request.message,
                    request.history,
                    context["profile"],
                    context["selected_name"],
                    context["sources"],
                    context["detail"],
                    context.setdefault("dialogue_state", {}),
                )
            except (ConnectionError, RuntimeError, ValueError) as exc:
                LOGGER.warning("Chat model response failed; using grounded fallback: %s", exc)
                answer = self.harness._chat_fallback(
                    request.message,
                    context["selected_name"],
                    context["sources"],
                    context["detail"],
                )
            cited_ids = set(re.findall(r"E\d+", answer))
            sources = [
                source for source in context["sources"]
                if source.get("evidence_id") in cited_ids
            ]
            return {"answer": answer, "sources": sources, "context_ready": True,
                "guidance_sources": context.get("dialogue_state", {}).get("guidance_sources", [])}


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_percentile_database(PERCENTILE_DATABASE)
    app.state.runtime = await asyncio.to_thread(RagRuntime)
    yield


app = FastAPI(
    title="AI 체력 코치 로컬 서버",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(fitness_mvp_router)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    if not FRONTEND_FILE.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Frontend HTML file not found: {FRONTEND_FILE}",
        )
    return FRONTEND_FILE.read_text(encoding="utf-8")


@app.get("/video-player", response_class=HTMLResponse)
def video_player(url: str, title: str = "공식 운동 영상") -> str:
    try:
        return _video_player_page(url, title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/health")
async def health() -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(app.state.runtime.health)
        result["fitness_package_db"] = str(FITNESS_PACKAGE_DB)
        result["fitness_user_db"] = str(FITNESS_USER_DB)
        result["fitness_mvp_ready"] = FITNESS_PACKAGE_DB.is_file() and FITNESS_USER_DB.is_file()
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/center-percentile-status")
async def center_percentile_status() -> dict[str, Any]:
    """홈 입력값과 센터 원시기록 규준을 혼동하지 않도록 상태를 명시한다."""
    return await asyncio.to_thread(percentile_status, PERCENTILE_DATABASE)


@app.get("/api/age-bmi-recommendation-status")
async def age_bmi_recommendation_status() -> dict[str, Any]:
    return await asyncio.to_thread(rule_status, AGE_BMI_RULE_DATABASE)


@app.get("/api/center-percentile-inputs")
async def center_percentile_inputs(age: int) -> dict[str, Any]:
    try:
        measures = await asyncio.to_thread(available_input_measures, PERCENTILE_DATABASE, age)
        return {"input_label": "홈체력측정 입력값", "result_label": RESULT_LABEL, "measures": measures}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/center-percentiles")
async def center_percentiles(request: PercentileRequest) -> dict[str, Any]:
    try:
        results = await asyncio.to_thread(
            lookup_percentiles, PERCENTILE_DATABASE, request.age, request.sex, request.measurements,
        )
        return {"input_label": "홈체력측정 입력값", "result_label": RESULT_LABEL, "results": results}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/options")
async def options() -> dict[str, Any]:
    return await asyncio.to_thread(app.state.runtime.options)


@app.post("/api/options")
async def filtered_options(request: OptionRequest) -> dict[str, Any]:
    return await asyncio.to_thread(app.state.runtime.options, request.model_dump())


@app.get("/api/video-link-audit")
async def video_link_audit() -> dict[str, Any]:
    return await asyncio.to_thread(app.state.runtime.video_link_audit)


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(app.state.runtime.chat, request)
        return {"status": "ok", **result}
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"챗봇 실행 실패: {exc}") from exc


@app.post("/api/coach")
async def coach(request: CoachRequest) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(app.state.runtime.answer, request)
        cited_ids = set(
            re.findall(r"E\d+", json.dumps(result["answer"], ensure_ascii=False))
        )
        cited_sources = [
            source
            for source in result["trace"].get("sources", [])
            if source.get("evidence_id") in cited_ids
        ]
        detail_source = result["trace"].get("detail_source")
        if detail_source and detail_source.get("document_id") not in {
            source.get("document_id") for source in cited_sources
        }:
            cited_sources.append(detail_source)
        friendly_copy = _friendly_result_copy(result["profile"], result["trace"])
        detail_notices = [
            _target_focus_notice(result["profile"], result["trace"]),
            _detail_notice(result["trace"].get("selected_detail", {})),
        ]
        return {
            "status": "ok",
            "answer": result["answer"],
            "applied_fitness_level": result["profile"].get("fitness_level"),
            "exercise_details": result["trace"].get("selected_detail", {}),
            "detail_notice": " ".join(notice for notice in detail_notices if notice),
            "video_options": result["trace"].get("video_options", []),
            "related_video_options": result["trace"].get("related_video_options", []),
            "bmi_recommendation": result["trace"].get("age_bmi_recommendation", {}),
            **friendly_copy,
            "sources": cited_sources,
            "health_sources": result["trace"].get("health_sources", []),
            "disability_sources": result["trace"].get("disability_sources", []),
            "retrieval": {
                "recommendation_mode": result["trace"].get("recommendation_mode", "general"),
                "raw_candidates": result["trace"].get("raw_candidates", 0),
                "structured_candidates": result["trace"].get("structured_candidates", 0),
                "screened_candidates": result["trace"].get("screened_candidates", 0),
                "selected_name": result["trace"].get("selected_name"),
                "candidate_selection": result["trace"].get("candidate_selection", {}),
                "relaxed_fields": result["trace"].get("relaxed_fields", []),
                "health_context_separated": result["trace"].get("health_context_separated", False),
                "health_condition": result["trace"].get("health_condition", ""),
                "health_condition_verified": result["trace"].get("health_condition_verified", False),
                "health_reference_found": result["trace"].get("health_reference_found", False),
                "health_source_scope": result["trace"].get("health_source_scope", ""),
                "disability_context_separated": result["trace"].get("disability_context_separated", False),
                "disability_condition": result["trace"].get("disability_condition", ""),
                "ignored_conditions": result["trace"].get("ignored_conditions", []),
                "facet_policy": result["trace"].get("facet_policy", {}),
                "available_alternatives": result["trace"].get("available_alternatives", []),
                "evidence_candidates": len(result["trace"].get("sources", [])),
            },
        }
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"하네스 실행 실패: {exc}") from exc


HTML_PAGE = r'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AI 체력 코치</title>
  <style>
    :root { color-scheme: light; --navy:#16324f; --blue:#2878c7; --pale:#eef6fc; --line:#d5e1eb; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Malgun Gothic",system-ui,sans-serif; background:#f5f8fb; color:#17212b; }
    header { background:linear-gradient(120deg,var(--navy),#245b86); color:white; padding:28px 24px; }
    header div { max-width:1080px; margin:auto; }
    h1 { margin:0 0 8px; font-size:28px; } header p { margin:0; opacity:.88; }
    main { max-width:1080px; margin:24px auto; padding:0 18px 40px; display:grid; grid-template-columns:1fr 1fr; gap:20px; }
    section { background:white; border:1px solid var(--line); border-radius:14px; padding:20px; box-shadow:0 5px 18px #16324f12; }
    h2 { margin:0 0 16px; font-size:19px; color:var(--navy); }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    label { display:block; font-size:13px; font-weight:700; margin-bottom:5px; }
    input,select,textarea { width:100%; border:1px solid #bdcbd8; border-radius:8px; padding:10px; font:inherit; background:white; }
    textarea { min-height:82px; resize:vertical; }
    .wide { grid-column:1/-1; }
    button { width:100%; margin-top:14px; border:0; border-radius:9px; padding:13px; color:white; background:var(--blue); font-weight:800; font-size:15px; cursor:pointer; }
    .condition-group button { margin-top:12px; }
    button:disabled { opacity:.55; cursor:wait; }
    #health { padding:10px 12px; border-radius:8px; background:var(--pale); margin-bottom:14px; font-size:13px; }
    #option-note { padding:10px 12px; border-radius:8px; background:#fff8e8; margin-bottom:14px; font-size:12px; line-height:1.55; }
    .source-tag { color:#47718f; font-size:11px; font-weight:400; }
    .condition-group { grid-column:1/-1; border:1px solid var(--line); border-radius:11px; padding:13px; background:#fbfdff; }
    .condition-group + .condition-group { margin-top:2px; }
    .condition-group h3 { margin:0 0 5px; color:var(--navy); font-size:15px; }
    .condition-group > p { margin:0 0 12px; color:#52687a; font-size:12px; line-height:1.45; }
    .check-row { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:700; }
    .check-row input { width:auto; }
    .result-heading { margin:18px 0 9px; padding-top:14px; border-top:2px solid var(--line); color:var(--navy); font-size:16px; }
    .result-heading:first-child { margin-top:0; padding-top:0; border-top:0; }
    .field { border-top:1px solid var(--line); padding:13px 0; }
    .field:first-child { border-top:0; } .field strong { display:block; color:var(--navy); margin-bottom:6px; }
    .sources { margin-top:18px; padding-top:14px; border-top:2px solid var(--line); }
    .source { margin-top:10px; padding:11px; border-radius:8px; background:var(--pale); font-size:12px; line-height:1.55; white-space:pre-wrap; }
    .quick-filter-grid { display:grid; gap:8px; margin:10px 0; }
    .quick-filter-grid>div { display:flex; flex-wrap:wrap; gap:8px 14px; align-items:center; border-top:1px solid var(--line); padding:8px 0; }
    .quick-filter-grid strong { min-width:76px; }.quick-filter-grid label { white-space:nowrap; }
    .source strong { display:block; margin-bottom:5px; color:var(--navy); }
    .detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:0 16px; margin-top:8px; }
    .detail-row { border-top:1px solid var(--line); padding:10px 0; }
    .detail-row strong { display:block; color:var(--navy); font-size:12px; margin-bottom:4px; }
    details { margin-top:16px; border-top:1px solid var(--line); padding-top:12px; }
    summary { cursor:pointer; color:var(--navy); font-weight:700; }
    #empty { color:#657786; line-height:1.7; }
    #error { display:none; color:#a32929; background:#fff0f0; padding:12px; border-radius:8px; white-space:pre-wrap; }
    .chat-panel { margin-top:24px; padding-top:18px; border-top:2px solid var(--line); }
    .chat-panel h2 { margin-bottom:6px; }
    .chat-note { margin:0 0 12px; color:#657786; font-size:12px; line-height:1.5; }
    .chat-messages { min-height:110px; max-height:360px; overflow:auto; padding:10px; border:1px solid var(--line); border-radius:10px; background:#f8fbfd; }
    .chat-message { max-width:88%; margin:8px 0; padding:10px 12px; border-radius:12px; line-height:1.55; white-space:pre-wrap; }
    .chat-message.user { margin-left:auto; color:white; background:var(--blue); }
    .chat-message.assistant { background:white; border:1px solid var(--line); }
    .chat-source { margin-top:6px; color:#47718f; font-size:11px; }
    .chat-form { display:flex; gap:8px; margin-top:10px; }
    .chat-form input { flex:1; }
    .chat-form button { width:auto; min-width:76px; }
    .percentile-preview { margin:0 0 16px; padding:13px; border:1px solid #bfd3e3; border-radius:11px; background:#f7fbff; }
    .percentile-preview summary { font-size:15px; }
    .percentile-preview p { margin:9px 0; font-size:12px; line-height:1.55; color:#455d70; }
    .percentile-preview ul { margin:8px 0 0; padding-left:20px; font-size:12px; line-height:1.7; }
    .percentile-pending { color:#8b5a00; font-weight:700; }
    .percentile-inputs { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:12px; }
    .measurement-target { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:10px 0; }
    .measurement-target label { font-size:12px; }
    .measurement-target.single { grid-template-columns:1fr; }
    .hidden-age-group { display:none; }
    .percentile-inputs label { font-size:12px; }
    .percentile-inputs input { padding:8px; }
    .percentile-form button { margin-top:10px; padding:10px; font-size:13px; }
    .percentile-results { margin-top:12px; font-size:12px; line-height:1.6; }
    .percentile-row { padding:8px 0; border-top:1px solid #d7e3ec; }
    footer { max-width:1080px; margin:auto; padding:0 18px 28px; color:#667; font-size:12px; }
    @media(max-width:800px){ main{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.wide{grid-column:auto} }
  </style>
</head>
<body>
<header><div><h1>AI 체력 코치</h1><p>로컬 Qwen3 4B Q4_K_M · ChromaDB · 근거 제한 하네스</p></div></header>
<main>
  <section>
    <h2>연동형 RAG 조건 선택</h2>
    <div id="health">서버 상태 확인 중…</div>
    <div id="profile-inputs" class="grid">
      <div><label>성별 <span class="source-tag">RAG</span></label><select id="sex" required></select></div>
      <div><label for="age">만 나이</label><input id="age" type="number" min="1" max="120" value="30" required></div>
      <div><label>키(cm) <span class="source-tag">사용자 조건</span></label><input id="height_cm" type="number" min="80" max="250" step="0.1" value="170" required></div>
      <div><label>체중(kg) <span class="source-tag">사용자 조건</span></label><input id="weight_kg" type="number" min="20" max="300" step="0.1" value="65" required></div>
    </div>
    <details class="percentile-preview" open>
      <summary>홈 체력측정 <span class="source-tag">입력값은 센터 결과가 아닙니다</span></summary>
      <p><strong>보유 센터 측정 원시기록 기준 상위 비율</strong><br>홈 체력측정으로 입력한 값을, 보유한 센터 측정 원시기록의 같은 성별·연령대 분포와 비교합니다. 좋은 기록일수록 상위 0%에, 낮은 기록일수록 상위 100%에 가까워집니다. 국민체력100 인증등급이나 공식 백분위가 아닙니다.</p>
      <h3 id="measurement-age-heading">연령군별 홈 체력측정</h3>
      <p id="measurement-age-note">만 나이를 입력하면 해당 연령군의 측정 항목만 표시됩니다.</p>
      <div class="measurement-target single">
        <div><label for="measurement-age-group">연령군</label><select id="measurement-age-group"><option value="youth">유소년 (만 11~12세)</option><option value="teen">청소년 (만 13~18세)</option><option value="adult">성인 (만 19~64세)</option><option value="senior">어르신 (만 65세 이상)</option></select></div>
      </div>
      <div id="percentile-status" class="percentile-pending">규준 테이블 상태를 확인하는 중…</div>
      <form id="percentile-form" class="percentile-form">
        <div id="percentile-inputs" class="percentile-inputs"></div>
        <button id="percentile-submit" type="submit">백분위 확인</button>
      </form>
      <div id="percentile-results" class="percentile-results" aria-live="polite"></div>
    </details>
    <div id="option-note">RAG 데이터의 실제 선택값을 불러오는 중입니다…</div>
    <details id="video-link-audit" class="sources">
      <summary>운동·공식 영상 미연동 항목 점검</summary>
      <div id="video-link-audit-body" class="source">목록을 열면 원문 운동명 기준 점검 결과를 불러옵니다.</div>
    </details>
    <details id="quick-filter" class="sources" hidden aria-hidden="true">
      <summary>간편 필터 · LLM 응답 시험용</summary>
      <div class="source">시범 화면입니다. 체크한 조건을 한 문장 질문으로 만들어 챗봇 입력칸에 넣습니다. 원문 RAG의 상세 추천 조건은 아래 목록을 사용합니다.</div>
      <div class="quick-filter-grid">
        <div><strong>대상</strong><label><input type="checkbox" data-quick="대상" value="유아기">유아기</label><label><input type="checkbox" data-quick="대상" value="유소년">유소년</label><label><input type="checkbox" data-quick="대상" value="청소년">청소년</label><label><input type="checkbox" data-quick="대상" value="성인">성인</label><label><input type="checkbox" data-quick="대상" value="어르신">어르신</label></div>
        <div><strong>체력항목</strong><label><input type="checkbox" data-quick="체력항목" value="근력/근지구력">근력/근지구력</label><label><input type="checkbox" data-quick="체력항목" value="심폐지구력">심폐지구력</label><label><input type="checkbox" data-quick="체력항목" value="민첩성/순발력">민첩성/순발력</label><label><input type="checkbox" data-quick="체력항목" value="유연성">유연성</label><label><input type="checkbox" data-quick="체력항목" value="평형성">평형성</label><label><input type="checkbox" data-quick="체력항목" value="협응력">협응력</label></div>
        <div><strong>운동부위</strong><label><input type="checkbox" data-quick="운동부위" value="몸통">몸통</label><label><input type="checkbox" data-quick="운동부위" value="상체">상체</label><label><input type="checkbox" data-quick="운동부위" value="전신">전신</label><label><input type="checkbox" data-quick="운동부위" value="하체">하체</label></div>
        <div><strong>운동도구</strong><label><input type="checkbox" data-quick="운동도구" value="맨몸">맨몸</label><label><input type="checkbox" data-quick="운동도구" value="머신">머신</label><label><input type="checkbox" data-quick="운동도구" value="의자">의자</label><label><input type="checkbox" data-quick="운동도구" value="짐볼">짐볼</label><label><input type="checkbox" data-quick="운동도구" value="폼롤러">폼롤러</label><label><input type="checkbox" data-quick="운동도구" value="탄력밴드">탄력밴드</label></div>
        <div><strong>질환</strong><label><input type="checkbox" data-quick="질환" value="고혈압">고혈압</label><label><input type="checkbox" data-quick="질환" value="요통">요통</label><label><input type="checkbox" data-quick="질환" value="골다공증">골다공증</label><label><input type="checkbox" data-quick="질환" value="관절염">관절염</label><label><input type="checkbox" data-quick="질환" value="우울증">우울증</label><label><input type="checkbox" data-quick="질환" value="치매">치매</label></div>
      </div>
      <button id="quick-filter-to-chat" type="button">선택 조건으로 LLM 질문 만들기</button>
    </details>
    <form id="coach-form">
      <div class="grid">
        <div class="hidden-age-group"><label>연령군</label><select id="age_group" required disabled></select></div>
        <div class="condition-group">
          <h3>운동·스트레칭 추천 조건</h3>
          <p>통증 부위와 운동 조건을 위에서 아래 순서로 고르면 다음 목록에는 앞 조건을 모두 만족하는 운동만 표시됩니다. 운동 경험은 원본 6종에 독립 필드가 없어 검색 조건에서 제외했습니다.</p>
          <p>센터 인증등급과 영상 난이도는 합치지 않습니다. 영상 원문의 1~2는 초급, 3은 중급, 4~5는 고급입니다. 1~5·공통·난이도 미표기는 초·중·고와 중복하지 않고 종합으로 표시합니다.</p>
          <div class="grid">
        <div id="group-pain_area"><label>통증 부위 <span class="source-tag">사용자 안전 조건</span></label><select id="pain_area"></select></div>
        <div id="group-health_information"><label>건강 목적 <span class="source-tag">원문 직접 분류</span></label><select id="health_information"></select></div>
        <div><label>운동 목표 부위 <span class="source-tag">RAG</span></label><select id="target_area" required></select></div>
        <div><label>운동 유형 <span class="source-tag">RAG</span></label><select id="exercise_type" required></select></div>
        <div><label>운동 단계 <span class="source-tag">미표기는 본운동으로 분류</span></label><select id="exercise_stage"></select></div>
        <div id="group-fitness_level"><label>영상 체력 수준/난이도 <span class="source-tag">RAG 원문 표기</span></label><select id="fitness_level" required></select></div>
        <div id="group-location"><label>운동 장소 <span class="source-tag">테스트 분류</span></label><select id="location" required></select><small>헬스기구는 헬스장, 물병·물통·장비 없음/미표기는 실내로 묶습니다. 원문 장소와 다를 수 있습니다.</small></div>
        <div id="group-equipment"><label>사용할 장비 <span class="source-tag">RAG</span></label><select id="equipment"></select></div>
        <div id="group-available_time"><label>운동 가능 시간 <span class="source-tag">사용자 조건</span></label><select id="available_time"></select></div>
        <button id="submit" type="button" disabled>운동·스트레칭 추천 검색</button>
          </div>
        </div>
      </div>
    </form>
  </section>
  <section>
    <h2>RAG 원문 기반 추천</h2>
    <div id="error"></div>
    <div id="empty">앞에서 선택한 조건에 맞는 값만 다음 목록에 표시됩니다.<br>추천 결과는 RAG 원문에 실제 존재하는 항목만 보여줍니다.</div>
    <div id="result"></div>
    <div class="chat-panel">
      <h2>AI 체력 코치 챗봇</h2>
      <p class="chat-note">선택한 운동뿐 아니라 다른 부위 운동, 운동 방법·루틴·회복도 물어보세요. 일반 운동 지식은 개인별 처방이 아니며, 원문을 활용한 답변에는 참고 출처를 표시합니다.</p>
      <div id="chat-messages" class="chat-messages"><div class="chat-message assistant">어떤 운동이 궁금하세요? 운동 추천부터 방법·루틴·회복까지 물어보세요.</div></div>
      <form id="chat-form" class="chat-form">
        <input id="chat-input" maxlength="500" autocomplete="off" placeholder="예: 팔 근력 운동도 추천해줘">
        <button id="chat-send" type="submit">보내기</button>
      </form>
    </div>
  </section>
</main>
<footer>이 서비스는 진단이나 치료 처방을 제공하지 않습니다. 모든 데이터와 모델 처리는 이 컴퓨터 안에서 실행됩니다.</footer>
<script>
const optionFields=["age_group","sex","target_area","exercise_type","exercise_stage","fitness_level","location","pain_area","equipment","available_time","health_information"];
const ragFields=["age_group","sex","health_information","target_area","exercise_type","exercise_stage","fitness_level","location","equipment"];
const cascadeFields=["health_information","target_area","exercise_type","exercise_stage","fitness_level","location","equipment"];
const facetInputFields=["age_group","sex","pain_area",...cascadeFields];
const defaults={age_group:"성인",sex:"M",exercise_type:"근력",fitness_level:"중급",location:"실내",pain_area:"없음",equipment:"없음",available_time:"30분",health_information:"없음"};
let facetRequestVersion=0;
let chatHistory=[];
let homeMeasurementSummary="";
let measurementInputRequestVersion=0;
function requestPayload(){const payload={selection_mode:true,user_id:"local-web-user",pain_level:0,disability_type:"없음"};optionFields.forEach(k=>payload[k]=document.getElementById(k).value.trim());payload.age=Number(document.getElementById("age").value);payload.height_cm=Number(document.getElementById("height_cm").value);payload.weight_kg=Number(document.getElementById("weight_kg").value);payload.home_measurement_context=homeMeasurementSummary;return payload;}
function prepareResult(){document.getElementById("empty").style.display="none";const result=document.getElementById("result");result.replaceChildren();return result;}
function ageGroupForAge(age){if(age<7)return "유아기";if(age<13)return "유소년";if(age<19)return "청소년";if(age<65)return "성인";return "어르신";}
function measurementGroupForAge(age){if(age>=65)return "senior";if(age>=19)return "adult";if(age>=13)return "teen";if(age>=11)return "youth";return "child";}
function measurementGroupName(group){return group==="senior"?"어르신":group==="adult"?"성인":group==="teen"?"청소년":group==="youth"?"유소년":"만 10세 이하";}
function measurementGroupMatchesAge(group,age){return group===measurementGroupForAge(age);}
function measurementAgeRange(group){return group==="senior"?"65세 이상":group==="adult"?"19~64세":group==="teen"?"13~18세":group==="youth"?"11~12세":"11세 이상";}
async function syncAgeGroup(){const select=document.getElementById("age_group");const value=ageGroupForAge(Number(document.getElementById("age").value));if(Array.from(select.options).some(option=>option.value===value)){select.value=value;await refreshFacets("age_group");}}
function fillOptions(id,items,useDefault=false){const select=document.getElementById(id);const previous=select.value;select.replaceChildren();if(!items.length){const option=document.createElement("option");option.value="";const emptyLabels={fitness_level:"앞 조건의 원문에 난이도 정보 없음",location:"앞 조건의 원문에 장소 정보 없음",equipment:"앞 조건과 함께 가능한 장비 없음"};option.textContent=emptyLabels[id]||"앞 조건과 함께 가능한 운동 없음";select.append(option);return previous!=="";}items.forEach(item=>{const option=document.createElement("option");option.value=item.value;const unit=cascadeFields.includes(id)?"개 운동":"건";const label=id==="equipment"&&item.value==="없음"?"없음/원문 미표기":item.label;option.textContent=item.count>0?`${label} (${item.count.toLocaleString()}${unit})`:label;select.append(option);});const preferred=useDefault?defaults[id]:previous;if(preferred&&items.some(item=>item.value===preferred))select.value=preferred;else if(items.some(item=>item.value==="없음"))select.value="없음";else select.value=items[0].value;return previous!==select.value;}
function currentFacetSelection(){const payload={};facetInputFields.forEach(id=>payload[id]=document.getElementById(id).value);return payload;}
function applyFacetPolicy(d){const disabled=new Set(d.facet_policy?.not_applicable||[]);["fitness_level","location","equipment","available_time","health_information"].forEach(id=>{const select=document.getElementById(id);const inactive=disabled.has(id);select.disabled=inactive;const group=document.getElementById(`group-${id}`);if(group)group.style.opacity=inactive?"0.55":"1";});const count=Number(d.matching_exercise_count||0);const button=document.getElementById("submit");button.dataset.noMatches=count===0?"1":"0";button.textContent=count>0?`선택 조건으로 RAG 추천 (${count.toLocaleString()}개 후보)`:"선택 가능한 운동 없음";const note=document.getElementById("option-note");note.textContent=`${d.facet_policy?.note||"RAG 데이터의 실제 필드로 검색합니다."} 현재 전체 조합은 ${count.toLocaleString()}개 운동입니다.`;}
async function loadVideoLinkAudit(){
 const details=document.getElementById("video-link-audit"),body=document.getElementById("video-link-audit-body");
 if(details.dataset.loaded||!details.open)return;
 details.dataset.loaded="1";body.textContent="원문과 영상 설명문을 대조하고 있습니다…";
 try{
  const response=await fetch("/api/video-link-audit"),data=await response.json();
  if(!response.ok)throw new Error(data.detail||"점검 실패");
  body.replaceChildren();
  const policy=document.createElement("div");policy.textContent=data.policy;body.append(policy);
  const count=document.createElement("strong");count.textContent=`연결 확인이 필요한 운동 ${data.unlinked_count}개 · 완료 항목은 숨겼습니다`;body.append(count);
  const search=document.createElement("input");search.placeholder="운동명·분류 검색 (예: 팔 근력, 골반)";search.setAttribute("aria-label","영상 연결 점검 목록 검색");body.append(search);
  const list=document.createElement("div");body.append(list);
  const render=()=>{
   list.replaceChildren();
   for(const [status,label] of [["unverified","연결 근거 미확인"]]){
    const section=document.createElement("details");section.open=true;
    const matches=(data.items||[]).filter(x=>x.link_status===status && (x.exercise_name+" "+x.display_group).includes(search.value.trim()));
    const summary=document.createElement("summary");summary.textContent=`${label} ${matches.length}개`;section.append(summary);
    const groups=new Map();matches.forEach(item=>{const group=item.display_group||"분류 미표기";if(!groups.has(group))groups.set(group,[]);groups.get(group).push(item);});
    for(const [group,items] of groups){
     const heading=document.createElement("strong");heading.textContent=group;section.append(heading);
     const ul=document.createElement("ul");
     items.forEach(item=>{
      const row=document.createElement("li");row.textContent=item.exercise_name+" — "+(item.stages||[]).join(" / ")+" · "+item.reason;
      (item.related_videos||[]).forEach(v=>{
       const card=document.createElement("div"),link=document.createElement("a");
       link.href="/video-player?url="+encodeURIComponent(v.url)+"&title="+encodeURIComponent(v.title);link.target="_blank";link.rel="noopener";link.textContent=v.title;
       card.append(link,document.createTextNode(" · 원문 대상: "+v.age_group+" · 원문 도구: "+v.equipment));
       const evidence=document.createElement("small");evidence.textContent="원문 근거: "+v.evidence;card.append(evidence);row.append(card);
      });ul.append(row);
     });section.append(ul);
    }list.append(section);
   }
  };search.addEventListener("input",render);render();
  if(data.truncated){const note=document.createElement("div");note.textContent="표시 한도를 넘는 항목은 생략되었습니다.";body.append(note);}
 }catch(error){details.dataset.loaded="";body.textContent="점검 오류: "+error.message;}
}
async function refreshFacets(changedField){const version=++facetRequestVersion;const button=document.getElementById("submit");const note=document.getElementById("option-note");button.disabled=true;button.textContent="가능한 운동 계산 중…";note.textContent="앞에서 선택한 조건에 맞는 운동 목록을 계산하고 있습니다.";const request=async()=>{const payload=currentFacetSelection();const r=await fetch("/api/options",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw new Error(d.detail||"연동 선택값 조회 실패");if(version!==facetRequestVersion)return null;let changed=false;ragFields.forEach(id=>{changed=fillOptions(id,d.options[id]||[])||changed;});changed=fillOptions("health_information",d.options.health_information||[])||changed;applyFacetPolicy(d);return {data:d,changed};};try{let state=null;for(let attempt=0;attempt<6;attempt+=1){state=await request();if(!state)return null;if(!state.changed)break;}let d=state?.data;if(changedField==="location"&&document.getElementById("location").value==="헬스장"&&!document.getElementById("equipment").disabled){const equipment=document.getElementById("equipment");if(equipment.value==="없음"&&Array.from(equipment.options).some(option=>option.value==="헬스기구")){equipment.value="헬스기구";state=await request();d=state?.data;}}return d;}finally{if(version===facetRequestVersion)button.disabled=button.dataset.noMatches==="1";}}
const ageInput=document.getElementById("age");
function syncMeasurementAgeToInput(){const select=document.getElementById("measurement-age-group");const group=measurementGroupForAge(Number(ageInput.value));select.value=group==="child"?"":group;return loadPercentileInputs();}
async function loadOptions(){const note=document.getElementById("option-note");try{const r=await fetch("/api/options");const d=await r.json();if(!r.ok)throw new Error(d.detail||"선택값 조회 실패");optionFields.forEach(id=>fillOptions(id,d.options[id]||[],true));facetInputFields.filter(id=>id!=="age_group").forEach(id=>document.getElementById(id).addEventListener("change",()=>refreshFacets(id).catch(e=>{note.textContent=`RAG 연동 오류: ${e.message}`})));const measurementAgeSelect=document.getElementById("measurement-age-group");ageInput.addEventListener("input",syncMeasurementAgeToInput);ageInput.addEventListener("change",()=>{syncAgeGroup().catch(e=>{note.textContent=`연령군 연동 오류: ${e.message}`});syncMeasurementAgeToInput();});measurementAgeSelect.addEventListener("change",()=>loadPercentileInputs());applyFacetPolicy(d);await syncAgeGroup();syncMeasurementAgeToInput();}catch(e){note.textContent=`RAG 선택값 오류: ${e.message}`;}}
async function checkHealth(){
  const box=document.getElementById("health");
  try{const r=await fetch("/api/health");const d=await r.json();if(!r.ok)throw new Error(d.detail||"상태 확인 실패");
    box.textContent=`정상 · 원본 ${d.source_dataset_count}종 ${d.total_source_rows.toLocaleString()}행 · RAG ${d.rag_dataset_count}범주 ${d.sqlite_documents.toLocaleString()}문서 · Chroma ${d.chroma_documents.toLocaleString()}건 (${d.index_scope==='full'?'전체':'표본'}) · Qwen3 준비 완료`;
  }catch(e){box.textContent=`서버 준비 중 또는 오류: ${e.message}`;box.style.background="#fff0f0";}
}
async function loadPercentileStatus(){
  const box=document.getElementById("percentile-status");
  try{
    const response=await fetch("/api/center-percentile-status");
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail||"규준 상태 확인 실패");
    const homeCoreCodes=new Set(["FLEX_SIT_REACH","MUSC_END_SITUP","CARDIO_2MINSTEP","POWER_LONGJUMP","LOWER_CHAIRSTAND"]);
    const homeCore=data.measures.filter(item=>homeCoreCodes.has(item.code));
    const youthCore=homeCore.filter(item=>item.age_scope.includes("유소년")).map(item=>item.name).join(", ");
    const teenCore=homeCore.filter(item=>item.age_scope.includes("청소년")).map(item=>item.name).join(", ");
    const adultCore=homeCore.filter(item=>item.age_scope.includes("성인")).map(item=>item.name).join(", ");
    const seniorCore=homeCore.filter(item=>item.age_scope.includes("어르신")).map(item=>item.name).join(", ");
    const additional=data.measures.filter(item=>item.stage==="primary"&&!homeCoreCodes.has(item.code)).map(item=>item.name).join(", ");
    const expansion=data.measures.filter(item=>item.stage==="expansion").map(item=>item.name).join(", ");
    box.replaceChildren();
    const current=document.createElement("p");
    current.textContent=data.norm_row_count>0?`현재: ${data.norm_row_count.toLocaleString()}개 규준값 · 입력한 성별과 5세 연령대의 센터 표본으로 상위 비율을 계산합니다.`:"현재: 공식 원시필드 매핑 확인 전이라 상위 비율은 아직 표시하지 않습니다.";
    const primaryLine=document.createElement("p");
    primaryLine.textContent=`기본 홈 체력측정 5종: 유소년 ${youthCore} / 청소년 ${teenCore} / 성인 ${adultCore} / 어르신 ${seniorCore}`;
    const additionalLine=document.createElement("p");
    additionalLine.textContent=additional?`추가 백분위 적용: ${additional}`:"";
    const expansionLine=document.createElement("p");
    expansionLine.textContent=`확장 준비: ${expansion}`;
    box.append(current,primaryLine,additionalLine,expansionLine);
  }catch(error){box.textContent=`규준 테이블 상태를 불러오지 못했습니다: ${error.message}`;}
}
async function loadPercentileInputs(){
  const inputs=document.getElementById("percentile-inputs"); const result=document.getElementById("percentile-results");
  const age=Number(document.getElementById("age").value);
  const requestVersion=++measurementInputRequestVersion;
  const heading=document.getElementById("measurement-age-heading"); const note=document.getElementById("measurement-age-note");
  const selectedGroup=age<11?"child":document.getElementById("measurement-age-group").value;
  const ageMatches=measurementGroupMatchesAge(selectedGroup,age);
  if(selectedGroup==="youth"){heading.textContent="유소년 홈 체력측정 (만 11~12세)";note.textContent="유소년으로 명시된 센터 원시기록 표본이 충분한 앉아 윗몸 앞으로 굽히기와 제자리 멀리뛰기만 입력할 수 있습니다.";}
  else if(selectedGroup==="teen"){heading.textContent="청소년 홈 체력측정 (만 13~18세)";note.textContent="청소년으로 명시된 센터 원시기록 표본이 충분한 앉아 윗몸 앞으로 굽히기와 제자리 멀리뛰기만 입력할 수 있습니다.";}
  else if(selectedGroup==="adult"){heading.textContent="성인 홈 체력측정 (만 19~64세)";note.textContent="앉아 윗몸 앞으로 굽히기, 교차 윗몸 일으키기, 제자리 멀리뛰기만 입력할 수 있습니다.";}
  else if(selectedGroup==="senior"){heading.textContent="어르신 홈 체력측정 (만 65세 이상)";note.textContent="앉아 윗몸 앞으로 굽히기, 의자에 앉았다 일어서기, 2분 제자리걷기, 3m 표적 돌아오기만 입력할 수 있습니다.";}
  else{heading.textContent="만 10세 이하 홈 체력측정";note.textContent="현재 보유 센터 원시기록 기반 상위 비율은 만 11세 이상만 제공합니다.";}
  const submit=document.getElementById("percentile-submit");
  if(selectedGroup==="child"){inputs.textContent="만 10세 이하 백분위 규준은 아직 제공하지 않습니다.";result.replaceChildren();homeMeasurementSummary="";submit.disabled=true;return;}
  submit.disabled=!ageMatches;
  try{
    const catalogAge=ageMatches?age:(selectedGroup==="senior"?65:selectedGroup==="adult"?19:selectedGroup==="teen"?13:11);
    const response=await fetch(`/api/center-percentile-inputs?age=${encodeURIComponent(catalogAge)}`); const data=await response.json();
    if(!response.ok)throw new Error(data.detail||"입력 항목 조회 실패");
    if(requestVersion!==measurementInputRequestVersion)return;
    inputs.replaceChildren(); result.replaceChildren(); homeMeasurementSummary="";
    data.measures.forEach(item=>{const field=document.createElement("div");const label=document.createElement("label");label.htmlFor=`measurement-${item.code}`;label.textContent=`${item.name} (${item.unit})`;const input=document.createElement("input");input.id=`measurement-${item.code}`;input.dataset.measureCode=item.code;input.type="number";input.step="any";input.min="0";input.placeholder="측정값 입력";field.append(label,input);inputs.append(field);});
    if(!data.measures.length)inputs.textContent="현재 연령에 적용할 수 있는 센터 원시기록 규준 항목이 없습니다.";
    if(!ageMatches){result.textContent=`${measurementGroupName(selectedGroup)}을 선택했습니다. 백분위 계산 전에는 실제 만 나이를 ${measurementAgeRange(selectedGroup)}으로 입력해 주세요.`;}
  }catch(error){if(requestVersion===measurementInputRequestVersion)inputs.textContent=`홈 체력측정 입력칸을 준비하지 못했습니다: ${error.message}`;}
}
document.getElementById("percentile-form").addEventListener("submit",async(event)=>{
  event.preventDefault();const button=document.getElementById("percentile-submit");const result=document.getElementById("percentile-results");const measurements={};
  const selectedGroup=document.getElementById("measurement-age-group").value;const measuredAge=Number(document.getElementById("age").value);
  if(!measurementGroupMatchesAge(selectedGroup,measuredAge)){result.textContent=`선택한 ${measurementGroupName(selectedGroup)} 대상과 만 나이가 일치하지 않습니다.`;return;}
  document.querySelectorAll("#percentile-inputs input[data-measure-code]").forEach(input=>{if(input.value.trim()!=="")measurements[input.dataset.measureCode]=Number(input.value);});
  if(!Object.keys(measurements).length){result.textContent="측정값을 하나 이상 입력해 주세요.";return;}
  button.disabled=true;button.textContent="백분위 계산 중…";
  try{const payload={age:Number(document.getElementById("age").value),sex:document.getElementById("sex").value,measurements};const response=await fetch("/api/center-percentiles",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok){const detail=Array.isArray(data.detail)?data.detail.map(item=>item.msg||String(item)).join(" / "):data.detail;throw new Error(detail||"상위 비율 계산 실패");}result.replaceChildren();const title=document.createElement("strong");title.textContent=data.result_label;result.append(title);const availableResults=data.results.filter(item=>item.available);const topRate=item=>Number(item.top_percent).toFixed(1);const comparedBands=[...new Set(availableResults.map(item=>item.age_band).filter(Boolean))];homeMeasurementSummary=`${measurementGroupName(selectedGroup)} 홈체력측정 입력값 · 만 ${measuredAge}세 · ${data.result_label} · 비교 연령대 ${comparedBands.join(", ")}: ${availableResults.map(item=>`${item.name} ${item.input_value}${item.unit}, 상위 ${topRate(item)}%`).join(" / ")}`;data.results.forEach(item=>{const row=document.createElement("div");row.className="percentile-row";row.textContent=item.available?`${item.name}: 입력 ${item.input_value}${item.unit} · 상위 ${topRate(item)}% (센터 표본 ${item.sample_size.toLocaleString()}명, ${item.age_band})`:`${item.name}: 비교 가능한 표본이 부족합니다.`;result.append(row);});}
  catch(error){result.textContent=`백분위 계산 오류: ${error.message}`;}finally{button.disabled=false;button.textContent="백분위 확인";}
});
function appendAgeBmiRecommendation(result,data){const bmi=data?.bmi||{};if(!bmi.available)return;const section=document.createElement("div");section.className="field";const title=document.createElement("strong");title.textContent="국내 성인 BMI 정보";const summary=document.createElement("div");summary.textContent=`입력 BMI ${Number(bmi.bmi).toFixed(1)} · 국내 성인 BMI 기준 ${bmi.bmi_grade}. 이 분류는 진단이나 치료 판단이 아닙니다.`;section.append(title,summary);const source=data.source||{};const sourceLine=document.createElement("div");sourceLine.className="source-tag";sourceLine.textContent=`BMI 기준 출처: ${source.bmi_source_title||bmi.source_title||"질병관리청 국가건강정보포털"}`;section.append(sourceLine);if(source.bmi_source_url||bmi.source_url){const link=document.createElement("a");link.href=source.bmi_source_url||bmi.source_url;link.target="_blank";link.rel="noopener";link.textContent="BMI 기준 보기";section.append(link);}result.append(section);}
document.getElementById("submit").addEventListener("click",async()=>{
  const button=document.getElementById("submit"); const error=document.getElementById("error");
  const readyLabel=button.textContent;
  button.disabled=true;button.textContent="검색·검증·생성 중…";error.style.display="none";
  const payload=requestPayload();
  try{const r=await fetch("/api/coach",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw new Error(d.detail||"생성 실패");
    const result=prepareResult();chatHistory=[];const chatMessages=document.getElementById("chat-messages");chatMessages.replaceChildren();appendChatMessage("assistant","추천이 준비됐어요. 이 운동에 대한 질문이나 다른 운동·운동 습관에 대해서도 물어보세요.",[]);
    const displayText=(value)=>String(value||"").replace(/\s*\[(?:[EHD]\d+(?:\s*,\s*[EHD]\d+)*)\]/g,"").replace(/\s{2,}/g," ").trim();
    appendAgeBmiRecommendation(result,d.bmi_recommendation);
    const healthCondition=d.retrieval?.health_condition;const recommendationTitle=document.createElement("h3");recommendationTitle.className="result-heading";recommendationTitle.textContent=healthCondition?`${healthCondition} 건강 목적 운동 추천 결과`:"운동·스트레칭 추천 결과";result.append(recommendationTitle);
    const reason=document.createElement("div");reason.className="field";const reasonTitle=document.createElement("strong");reasonTitle.textContent="추천 안내";const reasonText=document.createElement("div");reasonText.textContent=d.recommendation_guide||displayText(d.answer["추천이유"]);reason.append(reasonTitle,reasonText);result.append(reason);
    if(d.exercise_intro){const intro=document.createElement("div");intro.className="field";const introTitle=document.createElement("strong");introTitle.textContent="운동 소개";const introText=document.createElement("div");introText.textContent=d.exercise_intro;intro.append(introTitle,introText);result.append(intro);}
    if(d.exercise_method){const method=document.createElement("div");method.className="field";const methodTitle=document.createElement("strong");methodTitle.textContent="운동 방법";const methodText=document.createElement("div");methodText.textContent=d.exercise_method;method.append(methodTitle,methodText);result.append(method);}
    if(healthCondition&&!d.retrieval?.screened_candidates){const notice=document.createElement("div");notice.className="source";notice.textContent=`선택한 ‘${healthCondition}’과 현재 운동 조건이 한 원문에서 직접 연결된 자료가 없습니다. 질환과 연결되지 않은 일반 운동을 대신 추천하지 않았습니다.`;result.append(notice);}
    if(Object.keys(d.exercise_details||{}).length){if(d.detail_notice){const notice=document.createElement("div");notice.className="source";notice.textContent=d.detail_notice;result.append(notice);}const detailTitle=document.createElement("h3");detailTitle.textContent="운동 한눈에 보기";const grid=document.createElement("div");grid.className="detail-grid";Object.entries(d.exercise_details).filter(([label])=>!['설명','영상 URL'].includes(label)).forEach(([label,value])=>{const row=document.createElement("div");row.className="detail-row";const strong=document.createElement("strong");strong.textContent=label;const text=document.createElement("div");text.textContent=value;row.append(strong,text);grid.append(row);});if(grid.childElementCount)result.append(detailTitle,grid);}
    if(d.related_video_options?.length){
      const box=document.createElement("details");box.open=true;
      const heading=document.createElement("summary");heading.textContent=`관련 공식 영상 ${d.related_video_options.length}개 — 선택 조건과 별도`;box.append(heading);
      const note=document.createElement("div");note.className="source";note.textContent="공식 설명문 일치, 검증된 이름 대응 또는 사용자가 승인한 유사 운동 참고 영상입니다. 세부 동작·원문 대상·도구가 현재 선택 조건과 다를 수 있습니다.";box.append(note);
      d.related_video_options.forEach(v=>{
        const card=document.createElement("div");card.className="source";
        const link=document.createElement("a");link.href="/video-player?url="+encodeURIComponent(v.url)+"&title="+encodeURIComponent(v.title);link.target="_blank";link.rel="noopener";link.textContent=v.title;
        const meta=document.createElement("div");meta.textContent="원문 대상: "+v.age_group+" · 원문 도구: "+v.equipment;
        const source=document.createElement("small");source.textContent=(v.match_type==="similar"?"유사 연결 근거: ":"원문 연결 근거: ")+(v.match_note||v.evidence)+(v.missing_equipment_rows?" (동일 URL의 도구 미표기 중복 행은 따로 표시하지 않았습니다.)":"");
        card.append(link,meta,source);box.append(card);
      });result.append(box);
    }
    if(d.video_options?.length){const disclosure=document.createElement("details");disclosure.open=true;const summary=document.createElement("summary");summary.textContent=`함께 볼 공식 영상 ${d.video_options.length}개`;const guide=document.createElement("div");guide.className="source";guide.textContent="같은 운동명이라도 URL이 다르면 주차별로 나누어 표시합니다. 1~5·공통·난이도 미표기 영상은 초·중·고에 중복하지 않고 종합으로 표시합니다.";disclosure.append(summary,guide);d.video_options.forEach(v=>{const card=document.createElement("div");card.className="source";const title=document.createElement("strong");title.textContent=`${v.week?`${v.week} · `:""}${v.title}`;const meta=document.createElement("div");meta.textContent=`${v.condition_note} · 연령 ${v.age_group} · 수준 ${v.fitness_level} · 장소 ${v.location} · 장비 ${v.equipment}`;const description=document.createElement("div");description.textContent=v.description||"공식 영상 원문에 별도 설명이 없습니다.";const sourceRefs=v.sources||[];const sourceLine=document.createElement("div");sourceLine.className="source-tag";if(sourceRefs.length){const visibleSources=sourceRefs.slice(0,3).map(s=>`${s.source_file}${s.row_num!==null&&s.row_num!==undefined&&s.row_num!==""?` · 원본 ${s.row_num}행`:""}`);sourceLine.textContent=`출처: ${visibleSources.join(" / ")}${sourceRefs.length>3?` 외 ${sourceRefs.length-3}건`:""}`;}else{sourceLine.textContent="출처: 원본 파일 정보 없음";}const link=document.createElement("a");link.href=`/video-player?url=${encodeURIComponent(v.url)}&title=${encodeURIComponent(v.title)}`;link.target="_blank";link.rel="noopener";link.textContent="공식 영상 바로 보기";card.append(title,meta,description,sourceLine,link);disclosure.append(card);});result.append(disclosure);}
    if(d.retrieval?.available_alternatives?.length){const details=d.retrieval.available_alternatives.map(item=>`${item.title}: 연령군 ${item.age_group}, 수준 ${(item.fitness_levels||[]).join("/")||"정보 없음"}, 장소 ${item.location}, 장비 ${item.equipment}`).join("\n");const notice=document.createElement("div");notice.className="source";notice.textContent=`선택한 조건 전체와 일치하는 안전한 RAG 자료가 없습니다.\n가까운 실제 자료 조건:\n${details}\n위 조건과 다르게 선택하거나 건강·장비 조건에 맞는 자료가 추가되어야 합니다.`;result.prepend(notice);}
    if(d.retrieval?.health_context_separated){const notice=document.createElement("div");notice.className="source";notice.textContent=d.retrieval.health_reference_found?`${d.retrieval.health_condition} 키워드가 있는 건강 참고 원문과 현재 조건의 운동처방 원문을 따로 확인했습니다. 두 원문이 이 운동의 질환별 안전성을 직접 연결해 보증하는 것은 아닙니다. 치료 중이거나 증상이 있으면 시작 전에 의료진과 확인하세요.`:`현재 데이터에는 ${d.retrieval.health_condition}과 선택 운동을 직접 연결한 근거가 없습니다. 운동 결과는 건강 적합성 판정이 아니므로 치료 중이거나 증상이 있으면 시작 전에 의료진과 확인하세요.`;result.prepend(notice);}
    if(d.retrieval?.ignored_conditions?.length){const labels={fitness_level:"체력 수준/난이도",location:"운동 장소",available_time:"운동 가능 시간"};const notice=document.createElement("div");notice.className="source";notice.textContent=`장애인 처방 원문에 별도 필드가 없거나 의미가 다른 다음 항목은 결과 제외 조건으로 사용하지 않았습니다: ${d.retrieval.ignored_conditions.map(field=>labels[field]||field).join(", ")}. 장애 유형·연령·성별과 운동명 기반 부위·유형·장비는 유지했습니다.`;result.prepend(notice);}
    const ordinaryRelaxed=(d.retrieval?.relaxed_fields||[]).filter(field=>field!=="health_linkage"&&field!=="disability_linkage");if(ordinaryRelaxed.length){const labels={fitness_level:"체력 수준/난이도",exercise_type:"운동 유형 원문 정확 일치",location:"운동 장소 원문 정확 일치"};const relaxed=ordinaryRelaxed.map((field)=>labels[field]||field);const notice=document.createElement("div");notice.className="source";notice.textContent=`정확 일치 후보가 없어 다음 조건만 완화했습니다: ${relaxed.join(", ")}. 목표 부위·장비 조건은 유지했으며, 완화된 항목도 검색 의미에는 계속 반영됩니다.`;result.prepend(notice);}
  }catch(err){error.textContent=err.message;error.style.display="block";}finally{button.disabled=button.dataset.noMatches==="1";button.textContent=readyLabel;}
});
function appendChatMessage(role,text,sources,guidanceSources=[]){const box=document.getElementById("chat-messages");const bubble=document.createElement("div");bubble.className=`chat-message ${role}`;const content=document.createElement("div");content.textContent=String(text||"").replace(/\s*\[(?:E\d+(?:\s*,\s*E\d+)*)\]/g,"").trim();bubble.append(content);if(role==="assistant"&&sources?.length){const source=document.createElement("div");source.className="chat-source";source.textContent=`참고 출처: ${sources.map(item=>`${item.title}`).join(" · ")}`;bubble.append(source);}if(role==="assistant"&&guidanceSources.length){const refs=document.createElement("div");refs.className="chat-source";refs.append("일반 코칭 참고: ");guidanceSources.forEach((item,i)=>{if(i)refs.append(" · ");const a=document.createElement("a");a.textContent=item.title;const u=new URL(item.url);if(u.protocol==="https:"&&u.hostname==="www.nhs.uk"){a.href=u.href;a.target="_blank";a.rel="noopener";}refs.append(a);});bubble.append(refs);}box.append(bubble);box.scrollTop=box.scrollHeight;}
document.getElementById("chat-form").addEventListener("submit",async(event)=>{event.preventDefault();const input=document.getElementById("chat-input");const button=document.getElementById("chat-send");const message=input.value.trim();if(!message)return;const previousHistory=chatHistory.slice(-6);appendChatMessage("user",message,[]);chatHistory.push({role:"user",content:message});input.value="";button.disabled=true;button.textContent="답변 중…";try{const response=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_id:"local-web-user",message,history:previousHistory})});let data;try{data=await response.json();}catch{throw new Error(response.ok?"챗봇 응답을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.":"챗봇 서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.");}if(!response.ok)throw new Error(data.detail||"챗봇 응답 실패");appendChatMessage("assistant",data.answer,data.sources||[],data.guidance_sources||[]);chatHistory.push({role:"assistant",content:data.answer});}catch(error){const text=error instanceof TypeError||String(error?.message||"").includes("Failed to fetch")?"챗봇 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.":String(error?.message||"챗봇 응답에 문제가 생겼습니다.");appendChatMessage("assistant",text,[]);}finally{button.disabled=false;button.textContent="보내기";input.focus();}});
document.getElementById("measurement-age-group").value=measurementGroupForAge(Number(ageInput.value));
document.getElementById("video-link-audit").addEventListener("toggle",loadVideoLinkAudit);
document.getElementById("quick-filter-to-chat").addEventListener("click",()=>{const groups={};document.querySelectorAll("input[data-quick]:checked").forEach(input=>{(groups[input.dataset.quick]??=[]).push(input.value);});const parts=Object.entries(groups).map(([label,values])=>`${label}: ${values.join(", ")}`);const input=document.getElementById("chat-input");input.value=parts.length?`${parts.join(" / ")} 조건의 운동을 간단히 안내해줘.`:"간편 필터 조건을 선택한 뒤 운동을 간단히 안내해줘.";input.focus();});
Promise.all([checkHealth(),loadOptions(),loadPercentileStatus(),loadPercentileInputs()]);
</script>
</body></html>'''
