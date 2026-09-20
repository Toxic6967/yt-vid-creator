from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DB_PATH


DEFAULT_PROFILE = {
    "channel_name": "Roblox Stories",
    "niche": "Cinematic Roblox mini-movies, relatable gameplay situations, mysteries, horror, funny twists and player stories",
    "tone": "Cinematic, fast and relatable Roblox mini-movies; engaging but never babyish or cringe",
    "audience": "Kids / young Roblox players (roughly 8-14); energetic, clear, exciting, never babyish",
    "voice": "auto-youthful-male",
    "target_seconds": 65,
    "trend_weight": 70,
    "evergreen_weight": 20,
    "experiment_weight": 10,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    now = utc_now()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                niche TEXT NOT NULL,
                requested_topic TEXT,
                selected_topic TEXT,
                content_type TEXT NOT NULL DEFAULT 'auto',
                story_genre TEXT NOT NULL DEFAULT 'auto',
                voice TEXT NOT NULL,
                target_seconds INTEGER NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                manifest_json TEXT,
                output_path TEXT,
                approved INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS channel_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                channel_name TEXT NOT NULL,
                niche TEXT NOT NULL,
                tone TEXT NOT NULL,
                audience TEXT NOT NULL DEFAULT 'Kids / young Roblox players (roughly 8-14); energetic, clear, exciting, never babyish',
                voice TEXT NOT NULL,
                target_seconds INTEGER NOT NULL,
                trend_weight INTEGER NOT NULL,
                evergreen_weight INTEGER NOT NULL,
                experiment_weight INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS radar_runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                radar_run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                reason TEXT NOT NULL,
                score REAL NOT NULL,
                youtube_score REAL NOT NULL,
                recency_score REAL NOT NULL,
                curiosity_score REAL NOT NULL,
                channel_fit_score REAL NOT NULL,
                duplicate_risk REAL NOT NULL,
                evidence_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS generated_images (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                prompt TEXT NOT NULL,
                headline TEXT NOT NULL,
                aspect TEXT NOT NULL,
                output_path TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS media_jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                output_path TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_topics_score ON topics(score DESC);
            """
        )
        job_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "content_type" not in job_columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN content_type TEXT NOT NULL DEFAULT 'auto'")
        if "story_genre" not in job_columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN story_genre TEXT NOT NULL DEFAULT 'auto'")

        profile_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(channel_profile)").fetchall()
        }
        if "audience" not in profile_columns:
            conn.execute(
                "ALTER TABLE channel_profile ADD COLUMN audience TEXT NOT NULL DEFAULT "
                "'Kids / young Roblox players (roughly 8-14); energetic, clear, exciting, never babyish'"
            )

        if not conn.execute("SELECT id FROM channel_profile WHERE id = 1").fetchone():
            conn.execute(
                """
                INSERT INTO channel_profile (
                    id, channel_name, niche, tone, audience, voice, target_seconds,
                    trend_weight, evergreen_weight, experiment_weight, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_PROFILE["channel_name"], DEFAULT_PROFILE["niche"], DEFAULT_PROFILE["tone"],
                    DEFAULT_PROFILE["audience"], DEFAULT_PROFILE["voice"], DEFAULT_PROFILE["target_seconds"], DEFAULT_PROFILE["trend_weight"],
                    DEFAULT_PROFILE["evergreen_weight"], DEFAULT_PROFILE["experiment_weight"], now,
                ),
            )
        conn.execute(
            "UPDATE channel_profile SET voice=? WHERE id=1 AND voice=?",
            ("auto-youthful-male", "en-AU-WilliamNeural"),
        )
        # Story Studio V2.1 defaults to fuller ~65 second mini-movies.
        # Upgrade only old/default-length profiles; preserve deliberate 70/75 choices.
        conn.execute(
            "UPDATE channel_profile SET target_seconds=65 WHERE id=1 AND target_seconds<=58"
        )
        conn.execute(
            """
            UPDATE channel_profile
            SET channel_name='Roblox Stories',
                niche='Cinematic Roblox mini-movies, relatable gameplay situations, mysteries, horror, funny twists and player stories',
                tone='Cinematic, fast and relatable Roblox mini-movies; engaging but never babyish or cringe'
            WHERE id=1
              AND channel_name='Roblox Radar'
              AND niche='Roblox trends, updates, secrets and viral games'
            """
        )


def create_job(job: dict[str, Any]) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, created_at, updated_at, channel_name, niche, requested_topic,
                content_type, story_genre, voice, target_seconds, status, stage, progress
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["id"], now, now, job["channel_name"], job["niche"],
                job.get("requested_topic"), job.get("content_type", "auto"),
                job.get("story_genre", "auto"), job["voice"], job["target_seconds"],
                "queued", "Queued", 0,
            ),
        )


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)


