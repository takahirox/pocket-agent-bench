FROM python:3.12-slim-bookworm
COPY model_proxy.py /proxy.py
USER 65534
CMD ["python", "-I", "/proxy.py"]
