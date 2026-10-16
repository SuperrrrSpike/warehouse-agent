from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    root_dir: Path
    db_path: Path
    report_dir: Path
    openai_api_key: str | None
    openai_model: str
    anthropic_api_key: str | None
    anthropic_model: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        root_dir = Path(__file__).resolve().parent.parent
        db_path = Path(
            os.getenv("WAREHOUSE_DB_PATH") or root_dir / "data" / "warehouse_demo.db"
        )
        report_dir = Path(os.getenv("WAREHOUSE_REPORT_DIR") or root_dir / "reports")
        return cls(
            root_dir=root_dir,
            db_path=db_path.expanduser().resolve(),
            report_dir=report_dir.expanduser().resolve(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        )

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
