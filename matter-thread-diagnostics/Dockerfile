ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system diagnostic utilities for Thread/IPv6 routing inspection
RUN apk add --no-cache \
    bash \
    curl \
    jq \
    iproute2 \
    iputils \
    bind-tools \
    net-tools \
    ca-certificates

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

COPY app/ /app/

EXPOSE 8099

CMD ["/app/run.sh"]
