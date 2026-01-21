from paddleocr import PaddleOCR
from pdf2image import convert_from_path
import numpy as np
import pandas as pd

# =========================
# CONFIG
# =========================
PDF_PATH = "/Users/pawanpandey/Documents/document-validation/data/Sakshi Ganesh Pacharne/Transcripts Bachelors.pdf"
OUTPUT_TXT = "extracted_hierarchical_output.txt"
DPI = 300


# =========================
# INIT OCR
# =========================
ocr = PaddleOCR(use_angle_cls=True, lang="en")

# =========================
# HELPERS
# =========================
def sort_boxes(result):
    return sorted(result, key=lambda x: (x[0][0][1], x[0][0][0]))

def group_rows(lines, y_threshold=10):
    rows, current, last_y = [], [], None
    for box, (text, _) in lines:
        y = box[0][1]
        if last_y is None or abs(y - last_y) <= y_threshold:
            current.append((box, text))
        else:
            rows.append(current)
            current = [(box, text)]
        last_y = y
    if current:
        rows.append(current)
    return rows

def get_x_signature(row):
    xs = []
    for box, _ in row:
        # Case 1: [[x,y], ...]
        if isinstance(box[0], (list, tuple)):
            x = box[0][0]
        # Case 2: [x1,y1,x2,y2,...]
        else:
            x = box[0]
        xs.append(round(x / 20))
    return xs


def row_is_table_like(row):
    return len(row) >= 3   # minimum columns

def table_to_text(table):
    lines = []

    for row in table:
        # Separate real OCR cells and merged text cells
        ocr_cells = []
        extra_text = []

        for box, text in row:
            if box is None:
                extra_text.append(text)
            else:
                # Normalize box format
                if isinstance(box[0], (list, tuple)):
                    x = box[0][0]
                else:
                    x = box[0]
                ocr_cells.append((x, text))

        # Sort OCR cells by X (left → right)
        ocr_cells.sort(key=lambda x: x[0])

        row_text = " | ".join(text for _, text in ocr_cells)

        # Append any merged continuation text
        if extra_text:
            row_text = row_text + " " + " ".join(extra_text)

        lines.append(row_text)

    return "\n".join(lines)


# =========================
# MAIN LOGIC
# =========================
pages = convert_from_path(PDF_PATH, dpi=DPI)
document_blocks = []

for page in pages:
    image = np.array(page)
    result = ocr.ocr(image, cls=True)[0]
    result = sort_boxes(result)
    rows = group_rows(result)

    current_table = []
    table_signature = None
    current_text = []

    for row in rows:
        signature = get_x_signature(row)

        if row_is_table_like(row):
            if not current_table:
                table_signature = signature
            if signature == table_signature:
                if current_text:
                    document_blocks.append(("text", " ".join(current_text)))
                    current_text = []
                current_table.append(row)
                continue

        # Row does not match table
        if current_table:
            document_blocks.append(("table", current_table))
            current_table = []
            table_signature = None

        current_text.append(" ".join(text for _, text in row))

    if current_table:
        document_blocks.append(("table", current_table))
    if current_text:
        document_blocks.append(("text", " ".join(current_text)))


def merge_broken_tables(blocks):
    merged = []
    last_table = None

    for block_type, content in blocks:
        if block_type == "table":
            if last_table is None:
                last_table = content
            else:
                last_table.extend(content)

        else:  # text
            text = content.lower()

            # Check if text likely belongs to previous table
            if last_table and any(k in text for k in [
                "batch", "cr", "dr", "interest", "balance", "tax", "deposit"
            ]):
                # Append text to last row of table
                last_table[-1].append((None, content))
            else:
                if last_table:
                    merged.append(("table", last_table))
                    last_table = None
                merged.append(("text", content))

    if last_table:
        merged.append(("table", last_table))

    return merged

document_blocks = merge_broken_tables(document_blocks)


# =========================
# SAVE OUTPUT
# =========================
with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
    for i, (block_type, content) in enumerate(document_blocks, 1):
        f.write(f"\n===== BLOCK {i} ({block_type.upper()}) =====\n")
        if block_type == "text":
            f.write(content + "\n")
        else:
            f.write(table_to_text(content) + "\n")

print("✅ Extraction completed")
print(f"📄 Output saved to: {OUTPUT_TXT}")
