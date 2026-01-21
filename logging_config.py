import logging
import os
from datetime import datetime

def setup_logging(log_dir="logs"):
    """
    Sets up comprehensive logging for the document validation system.
    Creates a timestamped log file and configures formatters.
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Generate timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"validation_{timestamp}.log")
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            # File handler - writes to log file
            logging.FileHandler(log_filename, encoding='utf-8'),
            # Console handler - also prints to console
            logging.StreamHandler()
        ]
    )
    
    # Create a more detailed formatter for file logs
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-25s | %(funcName)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Apply detailed formatter to file handler only
    for handler in logging.root.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.setFormatter(file_formatter)
    
    logger = logging.getLogger(__name__)
    logger.info("="*80)
    logger.info("Document Validation System - Logging Initialized")
    logger.info(f"Log file: {log_filename}")
    logger.info("="*80)
    
    return log_filename
