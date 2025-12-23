# ocr_service.py
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import easyocr
from io import BytesIO
from PIL import Image
import numpy as np
import logging

# -----------------------------
# Logging Configuration
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("OCRService")

# -----------------------------
# OCR Configuration
# -----------------------------
OCR_LANGS = ['en']  # Add 'ar' for Arabic if needed
logger.info("Initializing EasyOCR reader...")
reader = easyocr.Reader(OCR_LANGS, gpu=False)  # Set gpu=True if GPU available
logger.info("EasyOCR reader initialized successfully.")

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(title="OCR Service")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Use specific URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/extract-text/")
async def extract_text(file: UploadFile = File(...)):
    logger.info(f"Received file: {file.filename}")
    try:
        # Read image from memory
        image_bytes = await file.read()
        logger.info(f"Read {len(image_bytes)} bytes from uploaded file.")

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        logger.info(f"Image opened successfully: format={image.format}, size={image.size}, mode={image.mode}")

        # Convert PIL Image to NumPy array
        image_np = np.array(image)
        logger.info(f"Converted image to NumPy array: shape={image_np.shape}, dtype={image_np.dtype}")

        # Run OCR
        results = reader.readtext(image_np, detail=0)
        logger.info(f"OCR completed. Number of text lines detected: {len(results)}")

        lines = [line.strip() for line in results if line.strip()]
        logger.info(f"Returning {len(lines)} cleaned text lines to client.")

        return JSONResponse(content={"text_lines": lines})

    except Exception as e:
        logger.error(f"Error processing file {file.filename}: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

# -----------------------------
# Optional: test route
# -----------------------------
@app.get("/")
def home():
    logger.info("Home route accessed.")
    return {"message": "OCR Service is running!"}
