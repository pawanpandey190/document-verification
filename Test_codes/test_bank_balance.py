import io
from PIL import Image
from pdf2image import convert_from_path
import os
import os
import logging
from dotenv import load_dotenv
load_dotenv()
print("✅ Script started")
logger = logging.getLogger(__name__)
import boto3
import re
from datetime import datetime

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



def call_textract_doc(client, image_bytes):
    return client.analyze_document(
        Document={'Bytes': image_bytes},
        FeatureTypes=['TABLES', 'FORMS']
    )


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

DATE_HEADERS = [
    "date", "txn date", "transaction date", "posting date", "value date"
]

BALANCE_HEADERS = [
    "balance", "closing balance", "running balance", "available balance", "ledger balance"
]

DATE_FORMATS = [
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %B %Y"
]


def parse_date(raw):
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def parse_balance(raw):
    raw = raw.replace(",", "")
    raw = re.sub(r"[^\d.\-]", "", raw)
    try:
        return float(raw)
    except Exception:
        return None


def extract_transactions_from_textract(response):
    blocks = response.get("Blocks", [])
    block_map = {b["Id"]: b for b in blocks}

    all_transactions = []

    for block in blocks:
        if block["BlockType"] != "TABLE":
            continue

        # ---- Build table grid ----
        table = {}
        for rel in block.get("Relationships", []):
            if rel["Type"] == "CHILD":
                for cid in rel["Ids"]:
                    cell = block_map[cid]
                    if cell["BlockType"] == "CELL":
                        r, c = cell["RowIndex"], cell["ColumnIndex"]

                        words = []
                        for cr in cell.get("Relationships", []):
                            if cr["Type"] == "CHILD":
                                for wid in cr["Ids"]:
                                    w = block_map[wid]
                                    if w["BlockType"] == "WORD":
                                        words.append(w["Text"])

                        table.setdefault(r, {})[c] = " ".join(words)

        # ---- Detect header row dynamically ----
        header_row = None
        date_col = balance_col = None

        for r, row in table.items():
            for c, text in row.items():
                t = text.lower()
                if any(h in t for h in DATE_HEADERS):
                    date_col = c
                if any(h in t for h in BALANCE_HEADERS):
                    balance_col = c
            if date_col and balance_col:
                header_row = r
                break

        if not header_row:
            continue  # Not a transaction table

        # ---- Parse rows after header ----
        for r in sorted(table.keys()):
            if r <= header_row:
                continue

            row = table[r]
            raw_date = row.get(date_col)
            raw_balance = row.get(balance_col)

            if not raw_date or not raw_balance:
                continue

            date = parse_date(raw_date)
            balance = parse_balance(raw_balance)

            if date and balance is not None:
                all_transactions.append({
                    "date": date,
                    "balance": balance
                })

    return all_transactions


def extract_text_with_textract(file_path: str) -> str:
    """
    Extracts text from an image or PDF using AWS Textract.
    For PDFs, it converts pages to images locally first, as Textract's 
    Synchronous API only supports PDF bytes when stored in S3.
    """
    try:
        if not os.path.exists(file_path):
            # logger.error(f"File not found: {file_path}")
            return ""

        client = get_textract_client()
        file_lower = file_path.lower()
        all_text = []
        all_text2 = []

        # Case 1: PDF Files (Must be converted to images for synchronous local processing)
        if file_lower.endswith(".pdf"):
            # logger.info(f"Converting PDF to images for Textract: {file_path}")
            # Convert PDF to list of PIL images
            images = convert_from_path(file_path, dpi=200) # 200 DPI is usually enough for OCR
            
            for i, img in enumerate(images):
                # Convert PIL image to bytes
                img_byte_arr = io.BytesIO()
                # Use JPEG with optimization to stay under 5MB Textract limit
                img.save(img_byte_arr, format='JPEG', optimize=True, quality=80)
                image_bytes = img_byte_arr.getvalue()

                # logger.info(f"Processing page {i+1}/{len(images)} via Textract...")
                response = call_textract_doc(client, image_bytes)
                page_text = parse_analyze_document_hierarchical(response)
                page_text1 = extract_transactions_from_textract(response)
                all_text.append(page_text)
                all_text2.append(page_text1)
        
        print(all_text2,"all_text2")

        try:
            with open("output4.txt", "w", encoding="utf-8") as file:
                file.write("\n".join(all_text2))
        except Exception as e:
            print(f"error {e}")
        
        try:
            with open("output3.txt", "w", encoding="utf-8") as file:
                file.write("\n".join(all_text))
        except Exception as e:
            print(f"error {e}")
        

        print("Text saved successfully.")

    except Exception as e:
        logger.error(f"AWS Textract error for {file_path}: {str(e)}", exc_info=True)
        return ""


    return all_text
    
                
                
                
       

    



data = extract_text_with_textract("/Users/pawanpandey/Documents/document-validation/data/Joy Sheikh - France/Bank Balance Statement.pdf")
print(data)


