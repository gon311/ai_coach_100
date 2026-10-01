"""Conversational, source-grounded Qwen3 fitness chat harness.

Goals
- Keep answers grounded in the existing RAG/DB context.
- Use logged-in user context throughout fitness conversations.
- Preserve follow-up context such as "그 운동", "왜", "다른 운동".
- Never expose internal ranking/demographic metadata in the user-facing answer.
- Never dump raw RAG rows when the model response fails validation.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


FITNESS_TERMS = (
    "운동", "체력", "근력", "근육", "유연", "스트레칭", "유산소", "심폐", "걷기", "달리기",
    "스쿼트", "푸시업", "윗몸", "플랭크", "악력", "민첩", "순발력", "균형", "자세", "반복", "세트",
    "허리", "무릎", "어깨", "팔", "다리", "코어", "측정", "백분위", "회복", "워밍업", "쿨다운",
    "추천", "왜", "이유", "다른", "그 운동", "그거", "이 운동",
)

OFF_TOPIC = "운동에 관한 질문을 해주세요"

# 검색/필터링에는 사용하지만 일반 대화에서는 보여주지 않는 내부 메타데이터
HIDDEN_CHAT_TERMS = (
    "체력 인증등급", "인증등급", "1등급", "2등급", "3등급",
    "성별: M", "성별: F", "성별 M", "성별 F",
    "대상 연령군", "RAG_DOCUMENT", "USER_MEASUREMENT",
    "document_id", "dataset", "retrieval_backend", "레코드", "청력",
)

REFERENTIAL_TERMS = (
    "그 동작", "그 운동", "그거", "이 동작", "이 운동", "그 방법",
    "왜", "이유", "다른 운동", "다른 거", "그 다음", "다음 운동",
)

NUTRITION_TERMS = (
    "음식", "식단", "영양", "단백질",
    "탄수화물", "지방", "비타민", "식사",
)

SPECIAL_CONDITION_TERMS = (
    "오십견", "관절염", "허리질환", "요통", "고혈압", "당뇨", "뇌졸중", "파킨슨",
    "골다공증", "치매", "뇌병변", "지적장애",
)

MEASUREMENT_GOALS = {
    "상지근기능": "상지 근력 악력 개선",
    "하지근기능": "하체 근력 개선",
    "근기능상지": "상지 근력 악력 개선",
    "근기능하지": "하체 근력 개선",
    "유연성": "유연성 스트레칭 개선",
    "심폐지구력": "심폐지구력 유산소 개선",
    "평형성": "균형 평형성 개선",
    "협응력": "협응력 균형 개선",
    "민첩성": "민첩성 방향전환 개선",
    "순발력": "하체 순발력 개선",
}

DISPLAY_STRIP_LABELS = (
    "체력 인증등급",
    "인증등급",
    "대상 연령군",
    "성별",
    "측정 장소",
    "데이터셋",
    "dataset",
    "document_id",
    "문서 ID",
    "evidence_type",
)


def _exercise_question(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    recent = " ".join(
        str(h.get("content") or "")
        for h in (history or [])[-4:]
    )

    normalized = re.sub(
        r"\s+",
        "",
        f"{message} {recent}",
    ).casefold()

    return any(
        term.casefold() in normalized
        for term in FITNESS_TERMS
    )


def _dedupe(text: str) -> str:
    parts = [
        part.strip()
        for part in re.split(
            r"(?<=[.!?。])\s+|\n+",
            text,
        )
        if part.strip()
    ]

    seen = set()
    unique = []

    for part in parts:
        key = re.sub(
            r"[^0-9가-힣a-z]",
            "",
            part.casefold(),
        )

        if not key or key in seen:
            continue

        seen.add(key)
        unique.append(part)

    return " ".join(unique)[:700]


def _fully_cited(text: str) -> bool:
    return bool(
        re.search(
            r"\[E[1-9]\d*\]",
            text,
        )
    )


def _citation_ids(text: str) -> set[str]:
    return set(
        re.findall(
            r"\[(E[1-9]\d*)\]",
            text,
        )
    )


def _document_id(source: dict[str, Any]) -> str:
    return str(
        source.get("id")
        or source.get("document_id")
        or ""
    ).strip()


def _retrieval_trace(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    하네스 평가용 내부 trace.

    사용자 화면에서는 렌더링하지 않는다.
    """

    trace = []

    for source in sources:
        document_id = _document_id(source)

        if not document_id:
            continue

        item = {
            "document_id": document_id,
            "score": round(
                float(source.get("score") or 0.0),
                6,
            ),
            "dataset": str(
                source.get("dataset") or ""
            ),
        }

        if source.get("retrieval_backend"):
            item["backend"] = str(
                source["retrieval_backend"]
            )

        trace.append(item)

    return trace


