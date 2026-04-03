import fitz
import pytesseract
from PIL import Image
import io

MIN_TEXT_THRESHOLD = 500

def is_scanned_pdf(text_length: int) -> bool:
    return text_length < MIN_TEXT_THRESHOLD

def render_pdf_to_images_gen(pdf_path: str, dpi: int = 200):
    """
    Generator to render PDF pages to images one by one to save memory.
    """
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            yield img

def run_ocr_on_images(pdf_path: str) -> tuple[str, int]:
    full_text = ""
    page_count = 0
    for i, img in enumerate(render_pdf_to_images_gen(pdf_path)):
        page_text = pytesseract.image_to_string(img)
        full_text += f"[Page {i+1}]\n{page_text}\n\n"
        page_count += 1
    return full_text, page_count

def clean_ocr_text(text: str) -> str:
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines)

def extract_text_with_ocr(pdf_path: str) -> dict:
    """
    Extracts text from PDF using OCR.
    Returns: {
        "text": str,
        "ocr_used": bool,
        "ocr_char_count": int,
        "ocr_page_count": int,
        "error": str | None
    }
    """
    try:
        # Check if tesseract is available
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        return {
            "text": "",
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "error": "OCR engine not available. Please install Tesseract."
        }
    except Exception as e:
        return {
            "text": "",
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "error": f"OCR initialization failed: {str(e)}"
        }

    try:
        raw_text, page_count = run_ocr_on_images(pdf_path)
        cleaned_text = clean_ocr_text(raw_text)

        char_count = len(cleaned_text)

        if char_count < MIN_TEXT_THRESHOLD:
             return {
                "text": cleaned_text,
                "ocr_used": True,
                "ocr_char_count": char_count,
                "ocr_page_count": page_count,
                "error": "OCR failed: insufficient text extracted from scanned PDF."
            }

        return {
            "text": cleaned_text,
            "ocr_used": True,
            "ocr_char_count": char_count,
            "ocr_page_count": page_count,
            "error": None
        }
    except Exception as e:
        return {
            "text": "",
            "ocr_used": True,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "error": f"OCR processing failed: {str(e)}"
        }
