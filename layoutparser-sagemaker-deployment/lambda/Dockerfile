FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies including Java, X11, and utilities
RUN dnf -y install \
    nss glibc fontconfig cups-libs libX11 libXext libX11-xcb libxcb \
    mesa-libGL libXrender libSM libICE libXinerama cairo libxslt \
    wget tar java-17-amazon-corretto-devel findutils \
    gcc gcc-c++ make libffi-devel python3-devel xz git \
    poppler-utils \  # <- add this line
    glibc-langpack-en glibc-locale-source \
    && dnf clean all && rm -rf /var/cache/dnf


# Generate en_US.UTF-8 locale
RUN localedef -i en_US -f UTF-8 en_US.UTF-8

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