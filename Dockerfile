# RAG-Anything with Docling parser
# Use Python base and install Tesseract
FROM python:3.11-slim

# Build arguments
ARG RAG_PARSER=docling

# Install basic system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Tesseract OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Install minimal OpenCV dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Install RAG-Anything from PyPI with all features
RUN pip install 'raganything[all]'

# Install Tesseract Python bindings (minimal OpenCV)
RUN pip install pytesseract opencv-python-headless pillow

# Install parser based on build argument
RUN if [ "$RAG_PARSER" = "docling" ]; then \
        pip install docling; \
    else \
        pip install mineru; \
    fi

# Create a simple entrypoint script
RUN echo '#!/bin/bash\n\
echo "RAG-Anything container ready!"\n\
echo "Parser: ${RAG_PARSER}"\n\
echo "Testing environment..."\n\
python -c "import raganything; print(\"✅ RAG-Anything OK\")"\n\
python -c "import pytesseract; print(\"✅ Tesseract OCR OK\")"\n\
python -c "import cv2; print(\"✅ OpenCV OK\")"\n\
if [ "$RAG_PARSER" = "docling" ]; then\n\
  python -c "import docling; print(\"✅ Docling OK\")"\n\
else\n\
  python -c "import mineru; print(\"✅ Mineru OK\")"\n\
fi\n\
exec "$@"' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-c", "import raganything; print('RAG-Anything is ready!')"]