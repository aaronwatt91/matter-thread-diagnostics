FROM docker.io/library/python:3.12-slim-bookworm

ENV LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system network diagnostic utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    jq \
    iproute2 \
    iputils-ping \
    dnsutils \
    net-tools \
    avahi-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

COPY app/ /app/

EXPOSE 8099

ENTRYPOINT ["/app/run.sh"]
