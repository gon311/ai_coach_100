"""미연동 목록을 분류한다. 추천용 운동 동등성/별칭을 만들지 않는다."""
import re
from urllib.parse import urlparse


# 처방 원문과 영상 원문을 직접 대조해 확인한 이름 대응만 둔다.
# 일반적인 유사도·자동 별칭 규칙으로 확장하지 않는다.
VERIFIED_VIDEO_ALIASES = {
    '물통으로양팔들어올리기': {
        '물병양팔들어올리기': '물통/물병 표기 차이, 나머지 동작명 일치',
    },
    '팔굽혀펴기무릎대고실시': {
        '무릎대고팔굽혀펴기kneelingpushup': '무릎 대고 실시하는 팔굽혀펴기 동작명 일치',
    },
    '앉아서덤벨로손목굽히기': {
        '앉아서손목굽히기': '공식 영상의 운동 도구가 덤벨로 명시됨',
    },
    '어깨앞쪽스트레칭': {
        '가슴어깨앞쪽스트레칭': '공식 영상명에 어깨 앞쪽 스트레칭이 그대로 포함됨',
    },
}

# 사용자가 유사 운동 참고 영상으로 연결하도록 승인한 대응이다.
# 원운동과 동일하다고 주장하지 않고 화면에도 유사 영상임을 명시한다.
APPROVED_SIMILAR_VIDEO_ALIASES = {
    '두발모아걷기': {
        '균형걷기': '두 발을 모아 걷는 원운동의 참고용으로 일반 균형 걷기 영상을 연결',
    },
    '앞뒤로한발씩걷기': {
        '한발따라가기': '앞뒤 방향으로 한 발씩 이동하는 참고 영상으로 연결',
    },
}


def key(value):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


def organize(items, videos):
    references = {}
    title_references = {}
    for title, content in videos:
        description = re.search(r"(?m)^설명:\s*(.+)$", content)
        named = re.search(r"운동 중,\s*(.+?)운동을 설명", description[1]) if description else None
        url = re.search(r"(?m)^영상 URL:\s*(\S+)", content)
        if not url:
            continue
        parsed = urlparse(url[1])
        if parsed.scheme not in {"http", "https"} or parsed.hostname != "openapi.kspo.or.kr" or not parsed.path.endswith('.mp4'):
            continue
        def field(label):
            match = re.search(rf"(?m)^{label}:\s*([^\n]+)", content)
            return match[1] if match else "미표기"
        evidence_name = named[1] if named else title
        evidence_text = description[1] if description else f'공식 영상 운동명: {title}'
        group = references.setdefault(key(evidence_name), {}).setdefault(url[1], {
            'url': url[1], 'titles': set(), 'evidence': evidence_text,
            'ages': set(), 'tools': set(), 'missing_equipment_rows': False,
        })
        group['titles'].add(title)
        group['ages'].add(field('대상 연령군'))
        equipment = field('운동 도구')
        if equipment == '미표기':
            group['missing_equipment_rows'] = True
        else:
            group['tools'].add(equipment)
        title_references.setdefault(key(title), set()).add((key(evidence_name), url[1], title))
    for groups in references.values():
        for group in groups.values():
            group['title'] = ' / '.join(sorted(group.pop('titles')))
            group['age_group'] = ' / '.join(sorted(group.pop('ages')))
            group['equipment'] = ' / '.join(sorted(group.pop('tools'))) or '원문 미표기 — 장비 없음으로 확인된 것은 아님'
    for item in items:
        item_key = key(item['exercise_name'])
        matched = {url: {**value, 'match_type': 'description', 'match_note': '공식 운동명 또는 설명문 일치'} for url, value in references.get(item_key, {}).items()}
        alias_notes = set()
        for alias_key, note in VERIFIED_VIDEO_ALIASES.get(item_key, {}).items():
            for named_key, url, matched_title in title_references.get(alias_key, set()):
                if url in references.get(named_key, {}):
                    matched[url] = {**references[named_key][url], 'title': matched_title, 'match_type': 'verified_name', 'match_note': note}
                    alias_notes.add(note)
        similar_notes = set()
        for alias_key, note in APPROVED_SIMILAR_VIDEO_ALIASES.get(item_key, {}).items():
            for named_key, url, matched_title in title_references.get(alias_key, set()):
                if url in references.get(named_key, {}):
                    matched[url] = {**references[named_key][url], 'title': matched_title, 'match_type': 'similar', 'match_note': note}
                    similar_notes.add(note)
        item['related_videos'] = sorted(matched.values(), key=lambda v: (v['title'], v['url']))
        item['link_status'] = 'description_reference' if item['related_videos'] else 'unverified'
        item['alias_evidence'] = sorted(alias_notes)
        item['similar_evidence'] = sorted(similar_notes)
        item['reason'] = ('사용자 승인 유사 운동 참고 영상 연결' if similar_notes else '검증된 원문 이름 대응으로 공식 영상 확인' if alias_notes else '공식 설명문에 운동명 확인 — 세부 영상은 별도 표시') if item['related_videos'] else '보유 자료에서 영상 연결 근거 미확인'
        types = item.get('exercise_types', [])
        kind = '스트레칭' if '스트레칭' in types else '근력운동' if '근력' in types else '/'.join(types)
        item['display_group'] = kind or '유형 미표기'
    return items
