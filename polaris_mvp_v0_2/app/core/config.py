from pathlib import Path
import os
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = Path(os.getenv("POLARIS_DATABASE_PATH", str(PROJECT_ROOT / "polaris.db")))
