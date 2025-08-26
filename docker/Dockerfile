# syntax=docker/dockerfile:1

# --- Builder stage: install deps and compile wheels ---
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    pkg-config \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    sqlcipher \
    libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only copy dependency descriptors first for better Docker layer caching
COPY pyproject.toml README.md ./

# Build wheels for the project (with optional extras flag)
ARG INSTALL_EXTRAS=
RUN python -m pip install --upgrade pip && \
    if [ -n "$INSTALL_EXTRAS" ]; then \
      python -m pip wheel --wheel-dir /wheels ".[${INSTALL_EXTRAS}]"; \
    else \
      python -m pip wheel --wheel-dir /wheels .; \
    fi

# Copy the source once wheels are built (keeps cache if code changes)
COPY walnut ./walnut
RUN python -m pip wheel --wheel-dir /wheels .


# --- Runtime stage: minimal image with runtime libs ---
FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Default bind
    WALNUT_BIND=0.0.0.0:8000

# Runtime OS packages (no build chain). sqlcipher provides lib for pysqlcipher3
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlcipher \
    ipmitool \
    telnet \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy prebuilt wheels and install
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --find-links /wheels walnut-orchestrator && rm -rf /wheels

# Create data dir for encrypted DB
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Copy entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "walnut.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

