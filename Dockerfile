# Containerized Dokimo MCP server for Smithery (and any HTTP host).
# Serves MCP Streamable HTTP at /mcp on $PORT (Smithery injects PORT=8081).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md dokimo_mcp.py ./
RUN pip install --no-cache-dir .

# HTTP transport for hosted deploys (stdio remains the default for local use).
ENV MCP_TRANSPORT=http
ENV PORT=8081
EXPOSE 8081

ENTRYPOINT ["dokimo-mcp"]
