from __future__ import annotations

import json
from pathlib import Path

from .models import DiagramDocument


def export_document(document: DiagramDocument, output_path: Path) -> None:
    output_path.write_text(json.dumps(document.to_dict(), indent=2), encoding="utf-8")
