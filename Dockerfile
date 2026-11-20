FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY main.py scheduler.py select_paths.py fixture_index.json sqlglot-source.zip LICENSE.sqlglot ./
CMD ["python", "/app/main.py"]
