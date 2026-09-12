"""Checks shared by the notebook, rebuild tool and serving runtime."""
import hashlib
import json

def validate_index(database, directory, collection, expected_ids):
    marker = directory / 'BUILD_COMPLETE.json'
    if not marker.is_file():
        raise RuntimeError('RAG 인덱스 구축이 완료되지 않았습니다.')
    info = json.loads(marker.read_text(encoding='utf-8'))
    if info.get('embedding_model') != 'jhgan/ko-sroberta-multitask':
        raise RuntimeError('RAG 임베딩 모델이 일치하지 않습니다.')
    source_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    if info.get('source_database_sha256') != source_hash:
        raise RuntimeError('RAG 원문 DB와 인덱스 버전이 다릅니다. 후보 폴더를 다시 구축·검증하세요.')
    actual = set()
    for offset in range(0, collection.count(), 2000):
        actual.update(collection.get(limit=2000, offset=offset, include=[])['ids'])
    if actual != expected_ids:
        raise RuntimeError(f'RAG 문서 ID 불일치: 누락 {len(expected_ids-actual)}, 추가 {len(actual-expected_ids)}')
    return info
