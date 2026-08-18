# ClipScribe

Local video and photo OCR with timestamped results. Video frames or a single photo are read by on-device text recognizers, then deleted. There are no API keys or per-minute bills.

## Run it

Prerequisites: macOS, Xcode Command Line Tools (`xcode-select --install`), Python 3.10+, and [FFmpeg](https://ffmpeg.org/download.html).

```bash
cd clipscribe
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Start the OCR API, then the Next.js interface in a second terminal:

```bash
# terminal 1
.venv/bin/python backend/app.py

# terminal 2
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The Next.js dev server proxies `/api/*` to Flask on port 5001. On the first Apple Vision scan, the app compiles a tiny local Swift bridge; there is no model download.

The **Local models** panel in the frontend can download and prepare PaddleOCR-VL 1.6 without using a terminal. The job runs locally, writes a small status log under `.cache/`, and downloads the model weights on your Mac.

## Cost and reliability choices

- **Apple Vision OCR:** native macOS text recognition, $0 per minute, private and reliable for printed/on-screen text.
- **Every-frame extraction:** decodes every video frame and preserves its actual presentation timestamp. This is comprehensive but can be slow for long or high-FPS videos.
- **Clean transcript:** removes consecutive duplicated words/lines and collapses near-identical OCR blocks from adjacent frames without using an LLM to rewrite the detected text.
- **Complete exports:** Download the full timestamped result as `.txt` or `.md` after a scan.
- **FFmpeg frame extraction:** accepts common video formats and sends Vision high-quality JPEG frames.

This is OCR for text visible in the video—not speech transcription. For spoken dialogue, add a separate local Whisper mode later.

## Optional: PaddleOCR-VL 1.6

Select **PaddleOCR-VL 1.6 — advanced layouts** in the app for slides with complex reading order, tables, formulas, or mixed layouts. It remains local, but is far heavier and slower than Apple Vision. Install it separately so the default app stays lightweight:

```bash
./scripts/install-paddle-vl.sh
```

PaddleOCR requires standard CPython (not Python 3.13's free-threaded `3.13t` build). The script automatically prefers a compatible interpreter such as Python 3.11.

The first Paddle run downloads the official model files. Apple Vision remains the recommended option for short clips and simple on-screen text. Paddle’s current Apple Silicon guidance documents local CPU inference and notes that its compatibility validation is on M4 hardware. [Official PaddleOCR-VL Apple Silicon guide](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL-Apple-Silicon.md)
