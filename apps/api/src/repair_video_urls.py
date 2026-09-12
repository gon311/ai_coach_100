"""원본 동영상 JSON의 파일명을 RAG SQLite 영상 URL에 복구한다.

초기 RAG 변환 결과에는 `file_url`만 저장되고 `file_nm`이 빠져 폴더 URL이
표시되었다. 원본의 파일 순번(01~07)과 row_num으로 레코드를 재매칭한다.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from pathlib import Path
from urllib.parse import urljoin


SOURCE_PREFIX = re.compile(r"^(\d{2})_")
GENERIC_VIDEO_URL = "http://openapi.kspo.or.kr/web/video/"


def source_rows(source_dir: Path) -> dict[tuple[str, int], str]:
    mapping: dict[tuple[str, int], str] = {}
    for json_file in sorted(source_dir.glob("*.json")):
        match = SOURCE_PREFIX.match(json_file.name)
        if not match:
            continue
        payload = json.loads(json_file.read_text(encoding="utf-8"))
        for row in payload.get("items", []):
            row_number = row.get("row_num")
            base_url = str(row.get("file_url") or "").strip()
            file_name = str(row.get("file_nm") or "").strip()
            if row_number is None or not base_url or not file_name:
                continue
            mapping[(match.group(1), int(row_number))] = urljoin(base_url, file_name)
    return mapping


def repair(database: Path, source_dir: Path, dry_run: bool = False) -> dict[str, int | str]:
    urls = source_rows(source_dir)
    if not urls:
        raise RuntimeError("원본 동영상 JSON에서 파일 URL을 찾지 못했습니다.")
    backup = database.with_suffix(database.suffix + ".before-video-url-repair")
    if not dry_run:
        shutil.copy2(database, backup)

    updated = 0
    already_full = 0
    unmatched = 0
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id, content, metadata_json FROM documents WHERE dataset='video_content'"
        ).fetchall()
        for document_id, content, metadata_json in rows:
            metadata = json.loads(metadata_json or "{}")
            current = str(metadata.get("video_url") or "").strip()
            if current and current != GENERIC_VIDEO_URL:
                already_full += 1
                continue
            source_name = str(metadata.get("source_file") or "")
            source_match = SOURCE_PREFIX.match(source_name)
            row_number = metadata.get("row_num")
            if not source_match or row_number is None:
                unmatched += 1
                continue
            actual_url = urls.get((source_match.group(1), int(row_number)))
            if not actual_url:
                unmatched += 1
                continue
            updated += 1
            if not dry_run:
                metadata["video_url"] = actual_url
                fixed_content = str(content).replace(GENERIC_VIDEO_URL, actual_url)
                connection.execute(
                    "UPDATE documents SET content=?, metadata_json=? WHERE id=?",
                    (fixed_content, json.dumps(metadata, ensure_ascii=False), document_id),
                )
        if not dry_run:
            connection.commit()
    return {
        "source_video_rows": len(urls),
        "updated": updated,
        "already_full": already_full,
        "unmatched": unmatched,
        "backup": str(backup) if not dry_run else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = repair(args.database, args.source_dir, args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
