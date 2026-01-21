from langchain_openai import ChatOpenAI
from pydantic import BaseModel
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


class BankExtraction(BaseModel):
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    closing_balance: Optional[float] = None
    currency: Optional[str] = None
    statement_period: Optional[str] = None
    balance_continuity: Optional[str] = None,
    monthly_average_balance: Optional[
        Dict[str, Dict[str, float]]
    ] = None

     # Description of balance flow (e.g., "Continuous", "Sudden deposit of 5k detected in Dec")


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

  "monthly_average_balance": {{
    "YYYY-MM": {{
      "DD-MM-YYYY": number
    }}
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

7. monthly_average_balance
   - A nested dictionary grouped by MONTH (YYYY-MM).
   - Inside each month, include DAILY CLOSING BALANCES only.
   - Date keys MUST be formatted as DD-MM-YYYY.
   - Values MUST be numeric balances.
   - If multiple transactions occur on the same date, use the LAST balance of that date.
   - If daily balances cannot be confidently identified, return null for this field.

   Example:
   {{
     "2025-02": {{
       "01-02-2025": 2000000.00,
       "11-02-2025": 2034500.00,
       "12-02-2025": 2028875.00
     }},
     "2025-01": {{
       "15-01-2025": 1950000.00,
       "31-01-2025": 1985000.00
     }}
   }}

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
).with_structured_output(BankExtraction)

# llm = ChatOpenAI(
#     model="gpt-5-mini",
#     temperature=0,
#     max_tokens=2000  
# ).with_structured_output(BankExtraction)


def count_tokens(text: str) -> int:
    """
    Rough token counter (1 token ≈ 4 characters for English text)
    This is an approximation; actual tokenization may vary slightly.
    """
    return len(text) // 4

def truncate_text_intelligently(text: str, max_tokens: int = 40000) -> tuple[str, bool]:
    """
    Intelligently truncates text if it exceeds max_tokens.
    Keeps first 50% and last 50% of the allowed tokens to preserve:
    - Account info and early transactions (beginning)
    - Recent transactions and closing balance (end)
    
    Returns: (truncated_text, was_truncated)
    """
    current_tokens = count_tokens(text)
    
    if current_tokens <= max_tokens:
        return text, False
    
    logger.warning(f"Text exceeds {max_tokens} tokens ({current_tokens} tokens). Truncating intelligently...")
    
    # Calculate character limits (tokens * 4 chars per token)
    max_chars = max_tokens * 4
    half_chars = max_chars // 2
    
    # Keep first half and last half
    truncated = text[:half_chars] + "\n\n[... MIDDLE SECTION TRUNCATED ...]\n\n" + text[-half_chars:]
    
    logger.info(f"Truncated from {current_tokens} tokens to ~{count_tokens(truncated)} tokens")
    return truncated, True

def extract_bank_llm(text: str) -> dict:
    """
    Safe LLM invocation with token limit protection.
    """
    try:
        # Check and truncate if needed
        processed_text, was_truncated = truncate_text_intelligently(text, max_tokens=40000)
        
        if was_truncated:
            logger.warning("Bank statement was truncated due to length. Extraction may be partial.")
        
        chain = BANK_PROMPT | llm
        result = chain.invoke({"text": processed_text})
        
        output = result.model_dump()
        
        # Add flag if truncation occurred
        if was_truncated:
            output["extraction_note"] = "Document was truncated due to length"
        
        print(output, "BANK_PROMPT")
        return output
        
    except OutputParserException as e:
        logger.error("LLM JSON parsing failed", exc_info=True)

        # 🚨 Fallback: return empty but valid structure
        return {
            "account_holder_name": None,
            "account_number": None,
            "closing_balance": None,
            "currency": None,
            "statement_period": None,
            "balance_continuity": None,
            "monthly_average_balance": None,
            "llm_error": "Invalid JSON output"
        }

    except Exception as e:
        logger.error("LLM invocation failed", exc_info=True)
        raise RuntimeError("LLM service unavailable")
