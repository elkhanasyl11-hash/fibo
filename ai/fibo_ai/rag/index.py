"""Small persistent JSON index, partitioned by machine and manual."""

import json
import threading
from pathlib import Path
from urllib.parse import quote

from fibo_ai.rag.ingest import ManualChunk

_WRITE_LOCK = threading.Lock()


def _machine_path(root: Path, machine_id: str) -> Path:
    return root / "machines" / f"{quote(machine_id, safe='')}.json"


def upsert_manual(root: Path, machine_id: str, manual_id: str, chunks: list[ManualChunk]) -> None:
    path = _machine_path(root, machine_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        records: list[dict[str, object]] = []
        if path.exists():
            try:
                records = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                records = []
        records = [row for row in records if row.get("manual_id") != manual_id]
        records.extend(chunk.model_dump() for chunk in chunks)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)


def read_machine_index(root: Path, machine_id: str) -> list[ManualChunk]:
    path = _machine_path(root, machine_id)
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        return [ManualChunk.model_validate(row) for row in records]
    except (OSError, json.JSONDecodeError, ValueError):
        return []
