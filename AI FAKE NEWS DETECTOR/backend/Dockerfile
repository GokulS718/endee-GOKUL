FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for newspaper3k
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    python3-dev \
    libxml2-dev \
    libxslt-dev \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data required by newspaper3k
RUN pip install nltk newspaper3k && python -m nltk.downloader punkt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
