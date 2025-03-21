# Use the official AWS Lambda Python image as a base image
FROM public.ecr.aws/lambda/python:3.13

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]