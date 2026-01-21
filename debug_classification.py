import os
from student_orchestration import classify_documents_by_content

def test_student(student_name, student_dir, filenames):
    print(f"\n--- Testing Student: {student_name} ---")
    result = classify_documents_by_content(student_dir, filenames)
    print(f"Reasoning: {result.reasoning}")
    print(f"Passport: {result.passport}")
    print(f"Bank Statement: {result.bank_statement}")
    print(f"Highest Academic: {result.highest_academic}")
    print(f"English Test: {result.english_test}")

if __name__ == "__main__":
    base_data = "/Users/pawanpandey/Documents/document-validation/data"
    
    # Test Beza
    beza_dir = os.path.join(base_data, "Beza Asnake Teshome - USA")
    beza_files = [
        "Acceptance Letter USA.pdf",
        "Bachelor Degree.pdf",
        "Bachelor Transcripts.pdf",
        "Bank Balance Statement.pdf",
        "High School Documents.pdf",
        "Higher Secondary Transcript.pdf",
        "Masters Transcripts.pdf",
        "Passport.pdf"
    ]
    test_student("Beza Asnake Teshome - USA", beza_dir, beza_files)

    # Test Prajwal
    prajwal_dir = os.path.join(base_data, "Prajwal Puri - France")
    prajwal_files = [
        "BBA Transcript.pdf",
        "Bank Balance Statements.pdf",
        "English Proficiency Test.pdf",
        "Higher Secondary 11th.pdf",
        "Higher Secondary Certificate.pdf",
        "Higher Secondary Transcript 10th.pdf",
        "Passport.pdf",
        "Senior Secondary Certificate.pdf"
    ]
    test_student("Prajwal Puri - France", prajwal_dir, prajwal_files)