def _strip_internal_metadata(text: str) -> str:
    """
    사용자에게 보이면 안 되는 RAG 내부 메타데이터 제거.
    """

    value = str(text or "")

    labels = "|".join(
        re.escape(label)
        for label in DISPLAY_STRIP_LABELS
    )

    value = re.sub(
        rf"(?:^|\s)(?:{labels})\s*:\s*[^\n|]+",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\bRAG_DOCUMENT\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\bUSER_MEASUREMENT\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\b[0-9a-f]{20,64}\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\b[123]등급\b",
        " ",
        value,
    )

    value = re.sub(
        r"\s*\|\s*",
        " · ",
        value,
    )

    value = re.sub(
        r"(?:\s*·\s*){2,}",
        " · ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip(" ·|-\n\t")


def _safe_excerpt(
    source: dict[str, Any],
    limit: int = 220,
) -> str:
    """
    사용자에게 보여줄 수 있는 근거 설명.
    """

    if source.get("dataset") == "fitness_user_records":
        return (
            "로그인 사용자의 현재 운동·측정 맥락을 "
            "추천에 반영했습니다."
        )

    return _strip_internal_metadata(
        str(source.get("text") or "")
    )[:limit]


def _public_title(
    source: dict[str, Any],
) -> str:
    if source.get("dataset") == "fitness_user_records":
        return "내 운동·측정 정보"

    title = _strip_internal_metadata(
        str(source.get("title") or "")
    )

    return title or "운동 근거 자료"


def _response(
    answer_text: str,
    evidence_sources: list[dict[str, Any]],
    retrieved_sources: list[dict[str, Any]],
    cited_evidence_ids: set[str] | None = None,
    routing_flag: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    사용자에게 보여주는 sources와
    하네스 평가용 trace를 분리한다.
    """

    cited_evidence_ids = (
        cited_evidence_ids or set()
    )

    visible_sources: list[dict[str, Any]] = []
    cited_doc_ids: list[str] = []
    evidence_text: dict[str, str] = {}

    for index, source in enumerate(
        evidence_sources,
        1,
    ):
        evidence_id = f"E{index}"

        if evidence_id not in cited_evidence_ids:
            continue

        document_id = _document_id(source)

        public_source = {
            "evidence_id": evidence_id,
            "title": _public_title(source),
            "url": str(
                source.get("url")
                or source.get("source_url")
                or ""
            ),
        }

        visible_sources.append(
            public_source
        )

        if document_id:
            cited_doc_ids.append(
                document_id
            )

            evidence_text[document_id] = str(
                source.get("text") or ""
            )[:700]

    return {
        "answer": _strip_internal_metadata(
            answer_text
        ),

        "sources": visible_sources,

        "grounded": bool(
            visible_sources
        ),

        "grounding_type": (
            "GROUNDED"
            if visible_sources
            else "NONE"
        ),

        "harness_version": (
            "fitness-chat-v3-conversational-grounded"
        ),

        # 아래 값들은 하네스/평가용이다.
        # 프론트 채팅창에는 렌더링하지 않는다.
        "retrieved_doc_ids": _retrieval_trace(
            retrieved_sources
        ),

        "cited_doc_ids": list(
            dict.fromkeys(
                cited_doc_ids
            )
        ),

        "evidence_text": evidence_text,

        "routing_flag": routing_flag,
        "diagnostics": diagnostics or {},
    }


def _last_assistant_text(
    history: list[dict[str, str]] | None,
) -> str:
    for item in reversed(
        history or []
    ):
        if (
            item.get("role") == "assistant"
            and str(
                item.get("content") or ""
            ).strip()
        ):
            return str(
                item.get("content") or ""
            ).strip()

    return ""


def _is_referential(
    message: str,
) -> bool:
    compact = re.sub(
        r"\s+",
        "",
        message,
    )

    return any(
        re.sub(
            r"\s+",
            "",
            term,
        ) in compact
        for term in REFERENTIAL_TERMS
    )


def _intent(message: str) -> str:
    compact = re.sub(r"\s+", "", message)
    if "측정" in compact and any(term in compact for term in ("반영", "맞춰", "기록", "결과")):
        return "MEASUREMENT_BASED_RECOMMEND"
    if any(term in compact for term in ("왜", "이유")):
        return "WHY_RECOMMENDED"
    if any(term in compact for term in ("어떻게", "방법", "자세", "하는법")) and _is_referential(message):
        return "HOW_TO"
    if any(term in compact for term in (
        "다른운동", "다른동작", "다른선택지", "다른걸추천", "다른거추천",
        "대신할운동", "대체운동",
    )):
        return "ALTERNATIVE"
    if any(term in compact for term in ("집에서", "실내", "홈트", "장비없이")):
        return "HOME_RECOMMEND"
    if any(term in compact for term in ("추천", "어떤운동", "뭐할")):
        return "RECOMMEND"
    return "EXERCISE_INFO"


def _last_recommended_exercise(history: list[dict[str, str]] | None) -> str:
    for item in reversed(history or []):
        if item.get("role") != "assistant":
            continue
        text = str(item.get("content") or "")
        for pattern in (
            r"오늘은\s+(.+?)(?:을|를)\s+(?:해보|추천)",
            r"다른 선택지로는\s+(.+?)(?:을|를)\s+(?:추천|볼)",
            r"앞서 추천한\s+(.+?)(?:은|는)\s+",
        ):
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip(" .")[:80]
                return re.sub(r"\s+운동$", "", name).strip()
    return ""


def _weakest_measurement_goal(user_context: str) -> str:
    candidates: list[tuple[float, str]] = []
    for factor, goal in MEASUREMENT_GOALS.items():
        for match in re.finditer(
            rf"{re.escape(factor)}[^/]*?상위\s*(\d+)(?:\s*[~～-]\s*(\d+))?%",
            user_context,
        ):
            upper = float(match.group(2) or match.group(1))
            candidates.append((upper, goal))
    return max(candidates, default=(0.0, ""))[1]


def _source_has_unrequested_condition(source: dict[str, Any], message: str, user_context: str) -> bool:
    haystack = f"{source.get('title', '')} {source.get('text', '')}"
    allowed = f"{message} {user_context}"
    return any(term in haystack and term not in allowed for term in SPECIAL_CONDITION_TERMS)


def _build_search_query(
    message: str,
    history: list[dict[str, str]] | None,
    user_context: str,
) -> str:
    """
    현재 질문 + 최근 대화 + 로그인 사용자 DB 맥락을
    검색 query에 같이 반영한다.
    """

    current_intent = _intent(message)
    last_exercise = _last_recommended_exercise(history)
    recent_users = [
        str(
            h.get("content") or ""
        )
        for h in (history or [])[-6:]
        if h.get("role") == "user"
    ]

    last_assistant = _last_assistant_text(
        history
    )

    if current_intent == "WHY_RECOMMENDED" and last_exercise:
        base = f"{last_exercise} 운동 목적 효과 추천 이유"
    elif current_intent == "HOW_TO" and last_exercise:
        base = f"{last_exercise} 운동 방법 수행 순서 자세"
    elif current_intent == "ALTERNATIVE":
        base = f"{message} 일반 운동 추천"
    elif current_intent == "HOME_RECOMMEND":
        base = f"{message} 실내 가정 홈트 공통 운동"
    elif current_intent == "MEASUREMENT_BASED_RECOMMEND":
        goal = _weakest_measurement_goal(user_context)
        base = f"{goal or '체력 보완'} 운동 추천"
    elif _is_referential(message) and last_assistant:
        base = f"{last_exercise or last_assistant[:160]} {message}"

    else:
        base = " ".join(
            [
                *recent_users[-2:],
                message,
            ]
        )

    profile_match = re.search(r"로그인 사용자 프로필:\s*([^.]*)", user_context or "")
    compact_user_context = profile_match.group(1).strip() if profile_match else ""

    if compact_user_context:
        base = (
            f"{base} "
            f"{compact_user_context}"
        )

    return base[-700:]


def _contains_hidden_chat_metadata(
    text: str,
) -> bool:
    folded = str(
        text or ""
    ).casefold()

    return any(
        term.casefold() in folded
        for term in HIDDEN_CHAT_TERMS
    )


def _exercise_name(
    source: dict[str, Any],
) -> str:
    """
    검색 문서에서 사용자용 운동명 추출.
    """

    title = _strip_internal_metadata(
        str(
            source.get("title") or ""
        )
    ).strip()

    if title and not any(term in title for term in ("설명한 운동처방 동영상", "운동처방 동영상")):
        title = re.sub(
            r"\s*\((?:준비운동|본운동|정리운동)\)\s*$",
            "",
            title,
        ).strip()

        return title

    text = str(
        source.get("text") or ""
    )

    match = re.search(
        r"운동명\s*:\s*([^\n|]+)",
        text,
    )

    if not match:
        title = re.sub(r"(?:을|를)?\s*설명한\s*운동처방\s*동영상.*$", "", title).strip()
        return title

    return _strip_internal_metadata(
        match.group(1)
    ).strip()


def _compact_match_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).casefold()


def _exercise_name_aliases(name: str) -> list[str]:
    """Return conservative public-name aliases for exact exercise matching.

    Many stored titles include an English parenthetical suffix while the user only
    types the Korean title.  Matching the full stored title alone therefore misses
    legitimate exact-exercise questions and lets a semantically similar exercise
    take over the answer.
    """
    raw = re.sub(r"\s+", " ", str(name or "")).strip()
    if not raw:
        return []
    aliases = [raw]
    no_parenthetical = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", raw).strip()
    if no_parenthetical and no_parenthetical not in aliases:
        aliases.append(no_parenthetical)

    # Bilingual/slash titles are common in the source data.  Treat each side as
    # a public exact alias too, e.g. "Dead lift/Bent over row" and
    # "Knee up/Shoulder press".
    parenthetical = re.search(r"[（(]([^）)]{2,120})[）)]", raw)
    parts_source = [raw, no_parenthetical]
    if parenthetical:
        inside = parenthetical.group(1).strip()
        if inside:
            aliases.append(inside)
            parts_source.append(inside)
    for value in parts_source:
        for part in re.split(r"[/／]", value or ""):
            part = re.sub(r"\s+", " ", part).strip(" -,.?\t")
            if len(_compact_match_text(part)) >= 4 and part not in aliases:
                aliases.append(part)

    # Numbered variants such as '-2' are matched both with and without spacing,
    # while keeping the numbered public title itself preferred.
    base_values = list(aliases)
    for value in base_values:
        numbered = re.sub(r"\s*-\s*(\d+)\s*$", r"-\1", value).strip()
        if numbered and numbered not in aliases:
            aliases.append(numbered)
        unnumbered = re.sub(r"\s*-\s*\d+\s*$", "", value).strip()
        if unnumbered and len(_compact_match_text(unnumbered)) >= 4 and unnumbered not in aliases:
            aliases.append(unnumbered)
    return aliases


def _requested_exercise_match(source: dict[str, Any], message: str) -> bool:
    """True when the requested public exercise is grounded in this source.

    Primary match uses the stored public exercise name.  Some production rows,
    especially video/prescription variants, do not expose `_exercise_name` in
    facet metadata even though the exact public name is present in title/content.
    In that case validate the high-precision query aliases against title/text
    rather than rejecting a legitimate exact hit.
    """
    question = _compact_match_text(message)
    for alias in _exercise_name_aliases(_exercise_name(source)):
        name = _compact_match_text(alias)
        if name and len(name) >= 4 and name in question:
            return True

    metadata_text = ""
    try:
        metadata_text = json.dumps(source.get("metadata") or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        metadata_text = str(source.get("metadata") or "")
    searchable = _compact_match_text(
        f"{source.get('title', '')} {source.get('text', '')} {metadata_text}"
    )
    if not searchable:
        return False
    for query in _exercise_lookup_queries(message):
        qkey = _compact_match_text(query)
        if len(qkey) >= 4 and qkey in searchable:
            return True
    return False


def _requested_exercise_specificity(source: dict[str, Any], message: str) -> int:
    """Prefer the longest public-name match over a slash component match."""
    query_keys = [
        _compact_match_text(value) for value in _exercise_lookup_queries(message)
        if len(_compact_match_text(value)) >= 4
    ]
    alias_keys = [
        _compact_match_text(value) for value in _exercise_name_aliases(_exercise_name(source))
        if len(_compact_match_text(value)) >= 4
    ]
    return max(
        (
            min(len(query_key), len(alias_key))
            for query_key in query_keys
            for alias_key in alias_keys
            if query_key in alias_key or alias_key in query_key
        ),
        default=0,
    )


# metadata-aware hybrid rerank v1 20260922
_METADATA_RERANK_AGE_TERMS = ("유소년", "청소년", "성인", "어르신")
_METADATA_RERANK_PHASE_TERMS = ("준비운동", "본운동", "마무리운동")


def _metadata_rerank_question_constraints(message: str) -> tuple[str | None, str | None, str | None]:
    text = str(message or "")
    age = next((value for value in _METADATA_RERANK_AGE_TERMS if value in text), None)
    sex = "M" if "남성" in text else ("F" if "여성" in text else None)
    phase = next((value for value in _METADATA_RERANK_PHASE_TERMS if value in text), None)
    return age, sex, phase


def _metadata_rerank_source_text(source: dict[str, Any]) -> str:
    metadata = source.get("metadata") or {}
    metadata_text = ""
    if isinstance(metadata, dict):
        metadata_text = "\n".join(
            f"{key}: {value}"
            for key, value in metadata.items()
            if value is not None
        )
    return (
        f"{source.get('title', '')}\n"
        f"{source.get('text', '')}\n"
        f"{metadata_text}"
    )


def _metadata_rerank_source_constraints(source: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    text = _metadata_rerank_source_text(source)

    age = None
    for pattern in (
        r"대상\s*연령군\s*:\s*([^\n\r|]+)",
        r"연령군\s*:\s*([^\n\r|]+)",
        r"age_group\s*:\s*([^\n\r|]+)",
        r"life_stage\s*:\s*([^\n\r|]+)",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            age = next((term for term in _METADATA_RERANK_AGE_TERMS if term in value), value or None)
            break

    sex = None
    for pattern in (
        r"성별\s*:\s*([MF])(?:\b|$)",
        r"sex\s*:\s*([MF])(?:\b|$)",
        r"gender\s*:\s*([MF])(?:\b|$)",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            sex = match.group(1).upper()
            break
    if sex is None:
        if "여성" in text:
            sex = "F"
        elif "남성" in text:
            sex = "M"

    phase = None
    for pattern in (
        r"운동\s*단계\s*:\s*([^\n\r|]+)",
        r"단계\s*:\s*([^\n\r|]+)",
        r"exercise_stage\s*:\s*([^\n\r|]+)",
        r"phase\s*:\s*([^\n\r|]+)",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            phase = next((term for term in _METADATA_RERANK_PHASE_TERMS if term in value), value or None)
            break
    if phase is None:
        phase = next((term for term in _METADATA_RERANK_PHASE_TERMS if term in text), None)

    return age, sex, phase


def _metadata_rerank_lexical_similarity(left: str, right: str) -> float:
    def _ngrams(value: str, n: int = 2) -> set[str]:
        compact = _compact_match_text(value)
        if not compact:
            return set()
        if len(compact) < n:
            return {compact}
        return {compact[i:i+n] for i in range(len(compact) - n + 1)}

    a = _ngrams(left)
    b = _ngrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _metadata_rerank_score(source: dict[str, Any], message: str, original_rank: int) -> float:
    age_q, sex_q, phase_q = _metadata_rerank_question_constraints(message)
    age_d, sex_d, phase_d = _metadata_rerank_source_constraints(source)

    exercise_name = _exercise_name(source) or _public_title(source)
    title = str(source.get("title") or "")

    lexical = (
        10.0 * _metadata_rerank_lexical_similarity(message, exercise_name)
        + 4.0 * _metadata_rerank_lexical_similarity(message, title)
    )

    # Exact name stays useful but is no longer an unconditional dominant boost.
    exact_strength = float(_requested_exercise_specificity(source, message) or 0)
    exact_boost = min(16.0, exact_strength * 0.8)

    metadata_score = 0.0
    explicit_constraints = 0
    conflicts = 0

    if age_q:
        explicit_constraints += 1
        if age_d == age_q:
            metadata_score += 9.0
        elif age_d:
            metadata_score -= 9.0
            conflicts += 1

    if sex_q:
        explicit_constraints += 1
        if sex_d == sex_q:
            metadata_score += 9.0
        elif sex_d:
            metadata_score -= 9.0
            conflicts += 1

    if phase_q:
        explicit_constraints += 1
        if phase_d == phase_q:
            metadata_score += 9.0
        elif phase_d:
            metadata_score -= 8.0
            conflicts += 1

    # Regression fix: exact-name sibling variants must not override explicit metadata.
    if explicit_constraints and conflicts:
        exact_boost = min(exact_boost, 4.0)

    # Preserve vector order as a modest prior.
    vector_prior = max(0.0, 3.0 - 0.04 * max(original_rank - 1, 0))

    return lexical + exact_boost + metadata_score + vector_prior


def _metadata_aware_rerank_sources(
    sources: list[dict[str, Any]],
    message: str,
) -> list[dict[str, Any]]:
    if len(sources) <= 1:
        return list(sources)

    ranked = sorted(
        enumerate(sources, 1),
        key=lambda item: (
            -_metadata_rerank_score(item[1], message, item[0]),
            item[0],
            _document_id(item[1]),
        ),
    )
    return [source for _, source in ranked]


def _explicit_exercise_lookup(message: str) -> bool:
    """Detect questions that name one exercise and ask about *that* exercise.

    These turns must never silently degrade into a generic recommendation.  It is
    safer to abstain when the named exercise cannot be grounded than to substitute
    the nearest vector-search result.
    """
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    compact = re.sub(r"\s+", "", text)
    if not text:
        return False
    if _intent(text) == "ALTERNATIVE":
        return False
    if _quoted_search_subject(text):
        return True
    cues = (
        "영상은", "영상 어디", "어디에서 볼", "어디서 볼",
        "어떤 운동 도구", "어떤 도구", "도구가 필요",
        "어느 연령군", "어떤 프로그램",
        "관련 있는 운동", "관련있는운동", "맞물리는 운동", "맞물리는운동",
        "이어지는 운동", "이어지는운동", "연결되는 운동", "연결되는운동",
        "같은 체력요인", "같은체력요인", "같은 갈래", "같은갈래",
        "운동인지", "운동인가요", "운동인가",
        "운동 후보", "운동후보", "후보에 들어", "후보가 되", "후보가 될",
        "어떤 운동인가요", "어떤운동인가요", "어떤 운동인가", "어떤운동인가",
        "운동은 무엇", "운동이 무엇",
    )
    if any(cue.replace(" ", "") in compact for cue in cues):
        return True
    # Program titles and slash/parenthetical exercise names are strong signs of
    # an explicitly named subject.  Do not treat generic phrases such as
    # "허리 운동을 추천해줘" or "그 운동은 왜?" as exact lookups.
    if "프로그램" in compact and any(term in compact for term in ("도제", "프로그램이", "프로그램은", "프로그램도", "프로그램을")):
        return True
    if ("/" in text or "(" in text or "（" in text) and "운동" in compact:
        return True
    return False


def _video_request(message: str) -> bool:
    """Recognize natural Korean requests that ask to receive or watch a video."""
    compact = re.sub(r"\s+", "", str(message or "")).casefold()
    if not any(token in compact for token in ("영상", "동영상", "비디오")):
        return False
    return any(token in compact for token in (
        "알려", "보여", "추천", "찾아", "찾어", "보고싶", "보려",
        "볼수", "어디", "링크", "주소", "열어", "틀어", "재생",
    ))


def _deterministic_video_response(
    message: str,
    sources: list[dict[str, Any]],
    retrieved_sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return playable cited video sources instead of a prose-only answer."""
    if not _video_request(message):
        return None
    videos: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for source in sources:
        url = str(source.get("url") or source.get("source_url") or "").strip()
        if not url:
            url = _field_value(source, ("영상 URL", "video_url", "url"))
        if not re.match(r"^https?://", url, flags=re.I) or url in seen_urls:
            continue
        seen_urls.add(url)
        item = dict(source)
        item["url"] = url
        videos.append(item)
        if len(videos) == 3:
            break
    if not videos:
        return _response(
            "요청하신 조건과 직접 일치하는 운동 자료는 확인했지만, 현재 근거에 재생할 수 있는 영상 주소가 없어요.",
            [], retrieved_sources, set(), routing_flag="VIDEO_URL_MISSING",
        )
    names = [(_exercise_name(source) or _public_title(source)) for source in videos]
    return _response(
        f"{', '.join(names)} 영상을 찾았어요. 아래 출처 박스의 '영상 보기'를 누르면 바로 확인할 수 있어요.",
        videos, retrieved_sources,
        {f"E{index}" for index in range(1, len(videos) + 1)},
        routing_flag="VIDEO_RESULTS",
    )


def _quoted_search_subject(message: str) -> str:
    """Return an explicitly quoted exercise/title for a high-precision search."""
    for pattern in (r"'([^']{2,120})'", r'"([^\"]{2,120})"', r"‘([^’]{2,120})’"):
        match = re.search(pattern, str(message or ""))
        if match:
            return match.group(1).strip()
    return ""




def _exercise_lookup_queries(message: str) -> list[str]:
    """Build a few high-precision search queries from a named-exercise turn.

    The production vector query may include profile/measurement prose.  For an
    exact exercise lookup that extra context can push the actual exercise out of
    top-k.  These compact subject queries intentionally keep only the part of the
    user utterance most likely to be the exercise/program title.
    """
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    if not text:
        return []
    candidates: list[str] = []

    # Explicit quoted title wins.
    quoted = _quoted_search_subject(text)
    if quoted:
        candidates.append(quoted)

    # Descriptive lookup such as "밴드로 어깨를 뒤로 들어올리는 운동은 무엇".
    # Remove common Korean particles/endings so stored noun-form titles can be
    # matched without knowing any particular case or exercise name.
    descriptive = re.search(r"(.{4,100}?)\s*운동(?:은|이)\s*무엇", text)
    if descriptive:
        candidate = descriptive.group(1).strip(" ,.?")
        if " 중 " in candidate:
            candidate = candidate.rsplit(" 중 ", 1)[-1].strip()
        candidate = re.sub(r"^([가-힣]+?)(?:으로|로)(?=\s)", r"\1", candidate)
        candidate = re.sub(r"([가-힣]+?)(?:을|를|은|는|이|가)(?=\s)", r"\1", candidate)
        candidate = re.sub(r"들어올리는$", "들어올리기", candidate)
        if len(_compact_match_text(candidate)) >= 4:
            candidates.append(candidate)

    # Slash-separated public exercise titles can be exact names even without
    # parentheses, e.g. "앞/옆으로 팔 들어올리기".  Query the complete slash
    # phrase before splitting it into components.
    slash_patterns = (
        r"([가-힣A-Za-z0-9·\- ]{2,60}/[가-힣A-Za-z0-9·\- ]{2,60})(?=\s*(?:\(|운동|은|는|이|가|도|을|를|영상|프로그램|후보|관련|$))",
        r"([가-힣A-Za-z0-9·\- ]{2,60}/[가-힣A-Za-z0-9·\- ]{2,60})",
    )
    for pattern in slash_patterns:
        for match in re.finditer(pattern, text):
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ,.?	")
            for delimiter in (
                "찾고 있는데 ", "나왔는데 ", "있는데 ", "볼 때 ", "놓고 볼 때 ",
                "기준으로 ", "고려하면 ", "생각하면 ", "중 ",
            ):
                if delimiter in candidate:
                    candidate = candidate.split(delimiter)[-1].strip()
            if len(_compact_match_text(candidate)) >= 4:
                candidates.append(candidate)

    # Korean shared-suffix shorthand such as "앞/옆으로 팔 들어올리기"
    # represents two public exercise names. Expand the short left side using
    # the particle/suffix from the right side so either stored title can match.
    for match in re.finditer(
        r"([가-힣]{1,8})/([가-힣]{1,12})(으로|로)\s+([가-힣A-Za-z0-9·\- ]{2,60})",
        text,
    ):
        left, right_root, particle, suffix = match.groups()
        suffix = re.sub(r"\s+", " ", suffix).strip()
        # Trim common grammatical tails after the exercise title.
        suffix = re.split(
            r"(?:이|가|은|는|도|을|를)?\s*(?:근력\s*쪽\s*)?(?:운동\s*)?(?:후보|관련|영상|프로그램)",
            suffix,
            maxsplit=1,
        )[0].strip()
        if suffix:
            # Korean directional particles depend on the left noun's 받침.
            # Generate both safe surface variants for the abbreviated left half;
            # exact matching will retain only the form present in the corpus.
            candidates.append(f"{left}으로 {suffix}")
            candidates.append(f"{left}로 {suffix}")
            candidates.append(f"{right_root}{particle} {suffix}")

    # Parenthetical bilingual titles such as
    # '무릎 올리기/머리 위로 들어올리기(Knee up/Shoulder press)'.
    for match in re.finditer(r"([가-힣A-Za-z0-9·/\- ]{3,100}\([^)]{2,100}\))", text):
        candidate = match.group(1).strip(" ,.?\t")
        # Keep only the tail after common context delimiters.
        for delimiter in ("나왔는데 ", "있는데 ", "볼 때 ", "기준으로 ", "고려하면 ", "생각하면 ", "중 "):
            if delimiter in candidate:
                candidate = candidate.split(delimiter)[-1].strip()
        if len(candidate) >= 4:
            candidates.append(candidate)

    # Take the phrase immediately preceding an information cue.
    cue_patterns = (
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*운동에는\s*어떤\s*운동\s*도구",
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*운동\s*영상",
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*영상은",
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*어느\s*연령군",
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*어떤\s*프로그램",
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*(?:제\s*)?근력\s*결과와\s*맞물리는",
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*(?:근력\s*쪽\s*)?운동\s*후보",
        r"(.{4,120}?)(?:은|는|이|가|도|을|를)?\s*관련\s*있는\s*운동",
    )
    for pattern in cue_patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        candidate = match.group(1).strip(" ,.?\t")
        for delimiter in (
            "나왔는데 ", "있는데 ", "볼 때 ", "기준으로 ", "고려하면 ", "생각하면 ",
            "중 ", "놓고 볼 때 ", "결과만 ", "결과를 ",
        ):
            if delimiter in candidate:
                candidate = candidate.split(delimiter)[-1].strip()
        # Remove broad setup clauses that are not part of the exercise title.
        candidate = re.sub(
            r"^(?:센터에서|집에서|현재|지금|앞에서는|계정이[^.?!]{0,40}?\s)",
            "",
            candidate,
        ).strip()
        if len(_compact_match_text(candidate)) >= 4:
            candidates.append(candidate)

    # Program titles often survive best when queried from their title suffix.
    program_match = re.search(r"([가-힣A-Za-z0-9·/\- ]{3,90}프로그램)", text)
    if program_match:
        candidate = program_match.group(1).strip()
        for delimiter in ("고려하면 ", "생각하면 ", "기준으로 "):
            if delimiter in candidate:
                candidate = candidate.split(delimiter)[-1].strip()
        candidates.append(candidate)

    # Also query each public component of bilingual/slash names independently.
    # This recovers source rows whose title stores only one half of the user's
    # composite label.
    composite_chunks: list[str] = []
    for candidate in list(candidates):
        paren = re.search(r"[（(]([^）)]{2,120})[）)]", candidate)
        if paren:
            composite_chunks.append(paren.group(1).strip())
        composite_chunks.append(re.sub(r"\s*[（(][^）)]*[）)]\s*", " ", candidate).strip())
    for chunk in composite_chunks:
        for part in re.split(r"[/／]", chunk):
            part = re.sub(r"\s+", " ", part).strip(" -,.?\t")
            if len(_compact_match_text(part)) >= 4:
                candidates.append(part)
                # Search both numbered and base public form.
                base = re.sub(r"\s*-\s*\d+\s*$", "", part).strip()
                if base and base != part:
                    candidates.append(base)

    # Deduplicate while preserving order; avoid using the whole question as a
    # supposedly precise query.
    result: list[str] = []
    seen: set[str] = set()
    whole = _compact_match_text(text)
    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,.?\t")
        key = _compact_match_text(candidate)
        if len(key) < 4 or key == whole or key in seen:
            continue
        seen.add(key)
        result.append(candidate[:160])
    return result[:10]



def _source_from_runtime_record(runtime: Any, document_id: str, record: Any, score: float = 1.0) -> dict[str, Any]:
    # Real RagRuntime._fetch_full_records() returns sqlite3.Row, while unit-test
    # doubles often return dict. Normalize both to a plain mapping before using
    # .get(), otherwise exact-index hits raise AttributeError and surface as 500.
    if not isinstance(record, dict):
        try:
            record = dict(record)
        except Exception:
            record = {
                key: record[key]
                for key in ("id", "dataset", "title", "content", "metadata_json", "occurrence_count")
                if hasattr(record, "keys") and key in record.keys()
            }
    metadata_raw = record.get("metadata_json")
    metadata = json.loads(metadata_raw or "{}") if isinstance(metadata_raw, str) else dict(metadata_raw or {})
    if hasattr(runtime, "_metadata_with_facets"):
        try:
            metadata = runtime._metadata_with_facets(document_id, metadata)
        except Exception:
            pass
    source = {
        "id": document_id,
        "dataset": str(record.get("dataset") or ""),
        "title": str(record.get("title") or ""),
        "text": str(record.get("content") or record.get("text") or ""),
        "metadata": metadata,
        "occurrence_count": int(record.get("occurrence_count") or 1),
        "score": float(score),
        "retrieval_backend": "exact_exercise_index",
    }
    video_url = str(metadata.get("video_url") or metadata.get("url") or "").strip()
    if not video_url:
        m = re.search(r"(?m)^영상 URL\s*:\s*(\S+)", source["text"])
        video_url = m.group(1).strip() if m else ""
    if video_url:
        source["url"] = video_url
    return source



def _runtime_documents_db_path(runtime: Any) -> Path | None:
    """Best-effort discovery of the runtime SQLite document store.

    Production RagRuntime keeps the parsed RAG documents in SQLite, but the
    exact attribute name is intentionally not assumed here.  Discover a local
    *.db/*.sqlite path from the runtime instance and verify that it contains
    the `documents` table before using it.
    """
    cached = getattr(runtime, "_exact_documents_db_path_cache", None)
    if cached:
        p = Path(str(cached))
        if p.exists():
            return p

    candidates: list[Path] = []
    preferred_names = (
        "sqlite_path", "sqlite_db_path", "db_path", "database_path",
        "sqlite_db", "db_file", "documents_db", "rag_db_path",
    )
    for name in preferred_names:
        value = getattr(runtime, name, None)
        if isinstance(value, (str, Path)):
            candidates.append(Path(value))

    try:
        values = vars(runtime).items()
    except Exception:
        values = ()
    for name, value in values:
        if not isinstance(value, (str, Path)):
            continue
        text = str(value)
        if text.lower().endswith((".db", ".sqlite", ".sqlite3")):
            candidates.append(Path(text))

    seen: set[str] = set()
    for candidate in candidates:
        try:
            candidate = candidate.expanduser().resolve()
        except Exception:
            continue
        key = str(candidate)
        if key in seen or not candidate.exists() or not candidate.is_file():
            continue
        seen.add(key)
        try:
            with sqlite3.connect(str(candidate)) as db:
                row = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1"
                ).fetchone()
            if row:
                try:
                    setattr(runtime, "_exact_documents_db_path_cache", str(candidate))
                except Exception:
                    pass
                return candidate
        except Exception:
            continue
    return None


def _sqlite_exact_exercise_sources(
    runtime: Any,
    message: str,
    datasets: list[str] | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Deterministic full-text fallback over the local SQLite document store.

    Used only when the lightweight facet exact index misses.  The query aliases
    are already high precision, so a local LIKE scan over title/content/metadata
    is safer than increasing vector-search top-k indefinitely.
    """
    db_path = _runtime_documents_db_path(runtime)
    if db_path is None:
        return []

    raw_queries = _exercise_lookup_queries(message)
    terms: list[str] = []
    seen_terms: set[str] = set()
    for query in raw_queries:
        query = re.sub(r"\s+", " ", str(query or "")).strip(" ,.?	")
        if not query:
            continue
        # Include aliases/components but avoid very short generic fragments.
        variants = [query] + _exercise_name_aliases(query)
        for value in variants:
            value = re.sub(r"\s+", " ", str(value or "")).strip(" ,.?	")
            key = value.casefold()
            if len(_compact_match_text(value)) < 4 or key in seen_terms:
                continue
            seen_terms.add(key)
            terms.append(value)
        if len(terms) >= 18:
            break
    if not terms:
        return []

    allowed = [str(x) for x in (datasets or []) if str(x).strip()]
    clauses: list[str] = []
    params: list[Any] = []
    for term in terms:
        pattern = f"%{term}%"
        clauses.append("(title LIKE ? COLLATE NOCASE OR content LIKE ? COLLATE NOCASE OR metadata_json LIKE ? COLLATE NOCASE)")
        params.extend([pattern, pattern, pattern])

    sql = (
        "SELECT id, dataset, title, content, metadata_json, occurrence_count "
        "FROM documents WHERE (" + " OR ".join(clauses) + ")"
    )
    if allowed:
        sql += " AND dataset IN (" + ",".join("?" for _ in allowed) + ")"
        params.extend(allowed)
    sql += " LIMIT ?"
    params.append(max(limit * 4, 80))

    try:
        with sqlite3.connect(str(db_path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(sql, params).fetchall()
    except Exception as exc:
        LOGGER.debug("SQLite exact exercise lookup failed: %s", exc)
        return []

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for position, row in enumerate(rows):
        source = _source_from_runtime_record(
            runtime,
            str(row["id"]),
            row,
            score=max(0.88, 0.995 - position * 0.0005),
        )

        # exact-source facet enrichment v2
        # Merge normalized fields from the facet belonging to the SAME document.
        # This does not infer new facts and does not use case/gold IDs.
        if source:
            source_doc_id = str(
                source.get("document_id")
                or source.get("id")
                or row["id"]
                or ""
            )
            matching_facet = next(
                (
                    facet
                    for facet in (getattr(runtime, "facet_records", []) or [])
                    if str(
                        facet.get("_id")
                        or facet.get("id")
                        or facet.get("document_id")
                        or ""
                    ) == source_doc_id
                ),
                None,
            )
            if matching_facet:
                facet_source = _source_from_exact_facet(
                    matching_facet,
                    score=float(source.get("score") or 1.0),
                )

                facet_meta = facet_source.get("metadata")
                if isinstance(facet_meta, dict):
                    merged_meta = dict(source.get("metadata") or {})
                    for key, value in facet_meta.items():
                        if value not in (None, "", [], {}):
                            merged_meta.setdefault(key, value)
                    source["metadata"] = merged_meta

                for key in (
                    "exercise_type",
                    "fitness_factor",
                    "factor_name",
                    "target_area",
                    "age_group",
                    "sex",
                    "equipment",
                    "location",
                ):
                    if source.get(key) in (None, "", [], {}):
                        value = _field_value(facet_source, (key,))
                        if value not in (None, "", [], {}):
                            source[key] = value

        searchable = _compact_match_text(
            f"{source.get('title', '')} {source.get('text', '')} "
            f"{json.dumps(source.get('metadata') or {}, ensure_ascii=False)}"
        )
        best = 0
        for term in terms:
            tkey = _compact_match_text(term)
            if not tkey:
                continue
            if tkey in searchable:
                # Full bilingual/slash titles outrank single components.
                bonus = 2 if ("/" in term or "(" in term) else 1
                best = max(best, len(tkey) + bonus * 100)
        if best and _requested_exercise_match(source, message):
            scored.append((best, -position, source))

    scored.sort(reverse=True, key=lambda x: (x[0], x[1]))
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for _, __, source in scored:
        doc_id = _document_id(source)
        if doc_id and doc_id in seen_ids:
            continue
        if doc_id:
            seen_ids.add(doc_id)
        out.append(source)
        if len(out) >= limit:
            break
    return out



def _fetch_scan_exact_exercise_sources(
    runtime: Any,
    message: str,
    datasets: list[str] | None = None,
    limit: int = 40,
    batch_size: int = 500,
) -> list[dict[str, Any]]:
    """Fallback exact scan using the runtime's own full-record fetcher.

    This does not depend on knowing the SQLite path.  It narrows IDs by dataset
    from `facet_records`, fetches records in local batches, and checks the exact
    aliases against title/content/metadata.  Results are cached per runtime/query.
    """
    fetch = getattr(runtime, "_fetch_full_records", None)
    facets = getattr(runtime, "facet_records", None) or []
    if not callable(fetch) or not facets:
        return []

    allowed = {str(x) for x in (datasets or []) if str(x).strip()}
    query_key = tuple(
        _compact_match_text(q)
        for q in _exercise_lookup_queries(message)
        if len(_compact_match_text(q)) >= 4
    )
    if not query_key:
        return []

    cache = getattr(runtime, "_exact_fetch_scan_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            setattr(runtime, "_exact_fetch_scan_cache", cache)
        except Exception:
            pass
    cache_key = (tuple(sorted(allowed)), query_key, int(limit))
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return [dict(x) for x in cached]

    ids: list[str] = []
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        dataset = str(facet.get("_dataset") or facet.get("dataset") or "")
        if allowed and dataset not in allowed:
            continue
        doc_id = str(facet.get("_id") or facet.get("id") or "")
        if doc_id:
            ids.append(doc_id)

    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for start in range(0, len(ids), max(50, int(batch_size))):
        batch = ids[start:start + max(50, int(batch_size))]
        try:
            records = fetch(batch)
        except Exception as exc:
            LOGGER.debug("Exact fetch-scan batch failed at %s: %s", start, exc)
            continue

        if isinstance(records, dict):
            iterable = [(doc_id, records.get(doc_id)) for doc_id in batch]
        else:
            try:
                iterable = []
                for row in records or []:
                    try:
                        row_map = dict(row) if not isinstance(row, dict) else row
                    except Exception:
                        continue
                    doc_id = str(row_map.get("id") or "")
                    iterable.append((doc_id, row))
            except Exception:
                iterable = []

        for doc_id, row in iterable:
            if not doc_id or row is None or doc_id in seen_ids:
                continue
            try:
                source = _source_from_runtime_record(runtime, doc_id, row, score=0.992)
            except Exception:
                continue
            if not _requested_exercise_match(source, message):
                continue
            seen_ids.add(doc_id)
            out.append(source)
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break

    cache[cache_key] = [dict(x) for x in out]
    return out



def _normalize_full_record_result(records: Any) -> dict[str, Any]:
    """Normalize production/test fetch return shapes to {document_id: row}.

    Different RagRuntime builds have returned dicts, lists of dict/sqlite3.Row,
    and iterable row collections.  Exact facet hits must not be discarded just
    because the container shape differs.
    """
    if records is None:
        return {}
    if isinstance(records, dict):
        return records

    normalized: dict[str, Any] = {}
    try:
        iterable = list(records)
    except Exception:
        return normalized

    for row in iterable:
        try:
            row_map = row if isinstance(row, dict) else dict(row)
        except Exception:
            continue
        doc_id = str(
            row_map.get("id")
            or row_map.get("document_id")
            or row_map.get("_id")
            or ""
        ).strip()
        if doc_id:
            normalized[doc_id] = row
    return normalized


def _source_from_exact_facet(facet: dict[str, Any], score: float = 1.0) -> dict[str, Any]:
    """Last-resort exact evidence from a facet record itself.

    This proves existence/name/dataset only.  It never invents URL, age group,
    program, equipment, or factor fields that are absent from the facet.
    """
    doc_id = str(facet.get("_id") or facet.get("id") or "")
    dataset = str(facet.get("_dataset") or facet.get("dataset") or "")
    name = str(facet.get("_exercise_name") or facet.get("exercise_name") or "")
    metadata = {}
    for key, value in facet.items():
        if key.startswith("_") and key not in ("_id", "_dataset", "_exercise_name"):
            metadata[key[1:]] = value
        elif key not in ("id", "dataset", "exercise_name"):
            metadata[key] = value
    return {
        "id": doc_id,
        "dataset": dataset,
        "title": name,
        "text": f"운동명: {name}" if name else "",
        "metadata": metadata,
        "occurrence_count": 1,
        "score": float(score),
        "retrieval_backend": "exact_exercise_facet",
    }


def _exact_exercise_sources(runtime: Any, message: str, datasets: list[str] | None = None, limit: int = 40) -> list[dict[str, Any]]:
    """Resolve named exercises from the runtime's already-loaded facet index.

    This bypasses vector ranking for exact public exercise names.  The server
    preloads facet_records for every RAG document, including _exercise_name,
    dataset and document id, so this lookup is deterministic and cheap.
    """
    if not _explicit_exercise_lookup(message):
        return []
    requested = _exercise_lookup_queries(message)
    requested_keys = [_compact_match_text(x) for x in requested if len(_compact_match_text(x)) >= 4]
    if not requested_keys:
        return []
    allowed = set(datasets or [])
    hits: list[tuple[int, int, str]] = []
    for position, facet in enumerate(getattr(runtime, "facet_records", []) or []):
        dataset = str(facet.get("_dataset") or "")
        if allowed and dataset not in allowed:
            continue
        name = str(facet.get("_exercise_name") or "")
        aliases = _exercise_name_aliases(name)
        best = 0
        for alias in aliases:
            akey = _compact_match_text(alias)
            if len(akey) < 4:
                continue
            for qkey in requested_keys:
                if akey == qkey:
                    best = max(best, 4)
                elif qkey in akey or akey in qkey:
                    best = max(best, 3)
        if best:
            hits.append((best, -position, str(facet.get("_id") or "")))
    if not hits:
        sqlite_hits = _sqlite_exact_exercise_sources(runtime, message, datasets=datasets, limit=limit)
        if sqlite_hits:
            return sqlite_hits
        return _fetch_scan_exact_exercise_sources(runtime, message, datasets=datasets, limit=limit)
    hits.sort(reverse=True)
    ids=[]
    seen=set()
    for _,__,doc_id in hits:
        if doc_id and doc_id not in seen:
            seen.add(doc_id); ids.append(doc_id)
        if len(ids) >= limit:
            break
    fetch = getattr(runtime, "_fetch_full_records", None)
    if not callable(fetch):
        return _sqlite_exact_exercise_sources(runtime, message, datasets=datasets, limit=limit)
    try:
        records_raw = fetch(ids)
    except Exception:
        records_raw = None

    records = _normalize_full_record_result(records_raw)
    out=[]
    for rank, doc_id in enumerate(ids):
        record=records.get(doc_id)
        if record is None:
            continue
        out.append(_source_from_runtime_record(runtime, doc_id, record, score=max(0.90, 1.0-rank*0.001)))

    if out:
        return out

    # Facet lookup already proved exact exercise-name equality.  If the runtime
    # cannot materialize the corresponding full rows, do not throw that exact
    # evidence away.  Try other stores first, then preserve the facet itself as
    # a conservative existence/name-only source.
    sqlite_hits = _sqlite_exact_exercise_sources(runtime, message, datasets=datasets, limit=limit)
    if sqlite_hits:
        return sqlite_hits
    scan_hits = _fetch_scan_exact_exercise_sources(runtime, message, datasets=datasets, limit=limit)
    if scan_hits:
        return scan_hits

    facet_by_id = {
        str(f.get("_id") or f.get("id") or ""): f
        for f in (getattr(runtime, "facet_records", []) or [])
        if isinstance(f, dict)
    }
    facet_sources = []
    for rank, doc_id in enumerate(ids):
        facet = facet_by_id.get(doc_id)
        if not facet:
            continue
        facet_sources.append(_source_from_exact_facet(facet, score=max(0.90, 1.0-rank*0.001)))
    return facet_sources


def _field_value(source: dict[str, Any], labels: tuple[str, ...]) -> str:
    text = str(source.get("text") or "")
    metadata = source.get("metadata") or {}
    for label in labels:
        for key in (label, label.replace(" ", "_"), label.casefold().replace(" ", "_")):
            value = metadata.get(key) if isinstance(metadata, dict) else None
            if value not in (None, "", [], {}):
                if isinstance(value, (list, tuple, set)):
                    return ", ".join(str(x) for x in value if str(x).strip())
                return str(value).strip()
        m = re.search(rf"(?m)^{re.escape(label)}\s*:\s*([^\n|]+)", text)
        if m:
            return _strip_internal_metadata(m.group(1)).strip()
    return ""



FACTOR_SYNONYMS = {
    "근력": ("근력", "상지근기능", "하지근기능", "근기능"),
    "근지구력": ("근지구력",),
    "유연성": ("유연성",),
    "평형성": ("평형성", "균형", "균형성"),
    "민첩성": ("민첩성", "민첩"),
    "순발력": ("순발력",),
    "심폐지구력": ("심폐지구력", "심폐", "유산소"),
    "협응력": ("협응력", "협응"),
}


def _canonical_factor(value: str) -> str:
    compact = _compact_match_text(value)
    if not compact:
        return ""
    for canonical, aliases in FACTOR_SYNONYMS.items():
        for alias in aliases:
            if _compact_match_text(alias) in compact:
                return canonical
    return ""


def _source_factor(source: dict[str, Any]) -> str:
    """Infer a factor only from text literally present in the retrieved source.

    This is intentionally conservative.  We do not infer physiology from our
    own exercise knowledge; we only normalize explicit source wording such as
    '유연성운동', '평형성운동', '근력운동', etc.
    """
    explicit = _field_value(
        source,
        (
            "체력요인", "체력 요소", "운동 목적",
            "exercise_type", "facet_exercise_type",
            "fitness_factor", "factor_name",
        ),
    )
    if explicit:
        factor = _canonical_factor(explicit)
        if factor:
            return factor

    text = f"{source.get('title', '')} {source.get('text', '')}"
    # Strongest literal labels first to avoid mapping generic body parts.
    for canonical, aliases in FACTOR_SYNONYMS.items():
        for alias in aliases:
            if alias and alias in text:
                return canonical
    return ""


def _question_factor(message: str) -> str:
    text = str(message or "")
    # Preserve explicit user framing. '다리 쪽' alone is a body region, not a
    # fitness factor, so it intentionally does not map to 근력.
    for canonical, aliases in FACTOR_SYNONYMS.items():
        for alias in aliases:
            if alias and alias in text:
                return canonical
    return ""



# Korean unit-boundary parsing
def _history_measurement_factor(
    history: list[dict[str, str]] | None,
) -> str:
    """Return a verified fitness factor from the most recent measurement-result turn.

    Only an assistant turn that visibly contains both a measurement/result cue and
    a concrete measured value is eligible. This prevents unrelated exercise
    discussion from becoming a personal fitness factor merely because it mentions
    words such as '근력' or '유연성'.
    """
    for item in reversed(history or []):
        if str(item.get("role") or "") != "assistant":
            continue

        text = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
        if not text:
            continue

        compact = _compact_match_text(text)
        if not any(
            cue in compact
            for cue in (
                _compact_match_text("측정"),
                _compact_match_text("기록"),
                _compact_match_text("결과"),
                _compact_match_text("백분위"),
            )
        ):
            continue

        if not re.search(
            r"-?\d+(?:\.\d+)?\s*(?:cm|초|회|%|kg)"
            r"(?=$|\s|[,.!?;:)\]}]|(?:이고|이며|입니다|이다|으로|로|을|를|이|가|은|는|의|에|에서))",
            text,
            re.I,
        ):
            continue

        factor = _canonical_factor(text)
        if factor:
            return factor

        return ""

    return ""


# content-alignment relation/data-gap patch 20260921
def _current_measurement_factor_for_message(message: str, user_context: str) -> str:
    """Resolve the factor only from a stored measurement item explicitly named now."""
    compact = _compact_match_text(message)
    if not compact or not user_context:
        return ""

    best: tuple[int, str] | None = None
    for row in _context_measurement_rows(user_context):
        item_name = str(row.get("item_name") or "").strip()
        item_key = _compact_match_text(item_name)
        if not item_key or item_key not in compact:
            continue

        raw_factor = str(row.get("factor_name") or "").strip()
        factor = _canonical_factor(raw_factor) or raw_factor
        if not factor:
            continue

        candidate = (len(item_key), factor)
        if best is None or candidate[0] > best[0]:
            best = candidate

    return best[1] if best else ""


def _relation_factors_compatible(
    source_factor: str,
    asked_factor: str,
    source: dict[str, Any],
) -> bool:
    """Conservative compatibility for measurement-to-exercise relation questions."""
    if not source_factor or not asked_factor:
        return False
    if source_factor == asked_factor:
        return True
    if {source_factor, asked_factor} <= {"근력", "근지구력"}:
        return True

    if asked_factor == "하지근기능" and source_factor in {"근력", "근지구력"}:
        haystack = " ".join(
            str(value or "")
            for value in (
                source.get("title"),
                source.get("text"),
                _field_value(
                    source,
                    (
                        "target_area", "운동 부위", "주요 근육", "주동근",
                        "exercise_type", "운동 목적",
                    ),
                ),
            )
        )
        return any(
            token in haystack
            for token in (
                "하체", "하지", "엉덩", "골반", "넓적다리", "허벅지",
                "볼기근", "대퇴", "hamstring", "glute",
            )
        )

    return False


def _history_measurement_state(history: list[dict[str, str]] | None) -> str:
    """Return HAS_VALUE / NO_RECORD / UNKNOWN for the most recent assistant turn."""
    for item in reversed(history or []):
        if str(item.get("role") or "") != "assistant":
            continue
        text = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
        if not text:
            continue
        compact = _compact_match_text(text)
        if any(token in compact for token in (
            _compact_match_text("기록이 저장되어 있지 않아요"),
            _compact_match_text("측정 기록이 없어요"),
            _compact_match_text("저장된 측정 기록이 없어"),
        )):
            return "NO_RECORD"
        if re.search(r"(?:결과는|기록은)\s*-?\d+(?:\.\d+)?\s*(?:cm|초|회|%|kg)", text, re.I):
            return "HAS_VALUE"
        # Only inspect the latest meaningful assistant turn.
        return "UNKNOWN"
    return "UNKNOWN"


def _weakest_measurement_factor(user_context: str) -> tuple[str, str]:
    """Pick the weakest latest factor from authenticated measurement context.

    Prefer the structured v5.7 context parser.  Records are newest-first, so the
    first record for each factor is the current value and older history cannot
    override it.  Larger '또래 상위 X%' means weaker standing.
    """
    rows = _context_measurement_rows(user_context)
    if rows:
        seen: set[str] = set()
        candidates: list[tuple[float, str, str]] = []
        for row in rows:
            factor = _canonical_factor(str(row.get("factor_name") or "")) or str(row.get("factor_name") or "")
            if not factor or factor in seen:
                continue
            seen.add(factor)
            pct_text = str(row.get("percentile_text") or "")
            m = re.search(r"상위\s*(\d+)(?:\s*[~～-]\s*(\d+))?%", pct_text)
            if not m:
                continue
            lo = int(m.group(1))
            hi = int(m.group(2) or m.group(1))
            band = f"또래 상위 {lo}~{hi}%" if m.group(2) else f"또래 상위 {lo}%"
            candidates.append((float(hi), factor, band))
        if candidates:
            _, factor, band = max(candidates, key=lambda x: x[0])
            return factor, band

    # Backward-compatible parser for older context strings.
    text = re.sub(r"\s+", " ", str(user_context or ""))
    if not text:
        return "", ""
    seen: set[str] = set()
    candidates: list[tuple[float, str, str]] = []
    pattern = re.compile(
        r"(상지근기능|하지근기능|근지구력|유연성|심폐지구력|평형성|협응력|민첩성|순발력|근력)"
        r".{0,160}?상위\s*(\d+)(?:\s*[~～-]\s*(\d+))?%",
    )
    for match in pattern.finditer(text):
        raw_factor = match.group(1)
        factor = _canonical_factor(raw_factor) or raw_factor
        if factor in seen:
            continue
        seen.add(factor)
        lo = int(match.group(2))
        hi = int(match.group(3) or match.group(2))
        candidates.append((float(hi), factor, f"또래 상위 {lo}~{hi}%" if match.group(3) else f"또래 상위 {lo}%"))
    if not candidates:
        return "", ""
    _, factor, band = max(candidates, key=lambda x: x[0])
    return factor, band



MEASUREMENT_ITEM_ALIASES = {
    "상대악력": ("상대악력", "상대 악력"),
    "앉아윗몸앞으로굽히기": ("앉아윗몸앞으로굽히기", "앉아 윗몸 앞으로 굽히기", "좌전굴"),
    "의자에앉아3m표적돌아오기": ("의자에앉아 3m 표적돌아오기", "의자에 앉아 3m 표적 돌아오기", "3m 표적돌아오기"),
    "의자에앉았다일어서기": ("의자에앉았다일어서기", "의자에 앉았다 일어서기", "30초 의자 일어서기"),
}


def _requested_measurement_item(message: str) -> str:
    compact = _compact_match_text(message)
    for canonical, aliases in MEASUREMENT_ITEM_ALIASES.items():
        if any(_compact_match_text(alias) in compact for alias in aliases):
            return canonical
    return ""


def _requested_measurement_source(message: str) -> tuple[str, bool]:
    compact = _compact_match_text(message)
    if "센터기록은빼고" in compact or "센터기록제외" in compact or "센터측정은빼고" in compact:
        return "CENTER", True
    if "센터에서" in compact or "센터측정" in compact or "센터기록" in compact:
        return "CENTER", False
    if "집에서" in compact or "집측정" in compact or "홈측정" in compact:
        return "HOME", False
    return "", False


def _context_measurement_rows(user_context: str) -> list[dict[str, Any]]:
    """Parse only the structured records emitted by fitness_mvp v5.7+."""
    text = str(user_context or "")
    if "최근 측정기록:" not in text:
        return []
    chunk = text.split("최근 측정기록:", 1)[1]
    chunk = chunk.split(" 측정 범위:", 1)[0]
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"레코드\s+(?P<id>\d+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
        r"\[(?P<source>HOME|CENTER)\]\s+(?P<item>.*?)\s+/\s+체력요인\s+(?P<factor>.*?)\s+/\s+"
        r"값\s+(?P<value>-?\d+(?:\.\d+)?)(?P<unit>cm|초|회|%|kg)\s+/\s+(?P<pct>.*?)(?=\s+/\s+레코드|\s*$)"
    )
    for m in pattern.finditer(chunk):
        rows.append({
            "record_id": int(m.group("id")),
            "date": m.group("date"),
            "source": m.group("source"),
            "item_name": m.group("item").strip(),
            "factor_name": m.group("factor").strip(),
            "value": float(m.group("value")),
            "unit": m.group("unit"),
            "percentile_text": m.group("pct").strip(),
        })
    return rows


def _question_measurement_assertion(message: str) -> tuple[float | None, str]:
    # This deliberately reads only an explicit measurement-like number from the
    # user turn, not age, program stage, or percentages inside chat history.
    patterns = (
        r"(-?\d+(?:\.\d+)?)\s*(cm)\b",
        r"(-?\d+(?:\.\d+)?)\s*(%)",
        r"(-?\d+(?:\.\d+)?)\s*(회)\b",
        r"(-?\d+(?:\.\d+)?)\s*(초)\b",
    )
    for pattern in patterns:
        m = re.search(pattern, str(message or ""), re.I)
        if m:
            return float(m.group(1)), m.group(2)
    return None, ""


def _active_measurement_for_question(message: str, user_context: str) -> dict[str, Any] | None:
    rows = _context_measurement_rows(user_context)
    if not rows:
        return None
    item = _requested_measurement_item(message)
    source, exclude = _requested_measurement_source(message)
    for row in rows:  # emitted newest-first
        if item:
            item_compact = _compact_match_text(row.get("item_name", ""))
            aliases = MEASUREMENT_ITEM_ALIASES.get(item, (item,))
            if not any(_compact_match_text(a) in item_compact for a in aliases):
                continue
        if source:
            if exclude and row.get("source") == source:
                continue
            if not exclude and row.get("source") != source:
                continue
        return row
    return None


def _measurement_assertion_status(message: str, user_context: str) -> tuple[str, dict[str, Any] | None, float | None, str]:
    claimed, unit = _question_measurement_assertion(message)
    if claimed is None:
        return "NONE", None, None, ""
    parsed_rows = _context_measurement_rows(user_context)
    # Assertion reconciliation is enabled only when the authenticated context
    # actually carries structured measurement rows.  Missing context is not the
    # same thing as a verified "no record" result.
    if not parsed_rows:
        return "UNKNOWN_CONTEXT", None, claimed, unit
    row = _active_measurement_for_question(message, user_context)
    if row is None:
        return "NO_RECORD", None, claimed, unit
    if unit and str(row.get("unit") or "") != unit:
        return "UNIT_MISMATCH", row, claimed, unit
    actual = float(row.get("value"))
    if abs(actual - claimed) <= 1e-6:
        return "MATCH", row, claimed, unit
    return "VALUE_MISMATCH", row, claimed, unit


def _source_matches_explicit_constraints(source: dict[str, Any], message: str) -> bool:
    """Reject only explicit contradictions; missing metadata is not invented."""
    text = str(message or "")
    constraints: list[tuple[tuple[str, ...], str]] = []
    if "성인" in text:
        constraints.append((("대상 연령군", "연령군", "life_stage"), "성인"))
    if "청소년" in text:
        constraints.append((("대상 연령군", "연령군", "life_stage"), "청소년"))
    if "어르신" in text or "노인" in text:
        constraints.append((("대상 연령군", "연령군", "life_stage"), "어르신"))
    if "여성" in text:
        constraints.append((("성별", "sex"), "F"))
    if "남성" in text:
        constraints.append((("성별", "sex"), "M"))
    if "일반 측정 장소" in text or "일반 측정장소" in text:
        constraints.append((("측정 장소", "측정장소", "location"), "일반"))
    if "본운동" in text:
        constraints.append((("운동 단계", "운동단계", "stage"), "본운동"))

    for labels, expected in constraints:
        actual = _field_value(source, labels)
        if not actual:
            continue
        folded = _compact_match_text(actual)
        if expected == "성인":
            if not any(k in folded for k in (_compact_match_text("성인"), "adult")):
                return False
        elif expected == "청소년":
            if not any(k in folded for k in (_compact_match_text("청소년"), "youth", "adolescent")):
                return False
        elif expected == "어르신":
            if not any(k in folded for k in (_compact_match_text("어르신"), _compact_match_text("노인"), "senior", "older")):
                return False
        elif expected in ("F", "M"):
            if folded not in (expected.casefold(), _compact_match_text("여성" if expected == "F" else "남성")):
                return False
        else:
            if _compact_match_text(expected) not in folded:
                return False
    return True




LIFE_STAGE_TERMS = {
    "유아기": ("유아기", "유아"),
    "청소년": ("청소년", "청소년기"),
    "성인": ("성인", "성인기"),
    "어르신": ("어르신", "노인", "노년", "노년기"),
    "공통": ("공통", "전체 연령", "전연령", "전 연령"),
}


def _user_life_stage(user_context: str) -> str:
    """Read the authenticated profile life stage from injected context.

    fitness_mvp emits enum-style values such as ADULT/SENIOR, while some older
    fixtures use Korean labels. Support both representations.
    """
    text = str(user_context or "")
    profile = text.split("최근 측정기록:", 1)[0]
    compact = _compact_match_text(profile)

    enum_map = (
        ("PRESCHOOL", "유아기"),
        ("CHILD", "청소년"),
        ("TEEN", "청소년"),
        ("ADULT", "성인"),
        ("SENIOR", "어르신"),
    )
    profile_upper = profile.upper()
    for token, canonical in enum_map:
        if token in profile_upper:
            return canonical

    for canonical in ("유아기", "청소년", "성인", "어르신"):
        if _compact_match_text(canonical) in compact:
            return canonical
    return ""


def _source_life_stage(source: dict[str, Any]) -> str:
    """Return only an explicitly stated life-stage label from evidence."""
    explicit = _field_value(
        source,
        ("대상 연령군", "연령군", "life_stage", "age_group"),
    )
    if explicit:
        compact = _compact_match_text(explicit)
        explicit_upper = str(explicit).upper()
        enum_map = (
            ("PRESCHOOL", "유아기"),
            ("CHILD", "청소년"),
            ("TEEN", "청소년"),
            ("ADULT", "성인"),
            ("SENIOR", "어르신"),
            ("COMMON", "공통"),
            ("ALL", "공통"),
        )
        for token, canonical in enum_map:
            if token in explicit_upper:
                return canonical
        for canonical, aliases in LIFE_STAGE_TERMS.items():
            if any(_compact_match_text(alias) in compact for alias in aliases):
                return canonical

    # Some video-content rows carry age only inside title/description.
    text = f"{source.get('title', '')} {source.get('text', '')}"
    try:
        metadata_text = json.dumps(source.get("metadata") or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        metadata_text = str(source.get("metadata") or "")
    haystack = _compact_match_text(f"{text} {metadata_text}")
    for canonical, aliases in LIFE_STAGE_TERMS.items():
        if any(_compact_match_text(alias) in haystack for alias in aliases):
            return canonical
    return ""


def _source_age_compatible(source: dict[str, Any], user_life_stage: str) -> bool:
    """Reject explicit age contradictions, allow common/unspecified evidence."""
    if not user_life_stage:
        return True
    stage = _source_life_stage(source)
    if not stage or stage == "공통":
        return True
    return stage == user_life_stage


def _factor_facet_sources(
    runtime: Any,
    factor: str,
    datasets: list[str] | None = None,
    limit: int = 20,
    user_life_stage: str = "",
) -> list[dict[str, Any]]:
    """Deterministically resolve exercises explicitly labeled with a fitness factor.

    This mirrors the exact-exercise strategy: scan the already-loaded facet index
    first instead of hoping vector search happens to surface a matching document.
    Only literal factor evidence is accepted through `_source_factor`.
    """
    canonical = _canonical_factor(factor)
    if not canonical:
        return []

    allowed = {str(x) for x in (datasets or []) if str(x).strip()}
    cache = getattr(runtime, "_factor_facet_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            setattr(runtime, "_factor_facet_cache", cache)
        except Exception:
            pass

    cache_key = (canonical, tuple(sorted(allowed)), int(limit), user_life_stage)
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return [dict(x) for x in cached]

    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for position, facet in enumerate(getattr(runtime, "facet_records", []) or []):
        if not isinstance(facet, dict):
            continue
        dataset = str(facet.get("_dataset") or facet.get("dataset") or "")
        if allowed and dataset not in allowed:
            continue

        source = _source_from_exact_facet(facet, score=max(0.90, 0.999 - position * 0.000001))
        if _source_factor(source) != canonical:
            continue
        if not _source_age_compatible(source, user_life_stage):
            continue

        name = _exercise_name(source) or _public_title(source)
        if not name:
            continue

        compact_name = _compact_match_text(name)
        strength = 0
        if _compact_match_text(canonical) in compact_name:
            strength += 4
        metadata = source.get("metadata") or {}
        try:
            metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        except Exception:
            metadata_text = str(metadata)
        if _compact_match_text(canonical) in _compact_match_text(metadata_text):
            strength += 2
        ranked.append((strength, -position, source))

    ranked.sort(reverse=True, key=lambda x: (x[0], x[1]))
    sources = [x[2] for x in ranked[:limit]]

    # If facet metadata proves the factor but richer full records are available,
    # materialize those rows so downstream citations contain actual text/URL.
    ids = [_document_id(s) for s in sources if _document_id(s)]
    fetch = getattr(runtime, "_fetch_full_records", None)
    if ids and callable(fetch):
        try:
            records = _normalize_full_record_result(fetch(ids))
        except Exception:
            records = {}
        materialized: list[dict[str, Any]] = []
        by_id = {_document_id(s): s for s in sources}
        for rank, doc_id in enumerate(ids):
            row = records.get(doc_id)
            if row is None:
                materialized.append(by_id[doc_id])
                continue
            full = _source_from_runtime_record(
                runtime,
                doc_id,
                row,
                score=max(0.90, 0.999 - rank * 0.001),
            )
            if _source_factor(full) == canonical and _source_age_compatible(full, user_life_stage):
                materialized.append(full)
            else:
                # Keep the facet-proven source only when it is also age-compatible.
                facet_source = by_id[doc_id]
                if _source_age_compatible(facet_source, user_life_stage):
                    materialized.append(facet_source)
        sources = materialized[:limit]

    cache[cache_key] = [dict(x) for x in sources]
    return sources


def _exact_miss_diagnostics(runtime: Any, message: str, limit: int = 8) -> dict[str, Any]:
    """Small diagnostic payload for the next regression result.

    It is evaluation-only metadata, not rendered to the user.
    """
    aliases = _exercise_lookup_queries(message)
    key_terms: list[str] = []
    for alias in aliases:
        for token in re.findall(r"[A-Za-z]{3,}|[가-힣]{2,}", alias):
            token_cf = token.casefold()
            if token_cf not in key_terms:
                key_terms.append(token_cf)
    candidates: list[tuple[int, dict[str, str]]] = []
    for facet in getattr(runtime, "facet_records", []) or []:
        if not isinstance(facet, dict):
            continue
        name = str(facet.get("_exercise_name") or "")
        if not name:
            continue
        name_cf = name.casefold()
        matched = sum(1 for t in key_terms if t in name_cf)
        if matched:
            candidates.append((matched, {
                "document_id": str(facet.get("_id") or ""),
                "dataset": str(facet.get("_dataset") or ""),
                "exercise_name": name[:180],
            }))
    candidates.sort(key=lambda x: (-x[0], x[1]["exercise_name"]))
    return {
        "query_aliases": aliases[:12],
        "near_facet_matches": [x[1] for x in candidates[:limit]],
    }


def _deterministic_exact_response(message: str, sources: list[dict[str, Any]], retrieved_sources: list[dict[str, Any]], history: list[dict[str, str]] | None = None, user_context: str = "") -> dict[str, Any] | None:
    """Answer narrow R6/R7 named-exercise questions from source fields only."""
    if not sources or not _explicit_exercise_lookup(message):
        return None
    compact = re.sub(r"\s+", "", message)
    # Prefer the richest exact document for the requested field.
    def richness(src: dict[str, Any]) -> int:
        score = len(str(src.get("text") or ""))
        if src.get("url") or _field_value(src, ("영상 URL",)):
            score += 2000
        return score
    ordered = sorted(
        sources,
        key=lambda source: (_requested_exercise_specificity(source, message), richness(source)),
        reverse=True,
    )
    src = ordered[0]
    name = _exercise_name(src) or "질문하신 운동"
    evidence_id = "E1"

    if any(x in compact for x in ("영상은어디", "영상어디", "어디에서볼", "어디서볼")):
        url = str(src.get("url") or "").strip() or _field_value(src, ("영상 URL",))
        if url:
            return _response(f"{name} 영상은 {url}에서 확인할 수 있어요.", [src], retrieved_sources, {evidence_id}, routing_flag="EXACT_FIELD_VIDEO")
        return _response(f"{name}의 직접 운동 근거는 확인했지만, 현재 근거에는 영상 URL이 명시되어 있지 않아요.", [src], retrieved_sources, {evidence_id}, routing_flag="EXACT_FIELD_VIDEO_MISSING")

    if "운동은무엇" in compact or "운동이무엇" in compact:
        stage = _field_value(src, ("운동 단계", "exercise_stage"))
        suffix = f" 운동 단계는 {stage}입니다." if stage else ""
        return _response(
            f"질문하신 조건에 해당하는 운동은 {name}입니다.{suffix}",
            [src], retrieved_sources, {evidence_id}, routing_flag="EXACT_FIELD_NAME",
        )

    if any(x in compact for x in ("어떤운동도구", "어떤도구", "도구가필요")):
        equipment = _field_value(src, ("운동 도구", "도구", "equipment"))
        if equipment:
            text = f"{name}에 명시된 운동 도구는 {equipment}입니다."
        elif "탄력밴드" in name:
            text = f"운동명에 탄력밴드가 명시되어 있어, {name}은 탄력밴드를 사용하는 운동입니다."
        else:
            text = f"{name}의 직접 근거는 확인했지만, 현재 근거에는 필요한 운동 도구가 명시되어 있지 않아요."
        return _response(text, [src], retrieved_sources, {evidence_id}, routing_flag="EXACT_FIELD_EQUIPMENT")

    if "어느연령군" in compact or "어떤프로그램" in compact:
        age = _field_value(src, ("대상 연령군", "연령군", "age_group"))
        stage = _field_value(src, ("운동 단계", "프로그램", "exercise_stage"))
        description = _field_value(src, ("설명", "description"))

        bits=[]
        if age:
            bits.append(f"대상 연령군은 {age}")
        if stage:
            bits.append(f"프로그램/운동 단계는 {stage}")
        elif "어떤프로그램" in compact and description:
            # Do not invent a program label.  When no explicit program field
            # exists, use the source's own description and label it as such.
            bits.append(f"자료 설명상 {description}")
        elif "어떤프로그램" in compact:
            bits.append("프로그램 정보는 현재 근거에 명시되어 있지 않아요")

        if bits:
            return _response(
                f"{name}은 " + ", ".join(bits) + "입니다.",
                [src],
                retrieved_sources,
                {evidence_id},
                routing_flag="EXACT_FIELD_AUDIENCE",
            )

    if any(x in compact for x in ("맞물리는운동", "운동후보", "후보에들어", "후보가되", "관련있는운동", "관련운동")):
        source_factor = _source_factor(src)
        assertion_status, active_row, claimed_value, claimed_unit = _measurement_assertion_status(message, user_context)
        if assertion_status in ("VALUE_MISMATCH", "UNIT_MISMATCH"):
            actual_text = ""
            if active_row:
                actual_text = (
                    f"현재 로그인 계정에서 조건에 맞는 최신 {active_row.get('item_name')} 기록은 "
                    f"{active_row.get('value'):g}{active_row.get('unit')}입니다. "
                )
            generic = f"자료상 {name}은 {source_factor} 관련 운동으로 확인됩니다." if source_factor else (
                f"{name}의 직접 운동 근거는 확인됐지만 체력요인은 자료에 명시되어 있지 않습니다."
            )
            return _response(
                f"{actual_text}질문에 적힌 {claimed_value:g}{claimed_unit}와 일치하지 않아 "
                f"그 값을 현재 계정 기록으로 사용해 개인화하지 않을게요. {generic}",
                [src], retrieved_sources, {evidence_id},
                routing_flag="MEASUREMENT_ASSERTION_MISMATCH",
            )
        if assertion_status == "NO_RECORD":
            return _response(
                f"질문에 적힌 측정값을 현재 로그인 계정의 해당 측정 기록에서 확인하지 못해 "
                f"그 값을 개인 기록으로 사용하지 않을게요.",
                [src], retrieved_sources, {evidence_id},
                routing_flag="MEASUREMENT_ASSERTION_NO_RECORD",
            )
        asked_factor = _question_factor(message)
        if not asked_factor:
            asked_factor = _current_measurement_factor_for_message(message, user_context)
        history_state = _history_measurement_state(history)
        prior = _last_measurement_fact(history)

        # A genuine follow-up may omit the factor in the current sentence and
        # refer to the verified previous measurement as "그 결과/그 기록".
        # Inherit only from the most recent assistant measurement-result turn.
        followup_measurement_reference = any(
            cue in compact
            for cue in (
                "그결과",
                "그수치",
                "그기록",
                "그측정",
                "결과를고려",
                "결과를바탕",
                "결과에따라",
                "기록을기준",
            )
        )
        history_factor = ""
        if (
            not asked_factor
            and history_state != "NO_RECORD"
            and followup_measurement_reference
        ):
            history_factor = _history_measurement_factor(history)
            if history_factor:
                asked_factor = history_factor

        # If the immediately preceding measurement lookup explicitly found no
        # record, never pretend that "그 결과" exists.
        if history_state == "NO_RECORD" and any(x in compact for x in ("그결과", "그수치", "그기록")):
            generic = ""
            if source_factor:
                generic = f" 다만 자료상 {name}은 {source_factor} 관련 운동으로 확인됩니다."
            return _response(
                "앞서 확인한 계정에는 해당 측정 기록이 없어서 그 결과를 기준으로 개인화해 연결할 수는 없어요."
                + generic,
                [src], retrieved_sources, {evidence_id},
                routing_flag="EXACT_FACTOR_NO_MEASUREMENT_RECORD",
            )

        if source_factor and asked_factor:
            if _relation_factors_compatible(source_factor, asked_factor, src):
                lead = "앞서 확인한 측정 결과를 이어서 보면, " if (prior or history_state == "HAS_VALUE") else ""
                return _response(
                    f"{lead}{name}은 자료에 {source_factor} 관련 운동으로 명시되어 있어 "
                    f"질문하신 {asked_factor} 관리 운동 후보로 연결할 수 있어요. "
                    "다만 이 측정값 하나만으로 운동 필요성이나 효과 크기를 단정하지는 않을게요.",
                    [src], retrieved_sources, {evidence_id},
                    routing_flag="EXACT_FIELD_FACTOR_MATCH",
                )
            return _response(
                f"{name}의 자료상 체력요인은 {source_factor}이고, 질문하신 기준은 {asked_factor}라서 "
                "같은 체력요인 운동이라고 연결하지 않을게요.",
                [src], retrieved_sources, {evidence_id},
                routing_flag="EXACT_FIELD_FACTOR_MISMATCH",
            )

        if source_factor:
            lead = "앞서 확인한 측정 결과를 이어서 보면, " if (prior or history_state == "HAS_VALUE") else ""
            return _response(
                f"{lead}{name}은 자료에 {source_factor} 관련 운동으로 명시되어 있어요. "
                "다만 질문에 개인 측정 체력요인이 명확히 특정되지 않아 개인 결과와의 적합성까지 단정하지는 않을게요.",
                [src], retrieved_sources, {evidence_id},
                routing_flag="EXACT_FIELD_FACTOR_SOURCE_ONLY",
            )

        lead = "앞서 확인한 측정 결과를 이어서 보면, " if prior else ""
        return _response(
            f"{lead}{name}의 직접 운동 근거는 확인했지만, 현재 근거에는 질문하신 체력요인과의 관계가 "
            "명시되어 있지 않아 관련 운동이라고 단정하지 않을게요.",
            [src], retrieved_sources, {evidence_id},
            routing_flag="EXACT_FIELD_FACTOR_MISSING",
        )
    return None

def _non_user_sources(
    sources: list[dict[str, Any]],
) -> list[
    tuple[int, dict[str, Any]]
]:
    return [
        (i, source)
        for i, source in enumerate(
            sources
        )
        if source.get("dataset")
        != "fitness_user_records"
    ]


def _last_measurement_fact(history: list[dict[str, str]] | None) -> str:
    """Return the latest deterministic measurement fact stated in chat history."""
    for item in reversed(history or []):
        if str(item.get("role") or "") != "assistant":
            continue
        text = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
        if not text:
            continue
        if re.search(r"(?:결과는|기록은)\s*-?\d+(?:\.\d+)?\s*(?:cm|초|회|%)", text, re.I):
            return text[:220]
    return ""


def _fallback_conversation(
    message: str,
    history: list[dict[str, str]] | None,
    sources: list[dict[str, Any]],
    retrieved_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Qwen 출력이 깨지거나 citation 검증 실패 시에도
    RAG 원문을 그대로 덤프하지 않는다.
    """

    current_intent = _intent(message)
    last_exercise = _last_recommended_exercise(history)
    candidates = [
        (index, source) for index, source in _non_user_sources(sources)
        if not (current_intent == "ALTERNATIVE" and last_exercise
                and last_exercise in _exercise_name(source))
    ]

    if not candidates:
        return _response(
            (
                "현재 보유한 운동 자료에서 "
                "바로 연결할 수 있는 운동을 찾지 못했어요. "
                "원하는 부위나 운동 목적을 조금 더 알려주세요."
            ),
            [],
            retrieved_sources,
            set(),
            routing_flag=(
                "NO_RELEVANT_EVIDENCE"
            ),
        )

    index, source = candidates[0]

    name = (
        _exercise_name(source)
        or "이 운동"
    )

    compact = re.sub(
        r"\s+",
        "",
        message,
    )

    last_answer = _last_assistant_text(
        history
    )

    if current_intent == "WHY_RECOMMENDED" and last_exercise:
        answer_text = (
            f"앞서 추천한 운동은 {last_exercise}입니다. "
            "보유 운동 자료와 현재 사용자 정보를 "
            "함께 확인했을 때 지금 질문의 조건과 "
            "연결되는 운동이라 추천했어요. "
            "원하시면 이 운동의 방법도 이어서 설명해드릴게요."
        )
    elif current_intent == "HOW_TO" and last_exercise:
        answer_text = (
            f"현재 자료에는 {last_exercise} 운동의 자세 순서까지 충분히 기록되어 있지 않아요. "
            "대신 수행 방법이 자세히 있는 운동을 추천해드릴까요?"
        )
    elif current_intent == "ALTERNATIVE":
        answer_text = (
            f"앞서 추천한 {last_exercise or '운동'}은 제외하고 다른 선택지로 {name} 운동을 추천해볼게요. "
            "원하시면 두 운동을 비교해서 "
            "어떤 차이가 있는지도 설명해드릴게요."
        )

    elif (
        _is_referential(message)
        and last_answer
    ):
        answer_text = (
            "네, 앞서 이야기한 흐름을 이어서 보면 "
            f"{name}을 기준으로 설명할 수 있어요. "
            "궁금한 점을 말씀해 주세요."
        )

    elif current_intent == "MEASUREMENT_BASED_RECOMMEND":
        answer_text = (
            f"최근 측정 결과에서 우선 보완할 체력 요소를 기준으로 {name} 운동을 추천해요. "
            "측정값 자체를 임의로 해석하지 않고 저장된 또래 비교 결과와 운동 자료를 함께 반영했습니다."
        )
    elif _explicit_exercise_lookup(message):
        prior_measurement = _last_measurement_fact(history)
        if prior_measurement and any(token in message for token in ("그 수치", "그 결과", "결과를 고려", "수치를 고려")):
            answer_text = (
                f"앞서 확인한 측정 결과를 이어서 보면, {name}에 대한 직접 운동 근거는 확인했어요. "
                "다만 현재 근거만으로 그 측정값 때문에 이 운동이 반드시 필요하다고 단정하지 않고, "
                "해당 운동이 질문한 체력요인과 관련된 후보인지까지만 안내할게요."
            )
        else:
            answer_text = (
                f"질문하신 {name}에 대한 직접 근거는 확인했어요. "
                "현재 자료에 확인되지 않는 효과나 운동량은 덧붙이지 않고, "
                "질문하신 운동 자체를 기준으로만 안내할게요."
            )
    else:
        answer_text = (
            f"오늘은 {name} 운동을 해보는 선택지가 있어요. "
            "현재 사용자 정보와 보유 운동 자료를 "
            "함께 반영해서 고른 운동입니다."
        )

    return _response(
        answer_text,
        sources,
        retrieved_sources,
        {f"E{index + 1}"},
        routing_flag=(
            "CONVERSATIONAL_FALLBACK"
        ),
    )


def answer(
    runtime: Any,
    message: str,
    history: list[dict[str, str]] | None = None,
    user_context: str = "",
) -> dict[str, Any]:

    LOGGER.info(
        "fitness_chat user_context_present=%s length=%d",
        bool(user_context),
        len(user_context or ""),
    )

    if not _exercise_question(
        message,
        history,
    ):
        return _response(
            OFF_TOPIC,
            [],
            [],
            routing_flag="OUT_OF_SCOPE",
        )

    # ---------------------------------------------------------
    # 1. 검색 query 구성
    # ---------------------------------------------------------

    search_query = _build_search_query(
        message,
        history,
        user_context,
    )
    # A new video request names its target in the current turn.  Carrying a
    # previous recommendation (for example flexibility) into this retrieval can
    # return a playable but unrelated video for "탄력 밴드 영상".
    if _video_request(message):
        search_query = re.sub(r"\s+", " ", str(message or "")).strip()

    # ---------------------------------------------------------
    # 2. 기존 RAG DB 검색
    # ---------------------------------------------------------

    search_datasets = [
        "video_content",
        "general_prescription",
        "measurement_prescription",
    ]
    exact_sources = _exact_exercise_sources(
        runtime, message, datasets=search_datasets, limit=50
    )
    retrieved_sources = runtime.semantic_search(
        search_query,
        k=20,
        datasets=search_datasets,
        min_score=0.28,
    )
    # Preserve the fact that the persisted vector index was actually exercised.
    # Later exact/document-id dedupe may replace the same document with an
    # exact/sqlite copy, which must not erase retrieval provenance.
    chroma_provenance_source = next(
        (
            dict(source)
            for source in retrieved_sources
            if str(source.get("retrieval_backend") or source.get("backend") or "") == "chroma_vector"
        ),
        None,
    )
    if exact_sources:
        merged_exact: list[dict[str, Any]] = []
        seen_exact: set[str] = set()
        for source in [*exact_sources, *retrieved_sources]:
            identity = _document_id(source) or json.dumps(source, ensure_ascii=False, sort_keys=True)
            if identity in seen_exact:
                continue
            seen_exact.add(identity)
            merged_exact.append(source)
        retrieved_sources = merged_exact[:100]
    precise_batches: list[dict[str, Any]] = []
    if _explicit_exercise_lookup(message):
        for precise_query in _exercise_lookup_queries(message):
            precise_batches.extend(runtime.semantic_search(
                precise_query,
                k=30,
                datasets=[
                    "video_content",
                    "general_prescription",
                    "measurement_prescription",
                ],
                min_score=0.22,
            ))
    if precise_batches:
        merged: list[dict[str, Any]] = []
        seen_documents: set[str] = set()

        # Exact deterministic hits must remain ahead of all semantic candidates.
        # Previously precise semantic batches were prepended and the final [:80]
        # truncation could silently delete exact_sources that had already been
        # found from facet_records.  That is why diagnostics showed the exact
        # CAL-003/CAL-004 exercise names while retrieval_backend contained only
        # chroma_vector.
        merge_order = [*exact_sources, *precise_batches, *retrieved_sources]
        for source in merge_order:
            identity = _document_id(source) or json.dumps(source, ensure_ascii=False, sort_keys=True)
            if identity in seen_documents:
                continue
            seen_documents.add(identity)
            merged.append(source)
        retrieved_sources = merged[:80]

    # preserve one chroma retrieval provenance row after document-id dedupe
    # This row is appended only for retrieval trace/audit. Exact sources remain
    # first, so answer selection and citation preference are unchanged.
    if (
        chroma_provenance_source
        and not any(
            str(source.get("retrieval_backend") or source.get("backend") or "") == "chroma_vector"
            for source in retrieved_sources
        )
    ):
        if len(retrieved_sources) >= 80:
            retrieved_sources = [*retrieved_sources[:79], chroma_provenance_source]
        else:
            retrieved_sources = [*retrieved_sources, chroma_provenance_source]

    # Apply generic metadata-aware rerank after vector/exact candidate merge.
    # No case_id or Gold document id participates in this ordering.
    retrieved_sources = _metadata_aware_rerank_sources(retrieved_sources, message)

    current_intent = _intent(message)
    last_exercise = _last_recommended_exercise(history)
    explicit_lookup = _explicit_exercise_lookup(message)
    requested_sources = [
        source for source in retrieved_sources
        if _requested_exercise_match(source, message)
    ]

    # prefer most-specific exact exercise matches before top-k truncation
    # When both a full composite exercise name and one of its components match
    # the question, keep the longest/public-name exact match group. Ties remain,
    # so duplicate documents/variants for the same exact exercise are preserved.
    if (
        explicit_lookup
        and requested_sources
        and any(sep in str(message or "") for sep in ("/", "／", "+", "&", " 및 ", " 그리고 "))
    ):
        specificity_pairs = [
            (_requested_exercise_specificity(source, message), source)
            for source in requested_sources
        ]
        max_specificity = max((score for score, _ in specificity_pairs), default=0)
        if max_specificity > 0:
            most_specific = [
                source for score, source in specificity_pairs
                if score == max_specificity
            ]
            if most_specific:
                requested_sources = most_specific

    # A named-exercise information/follow-up question is not a recommendation
    # request.  Once an exact public-name match exists, only that exercise may
    # participate in generation/citation.  If no exact match exists, abstain
    # instead of substituting a semantically nearby exercise.
    if explicit_lookup and requested_sources:
        filtered_sources = [
            source for source in requested_sources
            if not _source_has_unrequested_condition(source, message, user_context)
        ]
    elif explicit_lookup:
        return _response(
            (
                "질문하신 운동과 직접 일치하는 근거를 현재 보유 자료에서 찾지 못했어요. "
                "비슷한 다른 운동으로 바꾸어 답하지 않고, 해당 운동의 직접 근거가 확인될 때 안내할게요."
            ),
            [],
            retrieved_sources,
            set(),
            routing_flag="NO_EXACT_EXERCISE_EVIDENCE",
            diagnostics=_exact_miss_diagnostics(runtime, message),
        )
    else:
        filtered_sources = [
            source for source in retrieved_sources
            if not _source_has_unrequested_condition(source, message, user_context)
            and not (
                current_intent == "ALTERNATIVE"
                and last_exercise
                and last_exercise in _exercise_name(source)
            )
        ]
    if current_intent == "MEASUREMENT_BASED_RECOMMEND":
        measurement_goal = _weakest_measurement_goal(user_context)
        primary_goal = measurement_goal.split()[0] if measurement_goal else ""
        goal_sources = [
            source for source in filtered_sources
            if primary_goal in f"{source.get('title', '')} {source.get('text', '')}"
        ]
        if goal_sources:
            filtered_sources = goal_sources

    # Data-gap personalization stays Path B but must not invent a missing value.
    # Prefer general evidence matching requested factor and authenticated life-stage.
    if "저장된 측정 기록: 없음" in str(user_context or ""):
        gap_factor = _question_factor(message)
        compact_gap = _compact_match_text(message)
        if not gap_factor and any(
            token in compact_gap
            for token in (
                _compact_match_text("스트레칭"),
                _compact_match_text("유연성 운동"),
            )
        ):
            gap_factor = "유연성"

        if gap_factor:
            factor_aligned = [
                source for source in filtered_sources
                if _source_factor(source) == gap_factor
                or (
                    gap_factor == "근력"
                    and _source_factor(source) == "근지구력"
                )
            ]
            if factor_aligned:
                filtered_sources = factor_aligned

        profile_stage = _user_life_stage(user_context)
        if profile_stage:
            stage_aligned = [
                source for source in filtered_sources
                if _source_age_compatible(source, profile_stage)
            ]
            if stage_aligned:
                filtered_sources = stage_aligned

    # Vector similarity is not sufficient for a question naming an exercise.
    # Keep the original retrieval order inside each group, but place exact
    # public-name matches first so both generation and fallback cite them.
    constrained_sources = [
        source for source in filtered_sources
        if _source_matches_explicit_constraints(source, message)
    ]
    if constrained_sources:
        filtered_sources = constrained_sources

    filtered_sources = sorted(
        enumerate(filtered_sources),
        key=lambda item: (not _requested_exercise_match(item[1], message), item[0]),
    )
    filtered_sources = [source for _, source in filtered_sources]
    sources = list(filtered_sources[:5])

    video_response = _deterministic_video_response(
        message, sources, retrieved_sources
    )
    if video_response is not None:
        return video_response

    deterministic_exact = _deterministic_exact_response(
        message, sources, retrieved_sources, history, user_context
    )
    if deterministic_exact is not None:
        return deterministic_exact

    compact_message = _compact_match_text(message)
    if (
        not explicit_lookup
        and any(token in compact_message for token in (
            _compact_match_text("운동은 무엇인가요"),
            _compact_match_text("운동이 무엇인가요"),
            _compact_match_text("어떤 운동인가요"),
        ))
        and sources
    ):
        src0 = sources[0]
        name0 = _exercise_name(src0) or _public_title(src0)
        return _response(
            f"질문에 적힌 조건과 현재 근거를 대조하면 해당 운동은 {name0}입니다.",
            [src0], retrieved_sources, {"E1"},
            routing_flag="DESCRIPTIVE_EXERCISE_IDENTIFICATION",
        )

    # A direct "pick my weakest fitness factor" request should not be left to
    # free-form generation.  Use the latest per-factor percentile bands already
    # present in authenticated context and cite only a source that literally
    # carries that factor label.
    compact_message = _compact_match_text(message)
    if user_context and any(token in compact_message for token in (
        _compact_match_text("제일 떨어지는"),
        _compact_match_text("가장 떨어지는"),
        _compact_match_text("가장 부족한"),
        _compact_match_text("제일 부족한"),
    )):
        weakest_factor, weakest_band = _weakest_measurement_factor(user_context)
        if weakest_factor:
            factor_sources = [
                s for s in filtered_sources
                if _source_factor(s) == weakest_factor
            ]

            # The original question does not contain the derived weakest factor.
            # Resolve factor-labeled exercises deterministically from facet_records
            # before using vector search.  This avoids repeating the same semantic
            # retrieval miss for a factor we already know exactly.
            if not factor_sources:
                profile_stage = _user_life_stage(user_context)
                factor_sources = _factor_facet_sources(
                    runtime,
                    weakest_factor,
                    datasets=[
                        "general_prescription",
                        "measurement_prescription",
                        "video_content",
                    ],
                    limit=20,
                    user_life_stage=profile_stage,
                )

            # Semantic search remains only a fallback when the facet index itself
            # contains no literal factor-labeled exercise.
            if not factor_sources:
                focused_candidates: list[dict[str, Any]] = []
                for factor_query in (
                    f"{weakest_factor} 운동",
                    f"{weakest_factor} 운동처방",
                    f"{weakest_factor} 운동 프로그램",
                ):
                    try:
                        focused_candidates.extend(
                            runtime.semantic_search(
                                factor_query,
                                k=30,
                                datasets=[
                                    "general_prescription",
                                    "measurement_prescription",
                                    "video_content",
                                ],
                                min_score=0.20,
                            )
                        )
                    except Exception:
                        continue

                focused_seen: set[str] = set()
                focused_unique: list[dict[str, Any]] = []
                for candidate in focused_candidates:
                    identity = _document_id(candidate) or json.dumps(candidate, ensure_ascii=False, sort_keys=True)
                    if identity in focused_seen:
                        continue
                    focused_seen.add(identity)
                    focused_unique.append(candidate)

                profile_stage = _user_life_stage(user_context)
                factor_sources = [
                    s for s in focused_unique
                    if _source_factor(s) == weakest_factor
                    and _source_age_compatible(s, profile_stage)
                ]

            if factor_sources:
                focused_ids = {_document_id(x) for x in factor_sources}
                retrieved_sources = [
                    *factor_sources,
                    *[s for s in retrieved_sources if _document_id(s) not in focused_ids],
                ][:100]

            if factor_sources:
                src0 = factor_sources[0]
                name0 = _exercise_name(src0) or "이 운동"
                return _response(
                    f"현재 저장된 최신 측정 항목들 가운데 상대적으로 가장 낮은 체력요인은 "
                    f"{weakest_factor}이고, 비교 표시는 {weakest_band}입니다. "
                    f"현재 계정의 연령대와 모순되지 않는 자료 중 {weakest_factor} 관련 운동으로 "
                    f"명시된 {name0}을 후보로 안내할 수 있어요.",
                    [src0], retrieved_sources, {"E1"},
                    routing_flag="WEAKEST_FACTOR_DETERMINISTIC",
                )
            return _response(
                f"현재 저장된 최신 측정 항목들 가운데 상대적으로 가장 낮은 체력요인은 "
                f"{weakest_factor}이고, 비교 표시는 {weakest_band}입니다. "
                f"이번 검색 근거에서는 {weakest_factor}가 명시된 운동을 찾지 못해 "
                f"임의로 다른 운동을 추천하지 않을게요.",
                [], retrieved_sources, set(),
                routing_flag="WEAKEST_FACTOR_EVIDENCE_MISSING",
            )

    # ---------------------------------------------------------
    # 3. 지원하지 않는 영양 질문 방어
    # ---------------------------------------------------------

    if any(
        term in message
        for term in NUTRITION_TERMS
    ):

        searchable = " ".join(
            (
                f"{s.get('title', '')} "
                f"{s.get('text', '')}"
            )
            for s in sources
        ).casefold()

        if not any(
            term in searchable
            for term in NUTRITION_TERMS
        ):
            return _response(
                (
                    "현재 보유한 자료는 체력 측정과 "
                    "운동 방법 중심이라 음식이나 영양을 "
                    "근거 있게 안내하기 어려워요. "
                    "운동 방법이나 측정 결과에 관해 물어봐 주세요."
                ),
                [],
                retrieved_sources,
                routing_flag=(
                    "UNSUPPORTED_NUTRITION"
                ),
            )

    # ---------------------------------------------------------
    # 4. 사용자 DB context
    #
    # 기존 코드와 가장 중요한 차이.
    #
    # 기존:
    # "내 기록", "측정결과" 등이 있을 때만 사용.
    #
    # 수정:
    # 로그인 사용자 DB context가 존재하면
    # 모든 운동 대화에서 모델이 참고.
    # ---------------------------------------------------------

    if user_context:
        user_source = {
            "title": (
                "사용자 운동·측정 맥락"
            ),
            "text": user_context,
            "dataset": (
                "fitness_user_records"
            ),
            "score": 1.0,
        }

        sources = [
            user_source,
            *sources[:4],
        ]

    # ---------------------------------------------------------
    # 5. 근거 없음
    # ---------------------------------------------------------

    if not sources:
        return _response(
            (
                "보유한 운동 데이터에서 질문과 "
                "직접 연결되는 근거를 찾지 못했어요. "
                "운동 종목이나 목표를 조금 더 구체적으로 알려주세요."
            ),
            [],
            retrieved_sources,
            routing_flag="NO_EVIDENCE",
        )

    # ---------------------------------------------------------
    # 6. Qwen에게 줄 근거
    #
    # 내부 metadata를 정리한 버전을 모델에게 전달.
    # ---------------------------------------------------------

    evidence = "\n".join(
        (
            f"[E{i}] "
            f"{_public_title(source)} | "
            f"{_safe_excerpt(source, limit=280)}"
        )
        for i, source
        in enumerate(
            sources,
            1,
        )
    )

    # ---------------------------------------------------------
    # 7. 최근 대화
    # ---------------------------------------------------------

    history_text = "\n".join(
        (
            f"{h.get('role')}: "
            f"{h.get('content')}"
        )
        for h in (history or [])[-4:]
    )
    prompt_user_context = re.sub(r"\s+", " ", user_context or "").strip()[:900]

    # ---------------------------------------------------------
    # 8. System prompt
    # ---------------------------------------------------------

    system = """
당신은 친절하고 자연스럽게 대화하는 한국어 운동 코치다.

현재 질문에 먼저 직접 답한다.

최근 대화를 이용해
'그 운동',
'왜',
'다른 운동',
'그거 어떻게 해?'
같은 후속 질문의 대상을 이어서 이해한다.

로그인 사용자 맥락과 제공된 운동 근거를 함께 참고한다.

근거에 없는 운동, 효과, 횟수, 질환, 수치, 도구의 재질·형태·적합성을 만들지 않는다.
근거가 "탄력밴드"라고만 말하면 밴드의 모양·재질·최적성 같은 속성을 덧붙이지 않는다.

사용자가 특정 운동명을 직접 지정해 질문했다면 그 운동을 다른 운동으로 바꾸지 않는다.
지정한 운동의 직접 근거가 부족하면 비슷한 운동을 대신 추천하지 말고 근거 부족을 말한다.

운동명, 수행법, 효과를 말한 문장은 반드시 해당 운동 문서 근거를 인용한다.
사용자 기록 근거만으로 운동의 효과나 수행법을 설명하지 않는다.

체력 인증등급,
성별 코드 M/F,
대상 연령군,
RAG_DOCUMENT,
데이터셋명,
문서 ID,
검색 점수 같은 내부 메타데이터는
사용자에게 말하지 않는다.

내부 근거 문장을 그대로 복사하지 않는다.

사람과 대화하듯 자연스럽게 설명한다.

답변은 JSON 객체 하나만 출력한다.
""".strip()

    # ---------------------------------------------------------
    # 9. User prompt
    # ---------------------------------------------------------

    prompt = f"""
[현재 질문]
{message}

[최근 대화]
{history_text or '없음'}

[로그인 사용자 DB/프로필 맥락]
{prompt_user_context or '없음'}

[검색 근거]
{evidence}

규칙:

1. 질문에 바로 답한다.

2. 추천 질문이면
   운동명과 짧은 추천 이유를 자연스럽게 말한다.

3. "왜 추천했어?" 같은 후속 질문이면
   직전 추천 운동을 유지한 상태에서 이유를 설명한다.

4. "다른 운동은?"이라고 하면
   이전 추천과 다른 후보를 설명한다.

4-1. 현재 질문에 특정 운동명이 명시되어 있으면 그 운동을 그대로 유지한다.
     검색 결과의 다른 운동으로 대체하지 않는다.

5. 내부 등급,
   성별 코드,
   연령군 라벨,
   문서 ID,
   dataset,
   score는 절대 출력하지 않는다.

6. 구체적 근거를 사용한 문장 끝에는
   [E번호]를 붙인다.

6-1. 운동명, 수행법, 효과, 필요한 도구와 도구의 특성을 말할 때는 사용자 맥락이 아닌
     운동 문서의 [E번호]를 반드시 하나 이상 사용한다.
     문서에 없는 도구의 모양·재질·최적성은 추론하지 않는다.

6-2. "그 수치", "그 결과"가 나오면 최근 대화의 실제 측정 결과를 이어받는다.
     다만 그 수치와 특정 운동 사이의 인과·필요성을 문서가 직접 뒷받침하지 않으면 단정하지 않는다.

7. 자연스러운 2~4문장,
   360자 이내로 답한다.

8. JSON 형식:

{{
  "answer": "...",
  "used_evidence": ["E1"]
}}
""".strip()

    # ---------------------------------------------------------
    # 10. Qwen 호출
    # ---------------------------------------------------------

    try:
        raw = (
            runtime.qwen3_client.complete_json(
                system,
                prompt,
                max_tokens=320,
                response_schema={
                    "type": "object",

                    "properties": {
                        "answer": {
                            "type": "string",
                            "maxLength": 360,
                        },

                        "used_evidence": {
                            "type": "array",

                            "items": {
                                "type": "string",
                            },
                        },
                    },

                    "required": [
                        "answer",
                        "used_evidence",
                    ],

                    "additionalProperties": False,
                },
            )
        )

        parsed = json.loads(
            raw
        )

        text = _dedupe(
            str(
                parsed.get("answer")
                or ""
            )
        )

        used = {
            str(x)
            for x
            in parsed.get(
                "used_evidence",
                [],
            )
        }

        cited = _citation_ids(
            text
        )

        valid_labels = {
            f"E{i}"
            for i
            in range(
                1,
                len(sources) + 1,
            )
        }
        cited_document_labels = {
            label for label in cited
            if _document_id(sources[int(label[1:]) - 1])
        }
        requested_matches = {
            f"E{i}" for i, source in enumerate(sources, 1)
            if _requested_exercise_match(source, message)
        }

        # -----------------------------------------------------
        # 11. 모델 출력 검증
        # -----------------------------------------------------

        if (
            not text

            or not _fully_cited(
                text
            )

            or not used

            or used != cited

            or not cited <= valid_labels

            or not cited_document_labels

            or (requested_matches and not (cited & requested_matches))

            or _contains_hidden_chat_metadata(
                text
            )
        ):
            raise ValueError(
                "invalid grounded conversational response"
            )

        # citation 표시는 내부 검증에만 사용하고
        # 사용자 답변에서는 제거
        clean = re.sub(
            r"\s*\[E[1-9]\d*\]",
            "",
            text,
        ).strip()

        clean = _strip_internal_metadata(
            clean
        )

        if (
            current_intent in {"WHY_RECOMMENDED", "HOW_TO"}
            and last_exercise
            and last_exercise not in clean
        ):
            raise ValueError("follow-up lost the recommended exercise")
        if re.search(r"[\u4e00-\u9fff]", clean):
            raise ValueError("answer contains broken non-Korean CJK text")
        if current_intent == "MEASUREMENT_BASED_RECOMMEND" and "측정" not in clean:
            raise ValueError("measurement recommendation did not explain its context")

        # -----------------------------------------------------
        # 12. 직전 답변 그대로 반복 방지
        # -----------------------------------------------------

        previous_answers = [
            str(
                h.get("content") or ""
            ).strip()

            for h
            in (history or [])[-6:]

            if h.get("role")
            == "assistant"
        ]

        if clean in previous_answers:
            raise ValueError(
                "repeated prior response"
            )

        # -----------------------------------------------------
        # 13. 정상 반환
        # -----------------------------------------------------

        return _response(
            clean,
            sources,
            retrieved_sources,
            cited,
        )

    except Exception:
        # -----------------------------------------------------
        # 중요
        #
        # 예전 코드처럼:
        #
        # "보유 자료에서 확인한 내용이에요.
        #  운동 단계: ...
        #  성별: M
        #  체력 인증등급: 3등급"
        #
        # 형태로 raw RAG row를 절대 반환하지 않는다.
        # -----------------------------------------------------

        return _fallback_conversation(
            message,
            history,
            sources,
            retrieved_sources,
        )
