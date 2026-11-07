"""Standalone CPU inference smoke test for IndicOCR -- no weight download, no FastAPI.

Verifies both stages actually run a forward pass on CPU (not just that imports succeed):
  1. layout detection produces blocks without touching CUDA
  2. text recognition transcribes at least one block without touching CUDA

Run: .venv/bin/python test_cpu_inference.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_ROOT / "models" / "indic-ocr"
ASSET = MODEL_PATH / "assets" / "gallery-1-english-math-ramanujan.png"

sys.path.insert(0, str(MODEL_PATH))

import torch

# Fail loudly instead of silently falling back if anything tries to touch CUDA.
_orig_cuda_init = torch.cuda._lazy_init
def _blocked_cuda_init():
    raise AssertionError("CUDA was touched during what should be a CPU-only run")
torch.cuda._lazy_init = _blocked_cuda_init

from indic_ocr import IndicOCR  # noqa: E402

parser = IndicOCR.from_pretrained(str(MODEL_PATH), device="cpu")

print("== stage 1: layout detection ==")
layout = parser.detect(str(ASSET))
print(f"blocks detected: {len(layout['blocks'])}")
assert layout["blocks"], "layout stage returned zero blocks -- nothing to transcribe"
for b in layout["blocks"][:3]:
    print(" ", b["order"], b["type"], b["bbox_xyxy"])

print("== stage 2: text recognition ==")
page = parser.parse(str(ASSET))
transcribed = [b for b in page["blocks"] if b.get("text")]
print(f"blocks with text: {len(transcribed)} / {len(page['blocks'])}")
assert transcribed, "recognizer stage produced no transcribed text"
print("sample text:", transcribed[0]["text"][:200])

print("== model devices ==")
print("layout model device:", next(parser.layout.backend.model.parameters()).device)
print("recognizer model device:", parser.recognizer.backend.model.device)

print("\nOK: both stages ran on CPU with no CUDA calls.")
