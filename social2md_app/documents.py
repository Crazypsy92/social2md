from __future__ import annotations

import os
import tempfile
from pathlib import Path

DOCUMENT_EXTENSIONS = {
    ".pdf", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".html", ".epub", ".csv", ".json", ".xml",
}


def find_documents(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in DOCUMENT_EXTENSIONS
    )


def convert_document(source: Path, destination: Path) -> bool:
    """Convert one document to Markdown and atomically persist non-empty output."""
    from markitdown import MarkItDown

    result = MarkItDown().convert(str(source))
    content = (result.text_content or "").strip()
    if not content:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination.is_file() and destination.stat().st_size > 0
