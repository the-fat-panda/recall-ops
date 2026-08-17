FROM python:3.13-slim

WORKDIR /app

COPY backend/sandbox/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

EXPOSE 8080

CMD ["uvicorn", "backend.sandbox.orders_api:app", "--host", "0.0.0.0", "--port", "8080"]
