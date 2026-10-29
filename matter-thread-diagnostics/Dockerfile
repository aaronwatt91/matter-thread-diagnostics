ARG BUILD_FROM=python:3.12-alpine3.20
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system diagnostic utilities and build dependencies
RUN apk add --no-cache \
    bash \
    curl \
    jq \
    iproute2 \
    iputils \
    bind-tools \
    net-tools \
    ca-certificates \
    build-base \
    gcc \
    musl-dev \
    linux-headers \
    python3-dev

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Remove build tools after pip install to keep container slim
RUN apk del build-base gcc musl-dev linux-headers python3-dev

COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

COPY app/ /app/

EXPOSE 8099

ENTRYPOINT ["/app/run.sh"]
