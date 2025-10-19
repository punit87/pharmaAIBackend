import sys
import traceback

def test_tesseract():
    try:
        print("Testing PIL import...")
        from PIL import Image
        print("✅ PIL imported successfully")
        
        print("Testing pytesseract import...")
        import pytesseract
        print("✅ pytesseract imported successfully")
        
        print("Testing Tesseract installation...")
        version = pytesseract.get_tesseract_version()
        print(f"✅ Tesseract version: {version}")
        
        print("Testing image creation...")
        img = Image.new("RGB", (100, 30), color="white")
        print("✅ Test image created successfully")
        
        print("Testing OCR functionality...")
        result = pytesseract.image_to_string(img)
        print(f"✅ OCR result: '{result}'")
        
        print("✅ All Tesseract tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Tesseract test failed: {e}")
        print(f"Error type: {type(e).__name__}")
        print("Full traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting Tesseract test...")
    success = test_tesseract()
    if success:
        print("✅ Tesseract test completed successfully!")
        sys.exit(0)
    else:
        print("❌ Tesseract test failed!")
        sys.exit(1)
