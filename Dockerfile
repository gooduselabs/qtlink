FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY qtlink ./qtlink
COPY devices ./devices
COPY config.demo.yaml config.demo.vi.yaml config.example.yaml config.example.tt10.yaml ./
ENV TZ=UTC
EXPOSE 8080
CMD ["python", "-m", "qtlink", "run", "-c", "/app/config/config.yaml"]
