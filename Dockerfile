# Containerized Dokimo MCP server (stdio). Run: docker run -i --rm dokimo-mcp
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md dokimo_mcp.py ./
RUN pip install --no-cache-dir .

# stdio MCP server — attach with `docker run -i`
ENTRYPOINT ["dokimo-mcp"]
