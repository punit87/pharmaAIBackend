FROM public.ecr.aws/lambda/python:3.9

# Copy function code and requirements
COPY lambda-training-function.py ${LAMBDA_TASK_ROOT}
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Set the CMD to your handler
CMD ["lambda_handler"]