"""Background workers: claim queued OCR jobs from PostgreSQL.

Jobs are processed in chunks so progress is persisted continuously.
Pause and cancel requests are honored at frame granularity, and partial
results are stored on the job row so they can be watched mid-run. A
paused job keeps its upload and resumes where it stopped.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app import PADDLE_PYTHON, PADDLE_WORKER, clean_transcript, frame_timestamps
from db import connection, ensure_schema

UPLOADS = Path(os.environ.get("CLIPSCRIBE_UPLOADS_DIR", "/data/uploads"))
CHUNK_FRAMES = max(int(os.environ.get("CLIPSCRIBE_CHUNK_FRAMES", "20")), 5)
REQUEUE_AFTER_SECONDS = 180
REAPER_INTERVAL_SECONDS = 60
TERMINATE_GRACE_SECONDS = 15


class JobPaused(Exception):
    pass


class JobCancelled(Exception):
    pass


def timestamp(seconds: float) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{int(hours):02}:{int(minutes):02}:{seconds:05.2f}"


def pct(frames_done: int, frames_total: int) -> int:
    return 35 + int(55 * frames_done / max(frames_total, 1))


def update(job_id: str, progress: int, stage: str) -> None:
    with connection() as conn:
        conn.execute("UPDATE jobs SET progress=%s, stage=%s, updated_at=now() WHERE id=%s", (progress, stage, job_id))


def stripped(rows: list[dict]) -> list[dict]:
    return [{"start": row["start"], "end": row["end"], "text": row["text"]} for row in rows]


def checkpoint(job_id: str, state: dict, label: str, frames_total: int) -> None:
    payload = {
        "rows": stripped(state["rows"]),
        "clean_rows": clean_transcript(stripped(state["rows"])),
        "frames_done": state["frames_done"],
        "frames_total": frames_total,
        "engine_label": label,
    }
    with connection() as conn:
        conn.execute(
            "UPDATE jobs SET partial=%s::jsonb, progress=%s, stage=%s, updated_at=now() WHERE id=%s",
            (json.dumps(payload), pct(state["frames_done"], frames_total), f"{label} frame {state['frames_done']} of {frames_total}", job_id),
        )


def job_status(job_id: str) -> str | None:
    with connection() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id=%s", (job_id,)).fetchone()
    return row["status"] if row else None


def stop_requested(job_id: str) -> str | None:
    status = job_status(job_id)
    if status in {"pause_requested", "cancel_requested"}:
        return status
    return None


def load_state(job: dict) -> dict:
    partial = job.get("partial") or {}
    rows = partial.get("rows") if isinstance(partial, dict) else None
    frames_done = int(partial.get("frames_done", 0)) if isinstance(partial, dict) else 0
    if not isinstance(rows, list) or frames_done < 0:
        rows, frames_done = [], 0
    return {"rows": list(rows), "frames_done": frames_done}


def make_row(index: int, timestamps: list[float], text: str) -> dict:
    start = timestamps[index] if index < len(timestamps) else float(index)
    end = timestamps[index + 1] if index + 1 < len(timestamps) else start
    return {"i": index, "start": timestamp(start), "end": timestamp(end), "text": text}


def ocr_frames_in_process(files: list[Path], timestamps: list[float], recognize, job_id: str, label: str, state: dict) -> None:
    total = len(files)
    for index in range(state["frames_done"], total):
        signal = stop_requested(job_id)
        if signal == "cancel_requested":
            checkpoint(job_id, state, label, total)
            raise JobCancelled()
        if signal == "pause_requested":
            checkpoint(job_id, state, label, total)
            raise JobPaused()
        value = recognize(files[index]).strip()
        if value:
            state["rows"].append(make_row(index, timestamps, value))
        state["frames_done"] = index + 1
        update(job_id, pct(state["frames_done"], total), f"{label} frame {state['frames_done']} of {total}")
        if state["frames_done"] % CHUNK_FRAMES == 0 or state["frames_done"] == total:
            checkpoint(job_id, state, label, total)


def merge_tool_rows(state: dict, raw_rows: list[dict]) -> None:
    known = {row["i"]: row for row in state["rows"]}
    for row in raw_rows:
        index = int(row["frame_index"])
        known[index] = {"i": index, "start": row["start"], "end": row["end"], "text": row["text"]}
    state["rows"] = [known[index] for index in sorted(known)]
    if state["rows"]:
        state["frames_done"] = max(state["frames_done"], state["rows"][-1]["i"] + 1)


def run_paddle_vl_chunked(frames: Path, timestamps_file: Path, timestamps: list[float], job_id: str, label: str, state: dict) -> None:
    total = len(timestamps)
    progress_file = frames.parent / "paddle-progress.json"
    result_file = frames.parent / "paddle-result.json"
    process = subprocess.Popen(
        [str(PADDLE_PYTHON), str(PADDLE_WORKER), str(frames), str(timestamps_file), str(progress_file), str(result_file), str(state["frames_done"])],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
    )
    previous = -1
    last_checkpoint = state["frames_done"]
    while process.poll() is None:
        signal = stop_requested(job_id)
        if signal:
            process.terminate()
            try:
                process.wait(timeout=TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            try:
                merge_tool_rows(state, json.loads(result_file.read_text(encoding="utf-8")))
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            checkpoint(job_id, state, label, total)
            raise JobCancelled() if signal == "cancel_requested" else JobPaused()
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
            done = min(int(progress["done"]), total)
            if done != previous:
                update(job_id, pct(done, total), f"{label} frame {done} of {total}")
                previous = done
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            pass
        try:
            merge_tool_rows(state, json.loads(result_file.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if state["frames_done"] - last_checkpoint >= CHUNK_FRAMES:
            checkpoint(job_id, state, label, total)
            last_checkpoint = state["frames_done"]
        time.sleep(0.5)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, process.args)
    merge_tool_rows(state, json.loads(result_file.read_text(encoding="utf-8")))
    state["frames_done"] = max(state["frames_done"], total)
    checkpoint(job_id, state, label, total)


def run_tesseract(files: list[Path], timestamps: list[float], job_id: str, state: dict) -> None:
    def recognize(frame: Path) -> str:
        return subprocess.run(["tesseract", str(frame), "stdout", "-l", "eng", "--oem", "1", "--psm", "3"], check=True, capture_output=True, text=True).stdout

    ocr_frames_in_process(files, timestamps, recognize, job_id, "Tesseract", state)


def run_paddle_mobile(files: list[Path], timestamps: list[float], job_id: str, state: dict) -> None:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(text_detection_model_name="PP-OCRv5_mobile_det", text_recognition_model_name="en_PP-OCRv5_mobile_rec", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)

    def recognize(frame: Path) -> str:
        result = next(iter(ocr.predict(str(frame))))
        payload = result.json if hasattr(result, "json") else {}
        data = payload.get("res", payload) if isinstance(payload, dict) else {}
        return "\n".join(str(text) for text in data.get("rec_texts", []) if text)

    ocr_frames_in_process(files, timestamps, recognize, job_id, "PaddleOCR Mobile", state)


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
    if job["engine"] not in {"tesseract", "paddle-mobile", "paddle-vl"}:
        raise RuntimeError("Choose a Linux-compatible OCR engine.")

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
        total = len(timestamps)
        state = load_state(job)
        resumed = 0 < state["frames_done"] <= total
        if not resumed:
            state = {"rows": [], "frames_done": 0}
        if job["engine"] == "tesseract":
            label = "Tesseract · local CPU"
        elif job["engine"] == "paddle-mobile":
            label = "PaddleOCR Mobile · local CPU"
        else:
            label = "PaddleOCR-VL 1.6 · local CPU"
        update(job_id, pct(state["frames_done"], total), f"{'Resuming at frame ' + str(state['frames_done'] + 1) + ' of ' if resumed else 'Reading '}{total} frames")
        files = sorted(frames.glob("*.jpg"))
        if job["engine"] == "tesseract":
            run_tesseract(files, timestamps, job_id, state)
        elif job["engine"] == "paddle-mobile":
            run_paddle_mobile(files, timestamps, job_id, state)
        else:
            run_paddle_vl_chunked(frames, timestamps_file, timestamps, job_id, label, state)
        update(job_id, 90, "Cleaning transcript")

    clean_rows = clean_transcript(stripped(state["rows"]))
    return {
        "text": "\n\n".join(row["text"] for row in clean_rows),
        "segments": clean_rows,
        "raw_segments": stripped(state["rows"]),
        "language": label,
        "duration": stripped(state["rows"])[-1]["end"] if state["rows"] else "00:00:00",
        "frames_processed": total,
        "cleaned_blocks": len(clean_rows),
    }


def remove_upload(job_id: str) -> None:
    for source in UPLOADS.glob(f"{job_id}.*"):
        source.unlink(missing_ok=True)


def recover_stale_jobs() -> None:
    with connection() as conn:
        stale = conn.execute(
            "SELECT id FROM jobs WHERE status='processing' AND updated_at < now() - (%s * interval '1 second')",
            (REQUEUE_AFTER_SECONDS,),
        ).fetchall()
        for row in stale:
            conn.execute("UPDATE jobs SET status='queued', progress=0, stage='Requeued', updated_at=now() WHERE id=%s", (row["id"],))
        # Only reap requests a live worker has ignored: a healthy worker honors
        # pause/cancel within a second and touches updated_at every frame, so a
        # fresh request still belongs to it. Reaping unconditionally would race
        # the worker and could flip a cancelled job back to complete.
        cancelling = conn.execute(
            "SELECT id FROM jobs WHERE status='cancel_requested' AND updated_at < now() - (%s * interval '1 second')",
            (REQUEUE_AFTER_SECONDS,),
        ).fetchall()
        for row in cancelling:
            conn.execute("UPDATE jobs SET status='cancelled', stage='Cancelled', updated_at=now() WHERE id=%s", (row["id"],))
        pausing = conn.execute(
            "SELECT id FROM jobs WHERE status='pause_requested' AND updated_at < now() - (%s * interval '1 second')",
            (REQUEUE_AFTER_SECONDS,),
        ).fetchall()
        for row in pausing:
            conn.execute("UPDATE jobs SET status='paused', stage='Paused', updated_at=now() WHERE id=%s", (row["id"],))
    for row in cancelling:
        remove_upload(str(row["id"]))


def mark_paused(job_id: str) -> bool:
    with connection() as conn:
        row = conn.execute(
            "UPDATE jobs SET status='paused', stage='Paused — resume anytime', updated_at=now() WHERE id=%s AND status IN ('processing','pause_requested') RETURNING id",
            (job_id,),
        ).fetchone()
        if row:
            return True
        current = conn.execute("SELECT status FROM jobs WHERE id=%s", (job_id,)).fetchone()
    return current is not None and current["status"] != "cancel_requested"


def start_reaper() -> None:
    def loop() -> None:
        while True:
            time.sleep(REAPER_INTERVAL_SECONDS)
            try:
                recover_stale_jobs()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()


def run() -> None:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    ensure_schema()
    recover_stale_jobs()
    start_reaper()
    while True:
        job = claim()
        if not job:
            time.sleep(1)
            continue
        job_id = str(job["id"])
        try:
            result = process(job)
        except JobPaused:
            if not mark_paused(job_id):
                remove_upload(job_id)
                with connection() as conn:
                    conn.execute("UPDATE jobs SET status='cancelled', stage='Cancelled', updated_at=now() WHERE id=%s", (job_id,))
            continue
        except JobCancelled:
            with connection() as conn:
                conn.execute("UPDATE jobs SET status='cancelled', stage='Cancelled', updated_at=now() WHERE id=%s", (job_id,))
            remove_upload(job_id)
            continue
        except Exception as exc:
            with connection() as conn:
                conn.execute("UPDATE jobs SET status='failed', stage='Could not finish', error=%s, updated_at=now() WHERE id=%s", (str(exc), job_id))
            remove_upload(job_id)
            continue
        with connection() as conn:
            conn.execute(
                "UPDATE jobs SET status='complete', progress=100, stage='Transcript ready', result=%s::jsonb, partial=NULL, updated_at=now() WHERE id=%s",
                (json.dumps(result), job_id),
            )
        remove_upload(job_id)


if __name__ == "__main__":
    run()
