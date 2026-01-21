

import pandas as pd
from word_automation import generate_letters
def build_final_student_row(student_output) -> dict:
    """
    Builds one Excel row safely.
    NEVER crashes, even if wrong data is passed.
    """

    # -----------------------------
    # HARD GUARD (CRITICAL)
    # -----------------------------
    if not isinstance(student_output, dict):
        return {
            "name": "Invalid student data",
            "passport_validation": "Not Approved",
            "degree_validation": "Not Approved",
            "bank_statement_validation": "Not Approved",
            "final_status": "Not Approved",
            "reason": f"Invalid student_output type: {type(student_output).__name__}"
        }

    certificate = student_output.get("certificate") or {}
    passport = student_output.get("passport") or {}
    bank = student_output.get("bank_statement") or {}
    english = student_output.get("english_test") or {}
    validation = student_output.get("validation") or {}

    # -----------------------------
    # Name handling
    # -----------------------------
    degree_name = certificate.get("name_of_student") or passport.get("name") or "Name not extracted"
    passport_name = passport.get("name") or "Name not extracted"
    bank_name = bank.get("account_holder_name") or "Name not extracted"

    # -----------------------------
    # Passport Details
    # -----------------------------
    dob = passport.get("date_of_birth", "N/A")
    passport_no = passport.get("passport_number", "N/A")
    passport_expiry = passport.get("expiry_date", "N/A")
    nationality = passport.get("nationality", "N/A")

    # Calculate age if DOB exists
    age = "N/A"
    if dob and dob != "N/A":
        try:
            from datetime import datetime, date
            dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
            age = (date.today() - dob_date).days // 365
        except:
            pass

    # -----------------------------
    # Academic Details
    # -----------------------------
    institution = certificate.get("institution", "N/A")
    qualification = certificate.get("qualification", "N/A")
    degree_score = certificate.get("cumulative_score", "N/A")
    grading_type = certificate.get("grading_type", "N/A")
    country = certificate.get("country", "N/A")

    # -----------------------------
    # Bank Details
    # -----------------------------
    bank_balance = bank.get("closing_balance", "N/A")
    currency = bank.get("currency", "N/A")
    statement_period = bank.get("statement_period", "N/A")

    # -----------------------------
    # English Test Details
    # -----------------------------
    eng_test = english.get("test_type", "N/A")
    eng_score = english.get("overall_score", "N/A")

    # -----------------------------
    # Validation Statuses & Reasons (CONSOLIDATED)
    # -----------------------------
    degree_val = validation.get("degree") or {}
    degree_tag = "Approved" if degree_val.get("status") == "PASSED" else "Not Approved"
    degree_text = degree_val.get("reason", "Validation passed")
    degree_validation = f"{degree_tag}: {degree_text}"
    semester_marks = degree_val.get("semester_marks","not extracted")
    Degree_country_evidence = degree_val.get("Degree_country_evidence","not extracted")
    

    passport_val = validation.get("passport") or {}
    passport_tag = passport_val.get("status", "Not Approved")
    passport_text = passport_val.get("reason", "Validation passed")
    passport_validation = f"{passport_tag}: {passport_text}"

    bank_val = validation.get("bank") or {}
    bank_tag = bank_val.get("status", "Not Approved")
    monthly_average_balance = bank_val.get("monthly_average_balance","no low balance days")
    bank_text = bank_val.get("reason", "Validation passed")
    bank_validation = f"{bank_tag}: {bank_text}"

    # English Validation (Simple check if detected)
    english_tag = "Approved" if english.get("test_type") else "Not Approved"
    english_text = "English test detected" if english_tag == "Approved" else "English test not detected or uploaded"
    english_validation = f"{english_tag}: {english_text}"

    # Final Status Logic
    reasons = []
    if degree_tag == "Not Approved":
        reasons.append(f"Degree: {degree_text}")
    if passport_tag == "Not Approved":
        reasons.append(f"Passport: {passport_text}")
    if bank_tag == "Not Approved":
        reasons.append(f"Bank: {bank_text}")

    final_status = "Approved" if not reasons else "Not Approved"

    # Final Reason Consolidation
    all_validation_results = [
        f"Passport: {passport_validation}",
        f"Degree: {degree_validation}",
        f"Bank: {bank_validation}",
        f"English: {english_validation}"
    ]

    # French Equivalence
    french_equiv = degree_val.get("french_equivalent", "N/A")

    # -----------------------------
    # Selected Files
    # -----------------------------
    selected_files = student_output.get("selected_files") or {}

    # Bank Continuity
    bank_continuity = bank_val.get("balance_continuity", "N/A")

    return {
        # passport data
        "Passport Holder Name": passport_name,
        "Nationality": nationality,
        "Passport No": passport_no,
        "Passport Expiry": passport_expiry,
        "DOB": dob,
        "Age": age,
        "Passport File Name": selected_files.get("passport", "N/A"),
        "Passport Verification Status":passport_tag,
        "Passport Verdict Reason":passport_text,

        # Degree data
        "Degree Holder Name": degree_name,
        "Semester Wise Marks" :semester_marks,
        "Cumulative Score": f"{degree_score} ({grading_type})" if degree_score != "N/A" else "N/A",
        "Course Name": qualification,
        "Institution Name": institution,
        "Institution Country": country,
        "Institution Country Evidence":Degree_country_evidence,
        "French Equivalence": french_equiv,
        "Degree File Name": selected_files.get("highest_academic", "N/A"),
        "Qualification Verfification Status":degree_tag,
        "Qualification Verdict Reason":degree_text,
        
        # Bank Balance
        "Account Holder Name": bank_name,
        "Closing Bank Balance": f"{bank_balance} {currency}" if bank_balance != "N/A" else "N/A",
        "Monthly Average Bank Balance":monthly_average_balance,
        "Balance Continuity Status": bank_continuity,
        "Statement Period": statement_period,
        "Bank File Name": selected_files.get("bank_statement", "N/A"),
        "Bank Statment Verificatin Status":bank_tag,
        "Bank Statment Verdict Reason":bank_text,


        # english test
        "English Test": eng_test,
        "English Score": eng_score,
        "English File": selected_files.get("english_test", "N/A"),
        "Final Status": final_status,
        "Detailed Reason": " | ".join(all_validation_results)
    }

