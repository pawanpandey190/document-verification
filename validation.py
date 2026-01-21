from difflib import SequenceMatcher
from datetime import datetime, date
import re
import logging

logger = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    if not name:
        return ""
    # Remove titles
    for title in ["mr.", "ms.", "mrs.", "dr.", "prof."]:
        name = name.lower().replace(title, "")
    return "".join(name.split())

def names_match(name1: str, name2: str, threshold: float = 0.82) -> bool:
    """
    Fuzzy name match that handles minor OCR errors and titles.
    """
    if not name1 or not name2:
        return False
    
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    
    # Exact match after normalization
    if n1 == n2: return True
    
    # Partial match check (e.g., shorthand names)
    if n1 in n2 or n2 in n1: return True
    
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


# for calculating the average monthly amount in the bank
DATE_FORMATS = [
    "%d-%m-%Y", "%d/%m/%Y", "%d%m%Y",
    "%d-%b-%Y", "%d/%b/%Y", "%d%b%Y",
    "%d-%B-%Y", "%d/%B/%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%b %d %Y", "%B %d %Y"
]

def parse_date_safe(date_str):
    if not isinstance(date_str, str):
        return None

    cleaned = date_str.strip().replace("/", "-").replace(" ", "")

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except Exception:
            continue

    return None

def calculate_monthly_average_balance(daywise_data):
    """
    Converts {date: amount} → {YYYY-MM: average_balance}
    Never crashes.
    """
    try:
        if not isinstance(daywise_data, dict):
            return {}

        monthly_values = {}

        for date_key, amount in daywise_data.items():
            try:
                # ---- parse date ----
                date_obj = parse_date_safe(date_key)
                if not date_obj:
                    continue

                # ---- parse amount ----
                if isinstance(amount, (int, float)):
                    value = float(amount)
                elif isinstance(amount, str) and amount.replace(".", "", 1).isdigit():
                    value = float(amount)
                else:
                    continue

                month_key = date_obj.strftime("%Y-%m")

                monthly_values.setdefault(month_key, []).append(value)

            except Exception:
                continue

        # ---- calculate average ----
        monthly_avg = {}
        for month, values in monthly_values.items():
            try:
                if values:
                    monthly_avg[month] = round(sum(values) / len(values), 2)
            except Exception:
                continue

        return monthly_avg

    except Exception:
        logger.error("Failed to calculate monthly average balance", exc_info=True)
        return {}



def normalize_country(country_name: str) -> str:
    if not country_name:
        return ""
    
    country_map = {
        "uae": "United Arab Emirates",
        "unitedarabemirates": "United Arab Emirates",
        "us": "USA",
        "usa": "USA",
        "unitedstatesofamerica": "USA",
        "uk": "United Kingdom",
        "unitedkingdom": "United Kingdom",
        "ivorycoast": "Côte d'Ivoire",
        "cotedivoire": "Côte d'Ivoire",
    }
    
    # Basic cleanup
    clean_name = "".join(country_name.lower().split())
    
    return country_map.get(clean_name, country_name.title())

