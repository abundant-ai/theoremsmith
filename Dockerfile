FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive \
    ELAN_HOME=/opt/elan \
    PATH=/opt/elan/bin:/opt/venv/bin:/usr/local/bin:/usr/bin:/bin \
    THEOREMSMITH_DATA=/data \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git python3 python3-venv build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
      -o /tmp/elan-init.sh \
    && sh /tmp/elan-init.sh -y --default-toolchain none \
    && rm /tmp/elan-init.sh \
    && chmod -R a+rx /opt/elan

RUN python3 -m venv /opt/venv
WORKDIR /app
COPY pyproject.toml ./
COPY server/ ./server/
COPY --from=web /server/theoremsmith/web ./server/theoremsmith/web
RUN pip install --no-cache-dir .

VOLUME /data
EXPOSE 8000
CMD ["theoremsmith"]
