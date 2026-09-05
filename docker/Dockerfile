FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && apt-get update && apt-get install -y --no-install-recommends git ca-certificates procps \
 && npm install -g @openai/codex@0.144.4 \
 && useradd -m -u 1000 agent
COPY fleet /opt/fleet
RUN if [ -f /opt/fleet/pyproject.toml ]; then pip install --no-cache-dir /opt/fleet; fi
WORKDIR /app
RUN mkdir -p /app/input /app/output /app/src /logs/agent /logs/verifier /var/lib/pocket \
 && chown -R agent:agent /app /logs/agent \
 && chmod 700 /var/lib/pocket
