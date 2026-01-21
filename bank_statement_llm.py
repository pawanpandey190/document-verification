from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from typing import Optional,Dict
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import time
from tenacity import retry, wait_exponential, stop_after_attempt
from langchain_aws import ChatBedrock
import boto3
import json
from dotenv import load_dotenv
import os
from langchain_core.exceptions import OutputParserException
import logging
logger = logging.getLogger(__name__)
from pydantic import ConfigDict
import re
from datetime import datetime
# Load environment variables
load_dotenv()

# hepler functions
import re

# getting the right statement date
DATE_FORMATS = [
    "%d-%m-%Y", "%d/%m/%Y", "%d%m%Y",
    "%d-%b-%Y", "%d/%b/%Y", "%d%b%Y",
    "%d-%B-%Y", "%d/%B/%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%b %d %Y", "%B %d %Y"
]

def parse_single_date_safe(text: str):
    if not isinstance(text, str):
        return None

    cleaned = text.strip().replace("/", "-").replace(" ", "")

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except Exception:
            continue
    return None

def extract_dates_safe(period: str):
    dates = []

    if not isinstance(period, str):
        return dates

    try:
        candidates = re.findall(
            r"\d{1,4}[-/ ]?[A-Za-z]{0,9}[-/ ]?\d{2,4}",
            period
        )
    except Exception:
        return dates

    for c in candidates:
        try:
            parsed = parse_single_date_safe(c)
            if parsed:
                dates.append(parsed)
        except Exception:
            continue

    return dates

def derive_final_statement_period(all_periods):
    """
    Takes ALL collected statement_period strings
    and derives ONE correct final period.
    NEVER crashes.
    """
    try:
        if not isinstance(all_periods, list):
            return None

        starts = []
        ends = []

        for period in all_periods:
            try:
                dates = extract_dates_safe(period)
                if len(dates) >= 2:
                    starts.append(min(dates))
                    ends.append(max(dates))
            except Exception:
                continue

        if not starts or not ends:
            return None

        final_start = min(starts)
        final_end = max(ends)

        return f"{final_start.strftime('%d-%b-%Y')} to {final_end.strftime('%d-%b-%Y')}"

    except Exception:
        logger.error("Failed to derive final statement period", exc_info=True)
        return None

# making the LLM output in perfect json
def extract_json_block(text: str) -> str:
    match = re.search(r"\{[\s\S]*?\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM output")
    return match.group(0)

def safe_json_loads(text: str) -> dict:
    """
    Attempts to load JSON, repairing common LLM truncation issues.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Common fix: close dangling quotes and braces
        print("in except")
        repaired = text

        # Close unclosed string
        if repaired.count('"') % 2 != 0:
            repaired += '"'

        # Close braces if needed
        open_braces = repaired.count("{")
        close_braces = repaired.count("}")
        if close_braces < open_braces:
            repaired += "}" * (open_braces - close_braces)

        return json.loads(repaired)


class BankSecondaryExtraction(BaseModel):
    closing_balance: Optional[float] = None
    statement_period: Optional[str] = None
    balance_continuity: Optional[str] = None
    monthly_average_balance: Optional[Dict[str, float]] = None


class BankExtraction(BaseModel):
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    closing_balance: Optional[float] = None
    currency: Optional[str] = None
    statement_period: Optional[str] = None
    balance_continuity: Optional[str] = None
    monthly_average_balance: Optional[Dict[str, float]] = None

     # Description of balance flow (e.g., "Continuous", "Sudden deposit of 5k detected in Dec")

BALANCE_PROMPT= ChatPromptTemplate.from_messages([(
        "system",
        """
You are an expert financial document extraction engine and bank statement auditor.

CRITICAL INSTRUCTIONS:
- You MUST return ONLY valid JSON.
- You MUST strictly follow the provided JSON schema.
- Do NOT include explanations, comments, markdown, or extra text.
- Do NOT guess or infer missing values.
- If a value is unclear or not present, return null.
- All numeric values must be real numbers (not strings).
- Date formats MUST be respected exactly.
"""
    ),
    (
        "human",
        """
Extract structured bank statement data from the text below.

================ REQUIRED JSON SCHEMA =================

{{
  
  "closing_balance": number | null,
  "latest_transaction_date": "YYYY-MM-DD" | null,
  "statement_period": string | null,

  "monthly_average_balance":{{
    "DD-MM-YYYY": number
  }} | null,

  "balance_continuity": string | null
}}

================ FIELD DEFINITIONS =====================




5. latest_transaction_date
   - The most recent transaction date found anywhere in the statement.
   - Format MUST be: YYYY-MM-DD.

6. closing_balance
   - MUST be the balance corresponding to latest_transaction_date.
   - If unclear, return null.

