# RAG-Anything with Docling parser
FROM python:3.11-slim

# Build arguments
ARG RAG_PARSER=docling

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Install RAG-Anything from PyPI with all features
RUN pip install 'raganything[all]' --system

# Install parser based on build argument
RUN if [ "$RAG_PARSER" = "docling" ]; then \
        pip install docling --system; \
    else \
        pip install mineru --system; \
    fi

# Create a simple entrypoint script
RUN echo '#!/bin/bash\n\
echo "RAG-Anything container ready!"\n\
echo "Parser: ${RAG_PARSER}"\n\
echo "Testing environment..."\n\
python -c "import raganything; print(\"✅ RAG-Anything OK\")"\n\
if [ "$RAG_PARSER" = "docling" ]; then\n\
  python -c "import docling; print(\"✅ Docling OK\")"\n\
else\n\
  python -c "import mineru; print(\"✅ Mineru OK\")"\n\
fi\n\
exec "$@"' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-c", "import raganything; print('RAG-Anything is ready!')"]