
import os
import io
import logging
import boto3
import sys
import json
from PIL import Image
from pdf2image import convert_from_path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration & Clients ---

def mask_key(key):
    if not key: return "None"
    return f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"

def get_textract_client():
    """
    Initializes and returns a boto3 Textract client.
    Reads credentials directly from environment to ensure they are fresh.
    """
    load_dotenv(override=True)
    
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1").strip()

    # logger.info(f"Connecting to Textract in {region}...")
    # logger.info(f"Using Access Key: {mask_key(access_key)}")

    return boto3.client(
        'textract',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        region_name=region
    )

def call_textract_id(client, image_bytes):
    return client.analyze_id(DocumentPages=[{'Bytes': image_bytes}])

def call_analyze_document(client, image_bytes):
    return client.analyze_document(
        Document={"Bytes": image_bytes},
        FeatureTypes=["FORMS"]
    )

# --- Orientation Logic (From Image Orientation) ---

def detect_orientation_by_text_pil(image: Image.Image) -> int:
    """
    Detects orientation by trying OCR at different angles using Textract.
    Returns the angle with maximum text detection.
    """
    try:
        client = get_textract_client()
        scores = {}
        
        logger.info("Detecting orientation using text analysis...")
        
        for angle in [0, 90, 180, 270]:
            try:
                # Rotate image
                if angle != 0:
                    test_img = image.rotate(-angle, expand=True)
                else:
                    test_img = image
                
                # Convert to bytes
                img_byte_arr = io.BytesIO()
                test_img.save(img_byte_arr, format='JPEG', quality=85)
                image_bytes = img_byte_arr.getvalue()
                
                # Quick Textract detection
                response = client.detect_document_text(Document={'Bytes': image_bytes})
                
                blocks = response.get('Blocks', [])
                lines = [b for b in blocks if b.get('BlockType') == 'LINE']
                
                # Scoring Logic
                avg_confidence = sum(b.get('Confidence', 0) for b in lines) / max(len(lines), 1)
                score = avg_confidence / 2
                
                # Bonus 1: Portrait Mode
                width, height = test_img.size
                if height > width:
                    score += 50
                
                # Bonus 2: Layout Heuristics - Strict MRZ Check
                keyword_bonus = 0
                for line in lines:
                    text = line.get('Text', '').upper()
                    bbox = line.get('Geometry', {}).get('BoundingBox', {})
                    top = bbox.get('Top', 0)
                    
                    if "PASSPORT" in text and top < 0.5:
                        keyword_bonus += 20
                    
                    if "<<" in text and len(text) > 10:
                        if top > 0.5:
                            keyword_bonus += 200 # Massive bonus for MRZ at bottom
                        else:
                            keyword_bonus -= 100 # Penalty for MRZ at top
                
                score += keyword_bonus
                scores[angle] = score
                
                logger.debug(f"Angle {angle}°: Score={score:.1f}")
                
            except Exception as e:
                logger.warning(f"Error testing angle {angle}°: {e}")
                scores[angle] = -999
                continue
        
        best_angle = max(scores, key=scores.get)
        max_score = scores[best_angle]
        original_score = scores.get(0, 0)
        
        if best_angle != 0 and (max_score - original_score) > 10:
            logger.info(f"Best orientation is {best_angle}° (Score: {max_score:.1f})")
            return best_angle
        
        return 0
        
    except Exception as e:
        logger.error(f"Text-based orientation detection failed: {e}")
        return 0

def auto_correct_image_orientation(image: Image.Image) -> Image.Image:
    try:
        # Step 1: EXIF
        angle = 0
        try:
            exif = image.getexif()
            if exif:
                orientation = exif.get(274, 1)
                orientation_map = {1: 0, 3: 180, 6: 270, 8: 90}
                angle = orientation_map.get(orientation, 0)
        except:
            pass
        
        # Step 2: Text-based if EXIF is 0
        if angle == 0:
            angle = detect_orientation_by_text_pil(image)
        
        # Step 3: Rotate
        if angle != 0:
            corrected = image.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
            logger.info(f"Corrected orientation: {angle}°")
            return corrected
        
        return image
    except Exception as e:
        logger.error(f"Orientation correction failed: {e}")
        return image

# --- Parsing & Scoring Logic ---

def score_passport_page(data):
    if not data: return 0
    score = 0
    if data.get('ID_TYPE', {}).get('value') == 'PASSPORT': score += 50
    if data.get('EXPIRATION_DATE', {}).get('value'): score += 20
    if data.get('DATE_OF_BIRTH', {}).get('value'): score += 20
    if data.get('MRZ_CODE', {}).get('value'): score += 100
    return score

def parse_passport_mrz(mrz_string: str) -> dict:
    if not mrz_string: return {}
    lines = [line.strip().upper() for line in mrz_string.split('\n') if line.strip()]
    if not lines or len(lines) < 1: return {}
    
    line1 = lines[0]
    if not line1.startswith('P'): return {}
    
    country_code = line1[2:5].replace('<', '')
    name_part = line1[5:]
    
    if '<<' in name_part:
        parts = name_part.split('<<', 1)
        surname = parts[0].replace('<', ' ').strip()
        given_names = parts[1].replace('<', ' ').strip() if len(parts) > 1 else ""
    else:
        surname = name_part.replace('<', ' ').strip()
        given_names = ""
        
    return {
        "COUNTRY_CODE": country_code,
        "SURNAME": surname,
        "GIVEN_NAMES": given_names,
        "FULL_NAME": f"{given_names} {surname}".strip()
    }

