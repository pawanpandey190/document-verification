"""
Simplified orientation test - just checks if portrait mode is needed
"""

import sys
import os
from PIL import Image
from pdf2image import convert_from_path

def simple_orientation_test(file_path: str):
    """
    Simple test: just ensure passport is in portrait mode (height > width)
    """
    try:
        if not os.path.exists(file_path):
            print(f"❌ Error: File not found: {file_path}")
            return
        
        # Load image
        if file_path.lower().endswith('.pdf'):
            print("📥 Converting PDF to image...")
            images = convert_from_path(file_path, dpi=200)
            img = images[0]
        else:
            img = Image.open(file_path)
        
        print(f"\n📏 Original size: {img.size[0]}x{img.size[1]}")
        
        width, height = img.size
        
        if height > width:
            print("✅ Already in portrait mode - no rotation needed")
            corrected = img
        else:
            print("🔄 Converting to portrait mode - rotating 90°")
            corrected = img.rotate(-90, expand=True)
            print(f"📏 New size: {corrected.size[0]}x{corrected.size[1]}")
        
        # Save
        base_name = os.path.splitext(file_path)[0]
        output_path = f"{base_name}_simple_corrected.jpg"
        corrected.save(output_path, quality=95)
        print(f"\n💾 Saved to: {output_path}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_simple_orientation.py <file_path>")
        sys.exit(1)
    
    simple_orientation_test(sys.argv[1])
