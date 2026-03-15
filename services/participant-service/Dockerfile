FROM python:3.11-slim

WORKDIR /app

COPY services/participant-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/participant-service/app ./app
COPY shared/gen ./shared/gen

EXPOSE 8001
EXPOSE 50051

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