FOUNDATION_RULES = {

    # =====================
    # SOUTH ASIA
    # =====================
    "India": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 35,
            "official_pass": 33,
            "french_equivalent": "8/20"
        },
        "cgpa_10": {
            "scale": "0-10",
            "foundation_min": 4.0,
            "official_pass": 4.0,
            "french_equivalent": "8/20"
        }
    },

    "Nepal": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 35,
            "official_pass": 32,
            "french_equivalent": "8/20"
        }
    },

    "Pakistan": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 35,
            "official_pass": 33,
            "french_equivalent": "8/20"
        }
    },

    "Bangladesh": {
        "gpa_5": {
            "scale": "0-5",
            "foundation_min": 2.0,
            "official_pass": 1.0,
            "french_equivalent": "8/20"
        }
    },

    "Sri Lanka": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 40,
            "official_pass": 35,
            "french_equivalent": "8/20"
        }
    },

    # =====================
    # GCC & MENA
    # =====================
    "United Arab Emirates": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 50,
            "official_pass": 50,
            "french_equivalent": "8/20"
        }
    },

    "Saudi Arabia": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 50,
            "official_pass": 50,
            "french_equivalent": "8/20"
        }
    },

    "Qatar": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 45,
            "official_pass": 40,
            "french_equivalent": "8/20"
        }
    },

    "Kuwait": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 50,
            "official_pass": 50,
            "french_equivalent": "8/20"
        }
    },

    "Bahrain": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 50,
            "official_pass": 50,
            "french_equivalent": "8/20"
        }
    },

    "Oman": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 50,
            "official_pass": 50,
            "french_equivalent": "8/20"
        }
    },

    "Egypt": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 50,
            "official_pass": 50,
            "french_equivalent": "8/20"
        }
    },

    # =====================
    # SUB-SAHARAN AFRICA
    # =====================
    "Kenya": {
        "kcse": {
            "scale": "A–E",
            "foundation_min": "D (35%)",
            "official_pass": "D- (30%)",
            "french_equivalent": "8/20"
        }
    },

    "Nigeria": {
        "waec": {
            "scale": "A1–F9",
            "foundation_min": "D7 (45%)",
            "official_pass": "E8 (40%)",
            "french_equivalent": "8/20"
        }
    },

    "Ghana": {
        "wassce": {
            "scale": "A1–F9",
            "foundation_min": "D7 (45%)",
            "official_pass": "E8 (40%)",
            "french_equivalent": "8/20"
        }
    },

    "South Africa": {
        "nsc": {
            "scale": "Level 1–7",
            "foundation_min": "Level 3 (40%)",
            "official_pass": "Level 2 (30%)",
            "french_equivalent": "8/20"
        }
    },

    # =====================
    # FRANCOPHONE AFRICA
    # =====================
    "Morocco": {
        "french_20": {
            "scale": "0-20",
            "foundation_min": 8,
            "official_pass": 10,
            "french_equivalent": "8/20"
        }
    },

    "Algeria": {
        "french_20": {
            "scale": "0-20",
            "foundation_min": 8,
            "official_pass": 10,
            "french_equivalent": "8/20"
        }
    },

    "Tunisia": {
        "french_20": {
            "scale": "0-20",
            "foundation_min": 8,
            "official_pass": 10,
            "french_equivalent": "8/20"
        }
    },

    "Senegal": {
        "french_20": {
            "scale": "0-20",
            "foundation_min": 8,
            "official_pass": 10,
            "french_equivalent": "8/20"
        }
    },

    "Côte d'Ivoire": {
        "french_20": {
            "scale": "0-20",
            "foundation_min": 8,
            "official_pass": 10,
            "french_equivalent": "8/20"
        }
    },

    "Cameroon": {
        "french_20": {
            "scale": "0-20",
            "foundation_min": 8,
            "official_pass": 10,
            "french_equivalent": "8/20"
        }
    },

    # =====================
    # ASIA–PACIFIC
    # =====================
    "China": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 60,
            "official_pass": 60,
            "french_equivalent": "8/20"
        }
    },

    "Vietnam": {
        "gpa_10": {
            "scale": "0-10",
            "foundation_min": 4.0,
            "official_pass": 5.0,
            "french_equivalent": "8/20"
        }
    },

    "Philippines": {
        "gpa_5": {
            "scale": "1.0–5.0",
            "foundation_min": 3.0,
            "official_pass": 3.0,
            "french_equivalent": "8/20"
        }
    },

    "Indonesia": {
        "gpa_4": {
            "scale": "0-4.0",
            "foundation_min": 2.0,
            "official_pass": 2.0,
            "french_equivalent": "8/20"
        }
    },

    "Malaysia": {
        "spm": {
            "scale": "A+–G",
            "foundation_min": "E (40%)",
            "official_pass": "E (40%)",
            "french_equivalent": "8/20"
        }
    },

    # =====================
    # EUROPE & LATAM
    # =====================
    "Russia": {
        "grade_5": {
            "scale": "1–5",
            "foundation_min": 3,
            "official_pass": 3,
            "french_equivalent": "8/20"
        }
    },

    "Brazil": {
        "gpa_10": {
            "scale": "0-10",
            "foundation_min": 4.0,
            "official_pass": 5.0,
            "french_equivalent": "8/20"
        }
    },

    "Mexico": {
        "gpa_10": {
            "scale": "0-10",
            "foundation_min": 5.0,
            "official_pass": 6.0,
            "french_equivalent": "8/20"
        }
    },

    "Turkey": {
        "percentage": {
            "scale": "0-100",
            "foundation_min": 45,
            "official_pass": 45,
            "french_equivalent": "8/20"
        }
    },

    # =====================
    # INTERNATIONAL CURRICULA
    # =====================
    "International Baccalaureate": {
        "ib_diploma": {
            "scale": "0-45",
            "foundation_min": 24,
            "french_equivalent": "8/20"
        }
    },

    "Cambridge A Levels": {
        "a_levels": {
            "scale": "A*–E",
            "foundation_min": "EEE",
            "french_equivalent": "8/20"
        }
    },

    "Cambridge IGCSE": {
        "igcse": {
            "scale": "A*–G",
            "foundation_min": "C (5 subjects)",
            "french_equivalent": "8/20"
        }
    },

    "American Curriculum": {
        "high_school_gpa": {
            "scale": "0-4.0",
            "foundation_min": 2.0,
            "french_equivalent": "8/20"
        }
    }
}

