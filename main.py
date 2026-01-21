import os
import sys
import logging
from dotenv import load_dotenv
from student_orchestration import process_parent_directory
from excel_genration import generate_excel_for_students
from logging_config import setup_logging

# Setup Logging System
log_file = setup_logging()
logger = logging.getLogger(__name__)

def main():
    # Load environment variables
    load_dotenv()
    logger.info("Environment variables loaded")
    
    # 1. Verification of API Key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not found in .env file")
        print("\n❌ ERROR: OPENAI_API_KEY not found in .env file.")
        print("Please ensure your .env file is in the same folder as this application.")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    logger.info("OpenAI API key verified")

    print("\n" + "="*50)
    print("🚀 DOCUMENT VALIDATION SYSTEM STARTED")
    print("="*50)
    logger.info("Document Validation System Started")

    # 2. Set Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    parent_path = os.path.join(base_dir, "data")
    logger.info(f"Base directory: {base_dir}")
    logger.info(f"Data directory: {parent_path}")
    
    if not os.path.exists(parent_path):
        logger.error(f"Data folder not found at: {parent_path}")
        print(f"\n❌ ERROR: 'data' folder not found at: {parent_path}")
        print("Please create a folder named 'data' and put student folders inside it.")
        input("\nPress Enter to exit...")
        sys.exit(1)

    print(f"📂 Scanning Directory: {parent_path}")

    # 3. Process all student folders
    try:
        logger.info("Starting student directory processing")
        results = process_parent_directory(parent_path)
        
        if not results:
            logger.warning("No student folders found or no files processed")
            print("\n⚠️ No student folders found or no files processed.")
        else:
            logger.info(f"Successfully processed {len(results)} students")
            print(f"\n✅ Found and processed {len(results)} students.")

            # 4. Generate Excel report
            report_name = "student_validation_report.xlsx"
            logger.info(f"Generating Excel report: {report_name}")
            generate_excel_for_students(results, output_file=report_name)
            
            report_path = os.path.abspath(report_name)
            logger.info(f"Excel report generated successfully: {report_path}")
            print("\n" + "="*50)
            print("🎉 PROCESSING COMPLETE!")
            print(f"📊 Report Generated: {report_path}")
            print(f"📝 Log File: {log_file}")
            print("="*50)

    except Exception as e:
        logger.critical(f"CRITICAL ERROR during processing: {str(e)}", exc_info=True)
        print(f"\n❌ CRITICAL ERROR during processing: {str(e)}")
        import traceback
        traceback.print_exc()

    logger.info("Validation task finished")
    print("\nValidation task is finished.")
    input("Press Enter to close this window...")

if __name__ == "__main__":
    main()