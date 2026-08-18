"""Download PaddleOCR-VL 1.6's local pipeline weights without processing user media."""
from paddleocr import PaddleOCRVL

PaddleOCRVL(pipeline_version="v1.6", device="cpu")
print("PaddleOCR-VL 1.6 model files are ready.")
