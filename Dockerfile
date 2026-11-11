FROM ghcr.io/openai/tunnel-client:v0.0.20 AS tunnel

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN groupadd --gid 1000 collector && useradd --uid 1000 --gid collector --home /app collector
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY sql ./sql
COPY --from=tunnel /usr/bin/tunnel-client /usr/bin/tunnel-client
RUN mkdir -p /app/data/tokens && chown -R collector:collector /app/data

USER collector
CMD ["python", "-m", "app.combined"]