def set_manifest(job_id: str, manifest: dict[str, Any], output_path: str | None = None) -> None:
    update_job(job_id, manifest_json=json.dumps(manifest, ensure_ascii=False), output_path=output_path)


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_recent_content_types(limit: int = 6) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT content_type
            FROM jobs
            WHERE status != 'deleted' AND content_type IS NOT NULL
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [str(row["content_type"]) for row in rows if row["content_type"]]


def get_recent_generated_topics(limit: int = 80) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(selected_topic, requested_topic) AS topic
            FROM jobs
            WHERE status != 'deleted' AND COALESCE(selected_topic, requested_topic) IS NOT NULL
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row["topic"] for row in rows if row["topic"]]


def get_channel_profile() -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM channel_profile WHERE id = 1").fetchone()
    return dict(row) if row else dict(DEFAULT_PROFILE)


def save_channel_profile(profile: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """
            UPDATE channel_profile SET
                channel_name=?, niche=?, tone=?, audience=?, voice=?, target_seconds=?,
                trend_weight=?, evergreen_weight=?, experiment_weight=?, updated_at=?
            WHERE id=1
            """,
            (
                profile["channel_name"], profile["niche"], profile["tone"], profile["audience"], profile["voice"],
                profile["target_seconds"], profile["trend_weight"], profile["evergreen_weight"],
                profile["experiment_weight"], utc_now(),
            ),
        )
    return get_channel_profile()


def migrate_default_voice() -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE channel_profile SET voice=? WHERE id=1 AND voice=?",
            ("auto-youthful-male", "en-AU-WilliamNeural"),
        )


def start_radar_run(run_id: str) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO radar_runs (id, created_at, updated_at, status, error) VALUES (?, ?, ?, 'running', NULL)",
            (run_id, now, now),
        )


def finish_radar_run(run_id: str, status: str, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE radar_runs SET status=?, error=?, updated_at=? WHERE id=?",
            (status, error, utc_now(), run_id),
        )


def latest_radar_run() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM radar_runs ORDER BY created_at DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def replace_topics(run_id: str, topics: list[dict[str, Any]]) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute("DELETE FROM topics")
        for item in topics:
            conn.execute(
                """
                INSERT INTO topics (
                    id, radar_run_id, created_at, title, subject, reason, score,
                    youtube_score, recency_score, curiosity_score, channel_fit_score,
                    duplicate_risk, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"], run_id, now, item["title"], item["subject"], item["reason"], item["score"],
                    item["youtube_score"], item["recency_score"], item["curiosity_score"],
                    item["channel_fit_score"], item["duplicate_risk"],
                    json.dumps(item.get("evidence", {}), ensure_ascii=False),
                ),
            )


def list_topics(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM topics ORDER BY score DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
        out.append(item)
    return out


def get_topic(topic_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
    return item


def save_generated_image(image_id: str, prompt: str, headline: str, aspect: str, output_path: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO generated_images (id, created_at, prompt, headline, aspect, output_path) VALUES (?, ?, ?, ?, ?, ?)",
            (image_id, utc_now(), prompt, headline, aspect, output_path),
        )


def list_generated_images(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM generated_images ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def create_media_job(job_id: str, kind: str, prompt: str) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO media_jobs (id, created_at, updated_at, kind, prompt, status, progress) VALUES (?, ?, ?, ?, ?, 'queued', 0)",
            (job_id, now, now, kind, prompt),
        )


def update_media_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key}=?" for key in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE media_jobs SET {assignments} WHERE id=?",
            [*fields.values(), job_id],
        )


def get_media_job(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM media_jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_media_jobs(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM media_jobs WHERE status != 'deleted' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    raw = data.pop("manifest_json", None)
    data["manifest"] = json.loads(raw) if raw else None
    data["approved"] = bool(data.get("approved"))
    return data
