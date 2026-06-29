FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn[standard]>=0.30.0 \
    pydantic>=2.0 \
    pydantic-settings>=2.0 \
    httpx>=0.27.0 \
    python-dotenv>=1.0 \
    lark-oapi>=1.6.0

COPY . .

EXPOSE 8000

CMD ["python", "scripts/run.py"]
