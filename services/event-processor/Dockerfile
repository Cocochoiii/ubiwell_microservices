FROM python:3.11-slim

WORKDIR /app

COPY services/event-processor/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/event-processor/app ./app

CMD ["python", "app/main.py"]
