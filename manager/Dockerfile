FROM python:3.11-slim
WORKDIR /app
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "app.py"]
