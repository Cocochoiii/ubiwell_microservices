FROM python:3.11-slim

WORKDIR /app

COPY services/ingestion-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ingestion-service/app ./app
COPY shared/gen ./shared/gen

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
