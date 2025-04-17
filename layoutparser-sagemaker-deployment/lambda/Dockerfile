FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies
RUN dnf -y install \
    nss glibc fontconfig cups-libs libX11 libXext libX11-xcb libxcb \
    mesa-libGL libXrender libSM libICE libXinerama cairo cairo-devel libxslt \
    wget tar java-17-amazon-corretto-devel findutils \
    gcc gcc-c++ make libffi-devel python3-devel xz git \
    poppler-utils autoconf automake libtool pkgconfig \
    glibc-langpack-en glibc-locale-source glibc-devel \
    libtiff libtiff-devel \
    && dnf clean all && rm -rf /var/cache/dnf

# Generate en_US.UTF-8 locale
RUN localedef -i en_US -f UTF-8 en_US.UTF-8

# Build and install Leptonica
RUN curl -L -O https://github.com/DanBloomberg/leptonica/releases/download/1.83.1/leptonica-1.83.1.tar.gz && \
    tar -xvzf leptonica-1.83.1.tar.gz && \
    cd leptonica-1.83.1 && ./configure && make && make install && \
    cd .. && rm -rf leptonica*

# Set environment variables for build tools and runtime
ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
ENV PATH="/usr/local/bin:${PATH}"
ENV TESSDATA_PREFIX=/usr/local/share/tessdata/

# Build and install Tesseract
RUN curl -L -O https://github.com/tesseract-ocr/tesseract/archive/refs/tags/5.3.1.tar.gz && \
    tar -xvzf 5.3.1.tar.gz && \
    cd tesseract-5.3.1 && ./autogen.sh && ./configure && make && make install && \
    cd .. && rm -rf tesseract*

# Install Tesseract English language data
RUN mkdir -p /usr/local/share/tessdata && \
    curl -L -o /usr/local/share/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata

# Test Tesseract install
RUN tesseract --list-langs

# Download and extract LibreOffice
RUN wget https://download.documentfoundation.org/libreoffice/stable/25.2.2/rpm/x86_64/LibreOffice_25.2.2_Linux_x86-64_rpm.tar.gz && \
    mkdir -p /tmp/rpms && \
    tar -xzf LibreOffice_25.2.2_Linux_x86-64_rpm.tar.gz -C /tmp/rpms && \
    rm LibreOffice_25.2.2_Linux_x86-64_rpm.tar.gz

# Install LibreOffice headless essentials
RUN rpm -ivh \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libreoffice25.2-ure-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-core-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-images-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libreoffice25.2-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-writer-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-ooofonts-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-en-US-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libreoffice25.2-en-US-25.2.2.2-2.x86_64.rpm \
    && rm -rf /tmp/rpms

# Verify LibreOffice installation
RUN /opt/libreoffice25.2/program/soffice --headless --version

# Set environment variables
ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    HOME=/tmp \
    PATH=$PATH:/opt/libreoffice25.2/program \
    LIBREOFFICE_LANG=en-US

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt && \
    python3 -m spacy download en_core_web_lg

# Copy Lambda handler
COPY lambda_function.py .

# Define Lambda entrypoint
CMD ["lambda_function.lambda_handler"]
