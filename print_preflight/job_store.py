from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class JobStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.jobs_dir = self.data_dir / "jobs"
        self.database = self.data_dir / "metadata.sqlite3"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    access_token_hash TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    preset_id TEXT NOT NULL,
                    target_geometry_json TEXT,
                    status TEXT NOT NULL,
                    source_path TEXT,
                    output_path TEXT,
                    report_json TEXT,
                    fix_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    files_deleted_at TEXT
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "target_geometry_json" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN target_geometry_json TEXT")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    rule_id TEXT,
                    reason TEXT,
                    printer_outcome TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_expires_at ON jobs(expires_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_job_id ON feedback(job_id)"
            )

    def create_job(
        self,
        *,
        job_id: str,
        access_token: str,
        original_name: str,
        preset_id: str,
        target_geometry: dict[str, Any],
        source_path: Path,
        expires_at: str,
    ) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, access_token_hash, original_name, preset_id, target_geometry_json, status,
                    source_path, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    job_id,
                    token_hash(access_token),
                    original_name,
                    preset_id,
                    json.dumps(target_geometry, ensure_ascii=False),
                    str(source_path),
                    now,
                    now,
                    expires_at,
                ),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        payload = dict(row)
        for field in ("target_geometry_json", "report_json", "fix_json", "error_json"):
            payload[field.removesuffix("_json")] = json.loads(payload[field]) if payload[field] else None
            del payload[field]
        return payload

    def authorize(self, job_id: str, access_token: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if job is None or token_hash(access_token) != job["access_token_hash"]:
            return None
        return job

    def update(self, job_id: str, **values: Any) -> None:
        allowed = {
            "status",
            "original_name",
            "source_path",
            "output_path",
            "report_json",
            "fix_json",
            "error_json",
            "files_deleted_at",
        }
        unexpected = set(values) - allowed
        if unexpected:
            raise ValueError(f"Unsupported job fields: {sorted(unexpected)}")
        serialized = {}
        for key, value in values.items():
            serialized[key] = json.dumps(value, ensure_ascii=False) if key.endswith("_json") and value is not None else value
        serialized["updated_at"] = utc_now()
        columns = ", ".join(f"{key} = ?" for key in serialized)
        parameters = [*serialized.values(), job_id]
        with self._connect() as connection:
            connection.execute(f"UPDATE jobs SET {columns} WHERE id = ?", parameters)

    def add_feedback(
        self,
        job_id: str,
        *,
        rating: str,
        rule_id: str | None,
        reason: str | None,
        printer_outcome: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback (
                    job_id, rating, rule_id, reason, printer_outcome, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, rating, rule_id, reason, printer_outcome, utc_now()),
            )

    def delete_artifacts(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if job is None:
            return False
        job_dir = (self.jobs_dir / job_id).resolve()
        if job_dir.parent != self.jobs_dir or job_dir.is_symlink():
            return False
        if job_dir.exists():
            shutil.rmtree(job_dir)
        report = job.get("report") or {}
        analysis = report.get("analysis") or {}
        source = analysis.get("source") or {}
        retained_report = {
            "retentionVersion": "privacy-safe-v1",
            "sourceSummary": {
                key: source.get(key)
                for key in ("bytes", "sha256", "pdfFormat", "pageCount")
                if source.get(key) is not None
            },
            "preflight": report.get("preflight"),
            "afterPreflight": report.get("afterPreflight"),
            "validation": report.get("validation"),
            "fix": report.get("fix"),
        }
        self.update(
            job_id,
            status="deleted",
            original_name="deleted.pdf",
            source_path=None,
            output_path=None,
            report_json=retained_report,
            files_deleted_at=utc_now(),
        )
        return True

    def cleanup_expired(self, now: str | None = None) -> int:
        cutoff = now or utc_now()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM jobs WHERE expires_at <= ? AND files_deleted_at IS NULL",
                (cutoff,),
            ).fetchall()
        deleted = 0
        for row in rows:
            deleted += int(self.delete_artifacts(row["id"]))
        return deleted
