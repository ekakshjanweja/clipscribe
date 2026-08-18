FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PADDLE_VL_PYTHON=/usr/local/bin/python CLIPSCRIBE_DOCKER=1 CLIPSCRIBE_CACHE_DIR=/app/.cache

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libgomp1 tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir paddlepaddle==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
    && pip install --no-cache-dir "paddleocr[doc-parser]" gunicorn
COPY backend /app
EXPOSE 5001
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "0", "--bind", "0.0.0.0:5001", "app:app"]
