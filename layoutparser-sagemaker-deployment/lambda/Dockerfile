FROM public.ecr.aws/lambda/python:3.12
#spacy fails for 3.13 so opting for 3.12 which is the next latest

RUN dnf -y install libX11
# Install necessary dependencies and wget using dnf
RUN dnf -y install \
     nss glibc fontconfig cups-libs libX11 libXext libX11-xcb libxcb mesa-libGL libXrender libSM libICE libxcb wget tar libXinerama cairo libxslt libX11-xcb libxcb \
    && dnf clean all && rm -rf /var/cache/dnf


# Download LibreOffice tar.gz
RUN wget https://download.documentfoundation.org/libreoffice/stable/25.2.2/rpm/x86_64/LibreOffice_25.2.2_Linux_x86-64_rpm.tar.gz

# Create a directory for LibreOffice RPMs
RUN mkdir /tmp/rpms

# Extract LibreOffice tar.gz
RUN tar -xzf LibreOffice_25.2.2_Linux_x86-64_rpm.tar.gz -C /tmp/rpms/

# List contents for debugging
RUN ls -l /tmp/rpms/

RUN ls -l /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/

# Install essential LibreOffice RPMs for headless operation using rpm
RUN rpm -ivh \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libreoffice25.2-ure-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-core-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-images-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libreoffice25.2-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-writer-25.2.2.2-2.x86_64.rpm \
    /tmp/rpms/LibreOffice_25.2.2.2_Linux_x86-64_rpm/RPMS/libobasis25.2-ooofonts-25.2.2.2-2.x86_64.rpm

# Verify installation directory
RUN ls -l /opt/



# Find soffice binary
RUN dnf -y install findutils
RUN find / -name soffice

# Clean up temporary files
RUN rm -rf /tmp/rpms /LibreOffice_25.2.2_Linux_x86-64_rpm.tar.gz

# Check if LibreOffice is installed and supports headless mode
RUN export PATH=/var/lang/bin:/usr/local/bin:/usr/bin:/bin:/opt/libreoffice25.2/program && \
    /opt/libreoffice25.2/program/soffice --version && \
    /opt/libreoffice25.2/program/soffice --headless --version || echo "Headless mode check failed"

# Install Python dependencies
COPY requirements.txt .

RUN dnf install -y \
    gcc \
    gcc-c++ \
    make \
    libffi-devel \
    python3-devel \
    xz \
    git \
    && dnf clean all


RUN pip3 install --no-cache-dir -r requirements.txt
RUN python3 -m spacy download en_core_web_lg

# Copy the Lambda function
COPY lambda_function.py .

# Set the Lambda entry point
CMD ["lambda_function.lambda_handler"]