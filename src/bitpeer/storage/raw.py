from __future__ import annotations

import gzip
import json
from pathlib import Path

from bitpeer.models import RawFetchRecord


class RawStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def append(self, record: RawFetchRecord) -> Path:
        day = record.ts_utc.date().isoformat()
        out_path = self._data_dir / "raw" / day / f"{record.market}.jsonl.gz"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        payload = record.model_dump(mode="json")
        line = json.dumps(payload, ensure_ascii=False)
        with gzip.open(out_path, "at", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")

        return out_path

