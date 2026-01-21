import boto3
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

def mask_key(key):
    if not key: return "None"
    return f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"

def get_textract_client():
    """
    Initializes and returns a boto3 Textract client.
    Reads credentials directly from environment to ensure they are fresh.
    """
    # Force reload of .env to pick up manual changes without restarting process
    load_dotenv(override=True)
    
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1").strip()

    logger.info(f"Connecting to Textract in {region}...")
    logger.info(f"Using Access Key: {mask_key(access_key)}")
    logger.info(f"Using Session Token: {'YES' if session_token else 'NO'}")

    return boto3.client(
        'textract',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        region_name=region
    )

import io
from PIL import Image
from pdf2image import convert_from_path

def extract_text_with_textract(file_path: str) -> str:
    """
    Extracts text from an image or PDF using AWS Textract.
    For PDFs, it converts pages to images locally first, as Textract's 
    Synchronous API only supports PDF bytes when stored in S3.
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return ""

        client = get_textract_client()
        file_lower = file_path.lower()
        all_text = []

        # Case 1: PDF Files (Must be converted to images for synchronous local processing)
        if file_lower.endswith(".pdf"):
            logger.info(f"Converting PDF to images for Textract: {file_path}")
            # Convert PDF to list of PIL images
            images = convert_from_path(file_path, dpi=200) # 200 DPI is usually enough for OCR
            
            for i, img in enumerate(images):
                # Convert PIL image to bytes
                img_byte_arr = io.BytesIO()
                # Use JPEG with optimization to stay under 5MB Textract limit
                img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
                image_bytes = img_byte_arr.getvalue()

                logger.info(f"Processing page {i+1}/{len(images)} via Textract...")
                response = client.detect_document_text(Document={'Bytes': image_bytes})
                
                for item in response.get('Blocks', []):
                    if item.get('BlockType') == 'LINE':
                        all_text.append(item.get('Text', ""))

        # Case 2: Image Files (Directly supported)
        else:
            with open(file_path, 'rb') as document:
                image_binary = document.read()

            response = client.detect_document_text(Document={'Bytes': image_binary})
            for item in response.get('Blocks', []):
                if item.get('BlockType') == 'LINE':
                    all_text.append(item.get('Text', ""))

        print(all_text,"all_text")
        print(file_path,"file_path")
        return "\n".join(all_text).strip()

    except Exception as e:
        logger.error(f"AWS Textract error for {file_path}: {str(e)}", exc_info=True)
        return ""

