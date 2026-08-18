"""Background worker: claims queued OCR jobs from PostgreSQL."""

from __future__ import annotations

import json
import time
from pathlib import Path

from app import ALLOWED_EXTENSIONS, clean_transcript, frame_timestamps, run_paddle_vl
from db import connection, ensure_schema

UPLOADS = Path("/data/uploads")


def update(job_id: str, progress: int, stage: str) -> None:
    with connection() as conn:
        conn.execute("UPDATE jobs SET progress=%s, stage=%s, updated_at=now() WHERE id=%s", (progress, stage, job_id))


def claim() -> dict | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("UPDATE jobs SET status='processing', progress=5, stage='Preparing upload', updated_at=now() WHERE id=%s", (row["id"],))
            return row


def process(job: dict) -> dict:
    job_id = str(job["id"])
    source = next(UPLOADS.glob(f"{job_id}.*"), None)
    if not source:
        raise RuntimeError("The uploaded file is no longer available.")
    if job["engine"] != "paddle-vl":
        raise RuntimeError("Apple Vision is unavailable on the Linux homelab. Choose PaddleOCR-VL.")

    import shutil
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="clipscribe-job-") as temp_dir:
        frames = Path(temp_dir) / "frames"
        timestamps_file = Path(temp_dir) / "timestamps.json"
        frames.mkdir()
        update(job_id, 15, "Extracting frames")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-vf", "scale='min(1920,iw)':-2", "-q:v", "2", "-fps_mode", "passthrough", str(frames / "frame_%012d.jpg")],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("We couldn't read frames from that file.") from exc
        timestamps = frame_timestamps(source)
        timestamps_file.write_text(json.dumps(timestamps), encoding="utf-8")
        update(job_id, 35, f"Reading {len(timestamps)} frames")
        rows = run_paddle_vl(frames, timestamps_file)
        update(job_id, 90, "Cleaning transcript")

    clean_rows = clean_transcript(rows)
    return {
        "text": "\n\n".join(row["text"] for row in clean_rows),
        "segments": clean_rows,
        "raw_segments": rows,
        "language": "PaddleOCR-VL 1.6 · local CPU",
        "duration": rows[-1]["end"] if rows else "00:00:00",
        "frames_processed": len(timestamps),
        "cleaned_blocks": len(clean_rows),
    }


def run() -> None:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    ensure_schema()
    with connection() as conn:
        conn.execute("UPDATE jobs SET status='queued', progress=0, stage='Queued after restart', updated_at=now() WHERE status='processing'")
    while True:
        job = claim()
        if not job:
            time.sleep(1)
            continue
        job_id = str(job["id"])
        try:
            result = process(job)
            with connection() as conn:
                conn.execute("UPDATE jobs SET status='complete', progress=100, stage='Transcript ready', result=%s::jsonb, updated_at=now() WHERE id=%s", (json.dumps(result), job_id))
        except Exception as exc:
            with connection() as conn:
                conn.execute("UPDATE jobs SET status='failed', stage='Could not finish', error=%s, updated_at=now() WHERE id=%s", (str(exc), job_id))
        finally:
            for source in UPLOADS.glob(f"{job_id}.*"):
                source.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
