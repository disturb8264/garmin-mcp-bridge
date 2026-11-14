FROM ghcr.io/openai/tunnel-client:v0.0.20 AS tunnel

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway/ gateway/
COPY --from=tunnel /usr/bin/tunnel-client /usr/bin/tunnel-client
RUN groupadd --gid 1000 gateway && useradd --uid 1000 --gid gateway --home /app gateway
USER gateway
CMD ["python", "-m", "gateway.combined"]
