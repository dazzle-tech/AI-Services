from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4


@contextmanager
def temp_workdir(prefix: str = "medical_image_interpretation_") -> Iterator[Path]:
    base_dir = os.environ.get("MEDICAL_IMAGE_INTERPRETATION_TMP_DIR")
    if base_dir:
        tmp_base = Path(base_dir)
    else:
        import tempfile

        tmp_base = Path(tempfile.gettempdir()) / "medical_image_interpretation"

    tmp_base.mkdir(parents=True, exist_ok=True)
    workdir = tmp_base / f"{prefix}{uuid4().hex}"
    os.makedirs(workdir, exist_ok=False)
    try:
        yield workdir
    finally:
        try:
            shutil.rmtree(workdir)
        except Exception:
            pass
