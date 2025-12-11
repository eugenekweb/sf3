FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--timeout", "1800", "--keep-alive", "5", "--worker-class", "sync", "--worker-connections", "1000", "--limit-request-line", "8190", "--limit-request-fields", "100", "--limit-request-field_size", "8190", "app:app"]

