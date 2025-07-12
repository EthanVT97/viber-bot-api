FROM python:3.9-slim

# Install runtime system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd -m appuser && \
    chown -R appuser:appuser /app
USER appuser

# Copy application code
COPY --chown=appuser:appuser . .

# Configure runtime environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    UVICORN_WORKERS=4 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000 \
    UVICORN_RELOAD=0

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:$UVICORN_PORT/health || exit 1

# Fixed CMD instruction (Solution 1)
CMD uvicorn app.main:app --host $UVICORN_HOST --port $UVICORN_PORT --workers $UVICORN_WORKERS --loop uvloop --no-access-log
