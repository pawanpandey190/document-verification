from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict
from typing import Optional,Dict
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import time
from tenacity import retry, wait_exponential, stop_after_attempt
from langchain_aws import ChatBedrock
import boto3
from dotenv import load_dotenv
import os
from langchain_core.exceptions import OutputParserException
import logging
logger = logging.getLogger(__name__)
from pydantic import ConfigDict
# Load environment variables
load_dotenv()




class AcademicExtraction(BaseModel):
    name_of_student: Optional[str] = None
    country: Optional[str]
    country_evidence: Optional[str] # Explanation of why this country was chosen (e.g., "Found .ng domain and Naira currency")
    grading_type: Optional[str]  # percentage | cgpa_10 | gpa_5 | gpa_4 | level | grade
    cumulative_score: Optional[float]
    institution: Optional[str]
    qualification: Optional[str]
    graduation_year: Optional[int] = None
    semester_wise_marks: Optional[Dict[str, Optional[float]]] = None
    model_config = ConfigDict(extra="ignore")

ACADEMIC_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a strict academic transcript data extraction engine and geographic evidence analyzer.

CRITICAL BEHAVIOR RULES:
- You MUST return ONLY valid JSON.
- You MUST strictly follow the JSON schema below.
- Do NOT include explanations, markdown, comments, or extra text.
- Do NOT guess, hallucinate, or infer unsupported data.
- If a field cannot be determined with high confidence, return null.
- All numeric values must be real numbers (not strings).

"""
    ),
    (
        "human",
        """
Extract structured academic information from the transcript text below.

================ REQUIRED JSON SCHEMA =================

{{
  "name_of_student": string | null,
  "country": string | null,
  "country_evidence": string | null,
  "grading_type": "percentage" | "cgpa_10" | "gpa_5" | "gpa_4" | "level" | "grade" | null,
  "cumulative_score": number | null,
  "institution": string | null,
  "qualification": string | null,
  "graduation_year": number | null,
  "semester_wise_marks": {{
    "term1": number,
    "term2": number
  }} | null
}}

================ FIELD EXTRACTION RULES =================

1. name_of_student
   - Full name of the student.
   - Remove honorifics and titles (Mr, Ms, Mrs, Dr, etc.).
   - Preserve original spelling from the document.

2. country
   - Country where the institution is located.
   - Determine ONLY using explicit geographic evidence.
   - If insufficient or conflicting evidence exists, return null.

3. country_evidence
   - Short explanation of the geographic signals used.
   - Examples:
     - "Phone code +91 and INR currency"
     - "Mention of Lagos State and .edu.ng domain"
     - "Federal Republic seal and Nigerian grading system"
   - If country is null, clearly state why evidence was insufficient.

4. grading_type
   - Select ONE value that best represents the transcript grading system:
     percentage | cgpa_10 | gpa_5 | gpa_4 | level | grade
   - If unclear, return null.

5. cumulative_score
   - IMPORTANT (DO NOT SKIP):
     - If the transcript contains semester-wise / trimester-wise / year-wise results:
       → Calculate the AVERAGE of ALL FINAL TERM TOTALS.
     - Use ONLY final semester/trimester/year totals.
     - Do NOT average individual subject marks.
     - If grading system is GPA/CGPA, extract the FINAL cumulative value directly.
     - Return a FLOAT only.
     - If calculation cannot be done confidently, return null.

6. institution
   - Full official name of the university, college, or school.

7. qualification
   - Degree or qualification name.
   - Extract ONLY the highest or latest qualification mentioned.

8. graduation_year
   - Completion year in YYYY format.
   - If not clearly stated, return null.

9. semester_wise_marks
   - Capture semester / trimester / year-wise FINAL totals.
   - Use generic keys: term1, term2, term3, etc.
   - Example:
     {{
       "term1": 68.5,
       "term2": 72.0,
       "term3": 70.25
     }}
   - If not available, return null.

================ COUNTRY DISAMBIGUATION LOGIC =================

Use ONLY explicit evidence such as:
- Currency symbols or codes (INR, ₦, USD, EUR, etc.)
- Phone codes (+91, +92, +234, +44, etc.)
- States / provinces (Lagos, Maharashtra, Punjab, Ontario, etc.)
- Website or email TLDs (.edu.ng, .edu.in, .ac.uk, .edu.pk)
- Official seals or phrases ("Federal Republic of X", "Government of Y")
- National grading systems

DO NOT guess the country.
If unsure, return null.

================ ABSOLUTE RULES =================

- Highest qualification ONLY.
- Conservative extraction.
- Multilingual input supported.
- Do NOT invent missing values.
- Return ALL required keys (use null if unknown).
- Return ONLY valid JSON.

================ TRANSCRIPT TEXT =================
{text}
"""
    )
])


# Bedrock Haiku with Bearer Token Auth
bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    
)

llm = ChatBedrock(
    model_id="amazon.nova-pro-v1:0",
    client=bedrock_client,
    model_kwargs={"temperature": 0}
).with_structured_output(AcademicExtraction)

# llm = ChatOpenAI(
#     model="gpt-4o-mini",
#     temperature=0
# ).with_structured_output(AcademicExtraction)

parser = PydanticOutputParser(pydantic_object=AcademicExtraction)

@retry(
    wait=wait_exponential(multiplier=2, min=5, max=30),
    stop=stop_after_attempt(5)
)
def extract_degree_llm(text: str) -> dict:
    """
    Safe LLM invocation that NEVER crashes the API.
    """
    print(text,"extract_degree_llm_text")
    try:
        chain = ACADEMIC_PROMPT | llm
        result = chain.invoke({"text": text})
        print(result.model_dump(),"result.model_dump()")
        return result.model_dump()

    except OutputParserException as e:
        logger.error("LLM JSON parsing failed", exc_info=True)

        # 🚨 Fallback: return empty but valid structure
        return {
            "country": None,
            "country_evidence": None,
            "grading_type": None,
            "cumulative_score": None,
            "institution": None,
            "qualification": None,
            "semester_wise_marks":None,
            "llm_error": "Invalid JSON output"
        }

    except Exception as e:
        logger.error("LLM invocation failed", exc_info=True)
        raise RuntimeError("LLM service unavailable")

# def extract_academic_data_with_llm(extracted_text: str) -> dict:
#     if not extracted_text or len(extracted_text.strip()) < 50:
#         raise ValueError("Insufficient text for LLM extraction")

#     return invoke_llm_safe(extracted_text)
