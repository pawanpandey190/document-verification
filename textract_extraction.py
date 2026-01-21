import boto3
import os
import logging
from dotenv import load_dotenv
from image_orientation import auto_correct_image_orientation

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

def score_passport_page(data):
    """
    Scores a passport page based on presence of MRZ and critical fields.
    """
    if not data: return 0
    score = 0
    
    # 1. Identity Type is the strongest signal
    if data.get('ID_TYPE', {}).get('value') == 'PASSPORT':
        score += 50
    
    # 2. Critical fields (Dates) are only on the main page
    if data.get('EXPIRATION_DATE', {}).get('value'): score += 20
    if data.get('DATE_OF_BIRTH', {}).get('value'): score += 20
    
    # 3. MRZ is the gold standard
    if data.get('MRZ_CODE', {}).get('value'): score += 100
        
    return score


def extract_mrz_lines(blocks):
    """
    Extracts the two MRZ lines (TD3 format) from Textract blocks.
    Works for all countries.
    """
    candidates = []

    for block in blocks:
        if block["BlockType"] == "LINE":
            text = block.get("Text", "").replace(" ", "")
            if len(text) >= 40 and "<<" in text:
                candidates.append(text)

    # MRZ is ALWAYS the last two lines
    if len(candidates) >= 2:
        return candidates[-2], candidates[-1]

    return None

def parse_mrz(mrz_lines):
    """
    Parses ICAO TD3 MRZ format into structured fields.
    """
    line1, line2 = mrz_lines

    return {
        "document_type": "PASSPORT",
        "passport_number": line2[0:9].replace("<", ""),
        "nationality": line2[10:13],
        "date_of_birth": line2[13:19],
        "sex": line2[20],
        "expiry_date": line2[21:27],
        "surname": line1[5:].split("<<")[0].replace("<", " ").strip(),
        "given_names": line1.split("<<")[1].replace("<", " ").strip(),
        "mrz": f"{line1}\n{line2}",
        "source": "MRZ_Fallback",
        "confidence": 0.98
    }

def mrz_basic_valid(mrz_lines):
    return (
        len(mrz_lines[0]) == 44 and
        len(mrz_lines[1]) == 44
    )

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def parse_passport_mrz(mrz_string: str) -> dict:
    """
    Parses a standard ICAO Doc 9303 Type P (Passport) 2-line MRZ.
    Line 1: P<CCC_SURNAME<<GIVEN_NAMES<<<<
    Line 2: DOCUMENT#_CHECKDIGIT_COUNTRY_DOB_CHECKDIGIT_SEX_EXPIRY_CHECKDIGIT_OPTIONAL_CHECKDIGIT
    """
    if not mrz_string:
        return {}
        
    lines = [line.strip().upper() for line in mrz_string.split('\n') if line.strip()]
    if not lines or len(lines) < 1: return {}
    
    line1 = lines[0]
    if not line1.startswith('P'):
        return {}

    # ICAO Doc 9303 - Line 1 Analysis
    # Pos 1: P, Pos 2: < (or document type), Pos 3-5: Country Code
    country_code_raw = line1[2:5]
    country_code = country_code_raw.replace('<', '') # Handle 1 or 2 letter codes like D<<
    
    # Name part starts at index 5
    name_part = line1[5:]
    
    surname = ""
    given_names = ""
    
    if '<<' in name_part:
        parts = name_part.split('<<', 1)
        surname = parts[0].replace('<', ' ').strip()
        if len(parts) > 1:
            given_names = parts[1].replace('<', ' ').strip()
    else:
        # Fallback if double chevron is missing
        surname = name_part.replace('<', ' ').strip()
    print({
        "COUNTRY_CODE": country_code,
        "SURNAME": surname,
        "GIVEN_NAMES": given_names,
        "FULL_NAME": f"{given_names} {surname}".strip()
    })

    return {
        "COUNTRY_CODE": country_code,
        "SURNAME": surname,
        "GIVEN_NAMES": given_names,
        "FULL_NAME": f"{given_names} {surname}".strip()
    }

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception) # Broad for now, handles Token issues if we reload env
)
def call_textract_id(client, image_bytes):
    return client.analyze_id(DocumentPages=[{'Bytes': image_bytes}])

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
def call_textract_doc(client, image_bytes):
    return client.analyze_document(
        Document={'Bytes': image_bytes},
        FeatureTypes=['TABLES', 'FORMS']
    )

