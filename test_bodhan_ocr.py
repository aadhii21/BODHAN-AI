import sys
from huggingface_hub import snapshot_download

# Download the Bodhan OCR repository
repo = snapshot_download("bodhan-ai/indic-ocr")

# Add repository path to Python import path
sys.path.insert(0, repo)

# Import OCR class
from indic_ocr import IndicOCR

# Load the OCR model
parser = IndicOCR.from_pretrained(repo)

# Process birth certificate
page = parser.parse("birth_certificate.png")

# Print extracted text
print(page["markdown"])