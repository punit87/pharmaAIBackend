# Use the official AWS Lambda Python image as a base image
FROM public.ecr.aws/lambda/python:3.13

# Set the working directory in the container
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy the app.py file and the .env file to the container
COPY app.py ${LAMBDA_TASK_ROOT}

# Install dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Set the CMD to your handler function
CMD ["app.lambda_handler"]