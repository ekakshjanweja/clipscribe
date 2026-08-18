"""PaddleOCR-VL 1.6 adapter: frames directory -> timestamped text JSON."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from paddleocr import PaddleOCRVL


def timestamp(seconds: float) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{int(hours):02}:{int(minutes):02}:{seconds:05.2f}"


def main() -> None:
    frames = sorted(Path(sys.argv[1]).glob("*.jpg"))
    timestamps = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    pipeline = PaddleOCRVL(pipeline_version="v1.6", device="cpu")
    rows: list[dict[str, str]] = []

    # One frame at a time keeps each result mapped to its video timestamp.
    for index, frame in enumerate(frames):
        with tempfile.TemporaryDirectory(prefix="clipscribe-paddle-") as output_dir:
            result = next(iter(pipeline.predict(str(frame))))
            result.save_to_markdown(save_path=output_dir)
            markdown_files = list(Path(output_dir).rglob("*.md"))
            text = "\n".join(path.read_text(encoding="utf-8").strip() for path in markdown_files).strip()
        if not text:
            continue
        start = timestamps[index] if index < len(timestamps) else float(index)
        end = timestamps[index + 1] if index + 1 < len(timestamps) else start
        rows.append({"start": timestamp(start), "end": timestamp(end), "text": text})

    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
