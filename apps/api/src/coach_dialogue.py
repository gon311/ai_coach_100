"""Bounded dialogue: Qwen interprets questions; Python renders source-bound facts.

Model interpretations are separately labelled. Source IDs belong to each fact,
not to the combined corpus. Continuations consume a server-owned fact cursor.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence
from coaching_interpretation import generate as generate_interpretation

TOPICS = {
    "reason": ("왜", "이유", "근거", "맞는"),
    "name": ("이름", "운동명", "무슨 운동", "어떤 운동"),
    "area": ("부위", "어디", "근육"),
    "equipment": ("도구", "장비", "맨몸", "준비물"),
    "location": ("장소", "실내", "실외", "헬스장", "어디서"),
    "difficulty": ("난이도", "초급", "중급", "고급", "어려"),
    "stage": ("단계", "준비운동", "본운동", "정리운동"),
    "video": ("영상", "동영상", "비디오"),
    "method": ("방법", "어떻게", "자세", "호흡", "순서"),
    "dose": ("횟수", "몇 회", "몇회", "세트", "시간", "몇 분", "몇분", "주기", "얼마나"),
    "effect": ("효과", "좋아", "향상", "강화", "도움"),
    "age": ("연령", "나이", "대상"),
    "description": ("설명", "소개", "자세히", "길게"),
    "coaching": ("꾸준", "습관", "시작", "차이", "비교", "차라리", "다른 말", "무슨 뜻", "중요", "지루", "쉽게"),
}
INTENT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topics"],
    "properties": {"topics": {"type": "array", "minItems": 1, "maxItems": 5,
        "items": {"type": "string", "enum": list(TOPICS)}}},
}
LABELS = {
    "name": ("운동명",), "area": ("운동 부위", "주요 근육"),
    "equipment": ("운동 도구", "필요 장비"), "location": ("운동 장소",),
    "difficulty": ("난이도",), "stage": ("운동 단계",),
    "video": ("영상 URL",), "method": ("운동 방법", "동작 설명", "호흡"),
    "dose": ("반복 횟수", "세트", "권장 주기", "운동 시간"),
    "effect": ("운동 효과",), "age": ("대상 연령군",),
    "description": ("설명", "운동 유형"),
}
CONTINUE = re.compile(r"^(?:이어서|계속|더)(?:\s*(?:작성|설명|알려|말해|해|보여|줘|주세요|해줘|해요))*[.!?\s]*$")
PAIN = re.compile(r"(?:(무릎|허리|어깨|발목|손목|목|가슴|다리|팔)(?:이|가|은|는)?\s*(?:아프|아파|아픈|아픈데|아픔|통증)|통증(?:이|은|가)?\s*(?:있|심|생|늘)|아프(?:다|네|면|다고)|아픈데)")
SAFETY_MESSAGE = "통증이 있는 상태에서 이 운동이 적절한지는 현재 자료로 확인할 수 없어요. 통증 부위와 정도(0~10)를 운동 조건에 반영한 뒤 다시 확인해 주세요."
SEVERE_MESSAGE = "말씀하신 증상에서는 운동 안내를 중단할게요. 의료 전문가에게 현재 증상을 확인받아 주세요."
MAX_SENTENCES = 5
MAX_SENTENCE_CHARS = 80  # excludes the citation and source identifiers


def safety_update(message: str, profile: Mapping[str, Any]) -> dict[str, Any] | None:
    """Conservative gate before ALL routes; never silently reuse stale conditions."""
    compact = re.sub(r"\s+", "", message)
    severe = any(term in compact for term in ("흉통", "호흡곤란", "실신", "마비", "골절", "날카로운통증", "수술직후", "심한어지럼"))
    severe = severe or ("가슴" in compact and any(term in compact for term in ("조여", "쪼여", "답답", "압박")))
    # Negation is accepted only for the explicit pain span, not for the whole message.
    cleaned = re.sub(r"(?:무릎|허리|어깨|발목|손목|가슴|다리|팔)?\s*(?:통증이?\s*(?:없어요|없어|없음|없다)|아프지\s*않(?:아요|아|다))", "", message)
    pain = PAIN.search(cleaned)
    score = re.search(r"통증(?:\s*정도)?\s*(?:은|이|가|:)?\s*(10|[0-9])\s*(?:점|/\s*10)", message)
    try:
        severe = severe or float(profile.get("pain_level") or 0) >= 7
    except (TypeError, ValueError):
        pass
    severe = severe or bool(score and int(score.group(1)) >= 7)
    if not (severe or pain or (score and int(score.group(1)) > 0)):
        return None
    update = dict(profile)
    if pain and pain.group(1):
        update["pain_area"] = pain.group(1)
    if score:
        update["pain_level"] = int(score.group(1))
    return {"profile": update, "answer": SEVERE_MESSAGE if severe else SAFETY_MESSAGE}


def is_recommendation(message: str) -> bool:
    text = re.sub(r"\s+", "", message)
    if CONTINUE.fullmatch(message.strip()):
        return False
    if re.search(r"(?:다른|새로운|다음|그다음|또다른)(?:운동|스트레칭)|바꿔|대신.*(?:추천|알려)|그다음은", text):
        return True
    if any(term in text for term in ("왜", "이유", "근거", "추천한", "추천했", "추천해준", "추천하는거")):
        return False
    if "영상" in text:
        return False
    return bool(re.search(r"추천(?:해|하|좀|받|부탁|줘)|추천$|운동(?:을)?(?:찾아|알려)|할만한운동", text))


def infer_topics(message: str) -> list[str]:
    topics = [topic for topic, terms in TOPICS.items() if any(term in (message.replace("자세히", "") if topic == "method" else message) for term in terms)]
    if "어디서" in message and "area" in topics:
        topics.remove("area")
    return topics


def facts_from_sources(evidence: Sequence[Mapping[str, Any]], selected_name: str) -> dict[str, list[tuple[str, str]]]:
    facts: dict[str, list[tuple[str, str]]] = {}
    for item in evidence:
        eid = str(item.get("evidence_id") or "")
        if not re.fullmatch(r"E\d+", eid):
            continue
        for text in (item.get("text"), item.get("linked_detail_text")):
            for line in str(text or "").splitlines():
                if ":" not in line:
                    continue
                label, value = (part.strip() for part in line.split(":", 1))
                if value and (value, eid) not in facts.setdefault(label, []):
                    facts[label].append((value, eid))
        if not facts.get("운동명") and selected_name in str(item.get("text") or ""):
            facts.setdefault("운동명", []).append((selected_name, eid))
    return facts


def render(message: str, topics: Sequence[str], profile: Mapping[str, Any], selected_name: str,
           evidence: Sequence[Mapping[str, Any]], abstention: str,
           seen: Sequence[str] = (), max_sentences: int = MAX_SENTENCES) -> tuple[str, list[str]]:
    facts = facts_from_sources(evidence, selected_name)
    sentences: list[str] = []
    keys: list[str] = []

    def add(key: str, sentence: str, eid: str = "") -> None:
        if key in seen or key in keys or len(sentences) >= max_sentences:
            return
        # Never slice a source value into a misleading partial fact.
        if len(sentence) > MAX_SENTENCE_CHARS or re.search(r"[\u3400-\u9fff\u3040-\u30ff]|<|https?://", sentence):
            return
        if re.search(r"[A-Za-z]{3,}", sentence):
            return
        sentences.append(sentence + (f" [{eid}]" if eid else ""))
        keys.append(key)

    for topic in topics:
        if topic == "reason":
            matches = 0
            # Prefer exercise purpose/body area over incidental source venue.
            for field, label in (("target_area", "운동 부위"), ("exercise_type", "운동 유형")):
                expected = str(profile.get(field) or "").strip()
                values = facts.get(label, [])
                if expected and len({v for v, _ in values}) == 1 and expected in [x.strip() for x in re.split(r"[,/|]", values[0][0])]:
                    v, eid = values[0]
                    add(f"reason:{label}:{v}", f"선택하신 {label} ‘{expected}’ 조건이 이 운동의 원문과 일치해요", eid)
                    matches += 1
                else:
                    entry = next(((v, eid) for v, eid in facts.get("운동명", []) if expected and expected in v), None)
                    if entry:
                        v, eid = entry
                        add(f"reason:name:{expected}", f"선택하신 ‘{expected}’ 조건의 표현이 원문 운동명에 포함되어 있어요", eid)
                        matches += 1
            if not matches:
                entry = next(iter(facts.get("운동명", [])), None)
                if entry:
                    name, eid = entry
                    add("reason:selected", f"현재 확인한 운동은 ‘{name}’이에요", eid)
                else:
                    add("reason:missing", "현재 운동의 추천 이유를 설명할 원문 정보가 부족해요.")
            continue
        if topic == "coaching":
            continue
        labels = LABELS.get(topic, ())
        found = False
        for label in labels:
            values = facts.get(label, [])
            unique = {v for v, _ in values}
            if len(unique) > 1:
                add(f"conflict:{label}", f"{label} 정보가 원문끼리 달라 하나로 확정해 안내하기 어려워요.")
                found = True
                continue
            if not values:
                continue
            v, eid = values[0]
            if label == "영상 URL":
                if not re.fullmatch(r"https?://openapi\.kspo\.or\.kr/web/video/[^\s]+\.mp4", v):
                    continue
                sentence = "이 운동의 공식 영상 주소가 원문에 있어요"
            elif label == "운동명":
                # Omit parenthesized foreign translations, preserving Korean source name.
                display = re.sub(r"\([^)]*[A-Za-z\u3400-\u9fff][^)]*\)", "", v).strip()
                sentence = f"현재 선택된 운동은 ‘{display}’이에요"
            elif label == "설명":
                sentence = f"원문 설명은 ‘{v.rstrip('.')}’이에요"
            else:
                sentence = f"{label} 정보는 ‘{v}’예요"
            previous = len(sentences)
            add(f"{label}:{v}", sentence, eid)
            found = found or len(sentences) > previous or f"{label}:{v}" in seen
        if not found:
            human = {"method": "자세·호흡·동작 방법", "dose": "횟수·세트·시간", "effect": "운동 효과", "video": "공식 영상", "equipment": "운동 도구", "description": "운동 설명"}.get(topic, labels[0] if labels else "요청 항목")
            add(f"missing:{topic}", f"현재 원문에는 {human}에 관한 충분한 정보가 없어요.")
    if not sentences:
        return ("추가로 안내할 새로운 원문 정보가 없어요. 궁금한 항목을 구체적으로 말씀해 주세요." if seen else abstention), []
    if len(sentences) == 1 and keys[0].startswith(("missing:", "conflict:")):
        return abstention, keys
    return " ".join(sentences), keys


def respond(client: Any, system_prompt: str, message: str, history: Sequence[Mapping[str, Any]],
            profile: Mapping[str, Any], selected_name: str, evidence: Sequence[Mapping[str, Any]],
            abstention: str, state: dict[str, Any], coaching_prompt: str | None = None) -> str:
    safety = safety_update(message, profile)
    if safety:
        return str(safety["answer"])
    continuing = bool(CONTINUE.fullmatch(message.strip()))
    explicit = infer_topics(message)
    trace: dict[str, Any] = {"model_used": False, "intent_source": "rules", "errors": []}
    topics = explicit
    if not continuing:
        prompt = json.dumps({"question": message[:500], "selected_exercise": selected_name[:120],
            "available_fields": sorted(facts_from_sources(evidence, selected_name)),
            "recent_user_questions": [str(x.get("content") or "")[:180] for x in history[-4:] if x.get("role") == "user"],
            "allowed_topics": list(TOPICS)}, ensure_ascii=False)
        try:
            trace["model_used"] = True
            result = json.loads(client.complete_json(system_prompt, prompt, max_tokens=128, response_schema=INTENT_SCHEMA))
            proposed = result.get("topics") if isinstance(result, dict) and set(result) == {"topics"} else None
            if not isinstance(proposed, list) or not 1 <= len(proposed) <= 5 or any(not isinstance(t, str) or t not in TOPICS for t in proposed) or len(set(proposed)) != len(proposed):
                raise ValueError("허용된 topics 배열만 반환해야 합니다.")
            # Explicit user requirements cannot be dropped by the small model.
            topics = list(dict.fromkeys([*explicit, *proposed]))
            trace["intent_source"] = "rules+model" if explicit else "model"
            trace["model_topics"] = proposed
            trace["completion"] = getattr(client, "last_completion", {})
        except (ValueError, RuntimeError, ConnectionError, IndexError) as exc:
            trace["errors"].append(type(exc).__name__)
        if not topics:
            topics = ["name", "description"]
    else:
        topics = list(state.get("topics") or ["name", "description", "area", "equipment", "location", "difficulty", "stage", "video"])
    seen = state.get("seen", []) if continuing else []
    answer, keys = render(message, topics, profile, selected_name, evidence, abstention, seen)
    state["guidance_sources"] = []
    interpret = coaching_prompt and evidence and selected_name and not continuing and bool(set(topics) & {"reason", "effect", "description", "coaching"})
    if interpret:
        addition, refs, coaching_trace = generate_interpretation(client, coaching_prompt,
            message, history, profile, selected_name, evidence, state)
        trace["coaching"] = coaching_trace
        if addition:
            explanation, follow_up = addition
            # A concise factual lead plus interpretation; never label general
            # reasoning with an E citation belonging to the local exercise row.
            fact_topics = [t for t in topics if t not in {"effect", "description", "coaching"}]
            if not fact_topics:
                fact_topics = ["name"]
            if fact_topics == ["reason"]:
                fact_topics = ["name"]
            fact_answer, fact_keys = render(message, fact_topics[:2], profile,
                selected_name, evidence, abstention, max_sentences=2)
            lead = fact_answer if fact_answer != abstention else ""
            answer = (lead + "\n\n코치의 해석: " + explanation).strip()
            if follow_up:
                answer += "\n" + follow_up
            if len(answer) > 650:
                answer = lead + "\n\n코치의 해석: " + explanation
            keys = fact_keys
            state["guidance_sources"] = refs
    state.update(topics=list(topics), seen=list(dict.fromkeys([*seen, *keys])), trace=trace)
    return answer
