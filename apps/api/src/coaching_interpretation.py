"""Clearly labelled, bounded coaching interpretation; never an RAG source fact."""
import json
import re
from difflib import SequenceMatcher

GUIDANCE = [
    {"id": "G1", "title": "NHS: 근력·유연성 운동의 일반 원리",
     "url": "https://www.nhs.uk/live-well/exercise/how-to-improve-strength-flexibility/",
     "text": "유연성 운동은 일상 활동에 필요한 관절의 움직임을 유지하는 데 목적이 있다. 근력 운동은 근육을 평소보다 더 사용하며 일상 동작에 필요한 힘을 기르는 데 도움이 된다. 이 일반 원리를 특정 운동의 개인별 효과 보장으로 바꾸지 않는다."},
    {"id": "G2", "title": "NHS: 유연성 운동 안내",
     "url": "https://www.nhs.uk/live-well/exercise/flexibility-exercises/",
     "text": "유연성 운동은 움직임과 유연성을 위한 활동이다. 일반적으로 편안한 범위에서 시작해 점진적으로 늘리는 원칙을 설명할 수 있다. 해당 페이지의 동작과 로컬 영상이 같은 운동이라고 단정하거나 동작·횟수를 가져와 개인에게 처방하지 않는다."},
]
SCHEMA = {"type": "object", "additionalProperties": False,
    "required": ["coaching", "follow_up", "guidance_ids"], "properties": {
        "coaching": {"type": "array", "minItems": 2, "maxItems": 2,
                     "items": {"type": "string", "minLength": 1, "maxLength": 100}},
        "follow_up": {"type": "string", "maxLength": 80},
        "guidance_ids": {"type": "array", "minItems": 0, "maxItems": 2,
                         "items": {"type": "string", "enum": ["G1", "G2"]}},
    }}


def validate(result, selected_name, previous):
    if not isinstance(result, dict) or set(result) != {"coaching", "follow_up", "guidance_ids"}:
        return ["schema"]
    lines = result["coaching"]
    follow = result["follow_up"]
    gids = result["guidance_ids"]
    if not isinstance(lines, list) or not 1 <= len(lines) <= 2 or not all(isinstance(x, str) and 1 <= len(x) <= 100 for x in lines):
        return ["length"]
    if not isinstance(follow, str) or len(follow) > 80 or not isinstance(gids, list) or any(x not in ("G1", "G2") for x in gids):
        return ["schema"]
    text = " ".join([*lines, follow])
    errors = []
    if re.search(r"[0-9A-Za-z\u3400-\u9fff\u3040-\u30ff]|https?://|[<>\[\]{}]", text):
        errors.append("numbers_language_or_citations")
    # Interpretations may relate a goal to general exercise principles, but not
    # invent prescriptions, diagnoses, video contents or certainty of benefit.
    if re.search(r"완치|치료|진단|디스크|협착|염증|혈압|우울증|질환|수술|통증.*(?:완화|없애|해소|줄)|예방|교정|안전(?:해|하|합)|무조건|반드시|확실|보장|최적|최고|가장|세트|반복.*(?:회|번)|(?:매일|하루에)|몇\s*(?:회|분|번)|호흡|들이마|내쉬|시계방향|반시계|고개를|머리를|숙이|젖히|꺾|돌리세요|영상(?:에서|에는|을보면)|원문(?:에서|에는)|자료(?:에서|에는)", text):
        errors.append("unsupported_prescription_or_claim")
    if re.search(r"(?:체력이|근력이|유연성이).*(?:낮|약|부족)|당신은|나이에비해|수영장.*(?:적합|맞|위해)", text.replace(" ", "")):
        errors.append("unmeasured_personal_assumption")
    if not all(re.search(r"(?:요|니다)[.!?]?\s*$", x) for x in lines):
        errors.append("tone")
    if follow and not re.search(r"(?:\?|요\.?|니다\.?)$", follow):
        errors.append("follow_up")
    if len(set(lines)) != len(lines):
        errors.append("duplicate")
    for old in previous[-2:]:
        current_plain = re.sub(r"[^가-힣]", "", " ".join(lines)).replace(re.sub(r"[^가-힣]", "", selected_name), "")
        old_plain = re.sub(r"[^가-힣]", "", str(old)).replace(re.sub(r"[^가-힣]", "", selected_name), "")
        if SequenceMatcher(None, current_plain, old_plain).ratio() > 0.76 or (len(current_plain) > 12 and current_plain in old_plain):
            errors.append("repeated_explanation")
    return errors


