"""160,461개 RAG 문서를 전체 SentenceTransformer Chroma로 적재한다.

기존 2,000건 표본 인덱스는 건드리지 않으며, 중단 후 같은 명령으로 재개할 수 있다.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


COLLECTION_NAME = "fitness_rag_ko_sroberta_v1"
MODEL_NAME = "jhgan/ko-sroberta-multitask"
LOCAL_MODEL = Path(__file__).resolve().parent.parent / "models" / "ko-sroberta-multitask"


def sqlite_readonly_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro&immutable=1"


def metadata_for(row: sqlite3.Row) -> dict:
    metadata = json.loads(row["metadata_json"] or "{}")
    result = {
        "dataset": row["dataset"],
        "title": row["title"],
        "occurrence_count": int(row["occurrence_count"] or 1),
    }
    for key in (
        "source_file", "age_group", "sex", "certification_grade",
        "disability_type", "disability_detail", "difficulty", "place",
    ):
        value = metadata.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            result[key] = value
    return result


def build(database: Path, target: Path, batch_size: int) -> int:
    target.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(target))
    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embedding_model": MODEL_NAME},
    )
    if (collection.metadata or {}).get('embedding_model') != MODEL_NAME:
        raise RuntimeError('임베딩 모델이 다른 컬렉션입니다. 새 폴더를 사용하세요.')
    existing = {}
    for offset in range(0, collection.count(), 2000):
        page = collection.get(limit=2000, offset=offset, include=['documents','metadatas'])
        existing.update(zip(page['ids'], zip(page['documents'], page['metadatas'])))
    model = None
    vector_cache = {}

    with sqlite3.connect(sqlite_readonly_uri(database), uri=True) as connection:
        connection.row_factory = sqlite3.Row
        expected = int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        expected_ids = {row[0] for row in connection.execute('SELECT id FROM documents')}
        if set(existing) - expected_ids:
            raise RuntimeError('SQLite에 없는 문서가 인덱스에 있습니다. 별도 빈 폴더에 재구축하세요.')
        cursor = connection.execute(
            "SELECT id,dataset,title,content,metadata_json,occurrence_count "
            "FROM documents ORDER BY dataset,id"
        )
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []
        added = 0

        def flush() -> None:
            nonlocal added, model
            if not ids:
                return
            unique_texts = list(dict.fromkeys(text for text in texts if text not in vector_cache))
            if unique_texts and model is None:
                model = SentenceTransformer(str(LOCAL_MODEL) if LOCAL_MODEL.is_dir() else MODEL_NAME)
            if unique_texts:
                vectors = model.encode(unique_texts, batch_size=min(128, len(unique_texts)),
                    show_progress_bar=False, normalize_embeddings=True).tolist()
                vector_cache.update(zip(unique_texts, vectors))
            embeddings = [vector_cache[text] for text in texts]
            collection.upsert(
                ids=list(ids),
                embeddings=embeddings,
                documents=list(texts),
                metadatas=list(metadatas),
            )
            added += len(ids)
            print(
                f"[full-chroma] total={collection.count():,}/{expected:,} "
                f"added_this_run={added:,}",
                flush=True,
            )
            ids.clear(); texts.clear(); metadatas.clear()

        for row in cursor:
            document_id = str(row["id"])
            text = f"{row['title']}\n{row['content']}"
            metadata = metadata_for(row)
            if existing.get(document_id) == (text, metadata):
                continue
            ids.append(document_id)
            texts.append(text)
            metadatas.append(metadata)
            if len(ids) >= batch_size:
                flush()
        flush()

    actual = int(collection.count())
    if actual != expected:
        raise RuntimeError(f"전체 인덱스 건수 불일치: expected={expected}, actual={actual}")
    (target / "BUILD_COMPLETE.json").write_text(
        json.dumps(
            {
                "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "document_count": actual,
                "embedding_model": MODEL_NAME,
                "collection": COLLECTION_NAME,
                "source_database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
                "validation": "document_ids_text_and_metadata",
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"[full-chroma] COMPLETE {actual:,}", flush=True)
    return actual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    build(args.database, args.target, args.batch_size)


if __name__ == "__main__":
    main()