from datetime import datetime

def validate_degree_marks(extracted_data: dict) -> dict:
    """
    Validates student marks against FOUNDATION admission criteria
    using normalized country-wise rules.
    """

    student_name = extracted_data.get("name_of_student")
    country = normalize_country(extracted_data.get("country"))
    grading_type = extracted_data.get("grading_type")
    score = extracted_data.get("cumulative_score")
    semester_marks = extracted_data.get("semester_wise_marks")
    Degree_country_evidence = extracted_data.get("country_evidence")

    if not country or not grading_type or score is None:
        return {
            "status": "FAILED",
            "semester_marks":semester_marks,
            "Degree_country_evidence":Degree_country_evidence,
            "eligible": False,
            "reason": "Missing required academic information"
        }

    # ---- Graduation Year sanity check ----
    grad_year = extracted_data.get("graduation_year")
    current_year = datetime.now().year
    if grad_year and grad_year > current_year:
        return {
            "status": "FAILED",
            "semester_marks":semester_marks,
            "Degree_country_evidence":Degree_country_evidence,
            "eligible": False,
            "reason": f"Invalid graduation year ({grad_year}) – document appears future-dated"
        }

    # ---- Load country rules ----
    country_rules = FOUNDATION_RULES.get(country)
    if not country_rules:
        return {
            "status": "FAILED",
            "semester_marks":semester_marks,
            "Degree_country_evidence":Degree_country_evidence,
            "eligible": False,
            "reason": f"No foundation admission rules configured for {country}"
        }

    grading_rule = country_rules.get(grading_type)
    if not grading_rule:
        return {
            "status": "FAILED",
            "semester_marks":semester_marks,
            "Degree_country_evidence":Degree_country_evidence,
            "eligible": False,
            "reason": f"Unsupported grading system '{grading_type}' for {country}"
        }

    foundation_min = grading_rule.get("foundation_min")
    french_equivalent = grading_rule.get("french_equivalent", "8/20")
    scale = grading_rule.get("scale")

    # ---- Numeric grading systems (percentage / GPA / CGPA) ----
    if isinstance(foundation_min, (int, float)):
        if not isinstance(score, (int, float)):
            return {
                "status": "FAILED",
                "eligible": False,
                "reason": "Invalid numeric score format",
                "semester_marks":semester_marks,
                "Degree_country_evidence":Degree_country_evidence,
                "details": {
                    "expected_scale": scale,
                    "received_score": score
                }
            }

        if score >= foundation_min:
            return {
                "status": "PASSED",
                "eligible": True,
                "french_equivalent": french_equivalent,
                "semester_marks":semester_marks,
                "Degree_country_evidence":Degree_country_evidence,
                "details": {
                    "name": student_name,
                    "country": country,
                    "grading_type": grading_type,
                    "score": score,
                    "foundation_min": foundation_min,
                    "scale": scale
                }
            }

        return {
            "status": "FAILED",
            "eligible": False,
            "reason": "Score below foundation minimum",
            "semester_marks":semester_marks,
            "Degree_country_evidence":Degree_country_evidence,
            "details": {
                "name": student_name,
                "country": country,
                "grading_type": grading_type,
                "score": score,
                "foundation_min": foundation_min,
                "scale": scale
            }
        }

    # ---- Non-numeric grading systems (WAEC, KCSE, A-Levels, SPM, etc.) ----
    # These are evaluated by direct match or rank-based acceptance
    if isinstance(foundation_min, str):
        if str(score).strip() == foundation_min.strip():
            return {
                "status": "PASSED",
                "eligible": True,
                "french_equivalent": french_equivalent,
                "semester_marks":semester_marks,
                "Degree_country_evidence":Degree_country_evidence,
                "details": {
                    "name": student_name,
                    "country": country,
                    "grading_type": grading_type,
                    "grade": score,
                    "foundation_min": foundation_min,
                    "scale": scale
                }
            }

        return {
            "status": "FAILED",
            "eligible": False,
            "reason": "Grade below foundation minimum",
            "semester_marks":semester_marks,
            "Degree_country_evidence":Degree_country_evidence,
            "details": {
                "name": student_name,
                "country": country,
                "grading_type": grading_type,
                "grade": score,
                "foundation_min": foundation_min,
                "scale": scale
            }
        }


