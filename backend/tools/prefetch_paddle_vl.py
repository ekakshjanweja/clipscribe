"""Download PaddleOCR-VL 1.6's local pipeline weights without processing user media."""
from pathlib import Path
import os

from paddleocr import PaddleOCRVL

PaddleOCRVL(pipeline_version="v1.6", device="cpu")
cache_root = Path(os.environ.get("CLIPSCRIBE_CACHE_DIR", Path(__file__).resolve().parents[2] / ".cache"))
cache_root.mkdir(parents=True, exist_ok=True)
(cache_root / "paddle-vl.ready").touch()
print("PaddleOCR-VL 1.6 model files are ready.")
