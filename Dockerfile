# RAG-Anything with Docling parser
# Multi-stage build for optimized caching
FROM python:3.11-slim AS base

# Build arguments
ARG RAG_PARSER=docling

# ============================================
# System Dependencies Stage
# ============================================
FROM base AS system-deps

# Install all system dependencies in one layer
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ============================================
# Python Dependencies Stage
# ============================================
FROM system-deps AS python-deps

# Install uv first (cached layer)
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Install Python packages in order of stability (most stable first)
# This allows better layer caching when requirements change
RUN pip install --no-cache-dir pytesseract opencv-python-headless pillow

# Install RAG-Anything (large package, install separately for better caching)
RUN pip install --no-cache-dir 'raganything[all]'

# Install parser based on build argument (conditional layer)
RUN if [ "$RAG_PARSER" = "docling" ]; then \
        pip install --no-cache-dir docling; \
    else \
        pip install --no-cache-dir mineru; \
    fi

# ============================================
# Final Runtime Stage
# ============================================
FROM python-deps AS runtime

# Create entrypoint script (cached layer)
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

# Set environment variables for better performance
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# Expose port for container orchestration
EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-c", "import raganything; print('RAG-Anything is ready!')"]