"""ClipScribe: a small, local video-to-text app."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import os
import sys
import uuid
from pathlib import Path
from difflib import SequenceMatcher

from flask import Flask, Response, jsonify, request
from db import connection, ensure_schema, public_job

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1_000 * 1024 * 1024  # 1 GB

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "avi", "m4v", "jpg", "jpeg", "png", "heic", "heif", "tif", "tiff", "bmp", "gif"}
ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent
CACHE_ROOT = Path(os.environ.get("CLIPSCRIBE_CACHE_DIR", PROJECT_ROOT / ".cache"))
VISION_SOURCE = ROOT / "tools" / "vision_ocr.swift"
VISION_BINARY = ROOT / ".cache" / "vision_ocr"
PADDLE_WORKER = ROOT / "tools" / "paddle_vl_ocr.py"
PADDLE_PYTHON = Path(os.environ.get("PADDLE_VL_PYTHON", PROJECT_ROOT / ".venv-paddleocr" / "bin" / "python"))
PADDLE_INSTALL_LOG = CACHE_ROOT / "paddle-vl-install.log"
PADDLE_READY_FILE = CACHE_ROOT / "paddle-vl.ready"
UPLOADS = Path(os.environ.get("CLIPSCRIBE_UPLOADS_DIR", "/data/uploads"))
paddle_install: subprocess.Popen[str] | None = None


@app.after_request
def allow_local_frontend(response):
    response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def build_vision_runner() -> Path:
    """Compile the small Apple Vision bridge once, on the local Mac."""
    if VISION_BINARY.exists() and VISION_BINARY.stat().st_mtime >= VISION_SOURCE.stat().st_mtime:
        return VISION_BINARY
    if not shutil.which("swiftc"):
        raise RuntimeError("Apple Swift is required for local Vision OCR.")
    VISION_BINARY.parent.mkdir(exist_ok=True)
    subprocess.run(["swiftc", str(VISION_SOURCE), "-o", str(VISION_BINARY)], check=True, capture_output=True, text=True)
    return VISION_BINARY


def frame_timestamps(video: Path) -> list[float]:
    """Get the presentation timestamp of every decoded video frame."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(video)],
        check=True,
        capture_output=True,
        text=True,
    )
    values = (line.split(",", 1)[0].strip() for line in probe.stdout.splitlines())
    return [float(value) for value in values if value and value != "N/A"]


