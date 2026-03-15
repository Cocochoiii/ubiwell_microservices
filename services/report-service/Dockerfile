FROM python:3.11-slim

WORKDIR /app

COPY services/report-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/report-service/app ./app
COPY shared/contracts ./shared/contracts

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
