"""Live Qwen3 harness checks; retains responses for manual review."""
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
def post(endpoint, payload):
    req = Request('http://127.0.0.1:8501'+endpoint,
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json'},method='POST')
    with urlopen(req,timeout=240) as response:
        return json.load(response)

def run():
    base = dict(user_id='rag-update-review',age=30,sex='M',height_cm=170,weight_kg=65,
        selection_mode=True,disability_type='없음',health_information='없음',
        pain_area='없음',equipment='없음',fitness_level='종합',location='')
    cases = [
        ('허리 스트레칭',dict(base,target_area='허리',exercise_type='스트레칭')),
        ('복부 근력',dict(base,target_area='복부',exercise_type='근력')),
        ('높은 통증',dict(base,target_area='허리',exercise_type='스트레칭',pain_area='허리',pain_level=8)),
        ('자유 질문',dict(user_id='rag-update-free',question='악력을 높이는 운동을 알려줘',selection_mode=False)),
    ]
    results=[]
    options = post('/api/options', dict(age_group='성인', sex='M', target_area='허리', exercise_type='스트레칭'))
    stages = [item['value'] for item in options['options']['exercise_stage']]
    results.append(dict(name='단계 필터', checks={'main_available': '본운동' in stages, 'no_unspecified': '단계 미표기' not in stages}, stages=stages))
    for name,payload in cases:
        start=time.monotonic()
        response=post('/api/coach',payload)
        checks={'status_ok':response.get('status')=='ok'}
        retrieval=response.get('retrieval',{})
        if name=='높은 통증':
            checks['no_exercise_selected']=not retrieval.get('selected_name')
            checks['no_videos']=not response.get('video_options')
            checks['no_alternatives']=not retrieval.get('available_alternatives')
        elif name in {'허리 스트레칭','복부 근력'}:
            checks['selected_candidate']=bool(retrieval.get('selected_name'))
            checks['sources_present']=bool(response.get('sources'))
        if name=='복부 근력':
            checks['no_leg_press']='다리 밀기' not in str(retrieval.get('selected_name'))
        videos=response.get('video_options',[])
        checks['valid_video_urls']=all(v['url'].startswith('http://openapi.kspo.or.kr/web/video/') and v['url'].endswith('.mp4') for v in videos)
        item=dict(name=name,seconds=round(time.monotonic()-start,2),payload=payload,checks=checks,response=response)
        results.append(item)
        print(name,checks,'selected=',retrieval.get('selected_name'),'videos=',len(videos),flush=True)
        if name=='허리 스트레칭':
            chat=post('/api/chat',dict(user_id=base['user_id'],message='운동 이름과 영상이 있는지 간단히 알려줘',history=[]))
            results.append(dict(name='추천 후 챗봇',response=chat,checks={'answer_present':bool(chat.get('answer')),'context_ready':bool(chat.get('context_ready'))}))
            print('CHAT',chat.get('answer'),flush=True)
            next_chat=post('/api/chat',dict(user_id=base['user_id'],message='도구 없이 본운동 허리 스트레칭 추천해줘',history=[]))
            followup=post('/api/chat',dict(user_id=base['user_id'],message='이 운동 이름 알려줘',history=[]))
            results.append(dict(name='본운동 추천 후 맥락', response=next_chat, followup=followup, checks={'not_bmi': '입력 BMI' not in next_chat.get('answer',''), 'recommendation_sources': bool(next_chat.get('sources')), 'followup_sources': bool(followup.get('sources'))}))
            print('STAGE CHAT',next_chat.get('answer'), 'FOLLOWUP',followup.get('answer'),flush=True)
    report={'passed':all(all(r['checks'].values()) for r in results),'cases':results}
    destination=ROOT/'artifacts/rag_update_live_report.json'
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('REPORT',destination,'passed=',report['passed'],flush=True)
    if not report['passed']:
        raise SystemExit(1)

if __name__=='__main__':
    run()
