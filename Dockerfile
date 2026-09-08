FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app

RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN which tesseract && tesseract --version

CMD ["python", "main.py"]