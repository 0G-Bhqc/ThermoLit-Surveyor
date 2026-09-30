FROM python:3.11-slim

WORKDIR /app

# 先拷贝清单以利用层缓存
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir ".[server,export,checkpoint]"

RUN useradd --create-home thermolit
USER thermolit

EXPOSE 8000

CMD ["uvicorn", "thermolit.api:app", "--host", "0.0.0.0", "--port", "8000"]