7. monthly_average_balance
   - Extract DAILY CLOSING BALANCES as a FLAT dictionary.
   - Key: DD-MM-YYYY
   - Value: numeric closing balance.
   - Use LAST balance of the date.
   - Do NOT group by month.
   - Do NOT compute averages.

8. balance_continuity
   - Short analytical summary of balance flow.
   - Examples:
     - "Continuous and stable"
     - "Sudden deposit of INR 500000 on 2024-12-28"
   - If insufficient data, return null.

================ EXTRACTION RULES ======================

1. Statements usually cover the LAST 3 MONTHS.
2. Extract balances month-wise when possible.
3. DO NOT compute averages numerically unless balances are explicitly present.
4. If the statement currency is NOT EUR:
   - Convert balances to EUR ONLY if a clear conversion rate is explicitly stated.
   - If no conversion rate is shown, keep the original currency.
5. Do NOT infer missing balances.
6. Do NOT invent dates or amounts.
7. You are multilingual. The statement may not be in English.
8. Return ONLY valid JSON. No additional keys.

================ BANK STATEMENT TEXT ====================
{text}
"""
    )])


BANK_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are an expert financial document extraction engine and bank statement auditor.

CRITICAL INSTRUCTIONS:
- You MUST return ONLY valid JSON.
- You MUST strictly follow the provided JSON schema.
- Do NOT include explanations, comments, markdown, or extra text.
- Do NOT guess or infer missing values.
- If a value is unclear or not present, return null.
- All numeric values must be real numbers (not strings).
- Date formats MUST be respected exactly.
"""
    ),
    (
        "human",
        """
Extract structured bank statement data from the text below.

================ REQUIRED JSON SCHEMA =================

{{
  "account_holder_name": string | null,
  "account_number": string | null,
  "currency": string | null,
  "closing_balance": number | null,
  "latest_transaction_date": "YYYY-MM-DD" | null,
  "statement_period": string | null,

  "monthly_average_balance":{{
    "DD-MM-YYYY": number
  }} | null,

  "balance_continuity": string | null
}}

================ FIELD DEFINITIONS =====================

1. account_holder_name
   - Name of the account holder as printed on the statement.

2. account_number
   - Bank account number or IBAN shown on the statement.

3. currency
   - Currency code or symbol used in the statement (e.g. EUR, USD, INR, BDT).

4. statement_period
   - Period covered by the statement (e.g. "01-Nov-2024 to 12-Feb-2025").

5. latest_transaction_date
   - The most recent transaction date found anywhere in the statement.
   - Format MUST be: YYYY-MM-DD.

6. closing_balance
   - MUST be the balance corresponding to latest_transaction_date.
   - If unclear, return null.

7. daywise_balances
   - Extract DAILY CLOSING BALANCES as a FLAT dictionary.
   - Key: DD-MM-YYYY
      {{date1:amount,date2:amount.....}}
   - Value: numeric closing balance for that date.
   - this is very important to extract try hard to extract
   - If multiple transactions occur on the same date,
     use the LAST balance of that date.
   - Do NOT group by month.
   - Do NOT compute averages.
   - If unclear, return null.


8. balance_continuity
   - Short analytical summary of balance flow.
   - Examples:
     - "Continuous and stable"
     - "Sudden deposit of INR 500000 on 2024-12-28"
   - If insufficient data, return null.

================ EXTRACTION RULES ======================

1. Statements usually cover the LAST 3 MONTHS.
2. Extract balances month-wise when possible.
3. DO NOT compute averages numerically unless balances are explicitly present.
4. If the statement currency is NOT EUR:
   - Convert balances to EUR ONLY if a clear conversion rate is explicitly stated.
   - If no conversion rate is shown, keep the original currency.
5. Do NOT infer missing balances.
6. Do NOT invent dates or amounts.
7. You are multilingual. The statement may not be in English.
8. Return ONLY valid JSON. No additional keys.

================ BANK STATEMENT TEXT ====================
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
)

# llm = ChatOpenAI(
#     model="gpt-5-mini",
#     temperature=0,
#     max_tokens=2000  
# ).with_structured_output(BankExtraction)


def split_pages(text: str) -> list[str]:
    return [p.strip() for p in text.split("--- Page Break ---") if p.strip()]


def chunk_pages(pages: list[str], chunk_size: int = 4) -> list[str]:
    chunks = []
    for i in range(0, len(pages), chunk_size):
        chunks.append("\n\n--- Page Break ---\n\n".join(pages[i:i+chunk_size]))
    return chunks

def run_llm(prompt, text: str) -> dict:
    try:
        result = (prompt | llm).invoke({"text": text})
        raw = result.content
        json_block = extract_json_block(raw)
        return safe_json_loads(json_block)
    
    except Exception as e:
        logger.error("LLM execution failed", exc_info=True)
        raise RuntimeError("LLM extraction failed") from e
    

def merge_primary_and_secondary(
    primary: dict,
    secondary_chunks: list[dict]
) -> dict:
    """
    Safely merges primary and secondary LLM outputs.
    - Never crashes
    - Collects all statement periods
    - Merges balances defensively
    """

    try:
        # ---- Start with a safe base ----
        merged = primary.copy() if isinstance(primary, dict) else {}
    except Exception:
        logger.error("Primary data is not mergeable", exc_info=True)
        merged = {}

    # ---- Normalize monthly_average_balance ----
    try:
        if not isinstance(merged.get("monthly_average_balance"), dict):
            merged["monthly_average_balance"] = {}
    except Exception:
        merged["monthly_average_balance"] = {}

    # ---- Collect all statement periods ----
    try:
        merged["_all_statement_periods"] = []
        if isinstance(merged.get("statement_period"), str):
            merged["_all_statement_periods"].append(merged["statement_period"])
    except Exception:
        merged["_all_statement_periods"] = []

    # ---- Iterate secondary chunks safely ----
    for chunk in secondary_chunks or []:
        if not isinstance(chunk, dict):
            continue

        try:
            # ---- closing_balance (latest wins) ----
            try:
                if chunk.get("closing_balance") is not None:
                    merged["closing_balance"] = chunk["closing_balance"]
            except Exception:
                pass

            # ---- collect statement_periods (DO NOT overwrite) ----
            try:
                if isinstance(chunk.get("statement_period"), str):
                    merged["_all_statement_periods"].append(chunk["statement_period"])
            except Exception:
                pass

            # ---- balance_continuity (overwrite only if present) ----
            try:
                if chunk.get("balance_continuity"):
                    merged["balance_continuity"] = chunk["balance_continuity"]
            except Exception:
                pass

            # ---- merge flat day-wise balances ----
            try:
                balances = chunk.get("monthly_average_balance")
                if isinstance(balances, dict):
                    for date, balance in balances.items():
                        try:
                            merged["monthly_average_balance"][date] = balance
                        except Exception:
                            continue
            except Exception:
                pass

        except Exception:
            logger.warning("Skipping corrupted secondary chunk", exc_info=True)
            continue

    return merged


def extract_bank_statement(text: str) -> dict:

    try:
        page_breaks = text.count("--- Page Break ---")

        # 🟢 CASE 1: Small document (≤ 5 page breaks)
        if page_breaks <= 5:
            logger.info("Processing in SINGLE-PASS mode")
            try:
                data = run_llm(BANK_PROMPT, text)
                return BankExtraction.model_validate(data).model_dump()
            except Exception:
                logger.error("Single-pass extraction failed", exc_info=True)
                return BankExtraction().model_dump()

        # 🟡 CASE 2: Large document → chunking
        logger.info("Processing in CHUNKED mode")

        pages = split_pages(text)
        chunks = chunk_pages(pages, chunk_size=4)

        # First chunk extracts EVERYTHING
        try:
            base_data = run_llm(BANK_PROMPT, chunks[0])
        except Exception:
            logger.error("Primary chunk extraction failed", exc_info=True)
            base_data = {}

        # Other chunks extract balances only
        balance_chunks = []
        for chunk in chunks[1:]:
            try:
                balance_chunks.append(run_llm(BALANCE_PROMPT, chunk))
            except Exception:
                continue  # do not fail pipeline
        
        try:        
            merged = merge_primary_and_secondary(base_data, balance_chunks)
        except Exception:
            logger.critical(
                "Failed during merge_primary_and_secondary()",
                exc_info=True
            )
            # Fallback to empty structure (never crash)
            merged = {}

        try:
            all_periods = merged.pop("_all_statement_periods", [])

            if not isinstance(all_periods, list):
                all_periods = []

            final_period = derive_final_statement_period(all_periods)

            merged["statement_period"] = final_period

        except Exception:
            logger.error(
                "Failed to derive final statement period",
                exc_info=True
            )
            # Preserve whatever period existed (or None)
            merged.setdefault("statement_period", None)
            
        return BankExtraction.model_validate(merged).model_dump()
    except Exception as e:
        logger.critical("Bank statement extraction failed completely", exc_info=True)
        return BankExtraction().model_dump()

        




# def read_txt_file(file_path: str) -> str:
#     with open(file_path, "r", encoding="utf-8") as f:
#         return f.read()
    
    
# data_ = read_txt_file("/Users/pawanpandey/Documents/document-validation/output3.txt")
# output = extract_bank_statement(data_) 
# print(output)




