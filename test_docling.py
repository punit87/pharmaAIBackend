import sys
import json

def test_imports():
    try:
        import numpy
        import pandas
        import PIL
        import pytesseract
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
