"""Read-only inventory and document identity checks across local RAG stores."""
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def read_db(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)

def run():
    reports = []
    with read_db(ROOT / 'artifacts/rag_documents.sqlite') as c:
        expected = {r[0]: r[1]+'\n'+r[2] for r in c.execute('select id,title,content from documents')}
        print('DEPLOYMENT', len(expected), c.execute('pragma quick_check').fetchone())
    for root in [Path('C:/ai_fitness_local'), Path('C:/ai_fitness_qwen3_runtime'), Path('C:/ai_fitness_runtime'), ROOT/'artifacts/chroma']:
        for p in root.rglob('*.sqlite*'):
            if p.suffix not in ('.sqlite', '.sqlite3'):
                continue
            with read_db(p) as c:
                tables = {r[0] for r in c.execute('select name from sqlite_master')}
                report = {'path': str(p), 'bytes':p.stat().st_size}
                if 'documents' in tables:
                    docs = {r[0]:r[1]+'\n'+r[2] for r in c.execute('select id,title,content from documents')}
                elif 'embeddings' in tables:
                    docs = dict(c.execute("select e.embedding_id,m.string_value from embeddings e left join embedding_metadata m on m.id=e.id and m.key='chroma:document'"))
                else:
                    print(report); continue
                report.update(count=len(docs), missing_ids=len(expected.keys()-docs.keys()), extra_ids=len(docs.keys()-expected.keys()), changed_text=sum(docs[k]!=expected[k] for k in docs.keys() & expected.keys()))
                reports.append(report)
                print(json.dumps(report,ensure_ascii=False),flush=True)
    (ROOT/'artifacts/rag_storage_audit.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__ == '__main__':
    run()
