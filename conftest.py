"""Root conftest: ensure src/ is on sys.path when the editable pth is hidden by macOS."""

import sys
from pathlib import Path

src = Path(__file__).parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))
