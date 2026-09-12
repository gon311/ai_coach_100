"""Strict source-grounded Qwen3 fitness chat harness v2."""

from __future__ import annotations

import json
import re
from typing import Any


FITNESS_TERMS = (
    "운동", "체력", "근력", "근육", "유연", "스트레칭", "유산소", "심폐", "걷기", "달리기",
    "스쿼트", "푸시업", "윗몸", "플랭크", "악력", "민첩", "순발력", "균형", "자세", "반복", "세트",
    "허리", "무릎", "어깨", "팔", "다리", "코어", "측정", "백분위", "회복", "워밍업", "쿨다운",
)
OFF_TOPIC = "운동에 관한 질문을 해주세요"


def _exercise_question(message: str, history: list[dict[str, str]] | None = None) -> bool:
    recent = " ".join(str(h.get("content") or "") for h in (history or [])[-4:])
    normalized = re.sub(r"\s+", "", f"{message} {recent}").casefold()
    return any(term in normalized for term in FITNESS_TERMS)


def _dedupe(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?。])\s+|\n+", text) if part.strip()]
    seen, unique = set(), []
    for part in parts:
        key = re.sub(r"[^0-9가-힣a-z]", "", part.casefold())
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return " ".join(unique)[:700]


def _fully_cited(text: str) -> bool:
    return bool(re.search(r"\[E[1-5]\]", text))


def answer(runtime: Any, message: str, history: list[dict[str, str]] | None = None, user_context: str = "") -> dict[str, Any]:
    if not _exercise_question(message, history):
        return {"answer": OFF_TOPIC, "sources": [], "grounded": True, "harness_version": "fitness-chat-v2-triple-grounding"}
    recent_users = [str(h.get("content") or "") for h in (history or [])[-6:] if h.get("role") == "user"]
    recent_assistants = [str(h.get("content") or "") for h in (history or [])[-6:] if h.get("role") == "assistant"]
    referential = any(term in message for term in ("그 동작", "그 운동", "그거", "이 동작", "이 운동", "그 방법"))
    if referential and recent_assistants:
        search_query = f"{recent_assistants[-1]} {message}"[-900:]
    else:
        search_query = " ".join([*recent_users[-2:], message])[-700:]
    sources = runtime.semantic_search(
        search_query, k=5,
        datasets=["video_content", "general_prescription", "measurement_prescription"],
        min_score=0.28,
    )
    nutrition_terms = ("음식", "식단", "영양", "단백질", "탄수화물", "지방", "비타민", "식사")
    if any(term in message for term in nutrition_terms):
        searchable = " ".join(f"{s.get('title','')} {s.get('text','')}" for s in sources).casefold()
        if not any(term in searchable for term in nutrition_terms):
            return {"answer":"현재 보유한 자료는 체력 측정과 운동 방법 중심이라 음식이나 영양을 근거 있게 안내하기 어려워요. 운동 방법이나 측정 결과에 관해 물어봐 주세요.","sources":[],"grounded":True,"harness_version":"fitness-chat-v2-triple-grounding"}
    if user_context:
        sources = [{"title":"사용자 측정기록","text":user_context,"dataset":"fitness_user_records","score":1.0}] + sources[:4]
    if not sources:
        return {"answer":"보유한 운동 데이터에서 질문과 직접 연결되는 근거를 찾지 못했어요. 운동 종목이나 목표를 조금 더 구체적으로 알려주세요.","sources":[],"grounded":True,"harness_version":"fitness-chat-v2-triple-grounding"}
    evidence = "\n".join(f"[E{i}] {s['title']} | {str(s['text'])[:700]}" for i,s in enumerate(sources,1))
    triple = "\n\n".join(f"근거 고정 {i}/3:\n{evidence}" for i in range(1,4))
    history_text = "\n".join(f"{h.get('role')}: {h.get('content')}" for h in (history or [])[-4:])
    system = """당신은 친절하고 차분한 한국어 운동 코치다. 현재 질문에 먼저 직접 답하고, 최근 대화는 생략된 대상을 이해할 때만 참고한다. 제공된 근거에 명시된 사실만 사용하며 근거에 없는 횟수, 효과, 질환, 수치, 운동을 만들지 않는다. 앞 답변을 복사하거나 질문과 무관한 측정 결과를 되풀이하지 않는다. 명령조 대신 '~해보세요', '~하면 좋아요'처럼 부드럽게 말한다. 답변은 JSON 객체만 출력한다."""
    prompt = f"""질문: {message}
최근 대화: {history_text or '없음'}

아래 동일 근거를 세 번 확인한 뒤 답하세요. 세 묶음은 강조용이며 답변에서 반복하면 안 됩니다.
{triple}

규칙:
1. 답변의 모든 구체적 사실 뒤에 [E번호]를 붙입니다.
2. 근거 밖 추측은 쓰지 않습니다.
3. 자연스럽고 부드러운 2~4문장으로 현재 질문에 답합니다. 근거를 사용한 문장 끝에는 해당 [E번호]를 붙입니다.
4. JSON 형식은 {{"answer":"...","used_evidence":["E1"]}}입니다."""
    try:
        raw = runtime.qwen3_client.complete_json(
            system, prompt, max_tokens=500,
            response_schema={"type":"object","properties":{"answer":{"type":"string"},"used_evidence":{"type":"array","items":{"type":"string"}}},"required":["answer","used_evidence"]},
        )
        parsed = json.loads(raw)
        text = _dedupe(str(parsed.get("answer") or ""))
        used = {str(x) for x in parsed.get("used_evidence", [])}
        if not text or not _fully_cited(text) or not used or not all(re.fullmatch(r"E[1-5]", x) for x in used):
            raise ValueError("invalid grounded response")
        cited = {f"E{i}" for i in range(1,6) if f"E{i}" in text}
        if not cited:
            raise ValueError("missing citations")
        visible = [{"evidence_id":f"E{i}","title":s["title"],"dataset":s["dataset"],"score":round(float(s["score"]),4)} for i,s in enumerate(sources,1) if f"E{i}" in cited]
        clean = re.sub(r"\s*\[E[1-5]\]", "", text).strip()
        previous_answers = [str(h.get("content") or "").strip() for h in (history or [])[-6:] if h.get("role") == "assistant"]
        if clean in previous_answers:
            raise ValueError("repeated prior response")
        return {"answer":clean,"sources":visible,"grounded":True,"harness_version":"fitness-chat-v2-triple-grounding"}
    except Exception:
        first = sources[0]
        excerpt = re.sub(r"\s+", " ", str(first.get("text") or "")).strip()[:180]
        return {"answer":f"보유 자료에서 확인한 내용이에요. {excerpt}","sources":[{"evidence_id":"E1","title":first["title"],"dataset":first["dataset"],"score":round(float(first["score"]),4)}],"grounded":True,"harness_version":"fitness-chat-v2-triple-grounding"}
