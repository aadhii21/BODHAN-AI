import sys
from pathlib import Path
from functools import lru_cache

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "indic-ocr"
sys.path.insert(0, str(MODEL_PATH))

from indic_ocr import IndicOCR


@lru_cache(maxsize=1)
def load_ocr_model() -> IndicOCR:
    # No CUDA on macOS -- IndicOCR defaults to device="cuda", which raises
    # "Torch not compiled with CUDA enabled" as soon as the layout model loads.
    return IndicOCR.from_pretrained(str(MODEL_PATH), device="mps")