FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY edital_ia ./edital_ia
RUN pip install --no-cache-dir ".[dev,paridade]" && rm -rf build *.egg-info
COPY tests ./tests
COPY scripts ./scripts

RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "edital_ia.api:app", "--host", "0.0.0.0", "--port", "8000"]
