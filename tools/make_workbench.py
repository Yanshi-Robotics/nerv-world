"""Generate SO-101 desktop arenas from the scene configuration and object catalogue."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenes.so101_workbench.generate import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
