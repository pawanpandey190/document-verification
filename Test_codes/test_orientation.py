"""
Test script for image orientation detection and correction.
Tests a single passport image and saves the corrected version.
Supports both image files (JPG, PNG) and PDF files.

Usage:
    python test_orientation.py <path_to_passport_file>

Example:
    python test_orientation.py data/John_Smith/passport.jpg
    python test_orientation.py data/John_Smith/passport.pdf
"""

import sys
import os
from PIL import Image
from pdf2image import convert_from_path 
from image_orientation import auto_correct_image_orientation
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_orientation_correction(file_path: str):
    """
    Test orientation correction on a single image or PDF.
    Saves the corrected image with '_corrected' suffix.
    """
    try:
        # Validate input
        if not os.path.exists(file_path):
            print(f"❌ Error: File not found: {file_path}")
            return
        
        file_lower = file_path.lower()
        is_pdf = file_lower.endswith('.pdf')
        is_image = file_lower.endswith(('.jpg', '.jpeg', '.png'))
        
        if not (is_pdf or is_image):
            print(f"❌ Error: File must be JPG, JPEG, PNG, or PDF")
            return
        
        print("="*60)
        print("🔍 PASSPORT ORIENTATION TEST")
        print("="*60)
        print(f"📁 Input file: {file_path}")
        print(f"📄 File type: {'PDF' if is_pdf else 'Image'}")
        
        # Load the image (convert PDF if needed)
        if is_pdf:
            print("\n📥 Converting PDF to image...")
            images = convert_from_path(file_path, dpi=200)
            print(f"✅ PDF converted: {len(images)} page(s) found")
            
            if len(images) == 0:
                print("❌ Error: No pages found in PDF")
                return
            
            # Use first page for testing
            original_image = images[0]
            print(f"📄 Using page 1 for testing")
            
            # Save the extracted page as image for comparison
            base_name = os.path.splitext(file_path)[0]
            extracted_path = f"{base_name}_page1.jpg"
            original_image.save(extracted_path, quality=95)
            print(f"💾 Extracted page saved to: {extracted_path}")
        else:
            print("\n📥 Loading image...")
            original_image = Image.open(file_path)
        
        print(f"✅ Image loaded: {original_image.size[0]}x{original_image.size[1]} pixels")
        
        # Test orientation correction
        print("\n🔄 Testing orientation detection and correction...")
        print("📸 Ensuring passport photo is upright (vertical orientation)...")
        
        # Import Textract for text detection
        import boto3
        from textract_extraction import get_textract_client
        import io
        
        client = get_textract_client()
        
        # For passports, we need to:
        # 1. Ensure portrait mode (height > width)
        # 2. Ensure text is readable (not upside down)
        
        best_orientation = None
        max_score = 0
        scores = {}  # Store all scores
        
        print("\n🔍 Testing all orientations with layout analysis...")
        
        for angle in [0, 90, 180, 270]:
            if angle == 0:
                test_img = original_image
            else:
                test_img = original_image.rotate(-angle, expand=True)
            
            width, height = test_img.size
            is_portrait = height > width
            
            # Convert to bytes for Textract
            img_byte_arr = io.BytesIO()
            test_img.save(img_byte_arr, format='JPEG', quality=85)
            image_bytes = img_byte_arr.getvalue()
            
            # Quick text detection
            try:
                response = client.detect_document_text(Document={'Bytes': image_bytes})
                blocks = response.get('Blocks', [])
                lines = [b for b in blocks if b.get('BlockType') == 'LINE']
                
                # Base Score: Text Confidence
                avg_confidence = sum(b.get('Confidence', 0) for b in lines) / max(len(lines), 1)
                score = avg_confidence / 2  # Max 50 points from confidence
                
                # Bonus 1: Portrait Mode (+50)
                if is_portrait:
                    score += 50
                
                # Bonus 2: Layout Heuristics - STRICT MRZ CHECK
                # MRZ is the most reliable indicator. It MUST be at the bottom.
                keyword_bonus = 0
                mrz_found = False
                
                print(f"  --- Analyzing {angle}° ---")
                
                for line in lines:
                    text = line.get('Text', '').upper()
                    bbox = line.get('Geometry', {}).get('BoundingBox', {})
                    top = bbox.get('Top', 0) # 0 is top, 1 is bottom
                    
                    # Debug print for potentially relevant lines
                    if "PASSPORT" in text or "<<" in text or "P<" in text:
                        print(f"    Line: '{text}' at Top={top:.2f}")
                    
                    # Heuristic A: "PASSPORT" title should be in top 50%
                    if "PASSPORT" in text and top < 0.5:
                        keyword_bonus += 20
                        # print(f"    found 'PASSPORT' at top ({top:.2f})")
                    
                    # Heuristic B: MRZ (contains <<) should be in bottom 50% (Strict)
                    # MRZ presence is the strongest signal
                    if "<<" in text and len(text) > 10:
                        if top > 0.5:
                            keyword_bonus += 200 # Massive bonus for MRZ at bottom
                            mrz_found = True
                            print(f"    ✅ MATCH: MRZ at bottom ({top:.2f})")
                        else:
                            keyword_bonus -= 100 # Penalty for MRZ at top (upside down)
                            print(f"    ❌ MISMATCH: MRZ at top ({top:.2f})")
                
                score += keyword_bonus
                scores[angle] = score
                
                print(f"  {angle}° rotation: {width}x{height} | {len(lines)} lines | Bonus: {keyword_bonus} | TOTAL: {score:.1f}")
                
                if score > max_score:
                    max_score = score
                    best_orientation = angle
                    
            except Exception as e:
                print(f"  {angle}° rotation: Error - {str(e)}")
                scores[angle] = -999 # Fail this angle
        
        # Apply best rotation
        # Use a small threshold to favor 0° if scores are very close (e.g. difference < 5)
        # But allow rotation if layout heuristics clearly point to another angle
        original_score = scores.get(0, 0)
        improvement = max_score - original_score
        
        print(f"\n📊 Score Summary:")
        print(f"   Original (0°): {original_score:.1f}")
        print(f"   Best ({best_orientation}°): {max_score:.1f}")
        print(f"   Improvement: +{improvement:.1f} points")
        
        if best_orientation == 0 or improvement < 10:
            corrected_image = original_image
            print(f"\n✅ No rotation needed - image is already correctly oriented")
            if improvement > 0:
                print(f"   (Improvement of {improvement:.1f} points is below 10-point threshold)")
        else:
            corrected_image = original_image.rotate(-best_orientation, expand=True)
            print(f"\n🔄 Applied {best_orientation}° rotation for correct orientation")
            print(f"   Score improved from {original_score:.1f} to {max_score:.1f}")
        
        # Save corrected image
        base_name = os.path.splitext(file_path)[0]
        output_path = f"{base_name}_corrected.jpg"
        
        print(f"\n💾 Saving corrected image to: {output_path}")
        corrected_image.save(output_path, quality=95)
        
        # Show results
        print("\n" + "="*60)
        print("✅ TEST COMPLETE")
        print("="*60)
        print(f"📁 Original: {file_path}")
        if is_pdf:
            print(f"📁 Extracted: {extracted_path}")
        print(f"📁 Corrected: {output_path}")
        print(f"📏 Original size: {original_image.size[0]}x{original_image.size[1]}")
        print(f"📏 Corrected size: {corrected_image.size[0]}x{corrected_image.size[1]}")
        
        if original_image.size != corrected_image.size:
            print("\n⚠️ Note: Image dimensions changed (rotation was applied)")
        else:
            print("\n✅ Note: No rotation was needed (image was already correct)")
        
        print("\n💡 Tip: Open the corrected image to verify orientation")
        if is_pdf:
            print("💡 Compare: extracted page vs corrected image")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print(f"\n❌ Test failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_orientation.py <path_to_passport_file>")
        print("\nSupports: JPG, JPEG, PNG, and PDF files")
        print("\nExamples:")
        print("  python test_orientation.py data/John_Smith/passport.jpg")
        print("  python test_orientation.py data/John_Smith/passport.pdf")
        print("  python test_orientation.py test_passport.png")
        sys.exit(1)
    
    file_path = sys.argv[1]
    test_orientation_correction(file_path)
