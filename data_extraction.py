import os
import pdfplumber
from pdf2image import convert_from_path
import logging

# Removed PaddleOCR and Tesseract to reduce app size and dependencies.
# This system now relies entirely on AWS Textract for high-accuracy OCR.

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Standard text-based PDF extraction using pdfplumber.
    """
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        logger.error(f"pdfplumber failed for {pdf_path}: {e}")

    return text.strip()

def extract_first_page_preview(file_path: str) -> str:
    """
    Quickly extracts a text snippet from the first page only.
    Used for classification. No OCR fallback for speed.
    """
    if not os.path.exists(file_path): return ""
    
    file_lower = file_path.lower()
    text = ""
    
    try:
        if file_lower.endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf:
                if pdf.pages:
                    text = pdf.pages[0].extract_text() or ""
            
            # If text is too short, it might be scanned, try Textract for preview
            if len(text.strip()) < 50:
                from textract_extraction import extract_text_with_textract
                # We use a shortcut: extract one page via detect_document_text
                text = extract_text_with_textract(file_path, category="preview")
        
        elif file_lower.endswith((".png", ".jpg", ".jpeg")):
            from textract_extraction import extract_text_with_textract
            text = extract_text_with_textract(file_path, category="preview")
            
    except Exception as e:
        logger.error(f"Preview extraction failed for {file_path}: {e}")
        
    return text[:2500].strip()