def generate(client, prompt, message, history, profile, selected_name, evidence, state):
    # Bounded raw evidence supplies semantics missing from sparse facet labels.
    payload = {
        "question": message[:500], "selected_exercise": selected_name[:120],
        "user_conditions": {k: str(profile[k])[:160] for k in ("target_area", "exercise_type", "goal", "fitness_level") if profile.get(k)},
        "source_data": [{"id": str(x.get("evidence_id", "")), "text": str(x.get("text", ""))[:800]} for x in evidence[:4]],
        "general_guidance": GUIDANCE,
        "recent_dialogue": state.get("coaching_dialogue") or [{"role": str(x.get("role")), "content": str(x.get("content", ""))[:300]} for x in history[-4:] if x.get("role") in ("user", "assistant")],
        "previous_interpretations": state.get("interpretations", [])[-2:],
    }
    if any(term in message for term in ("싶", "목표", "원해")):
        focus = "사용자가 목표를 밝혔다. 목표를 다시 묻지 말고, 그 목표를 어떤 일상 상황에서 확인하고 싶은지 구체화하는 관점과 운동 선택 기준을 설명한다. 유연성을 높인다는 설명을 반복하지 않는다."
    elif any(term in message for term in ("도움", "효과", "좋은", "좋아")):
        focus = "효과의 의미를 묻는다. 유연성이 좋아진다는 말만 반복하지 말고 선택한 운동 부위와 관련된 일상적 움직임 상황 하나를 예로 들어 원리를 설명한다. 구체적 수행 자세나 횟수는 말하지 않는다."
    elif any(term in message for term in ("습관", "꾸준", "지루", "시작")):
        focus = "생활 속에서 기억하기 쉬운 계기와 구체적인 목적을 정하는 등 지속하기 위한 일반적인 생각을 설명한다. 의학적 효과 설명을 반복하지 않는다."
    elif any(term in message for term in ("왜", "이유", "추천")):
        focus = "이 운동의 성격과 사용자의 목적이 어떻게 연결되는지 두 문장으로 설명한다. 한 문장은 목적, 다른 문장은 목표에 따른 선택 기준을 설명한다."
    else:
        focus = "현재 질문의 핵심에 직접 답하고 앞서 말하지 않은 관점이나 조건을 설명한다."
    payload["current_focus"] = focus
    trace = {"used": False, "errors": []}
    try:
        raw = client.complete_json(prompt, json.dumps(payload, ensure_ascii=False), max_tokens=384, response_schema=SCHEMA, temperature=0.7, top_p=0.8)
        result = json.loads(raw)
        if isinstance(result, dict) and isinstance(result.get("follow_up"), str):
            prior_questions = [x.get("content", "") for x in state.get("coaching_dialogue", []) if x.get("role") == "assistant"]
            follow = result["follow_up"]
            if "더 궁금" in follow or any(follow and follow in x for x in prior_questions):
                result["follow_up"] = ""
        errors = validate(result, selected_name, state.get("interpretations", []))
        if errors == ["repeated_explanation"]:
            payload["revision"] = "직전 해석과 거의 같은 답이므로 한 번만 고친다. 이미 한 운동 목적 설명 대신 현재 질문에 맞는 일상적 의미나 선택 기준을 새로 설명한다. 예를 들어 일상에서 편안하게 움직이는 목표인지 확인한다. 효과나 동작을 새로 만들어내지는 않는다."
            raw = client.complete_json(prompt, json.dumps(payload, ensure_ascii=False), max_tokens=384, response_schema=SCHEMA, temperature=0.7, top_p=0.8)
            result = json.loads(raw)
            errors = validate(result, selected_name, state.get("interpretations", []))
            trace["revised_once"] = True
        trace.update(errors=errors, completion=getattr(client, "last_completion", {}))
        if errors:
            return None, [], trace
        # Keep complete sentences only; never slice through a claim.
        sentences = [part.strip() for line in result["coaching"]
                     for part in re.split(r"(?<=[.!?])\s+", line) if part.strip()]
        previous_sentences = {re.sub(r"[^가-힣]", "", part)
                              for old in state.get("interpretations", [])[-2:]
                              for part in re.split(r"(?<=[.!?])\s+", old)}
        sentences = [part for part in sentences
                     if re.sub(r"[^가-힣]", "", part) not in previous_sentences]
        if not sentences:
            trace["errors"] = ["repeated_explanation"]
            return None, [], trace
        text = " ".join(sentences[:2])
        state["interpretations"] = [*state.get("interpretations", []), text][-3:]
        state["coaching_dialogue"] = [*state.get("coaching_dialogue", []),
            {"role": "user", "content": message[:300]},
            {"role": "assistant", "content": text + " " + result["follow_up"]}][-4:]
        trace["used"] = True
        refs = [{"title": x["title"], "url": x["url"]} for x in GUIDANCE if x["id"] in result["guidance_ids"]]
        return (text, result["follow_up"]), refs, trace
    except (ValueError, RuntimeError, ConnectionError, IndexError) as exc:
        trace["errors"] = [type(exc).__name__]
        return None, [], trace