def parse_analyze_id_response(response):
    """
    Parses Textract analyze_id response into a clean dict.
    Includes MRZ parsing for names.
    """
    extracted = {}
    mrz_code = None
    
    for doc in response.get("IdentityDocuments", []):
        for field in doc.get("IdentityDocumentFields", []):
            key = field["Type"]["Text"]
            value = field.get("ValueDetection", {}).get("Text", "")
            extracted[key] = {"value": value}
            if key == "MRZ_CODE":
                mrz_code = value

    # Deep parse MRZ for names if available
    if mrz_code:
        mrz_data = parse_passport_mrz(mrz_code)
        if mrz_data:
            extracted["MRZ_PARSED_NAME"] = {"value": mrz_data.get("FULL_NAME")}
            extracted["COUNTRY_CODE"] = {"value": mrz_data.get("COUNTRY_CODE")}
            # Override visual names if they look partial/wrong
            if mrz_data.get("SURNAME"):
                extracted["SURNAME"] = {"value": mrz_data.get("SURNAME")}
            if mrz_data.get("GIVEN_NAMES"):
                extracted["FIRST_NAME"] = {"value": mrz_data.get("GIVEN_NAMES")}
                
    return extracted

def parse_analyze_document_hierarchical(response):
    blocks = response.get("Blocks", [])
    block_map = {b["Id"]: b for b in blocks}

    # Sort blocks top-to-bottom
    sorted_blocks = sorted(
        blocks,
        key=lambda b: b.get("Geometry", {}).get("BoundingBox", {}).get("Top", 0)
    )

    output = []
    rendered_tables = set()
    table_boxes = []

    # Helper: extract text from CHILD words
    def extract_text(block):
        words = []
        for rel in block.get("Relationships", []):
            if rel["Type"] == "CHILD":
                for cid in rel["Ids"]:
                    child = block_map[cid]
                    if child["BlockType"] == "WORD":
                        words.append(child["Text"])
        return " ".join(words)

    # Helper: bounding box overlap
    def overlaps(box1, box2):
        return not (
            box1["Left"] + box1["Width"] < box2["Left"] or
            box2["Left"] + box2["Width"] < box1["Left"] or
            box1["Top"] + box1["Height"] < box2["Top"] or
            box2["Top"] + box2["Height"] < box1["Top"]
        )

    # Step 1: collect table bounding boxes
    for block in blocks:
        if block["BlockType"] == "TABLE":
            table_boxes.append(block["Geometry"]["BoundingBox"])

    # Helper: extract table rows
    def extract_table(table_block):
        table = {}
        max_row, max_col = 0, 0

        for rel in table_block.get("Relationships", []):
            if rel["Type"] == "CHILD":
                for cid in rel["Ids"]:
                    cell = block_map[cid]
                    if cell["BlockType"] == "CELL":
                        r, c = cell["RowIndex"], cell["ColumnIndex"]
                        max_row = max(max_row, r)
                        max_col = max(max_col, c)
                        table.setdefault(r, {})[c] = extract_text(cell)

        rows = []
        for r in range(1, max_row + 1):
            rows.append([table.get(r, {}).get(c, "") for c in range(1, max_col + 1)])
        return rows

    # Step 2: render in reading order
    for block in sorted_blocks:
        btype = block["BlockType"]

        # ----- TABLE -----
        if btype == "TABLE" and block["Id"] not in rendered_tables:
            output.append("\n[TABLE]")
            for row in extract_table(block):
                output.append(" | ".join(row))
            output.append("[/TABLE]\n")
            rendered_tables.add(block["Id"])

        # ----- LINE (skip if inside table) -----
        elif btype == "LINE":
            line_box = block["Geometry"]["BoundingBox"]
            inside_table = any(overlaps(line_box, tb) for tb in table_boxes)

            if not inside_table:
                output.append(block["Text"])

    return "\n".join(output)


