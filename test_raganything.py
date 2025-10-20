import sys
import traceback

def test_raganything():
    try:
        print("Testing RAG-Anything import...")
        import raganything
        print("✅ RAG-Anything imported successfully")
        
        print("Testing RAGAnything class...")
        from raganything import RAGAnything
        print("✅ RAGAnything class imported successfully")
        
        print("Testing basic initialization...")
        # Test basic initialization (without API key for now)
        rag = RAGAnything()
        print("✅ RAGAnything initialized successfully")
        
        print("✅ All RAG-Anything tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ RAG-Anything test failed: {e}")
        print(f"Error type: {type(e).__name__}")
        print("Full traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting RAG-Anything test...")
    success = test_raganything()
    if success:
        print("✅ RAG-Anything test completed successfully!")
        sys.exit(0)
    else:
        print("❌ RAG-Anything test failed!")
        sys.exit(1)
