import boto3
import time

def extract_text_with_textract(file_path):
    client = boto3.client('textract', region_name='your-region')

    # Read the file
    with open(file_path, 'rb') as document:
        image_binary = document.read()

    # For single-page PDFs/Images, use synchronous:
    # response = client.detect_document_text(Document={'Bytes': image_binary})
    
    # For multi-page or robust PDF processing, use Asynchronous:
    # Note: For async, files usually need to be in an S3 bucket.
    # But for small local files, standard detection works:
    response = client.detect_document_text(
        Document={'Bytes': image_binary}
    )

    # Extracting the lines of text
    extracted_text = ""
    for item in response.get('Blocks', []):
        if item.get('BlockType') == 'LINE':
            extracted_text += item.get('Text', "") + "\n"
            
    return extracted_text.strip()