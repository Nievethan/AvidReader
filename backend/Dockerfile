FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CPU-only by default. No GPU, no external AI keys, and no optional
# databases (Qdrant/Neo4j) are required for the backend to start.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]