def generate_excel_for_students(students_data: dict, output_file: str = "student_validation_report.xlsx"):
    """
    Takes a dictionary of { "student_name": {data} } and creates an Excel report.
    """
    rows = []
    for name, data in students_data.items():
        rows.append(build_final_student_row(data))

    df = pd.DataFrame(rows)
    
    # Ensure columns are in a nice order
    all_columns = [
        "Passport Holder Name","Nationality", "Passport No","Passport Expiry", "DOB", "Age", "Passport File Name", "Passport Verification Status","Passport Verdict Reason",
        "Degree Holder Name", "Semester Wise Marks", "Cumulative Score", "Course Name","Institution Name","Institution Country","Institution Country Evidence","French Equivalence","Degree File Name","Qualification Verfification Status","Qualification Verdict Reason",
        "Account Holder Name", "Monthly Average Bank Balance","Closing Bank Balance","Statement Period", "Balance Continuity Status", "Bank File Name", "Bank Statment Verificatin Status", "Bank Statment Verdict Reason",
        "English Test", "Bank Continuity", "Statement Period", "Bank File",
        "English Test", "English Score", "English File",
        "Final Status", "Detailed Reason"
    ]
    
    # Only keep columns that actually exist in the DataFrame
    existing_columns = [col for col in all_columns if col in df.columns]
    df = df[existing_columns]

    df.to_excel(output_file, index=False)
    generate_letters(output_file)
    print(f"✅ Excel file created successfully: {output_file} and Condition letters are also created.")
