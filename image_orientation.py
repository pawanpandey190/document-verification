"""
Image Orientation Detection and Correction Module
Specifically designed for passport image preprocessing before Textract
"""

import os
import logging
from PIL import Image, ImageOps
import tempfile
import io

logger = logging.getLogger(__name__)

def detect_orientation_by_text_pil(image: Image.Image) -> int:
    """
    Detects orientation by trying OCR at different angles using Textract.
    Works with PIL Image objects directly.
    Returns the angle with maximum text detection.
    """
    try:
        import boto3
        from textract_extraction import get_textract_client
        
        client = get_textract_client()
        best_angle = 0
        max_confidence = 0
        scores = {}  # Store scores for all angles
        
        logger.info("Detecting orientation using text analysis...")
        
        # Try each rotation angle
        for angle in [0, 90, 180, 270]:
            try:
                # Rotate image
                if angle != 0:
                    test_img = image.rotate(-angle, expand=True)
                else:
                    test_img = image
                
                # Convert to bytes
                img_byte_arr = io.BytesIO()
                test_img.save(img_byte_arr, format='JPEG', quality=85)
                image_bytes = img_byte_arr.getvalue()
                
                # Quick Textract detection
                response = client.detect_document_text(Document={'Bytes': image_bytes})
                
                # Extract text lines
                blocks = response.get('Blocks', [])
                lines = [b for b in blocks if b.get('BlockType') == 'LINE']
                
                # Base Score: Text Confidence (Max 50)
                avg_confidence = sum(b.get('Confidence', 0) for b in lines) / max(len(lines), 1)
                score = avg_confidence / 2
                
                # Bonus 1: Portrait Mode (+50)
                width, height = test_img.size
                if height > width:
                    score += 50
                
                # Bonus 2: Layout Heuristics - STRICT MRZ CHECK
                # MRZ is the most reliable indicator. It MUST be at the bottom.
                keyword_bonus = 0
                for line in lines:
                    text = line.get('Text', '').upper()
                    bbox = line.get('Geometry', {}).get('BoundingBox', {})
                    top = bbox.get('Top', 0) # 0 is top, 1 is bottom
                    
                    # Heuristic A: "PASSPORT" title should be in top 50%
                    if "PASSPORT" in text and top < 0.5:
                        keyword_bonus += 20
                    
                    # Heuristic B: MRZ (contains <<) should be in bottom 50% (Strict)
                    if "<<" in text and len(text) > 10:
                        if top > 0.5:
                            keyword_bonus += 200 # Massive bonus for MRZ at bottom
                        else:
                            keyword_bonus -= 100 # Penalty for MRZ at top (upside down)
                
                score += keyword_bonus
                scores[angle] = score
                
                logger.debug(f"Angle {angle}°: {len(lines)} lines, Conf={avg_confidence:.1f}%, Bonus={keyword_bonus}, Score={score:.1f}")
                
            except Exception as e:
                logger.warning(f"Error testing angle {angle}°: {e}")
                scores[angle] = -999 # Fail this angle
                continue
        
        # Determine winner
        best_angle = max(scores, key=scores.get)
        max_score = scores[best_angle]
        original_score = scores.get(0, 0)
        
        # Only rotate if improvement is significant (10 points)
        if best_angle != 0 and (max_score - original_score) > 10:
            logger.info(f"Text-based detection: Best orientation is {best_angle}° (Score: {max_score:.1f} vs {original_score:.1f})")
            return best_angle
        
        return 0
        
    except Exception as e:
        logger.error(f"Text-based orientation detection failed: {e}")
        return 0


def auto_correct_image_orientation(image: Image.Image) -> Image.Image:
    """
    Automatically detects and corrects image orientation for a PIL Image.
    
    Strategy:
    1. Try EXIF metadata first (fast)
    2. If EXIF fails or returns 0, use text-based detection (slower but reliable)
    3. Rotate image if needed (Uses high quality settings)
    
    Returns: Corrected PIL Image object
    """
    try:
        logger.info("🔄 Checking passport image orientation...")
        
        # Step 1: Try EXIF
        angle = 0
        try:
            exif = image.getexif()
            if exif:
                orientation = exif.get(274, 1)
                orientation_map = {
                    1: 0,    # Normal
                    3: 180,  # Upside down
                    6: 270,  # Rotated 90° CW
                    8: 90    # Rotated 90° CCW
                }
                angle = orientation_map.get(orientation, 0)
                if angle != 0:
                    logger.info(f"EXIF orientation detected: {orientation} -> Rotating {angle}°")
        except Exception as e:
            logger.debug(f"Could not read EXIF data: {e}")
        
        # Step 2: If EXIF didn't help, use text-based detection
        if angle == 0:
            logger.info("No EXIF orientation found, using text-based detection...")
            angle = detect_orientation_by_text_pil(image)
        
        # Step 3: Rotate if needed
        if angle != 0:
            # High quality rotation
            corrected = image.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
            logger.info(f"✅ Image orientation corrected: {angle}° rotation applied")
            return corrected
        else:
            logger.info("✅ Image orientation is correct, no rotation needed")
            return image
            
    except Exception as e:
        logger.error(f"Orientation correction failed: {e}", exc_info=True)
        return image  # Return original on any failure
