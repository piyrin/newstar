FROM apache/airflow:3.3.2
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer fonts-noto-cjk poppler-utils tesseract-ocr \
    tesseract-ocr-chi-sim tesseract-ocr-eng \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER airflow
COPY resume/requirements.txt /tmp/resume-requirements.txt
RUN pip install --no-cache-dir -r /tmp/resume-requirements.txt
