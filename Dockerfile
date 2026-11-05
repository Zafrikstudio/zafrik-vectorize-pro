FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

RUN apt-get update \
    && apt-get install -y --no-install-recommends libcairo2 libffi8 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Un solo worker y un solo hilo para respetar el límite de memoria de Render Free.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 1 --worker-class sync --timeout 180 --max-requests 30 --max-requests-jitter 5 app:app"]
