FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends tesseract-ocr && \
    command -v tesseract && \
    tesseract --version && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PATH="/usr/bin:${PATH}"

RUN python -c "import pytesseract; print('pytesseract OK'); print(pytesseract.get_tesseract_version())"

CMD ["python", "main.py"]