def run_paddle_vl(frames: Path, timestamps: Path) -> list[dict[str, str]]:
    """Use PaddleOCR-VL 1.6 from its dedicated local environment."""
    if not PADDLE_PYTHON.is_file():
        raise RuntimeError(
            "PaddleOCR-VL is not installed yet. Run ./scripts/install-paddle-vl.sh, then try again."
        )
    output = subprocess.run(
        [str(PADDLE_PYTHON), str(PADDLE_WORKER), str(frames), str(timestamps)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(output.stdout)


def normalize_for_comparison(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def clean_ocr_block(text: str) -> str:
    """Remove only obvious consecutive OCR repeats without rewriting the content."""
    clean_lines: list[str] = []
    previous_line = ""
    for line in text.splitlines() or [text]:
        words = line.split()
        kept: list[str] = []
        previous_word = ""
        for word in words:
            normalized = normalize_for_comparison(word)
            if normalized and normalized == previous_word:
                continue
            kept.append(word)
            previous_word = normalized
        cleaned = " ".join(kept).strip()
        line_key = normalize_for_comparison(cleaned)
        if cleaned and line_key != previous_line:
            clean_lines.append(cleaned)
            previous_line = line_key
    return "\n".join(clean_lines)


def clean_transcript(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse near-identical OCR blocks repeated across neighbouring video frames."""
    cleaned_rows: list[dict[str, str]] = []
    previous = ""
    for row in rows:
        text = clean_ocr_block(row["text"])
        normalized = normalize_for_comparison(text)
        if not normalized:
            continue
        similarity = SequenceMatcher(None, previous, normalized).ratio() if previous else 0
        if normalized == previous or similarity >= 0.96:
            continue
        cleaned_rows.append({**row, "text": text})
        previous = normalized
    return cleaned_rows


def paddle_is_ready() -> bool:
    if not PADDLE_PYTHON.is_file():
        return False
    check = subprocess.run(
        [str(PADDLE_PYTHON), "-c", "from paddleocr import PaddleOCRVL"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return check.returncode == 0 and PADDLE_READY_FILE.exists()


@app.get("/models")
def models():
    installing = paddle_install is not None and paddle_install.poll() is None
    log = PADDLE_INSTALL_LOG.read_text(encoding="utf-8", errors="replace")[-1200:] if PADDLE_INSTALL_LOG.exists() else ""
    return jsonify(models=[
        {"id": "apple-vision", "name": "Apple Vision", "description": "Built into macOS. No download needed.", "status": "ready" if sys.platform == "darwin" else "unavailable", "size": "native"},
        {"id": "paddle-vl", "name": "PaddleOCR-VL 1.6", "description": "Advanced local layout, table, and document OCR.", "status": "installing" if installing else ("ready" if paddle_is_ready() else "not-installed"), "size": "downloads model files on first setup", "log": log},
    ])


@app.post("/models/paddle-vl/install")
def install_paddle_vl():
    global paddle_install
    if paddle_install is not None and paddle_install.poll() is None:
        return jsonify(status="installing"), 202
    PADDLE_INSTALL_LOG.parent.mkdir(exist_ok=True)
    log_handle = PADDLE_INSTALL_LOG.open("w", encoding="utf-8")
    command = [str(PADDLE_PYTHON), str(ROOT / "tools" / "prefetch_paddle_vl.py")] if os.environ.get("CLIPSCRIBE_DOCKER") else ["/bin/bash", "-lc", "./backend/scripts/install-paddle-vl.sh && .venv-paddleocr/bin/python backend/tools/prefetch_paddle_vl.py"]
    paddle_install = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT, stdout=log_handle, stderr=subprocess.STDOUT, text=True,
    )
    return jsonify(status="installing"), 202


@app.get("/")
def index():
    return jsonify(name="ClipScribe OCR API", status="ok")


@app.get("/health")
def health():
    return jsonify(status="ok")


def valid_upload():
    video = request.files.get("video")
    if not video or not video.filename:
        return None, jsonify(error="Choose a video file first."), 400
    if "." not in video.filename or video.filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return None, jsonify(error="Supported formats: common video files plus JPG, PNG, HEIC, TIFF, BMP, and GIF images."), 400
    return video, None, None


@app.post("/jobs")
def create_job():
    video, error, status = valid_upload()
    if error:
        return error, status
    engine = request.form.get("engine", "paddle-vl")
    if engine not in {"vision", "paddle-vl"}:
        return jsonify(error="Choose a supported OCR engine."), 400
    if engine == "vision" and sys.platform != "darwin":
        return jsonify(error="Apple Vision is only available on macOS. Choose PaddleOCR-VL."), 400
    job_id = uuid.uuid4()
    extension = video.filename.rsplit(".", 1)[1].lower()
    UPLOADS.mkdir(parents=True, exist_ok=True)
    destination = UPLOADS / f"{job_id}.{extension}"
    video.save(destination)
    try:
        ensure_schema()
        with connection() as conn:
            row = conn.execute(
                "INSERT INTO jobs (id, filename, engine) VALUES (%s, %s, %s) RETURNING *",
                (str(job_id), video.filename, engine),
            ).fetchone()
        return jsonify(job=public_job(row)), 202
    except Exception:
        destination.unlink(missing_ok=True)
        app.logger.exception("Could not create OCR job")
        return jsonify(error="The local job queue is unavailable. Please try again."), 503


@app.get("/jobs/<job_id>")
def get_job(job_id: str):
    try:
        ensure_schema()
        with connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
    except Exception:
        app.logger.exception("Could not read OCR job")
        return jsonify(error="The local job queue is unavailable. Please try again."), 503
    if not row:
        return jsonify(error="This OCR job no longer exists."), 404
    return jsonify(job=public_job(row))


@app.get("/jobs/<job_id>/download/<extension>")
def download_job(job_id: str, extension: str):
    if extension not in {"txt", "md"}:
        return jsonify(error="Choose txt or md."), 400
    with connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
    if not row or row["status"] != "complete":
        return jsonify(error="The transcript is not ready yet."), 409
    result = row["result"]
    segments = result["segments"]
    content = "\n\n".join(f"[{segment['start']}] {segment['text']}" for segment in segments) if extension == "txt" else "# ClipScribe clean transcript\n\n" + "\n\n".join(f"## {segment['start']}\n\n{segment['text']}" for segment in segments)
    return Response(content, mimetype=f"text/{'plain' if extension == 'txt' else 'markdown'}; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="clipscribe-{job_id}.{extension}"'})


@app.post("/scan")
def scan():
    video = request.files.get("video")
    engine = request.form.get("engine", "vision")
    if not video or not video.filename:
        return jsonify(error="Choose a video file first."), 400
    if "." not in video.filename or video.filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return jsonify(error="Supported formats: common video files plus JPG, PNG, HEIC, TIFF, BMP, and GIF images."), 400
    if not shutil.which("ffmpeg"):
        return jsonify(error="FFmpeg is not installed or is not on your PATH."), 500
    if engine not in {"vision", "paddle-vl"}:
        return jsonify(error="Choose a supported OCR engine."), 400
    if engine == "vision" and sys.platform != "darwin":
        return jsonify(error="Apple Vision is only available on macOS. Choose PaddleOCR-VL."), 400

    with tempfile.TemporaryDirectory(prefix="clipscribe-") as temp_dir:
        source = Path(temp_dir) / f"source.{video.filename.rsplit('.', 1)[1].lower()}"
        frames = Path(temp_dir) / "frames"
        timestamps_file = Path(temp_dir) / "timestamps.json"
        frames.mkdir()
        video.save(source)

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-vf", "scale='min(1920,iw)':-2", "-q:v", "2", "-fps_mode", "passthrough", str(frames / "frame_%012d.jpg")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            timestamps = frame_timestamps(source)
            timestamps_file.write_text(json.dumps(timestamps), encoding="utf-8")
            if engine == "paddle-vl":
                rows = run_paddle_vl(frames, timestamps_file)
                engine_label = "PaddleOCR-VL 1.6 · local CPU"
            else:
                output = subprocess.run([str(build_vision_runner()), str(frames), str(timestamps_file)], check=True, capture_output=True, text=True)
                rows = json.loads(output.stdout)
                engine_label = "Apple Vision · on device"
        except subprocess.CalledProcessError:
            return jsonify(error="We couldn't read frames from that video."), 422
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        except Exception as exc:  # keeps the API response useful while logging server-side detail
            app.logger.exception("OCR scan failed")
            return jsonify(error=f"Local OCR failed: {exc}"), 500

    clean_rows = clean_transcript(rows)
    text = "\n\n".join(row["text"] for row in clean_rows)
    return jsonify(
        text=text,
        segments=clean_rows,
        raw_segments=rows,
        language=engine_label,
        duration=rows[-1]["end"] if rows else "00:00:00",
        frames_processed=len(timestamps),
        cleaned_blocks=len(clean_rows),
    )


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify(error="That file is over the 1 GB limit. Trim it first, then try again."), 413


if __name__ == "__main__":
    app.run(debug=False, port=5001)
