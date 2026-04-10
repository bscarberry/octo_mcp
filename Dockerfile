FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY server.py ./

EXPOSE 8000

CMD ["python", "server.py"]
