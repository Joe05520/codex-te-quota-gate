"""Atomic private snapshots. Never store hook payloads or raw account responses."""
import json
import os
from pathlib import Path
import tempfile


def write_snapshot(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".quota-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, allow_nan=False)
            out.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_snapshot(path):
    with open(path, encoding="utf-8") as source:
        return json.load(source)
