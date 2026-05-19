from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4


@contextmanager
def temp_workdir(prefix: str = "radiology_qc_ai_") -> Iterator[Path]:
    # In some sandboxed environments, the system temp directory may not be writable.
    # Prefer a service-local temp folder by default, with an env override for production.
    base_dir = os.environ.get("RADIOLOGY_QC_AI_TMP_DIR")
    if base_dir:
        tmp_base = Path(base_dir)
    else:
        # `.../RadiologyQaAI/app/storage.py` -> service root is parent of `app/`
        tmp_base = Path(__file__).resolve().parents[1] / ".tmp"

    tmp_base.mkdir(parents=True, exist_ok=True)

    # NOTE: Avoid `tempfile.TemporaryDirectory` here: in some locked-down Windows
    # environments it creates directories that are not writable/deletable by the process.
    workdir = tmp_base / f"{prefix}{uuid4().hex}"
    os.makedirs(workdir, exist_ok=False)
    try:
        yield workdir
    finally:
        try:
            shutil.rmtree(workdir)
        except Exception:
            # Best-effort cleanup. If it fails, leaving temp artifacts is preferable to crashing the request.
            pass


def ensure_dir(path: Path) -> Path:
    os.makedirs(path, exist_ok=True)
    return path
