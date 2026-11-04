FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY qtlink ./qtlink
COPY config.demo.yaml config.example.yaml ./
ENV TZ=Asia/Ho_Chi_Minh
EXPOSE 8080
CMD ["python", "-m", "qtlink", "run", "-c", "/app/config/config.yaml"]