def parse_analyze_id_response(response):
    extracted = {}
    mrz_code = None
    
    for doc in response.get("IdentityDocuments", []):
        for field in doc.get("IdentityDocumentFields", []):
            key = field["Type"]["Text"]
            value = field.get("ValueDetection", {}).get("Text", "")
            extracted[key] = {"value": value}
            if key == "MRZ_CODE":
                mrz_code = value

    if mrz_code:
        mrz_data = parse_passport_mrz(mrz_code)
        if mrz_data:
            extracted["MRZ_PARSED_NAME"] = {"value": mrz_data.get("FULL_NAME")}
            extracted["COUNTRY_CODE"] = {"value": mrz_data.get("COUNTRY_CODE")}
            if mrz_data.get("SURNAME"): extracted["SURNAME"] = {"value": mrz_data.get("SURNAME")}
            if mrz_data.get("GIVEN_NAMES"): extracted["FIRST_NAME"] = {"value": mrz_data.get("GIVEN_NAMES")}
                
    return extracted

def extract_mrz_lines(blocks):
    candidates = []
    for block in blocks:
        if block["BlockType"] == "LINE":
            text = block.get("Text", "").replace(" ", "")
            if len(text) >= 40 and "<<" in text:
                candidates.append(text)
    if len(candidates) >= 2:
        return candidates[-2], candidates[-1]
    return None

def parse_mrz(mrz_lines):
    line1, line2 = mrz_lines
    return {
        "document_type": "PASSPORT",
        "passport_number": line2[0:9].replace("<", ""),
        "nationality": line2[10:13],
        "date_of_birth": line2[13:19],
        "expiry_date": line2[21:27],
        "surname": line1[5:].split("<<")[0].replace("<", " ").strip(),
        "given_names": line1.split("<<")[1].replace("<", " ").strip(),
        "mrz": f"{line1}\n{line2}",
        "source": "MRZ_Fallback",
    }

def mrz_basic_valid(mrz_lines):
    return len(mrz_lines[0]) == 44 and len(mrz_lines[1]) == 44

# --- Extraction Functions ---

def extract_text_with_textract(file_path: str):
    """
    Primary Method: Use analyze_id
    """
    try:
        if not os.path.exists(file_path): return []
        client = get_textract_client()
        file_lower = file_path.lower()
        all_pages_results = []

        if file_lower.endswith(".pdf"):
            images = convert_from_path(file_path, dpi=200)
            for i, img in enumerate(images):
                img = auto_correct_image_orientation(img)
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
                image_bytes = img_byte_arr.getvalue()

                response = call_textract_id(client, image_bytes)
                
                if not response.get("IdentityDocuments"):
                    continue
                    
                data = parse_analyze_id_response(response)
                # Fallback text
                data['raw_text'] = "\n".join([b['Text'] for b in response.get('Blocks', []) if b['BlockType'] == 'LINE'])
                data['score'] = score_passport_page(data)
                
                all_pages_results.append(data)
                
        return all_pages_results

    except Exception as e:
        logger.error(f"Analyze ID error: {e}")
        return []

def extract_passport_universal(file_path):
    """
    Fallback Method: Use analyze_document (FORMS) + Manual MRZ Parsing
    """
    try:
        textract = get_textract_client()
        file_lower = file_path.lower()
        
        if file_lower.endswith(".pdf"):
            images = convert_from_path(file_path, dpi=200)
            for img in images:
                img = auto_correct_image_orientation(img)
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
                image_bytes = img_byte_arr.getvalue()

                response = call_analyze_document(textract, image_bytes)
                blocks = response.get("Blocks", [])
                mrz_lines = extract_mrz_lines(blocks)

                if mrz_lines and mrz_basic_valid(mrz_lines):
                    logger.info("Universal extraction found valid MRZ")
                    return parse_mrz(mrz_lines)
                    
    except Exception as e:
        logger.error(f"Universal extraction error: {e}")

    return {"error": "MRZ not detected", "action": "Manual review required"}

# --- Orchestrator ---

def analyze_doc(file_path: str):
    """
    Hybrid extraction strategy:
    1. Try analyze_id (best for identity fields)
    2. If MRZ not clearly found, fallback to analyze_document (universal)
    """
    logger.info(f"Analyzing: {file_path}")
    
    # 1. Try Primary (Analyze ID)
    results = extract_text_with_textract(file_path)
    
    # Check if any page yielded a valid result with MRZ
    for page_data in results:
        mrz_val = page_data.get('MRZ_CODE', {}).get('value', '')
        if "P<" in mrz_val and "<<" in mrz_val:
            logger.info("✅ AnalyzeID Successful")
            return page_data
            
    logger.warning("AnalyzeID unclear. Switching to Universal Fallback...")
    
    # 2. Try Fallback (Universal)
    return extract_passport_universal(file_path)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        result = analyze_doc(test_file)
        print(json.dumps(result, indent=2, default=str))
    else:
        # Default test path from user request
        default_path = "/Users/pawanpandey/Documents/document-validation/data/Daniel Jonathan _France/Passport.pdf"
        result = analyze_doc(default_path)
        print(json.dumps(result, indent=2, default=str))