# orchestrator/student_orchestrator.py
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from passport_llm import extract_passport_llm
from bank_statement_llm import extract_bank_statement
from degree_llm import extract_degree_llm
from english_llm import extract_english_llm
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel,Field
from typing import List, Optional
import json
from langchain_aws import ChatBedrock
from validation import (
    validate_passport,
    validate_bank,
    validate_degree_marks
)

from textract_extraction import extract_text_with_textract
from data_extraction import extract_first_page_preview

logger = logging.getLogger(__name__)

class FileClassification(BaseModel):
    filename: str
    document_type: str # passport | bank_statement | academic | english_test | unknown
    academic_level: Optional[int] = None # 1 (PhD) to 6 (10th)
    graduation_year: Optional[int] = None
    confidence_score: int # 1-100

# class DocumentClassification(BaseModel):
#     reasoning: str
#     classifications: List[FileClassification]

class DocumentClassification(BaseModel):
    reasoning: Optional[str] = Field(
        default=None,
        description="Optional explanation of classification logic"
    )
    classifications: List[FileClassification]

CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a strict document triage and classification engine.

CRITICAL BEHAVIOR RULES:
- You MUST classify EVERY file provided.
- You MUST return ONLY valid JSON.
- Do NOT include explanations outside the JSON structure.
- Do NOT omit any file.
- Do NOT guess or hallucinate document types.
- CONTENT always has higher priority than filename.
- You are multilingual; documents may not be in English.
"""
    ),
    (
        "human",
        """
Analyze each file using BOTH its filename and its content preview.

================ REQUIRED JSON SCHEMA =================

{{
  "reasoning": string,
  "classifications": [
    {{
      "filename": string,
      "document_type": "passport" | "bank_statement" | "academic" | "english_test" | "other",
      "academic_level": number | null,
      "graduation_year": number | null,
      "confidence_score": number
    }}
  ]
}}

================ DOCUMENT TYPE DEFINITIONS ==============

1. passport
   - Strong indicators:
     - "Passport"
     - MRZ lines such as "P<", "P<IND", "<<"
     - Fields like Nationality, Date of Birth, Place of Birth
   - MRZ presence is definitive.

2. bank_statement
   - Strong indicators:
     - Account number
     - Transaction history
     - Debit / Credit
     - Balance, Closing Balance
     - Currency symbols or codes

3. academic
   - Strong indicators:
     - Transcript
     - CGPA / GPA / Percentage / Grades
     - University / College / School
     - Degree names (Bachelor, Master, Diploma, PhD)
   - Focus more on the transcripts file.
   - If the document does NOT contain grades/marks, DO NOT classify as academic.

4. english_test
   - Strong indicators:
     - IELTS / TOEFL / PTE / Duolingo
     - Overall band score
     - Listening / Reading / Writing / Speaking sections
     - Test Report Form

5. other
   - Use ONLY if none of the above categories confidently apply.

================ ACADEMIC LEVEL HIERARCHY =================

Use STRICT hierarchy (lower number = higher level):

1 → Doctorate / PhD  
2 → Masters / Masters Transcript  
3 → Bachelor / Bachelor Transcript  
4 → Diploma  
5 → Higher Secondary / 12th / A-Level  
6 → Secondary / 10th / GCSE  
7 → Unknown / Other  

Rules:
- Assign academic_level ONLY if document_type = academic.
- If academic but level is unclear, use 7.
- If multiple academic documents exist at the SAME level,
  prefer the one with the LATEST graduation year.

================ SELECTION & DISAMBIGUATION RULES =========

- CONTENT IS TRUTH:
  - Ignore misleading filenames if content indicates another type.
  - Example: "degree.pdf" containing a passport → passport.

- ACADEMIC DOCUMENTS:
  - If multiple files exist (transcript, degree, certificate):
    - Prefer the file with CLEAR grades/marks.
    - Prefer the LATEST year.
  - If filename is similar but content differs, trust content.

- RECENCY:
  - For academic documents, extract graduation_year if visible.
  - If not visible, return null.

- CONFIDENCE SCORE:
  - Integer from 1 to 100.
  - Higher confidence if multiple strong indicators exist.
  - Lower confidence if classification is weak but best possible.

================ OUTPUT RULES ==============================