def find_low_balance_days(monthly_balances: dict, threshold: float = 7500) -> dict:
    """
    Returns month-wise dates where balance is below the threshold.

    Output format:
    {
        "YYYY-MM": {
            "YYYY-MM-DD": balance
        }
    }
    """
    low_balance_map = {}

    if not monthly_balances:
        return low_balance_map

    for month, daily_data in monthly_balances.items():
        for date, amount in daily_data.items():
            if amount is not None and amount < threshold:
                low_balance_map.setdefault(month, {})[date] = amount

    return low_balance_map


def validate_bank(bank: dict, degree_name: str) -> dict:
    reasons = []

    if not bank:
        return {
            "status": "Not Approved",
            "reason": "Bank statement not uploaded"
        }

    bank_name = bank.get("account_holder_name")
    balance = bank.get("closing_balance")
    currency = bank.get("currency")
    period = bank.get("statement_period")
    raw_daywise = bank.get("monthly_average_balance")
    print(raw_daywise,degree_name,"bank validation")
    
    # DERIVE MONTHLY AVERAGE SAFELY
    monthly_average_balances = calculate_monthly_average_balance(raw_daywise)
    


    # ---- Name match ----
    

    # ---- Currency ----
    if currency != "EUR":
        reasons.append("Bank balance is not in EUR")

    # ---- Balance check ----
    if balance is None:
        reasons.append("Closing balance not found in bank statement")
    

    # ---- 3-month consistency ----
    if not period:
        reasons.append("3-month bank statement period not detected")


    # low_balance_days = find_low_balance_days(monthly_average_balances, threshold=7500)

    # if low_balance_days:
    #     reasons.append("Balance dropped below 7,500 EUR on some dates")

    if reasons:
        return {
            "status": "Not Approved",
            "reason": "; ".join(reasons),
            "balance_continuity": bank.get("balance_continuity", "N/A"),
            "monthly_average_balance": monthly_average_balances
        }

    return {
        "status": "Approved",
        "reason": "Bank statement validation passed",
        "balance_continuity": bank.get("balance_continuity", "Continuous"),
        "monthly_average_balance": monthly_average_balances
    }






def validate_passport(passport: dict, degree_name: str) -> dict:
    reasons = []

    if not passport:
        return {
            "status": "Not Approved",
            "reason": "Passport not uploaded"
        }

    passport_name = passport.get("name")
    dob = passport.get("date_of_birth")
    expiry = passport.get("expiry_date")

    # ---- Name match ----
    if not names_match(degree_name, passport_name):
        reasons.append(
            "Name mismatch between degree certificate and passport (wrong document uploaded)"
        )

    # ---- DOB & Age ----
    if not dob:
        reasons.append("Date of birth missing in passport")
    else:
        dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
        age = (date.today() - dob_date).days // 365
        if age < 18:
            reasons.append("Applicant age is below 18 years")

    # ---- Passport validity ----
    if not expiry:
        reasons.append("Passport expiry date missing")
    else:
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        # Requirement: 2 years validity from today
        days_left = (expiry_date - date.today()).days
        if days_left < 730:
            reasons.append(f"Passport validity is less than 2 years ({days_left} days remaining)")

    if reasons:
        return {
            "status": "Not Approved",
            "reason": "; ".join(reasons)
        }

    return {
        "status": "Approved",
        "reason": "Passport validation passed"
    }
