#!/usr/bin/env python3
"""Entry point for the independent archived-content processing trial."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from social2md_app.content_pipeline import main  # noqa: E402

raise SystemExit(main())
