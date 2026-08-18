#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if not (hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()) else 1)' >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v "$candidate")"
    break
  fi
done

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "PaddleOCR needs a standard (non-free-threaded) CPython 3.9–3.13 interpreter." >&2
  echo "Install Python 3.11, then run this script again." >&2
  exit 1
fi

if [[ -x .venv-paddleocr/bin/python ]] && ! .venv-paddleocr/bin/python -c 'import sys; raise SystemExit(0 if not (hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()) else 1)'; then
  echo "Existing .venv-paddleocr uses free-threaded Python and cannot run PaddleOCR." >&2
  echo "Rename or remove .venv-paddleocr, then rerun this script." >&2
  exit 1
fi

"$PYTHON_BIN" -m venv .venv-paddleocr
.venv-paddleocr/bin/python -m pip install --upgrade pip
.venv-paddleocr/bin/python -m pip install paddlepaddle==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
.venv-paddleocr/bin/python -m pip install -U "paddleocr[doc-parser]"
echo "PaddleOCR-VL is ready. Restart ClipScribe, select PaddleOCR-VL 1.6, and scan a video."
