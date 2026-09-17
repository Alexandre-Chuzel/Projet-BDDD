FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install uv

RUN uv sync

CMD ["uv", "run", "fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]