- You MUST return a classification object for EVERY file.
- reasoning:
  - Brief explanation summarizing overall classification logic.
- Do NOT add extra keys.
- Do NOT omit required keys.
- Return ONLY valid JSON.

================ FILES AND PREVIEWS ========================
{file_data}
"""
    )
])

bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    
)
llm = ChatBedrock(
    model_id="amazon.nova-pro-v1:0",
    client=bedrock_client,
    model_kwargs={"temperature": 0}
).with_structured_output(DocumentClassification)


# classifier_llm = ChatOpenAI(
#     model="gpt-4o-mini",
#     temperature=0
# ).with_structured_output(DocumentClassification)

def classify_documents_by_content(student_dir: str, filenames: List[str]) -> DocumentClassification:
    """
    Classifies documents using content previews.
    Returns a safe fallback if classification fails.
    """
    try:
        if not filenames:
            logger.warning(f"No files found in {student_dir}")
            return DocumentClassification(
                reasoning="No files found in directory",
                classifications=[]
            )
        
        file_previews = []
        for filename in filenames:
            path = os.path.join(student_dir, filename)
            preview = extract_first_page_preview(path)
            file_previews.append(f"File: {filename}\\nPreview:\\n{preview}\\n---")
            
        print(f"Classifying {len(filenames)} documents for student...")
        chain = CLASSIFY_PROMPT | llm
        result = chain.invoke({"file_data": "\\n".join(file_previews)})
        print(f"Classification result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"CRITICAL: Content classification failed: {e}", exc_info=True)
        # Return safe fallback with empty classifications
        return DocumentClassification(
            reasoning=f"Classification failed: {str(e)}",
            classifications=[]
        )



def process_student_directory(student_dir: str) -> dict:
    """
    Process a single student directory.
    Returns a safe error structure if processing fails.
    """
    output = {
        "certificate": None,
        "passport": None,
        "bank_statement": None,
        "english_test": None,
        "selected_files": {},
        "validation": {},
        "processing_error": None
    }

    try:
        dir_files = []
        for f in os.listdir(student_dir):
            full_path = os.path.join(student_dir, f)
            if os.path.isfile(full_path) and not f.startswith('.'):
                dir_files.append(f)
        
        if not dir_files:
            logger.warning(f"No valid files found in {student_dir}")
            output["processing_error"] = "No valid files found in directory"
            return output
        
        classification = classify_documents_by_content(student_dir, dir_files)
        
        # Handle empty classifications gracefully
        if not classification.classifications:
            logger.warning(f"Classification returned no results for {student_dir}")
            output["processing_error"] = "Classification failed - no documents identified"
            return output
        
        # SOLID LOGIC: Pick the winners
        selected = {
            "passport": None,
            "bank_statement": None,
            "academic": None,
            "english_test": None
        }

        best_academic = {"file": None, "level": 99, "year": 0}

        for cls in classification.classifications:
            if cls.document_type == "passport" and not selected["passport"]:
                selected["passport"] = cls.filename
                
            if cls.document_type == "bank_statement" and not selected["bank_statement"]:
                selected["bank_statement"] = cls.filename
                
            if cls.document_type == "academic":
                level = cls.academic_level or 7
                year = cls.graduation_year or 0
                
                if level < best_academic["level"]:
                    best_academic = {"file": cls.filename, "level": level, "year": year}
                elif level == best_academic["level"] and year > best_academic["year"]:
                    best_academic = {"file": cls.filename, "level": level, "year": year}
            
            if cls.document_type == "english_test" and not selected["english_test"]:
                selected["english_test"] = cls.filename

        selected["academic"] = best_academic["file"]

        output["selected_files"] = {
            "passport": selected["passport"],
            "bank_statement": selected["bank_statement"],
            "highest_academic": selected["academic"],
            "english_test": selected["english_test"],
            "reasoning": classification.reasoning
        }
        
        work_plan = {
            "passport": (selected["passport"], extract_passport_llm),
            "bank_statement": (selected["bank_statement"], extract_bank_statement),
            "certificate": (selected["academic"], extract_degree_llm),
            "english_test": (selected["english_test"], extract_english_llm)
        }

        # EXTRACTION PHASE
        for key, (filename, extract_fn) in work_plan.items():
            if not filename:
                continue
            
            try:
                path = os.path.join(student_dir, filename)
                print(f"Extracting {key} from: {filename}")
                
                text = extract_text_with_textract(path, category=("passport" if key == "passport" else "general"))
                
                if not text or len(text) < 10:
                    logger.warning(f"Textract failed for {filename}")
                    continue
                    
                output[key] = extract_fn(text)
                
            except Exception as e:
                logger.error(f"Extraction failed for {key} ({filename}): {e}", exc_info=True)
                output[key] = None

        # VALIDATION PHASE
        try:
            certificate = output.get("certificate") or {}
            passport = output.get("passport") or {}
            bank = output.get("bank_statement") or {}
            
            degree_name = certificate.get("name_of_student", "Unknown")
            
            output["validation"] = {
                "degree": validate_degree_marks(certificate) if certificate else {"status": "FAILED", "reason": "No degree certificate found"},
                "passport": validate_passport(passport, degree_name) if passport else {"status": "Not Approved", "reason": "No passport found"},
                "bank": validate_bank(bank, degree_name) if bank else {"status": "Not Approved", "reason": "No bank statement found"}
            }
        except Exception as e:
            logger.error(f"Validation failed: {e}", exc_info=True)
            output["validation"] = {
                "degree": {"status": "FAILED", "reason": f"Validation error: {str(e)}"},
                "passport": {"status": "Not Approved", "reason": "Validation error"},
                "bank": {"status": "Not Approved", "reason": "Validation error"}
            }

        return output
        
    except Exception as e:
        logger.critical(f"CRITICAL: Student processing failed for {student_dir}: {e}", exc_info=True)
        output["processing_error"] = f"Critical error: {str(e)}"
        return output


def process_parent_directory(parent_dir: str) -> dict:
    """
    Iterates through each student's subdirectory and processes them IN PARALLEL.
    Continues processing even if individual students fail.
    Returns: { "folder_name": {student_result_dict}, ... }
    """
    results = {}
    
    try:
        subdirs = [d for d in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, d))]
        
        if not subdirs:
            logger.warning(f"No student directories found in {parent_dir}")
            return results
        
        # Filter out hidden directories
        student_folders = []
        for folder_name in subdirs:
            if not folder_name.startswith('.'):
                path = os.path.join(parent_dir, folder_name)
                student_folders.append((folder_name, path))
        
        if not student_folders:
            logger.warning("No valid student folders found")
            return results
        
        logger.info(f"🚀 Processing {len(student_folders)} students in PARALLEL (max 5 concurrent)...")
        print(f"\n🚀 Processing {len(student_folders)} students in parallel...")
        
        # Process students in parallel using ThreadPoolExecutor
        # max_workers=5 to avoid overwhelming API rate limits
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all student processing tasks
            future_to_student = {
                executor.submit(process_student_directory, path): folder_name
                for folder_name, path in student_folders
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_student):
                folder_name = future_to_student[future]
                completed += 1
                
                try:
                    student_data = future.result()
                    results[folder_name] = student_data
                    
                    # Log progress
                    if student_data.get("processing_error"):
                        logger.warning(f"[{completed}/{len(student_folders)}] ⚠️ {folder_name}: {student_data['processing_error']}")
                        print(f"[{completed}/{len(student_folders)}] ⚠️ {folder_name}: Error")
                    else:
                        logger.info(f"[{completed}/{len(student_folders)}] ✅ {folder_name}: Completed")
                        print(f"[{completed}/{len(student_folders)}] ✅ {folder_name}: Completed")
                        
                except Exception as e:
                    logger.error(f"Failed to process student {folder_name}: {e}", exc_info=True)
                    print(f"[{completed}/{len(student_folders)}] ❌ {folder_name}: Failed - {str(e)}")
                    # Add error entry but continue with other students
                    results[folder_name] = {
                        "processing_error": f"Critical failure: {str(e)}",
                        "certificate": None,
                        "passport": None,
                        "bank_statement": None,
                        "english_test": None,
                        "selected_files": {},
                        "validation": {}
                    }
        
        logger.info(f"✅ Completed processing {len(results)} students in parallel")
        print(f"\n✅ All {len(results)} students processed!")
        return results
        
    except Exception as e:
        logger.critical(f"Critical error in parent directory processing: {e}", exc_info=True)
        return results  # Return whatever we managed to process

