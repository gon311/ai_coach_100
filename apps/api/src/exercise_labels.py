"""원문을 보존하는 운동명 표시 및 단계 분류."""
import re


def display_name(name):
    name = re.sub(r"\s*\((?:사전운동|준비운동|본운동|정리운동|마무리운동|단계 미상)\)\s*$", "", str(name or ""))
    return re.sub(r"^(?:(?:사전운동|준비운동|본운동|정리운동|마무리운동)\s*[-:·]\s*)+", "", name).strip()


def exercise_stages(title, content, metadata=None):
    raw = [str((metadata or {}).get('exercise_stage') or '')]
    raw += re.findall(r'(?m)^운동 단계\s*:\s*([^\n]+)', content or '')
    prefix = re.match(r'^(사전운동|준비운동|본운동|정리운동|마무리운동)\s*[-:·]', str(title or ''))
    if prefix:
        raw.append(prefix[1])
    stages = {stage for text in raw for stage in ('사전운동', '준비운동', '본운동', '정리운동', '마무리운동') if stage in text}
    # 서비스 분류 정책: 원문 단계가 없는 경우에만 본운동으로 묶는다.
    return {{'사전운동': '준비운동', '마무리운동': '정리운동'}.get(s, s) for s in stages} or {'본운동'}
