import os
from textract_extraction import extract_text_with_textract
from degree_llm import extract_degree_llm

def test_extraction(file_path):
    print(f"\n--- Testing Extraction: {os.path.basename(file_path)} ---")
    text = extract_text_with_textract(file_path, category="certificate")
    print(f"Text Length: {len(text)}")
    result = extract_degree_llm(text)
    print(f"Extraction Result: {result}")

if __name__ == "__main__":
    # Test Beza Masters
    test_extraction("/Users/pawanpandey/Documents/document-validation/data/Beza Asnake Teshome - USA/Masters Transcripts.pdf")
    
    # Test Beza Bachelors (just in case)
    test_extraction("/Users/pawanpandey/Documents/document-validation/data/Beza Asnake Teshome - USA/Bachelor Degree.pdf")
