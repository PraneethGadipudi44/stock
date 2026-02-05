from __future__ import annotations

import subprocess
from pathlib import Path


def test_no_bom_in_tracked_files():
    result = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    exts = {".py", ".yaml", ".yml", ".json"}

    for rel_path in result:
        path = Path(rel_path)
        if path.suffix.lower() not in exts:
            continue
        data = path.read_bytes()
        assert not data.startswith(b"ï»¿"), f"BOM found in {rel_path}"
