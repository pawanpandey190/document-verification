from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from typing import Optional
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


class PassportExtraction(BaseModel):
    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    expiry_date: Optional[str] = None
    passport_number: Optional[str] = None
    nationality: Optional[str] = None

PASSPORT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a strict passport data extraction engine specialized in ICAO-compliant passports.

CRITICAL BEHAVIOR RULES:
- You MUST return ONLY valid JSON.
- You MUST strictly follow the JSON schema provided.
- Do NOT include explanations, comments, markdown, or additional text.
- Do NOT guess, infer, or autocorrect data.
- If a field cannot be determined with high confidence, return null.
- MRZ data, when present, is the authoritative legal source of truth.
"""
    ),
    (
        "human",
        """
Extract passport information from the input text below.
The input may contain OCR text, structured fields, and MRZ-parsed values.

================ REQUIRED JSON SCHEMA =================

{{
  "name": string | null,
  "date_of_birth": "YYYY-MM-DD" | null,
  "expiry_date": "YYYY-MM-DD" | null,
  "passport_number": string | null,
  "nationality": string | null
}}

================ FIELD EXTRACTION RULES =================

1. name
   - Full name of the passport holder as a SINGLE STRING.
   - Format: "FIRST MIDDLE LAST" (uppercase or title case is acceptable).
   - ABSOLUTE PRIORITY:
     - If MRZ_PARSED_NAME is present, it MUST be used.
     - Ignore visual/OCR name fields if they conflict with MRZ.
   - Convert MRZ separators (<) into single spaces.
   - Do NOT reorder name components from MRZ.
   - Remove honorifics and titles (Mr, Ms, Mrs, Dr, etc.).
   - Preserve spelling EXACTLY as in MRZ (no corrections).

2. date_of_birth
   - Format MUST be ISO: YYYY-MM-DD.
   - If MRZ date is present, it MUST be used.
   - Convert MRZ YYMMDD carefully:
     - Use passport expiry year to infer century.
   - Must be a valid calendar date.
   - If unclear or conflicting, return null.

3. expiry_date
   - Format MUST be ISO: YYYY-MM-DD.
   - If MRZ expiry date is present, it MUST be used.
   - Convert MRZ YYMMDD carefully.
   - Must be a valid calendar date.
   - If unclear, return null.

4. passport_number
   - Use document number from MRZ if available.
   - Remove filler characters (<).
   - Preserve original alphanumeric sequence.
   - Do NOT guess missing characters.
   - If incomplete or unclear, return null.

5. nationality
   - If derived from MRZ, return the ICAO / ISO alpha-3 code
     (e.g., IND, USA, GBR, NGA).
   - If MRZ is absent and only a country name is visible,
     return the country name exactly as shown.
   - If conflicting or unclear, return null.

================ ABSOLUTE PRIORITY ORDER =================

MRZ data
  > Structured / parsed fields
    > Visual OCR text

If any conflict exists, ALWAYS trust MRZ.

================ SAFETY & VALIDATION RULES =================

- Do NOT fabricate values.
- Do NOT normalize spellings beyond MRZ conversion rules.
- Dates must be valid real-world dates.
- You are multilingual; input text may not be English.
- Output MUST be valid JSON only.
- Do NOT add extra keys.
- Do NOT omit required keys (use null instead).

================ INPUT DATA =================
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
).with_structured_output(PassportExtraction)


# llm = ChatOpenAI(
#     model="gpt-4o-mini",
#     temperature=0
# ).with_structured_output(PassportExtraction)


parser = PydanticOutputParser(pydantic_object=PassportExtraction)

@retry(
    wait=wait_exponential(multiplier=2, min=5, max=30),
    stop=stop_after_attempt(5)
)


def extract_passport_llm(text: str) -> dict:
    try:
        chain = PASSPORT_PROMPT | llm
        print(chain.invoke({"text": text}).model_dump(),"PASSPORT_PROMPT")
        return chain.invoke({"text": text}).model_dump()
    
    except OutputParserException as e:
        logger.error("LLM JSON parsing failed", exc_info=True)

        # 🚨 Fallback: return empty but valid structure
        return {
            "name": None,
            "date_of_birth": None,
            "expiry_date": None,
            "passport_number": None,
            "nationality": None,
            "llm_error": "Invalid JSON output"
        }

    except Exception as e:
        logger.error("LLM invocation failed", exc_info=True)
        raise RuntimeError("LLM service unavailable")

