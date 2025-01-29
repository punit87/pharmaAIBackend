# Use the official AWS Lambda Python image as a base image
FROM public.ecr.aws/lambda/python:3.13

# Set the working directory in the container
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy the app.py file to the container
COPY app.py ${LAMBDA_TASK_ROOT}

# Install dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Define the NLTK data directory to match one of the searched paths
ENV NLTK_DATA=/usr/share/nltk_data

# Ensure the directory exists
RUN mkdir -p /usr/share/nltk_data

# Download the 'punkt' tokenizer data to the specified directory
RUN python -m nltk.downloader -d /usr/share/nltk_data punkt
RUN python -m nltk.downloader -d /usr/share/nltk_data punkt_tab


# Verify the installation of the 'punkt' tokenizer
RUN ls -l /usr/share/nltk_data/tokenizers


# Set the CMD to your handler function
CMD ["app.lambda_handler"]