def extract_text_with_textract(file_path: str, category: str = "general") -> str:
    """
    Extracts high-precision data from a document using AWS Textract.
    - category='passport': Uses analyze_id and scores multiple pages to find the main ID page.
    - category='general': Uses detect_document_text or analyze_document for other types.
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return ""

        client = get_textract_client()
        file_lower = file_path.lower()
        
        # 1. Convert PDF to images for synchronous processing
        images = []
        if file_lower.endswith(".pdf"):
            images = convert_from_path(file_path, dpi=200)
        else:
            images = [Image.open(file_path)]

        # 2. Category-based processing
        if category == "preview":
            # FAST PATH: Just the first page for classification
            img = images[0]
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', optimize=True, quality=70)
            image_bytes = img_byte_arr.getvalue()
            
            logger.info(f"Fast detection for preview: {file_path}")
            # detect_document_text is cheaper and faster
            response = client.detect_document_text(Document={'Bytes': image_bytes})
            return "\n".join([b['Text'] for b in response.get('Blocks', []) if b['BlockType'] == 'LINE'])

        elif category == "passport":
            all_pages_results = []
            for i, img in enumerate(images):
                # CRITICAL: Auto-correct orientation for each passport image
                logger.info(f"Processing passport page {i+1}/{len(images)}")
                img = auto_correct_image_orientation(img)
                
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
                image_bytes = img_byte_arr.getvalue()

                logger.info(f"Analyzing Passport Page {i+1}/{len(images)} via analyze_id...")
                response = call_textract_id(client, image_bytes)
                
                # SANITY CHECK: Did we actually find an ID?
                if not response.get("IdentityDocuments"):
                    logger.warning(f"Page {i+1} does not appear to be an Identity Document. Skipping.")
                    continue

                data = parse_analyze_id_response(response)
                data['raw_text'] = "\n".join([b['Text'] for b in response.get('Blocks', []) if b['BlockType'] == 'LINE']) # Fallback text
                data['score'] = score_passport_page(data)
                logger.info(f"Analyzing Passport Page {all_pages_results} of filename {file_path}.")
                
                all_pages_results.append(data)

            # Pick the winner
            best_page = None
            if all_pages_results:
                best_page = max(all_pages_results, key=lambda x: x['score'])
            
            # --- HYBRID FALLBACK LOGIC ---
            # Check if Primary Method (Analyze ID) worked
            primary_success = False
            if best_page:
                mrz_val = best_page.get('MRZ_CODE', {}).get('value', '')
                if "P<" in mrz_val and "<<" in mrz_val:
                    primary_success = True
                    logger.info(f"✅ Primary Strategy (Analyze ID) Successful. Score: {best_page['score']}")
            
            if primary_success:
                # Convert the dict to a string for the LLM to process
                import json
                print(all_pages_results,"all_pages_results")
                print(file_path,"file_path")
                return json.dumps(best_page, indent=2)
            
            else:
                logger.warning(f"⚠️ Primary Strategy failed/unclear for {file_path}. Attempting Universal Fallback...")
                
                # FALLBACK: Use analyze_document (Universal) on the same images
                for i, img in enumerate(images):
                    try:
                        # Re-orient specifically for fallback? Already done above, reuse 'img'
                        # But 'img' loop variable from above is gone. We iterate 'images' again.
                        # Note: images list contains PIL objects. 
                        # They might have been modified in place? No, auto_correct... returns new image usually.
                        # Wait, auto_correct check: "returns corrected". 
                        # So we should re-apply orientation or save corrected ones.
                        # Optimization: The previous loop didn't save corrected images back to list.
                        # So we must correct again or just do it inside this loop.
                        
                        logger.info(f"Fallback: Processing page {i+1} via analyze_document...")
                        img = auto_correct_image_orientation(img)
                        
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
                        image_bytes = img_byte_arr.getvalue()
                        
                        response = call_textract_doc(client, image_bytes)
                        blocks = response.get("Blocks", [])
                        
                        mrz_lines = extract_mrz_lines(blocks)
                        
                        if mrz_lines and mrz_basic_valid(mrz_lines):
                            logger.info("✅ Universal Fallback Successful: Found valid MRZ")
                            fallback_data = parse_mrz(mrz_lines)
                            logger.info(f"Fallback: Processing page fallbackdata {fallback_data} of the filename {file_path}")
                            import json
                            return json.dumps(fallback_data, indent=2)
                            
                            
                    except Exception as e:
                        logger.warning(f"Fallback attempt failed for page {i+1}: {e}")
                
                # If fallback also fails, return best effort from primary or empty
                if best_page:
                    logger.warning("Fallback failed. Returning best effort from Primary.")
                    import json
                    return json.dumps(best_page, indent=2)
                else:
                    logger.error("All extraction strategies failed.")
                    return ""

        else:
            # For Bank Statements and Degrees, use analyze_document for richer structure
            all_text_parts = []
            for i, img in enumerate(images):
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
                image_bytes = img_byte_arr.getvalue()

                logger.info(f"Analyzing Document Page {i+1}/{len(images)} via analyze_document...")
                # Use Tables and Forms for structural awareness
                response = call_textract_doc(client, image_bytes)
                page_text = parse_analyze_document_hierarchical(response)
                all_text_parts.append(page_text)

            # test purpose
            # file_path_ = "output3.txt"

            # try:
            #     with open(file_path_, "a", encoding="utf-8") as f:
            #         safe_text_parts = []

            #         for part in all_text_parts:
            #             if isinstance(part, list):
            #                 safe_text_parts.append("\n".join(map(str, part)))
            #             else:
            #                 safe_text_parts.append(str(part))

            #         f.write("\n\n--- Page Break ---\n\n".join(safe_text_parts))
            # except Exception as e:
            #     logger.error(f"text not saved in the {file_path_}: {str(e)}", exc_info=True)

            return "\n\n--- Page Break ---\n\n".join(all_text_parts)

    except Exception as e:
        logger.error(f"AWS Textract error for {file_path}: {str(e)}", exc_info=True)
        return ""

