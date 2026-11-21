FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
COPY fixture_bundle.py fixture_bundle.json select_observed.py observed.json.gz select_lines.py lines.json.gz main.py scheduler.py select_paths.py select_scopes.py select_dialects.py fixture_index.json dialects.json.gz scopes.json.gz sqlglot-source.zip /app/
CMD ["python", "/app/main.py"]
