import sys
import pytesseract
from PIL import Image

def test_tesseract():
    try:
        # Create a simple test image
        img = Image.new("RGB", (100, 30), color="white")
        result = pytesseract.image_to_string(img)
        print("✅ Tesseract working correctly")
        return True
    except Exception as e:
        print(f"❌ Tesseract test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_tesseract()
    sys.exit(0 if success else 1)
