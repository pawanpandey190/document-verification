from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from typing import Optional
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, wait_exponential, stop_after_attempt
from dotenv import load_dotenv
import os
import logging

load_dotenv()
logger = logging.getLogger(__name__)

class EnglishExtraction(BaseModel):
    test_type: Optional[str] = None # Duolingo | IELTS | TOEFL | PTE
    overall_score: Optional[float] = None
    date_of_test: Optional[str] = None

ENGLISH_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Extract English proficiency test data. Return ONLY valid JSON."),
    ("human", """
Extract the following fields from the text:
- 
- overall_score: The total/overall score as a float
- date_of_test: Date in YYYY-MM-DD format

Rules:
1. Return ONLY the JSON object.
2. If not visible, return null.
3. Dates MUST be in YYYY-MM-DD.

Text:
----------------
{text}
""")
])

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
).with_structured_output(EnglishExtraction)

def extract_english_llm(text: str) -> dict:
    try:
        chain = ENGLISH_PROMPT | llm
        return chain.invoke({"text": text}).model_dump()
    except Exception as e:
        logger.error("LLM English extraction failed", exc_info=True)
        return {
            "test_type": None,
            "overall_score": None,
            "date_of_test": None,
            "error": str(e)
        }
