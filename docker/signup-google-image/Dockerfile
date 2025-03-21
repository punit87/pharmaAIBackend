# Use the official AWS Lambda Python image as a base image
FROM public.ecr.aws/lambda/python:3.13

# Install PostgreSQL development libraries with dnf
RUN dnf install -y postgresql-devel gcc python3-devel && dnf clean all

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app.py ${LAMBDA_TASK_ROOT}

CMD ["app.lambda_handler"]