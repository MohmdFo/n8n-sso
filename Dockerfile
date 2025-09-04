# Dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

# your app listens on 8512
EXPOSE 8512

CMD ["uvicorn", "apps.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
