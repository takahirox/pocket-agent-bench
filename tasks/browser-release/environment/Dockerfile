FROM pocket-agent-bench-runtime:0.1
RUN apt-get update && apt-get install -y --no-install-recommends chromium && rm -rf /var/lib/apt/lists/*
COPY --chown=agent:agent input/ /app/input/
COPY --chown=agent:agent src/ /app/src/
COPY mock_api.py bootstrap.py smoke.py execution.py /opt/pocket/
WORKDIR /app
ENTRYPOINT ["python", "/opt/pocket/bootstrap.py"]
