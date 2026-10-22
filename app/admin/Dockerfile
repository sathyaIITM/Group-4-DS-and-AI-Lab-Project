FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

COPY app/admin ./app/admin

EXPOSE 8001
CMD ["uvicorn", "app.admin.main:app", "--host", "0.0.0.0", "--port", "8001"]
