import boto3
import os
import logging
from dotenv import load_dotenv
import io
from PIL import Image
from pdf2image import convert_from_path

# Load environment variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

def mask_key(key):
    if not key: return "None"
    return f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"

# initialize the textract client
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


# passport extraction
def extract_passport_data(image_bytes):

    client = get_textract_client()
    response = client.analyze_id(
        DocumentPages=[
            {
                "Bytes": image_bytes
            }
        ]
    )

    extracted_data = {}

    for doc in response["IdentityDocuments"]:
        for field in doc["IdentityDocumentFields"]:
            key = field["Type"]["Text"]
            value = field.get("ValueDetection", {}).get("Text", "")
            # confidence = field["Confidence"]

            extracted_data[key] = {
                "value": value,
                # "confidence": confidence
            }

    return extracted_data



def sending_img_byte(file_path):

    extracted_data = []
    file_lower = file_path.lower()
    if file_lower.endswith(".pdf"):
        logger.info(f"Converting PDF to images for Textract: {file_path}")
        # Convert PDF to list of PIL images
        images = convert_from_path(file_path, dpi=300) # 200 DPI is usually enough for OCR
        
        for i, img in enumerate(images):
            # Convert PIL image to bytes
            img_byte_arr = io.BytesIO()
            # Use JPEG with optimization to stay under 5MB Textract limit
            img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
            image_bytes = img_byte_arr.getvalue()
            print("page")
            data = extract_passport_data(image_bytes)
            print(data,"data")
            extracted_data.append(data)

    # print(extracted_data,"extracted_data")
    
    return extracted_data


if __name__ == "__main__":
    data = sending_img_byte("/Users/pawanpandey/Documents/document-validation/data/Daniel Jonathan _France/Passport.pdf")
    print(data)




