# AnyLegal OSS — backend
FROM python:3.11-slim

# System dependencies. Node is needed for the docx-js runtime invoked by
# the `draft` skill via run_code(language=node). build-essential supports
# any wheel-less Python deps that need to compile from source on install.
# git is needed by pip to install the `lexwiki` package directly from its
# GitHub source (see requirements.txt — not on PyPI yet).
# docker.io provides the docker CLI so the `run_code` tool can launch the
# sandbox container (anylegal-sandbox:latest) on the host's docker daemon
# via /var/run/docker.sock — see docker-compose.yml for the socket mount
# and README's "Optional — build the Python sandbox" section for the
# security framing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    docker-cli \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install docx-js globally (required by the `draft` skill)
RUN npm install -g docx@9.5.1

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Create runtime directories
RUN mkdir -p /app/data /app/logs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
