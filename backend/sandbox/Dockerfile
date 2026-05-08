# AnyLegal OSS — Python sandbox for the run_python tool.
#
# Demo sandbox configuration. Production hardening (seccomp profiles,
# cgroup-v2 limits, network namespaces, syscall denylists, gVisor /
# Firecracker isolation) is part of AnyLegal hosted — see anylegal.ai
# for the production-grade version. Self-hosted users running untrusted
# LLM-generated code in this container do so at their own risk.
#
# Build:  docker build -t anylegal-sandbox:latest backend/sandbox/

FROM python:3.11-slim

# LibreOffice headless is needed for any docx/odf round-tripping that
# happens inside the sandbox. The full LibreOffice service runs as a
# separate container; this is just the local fallback.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-core \
    && rm -rf /var/lib/apt/lists/*

# Non-root sandbox user — matches the --user 1000:1000 flag in
# python_tools.py:_run_sandbox_command.
RUN useradd -u 1000 -m sandbox

COPY requirements.txt /sandbox/requirements.txt
RUN pip install --no-cache-dir -r /sandbox/requirements.txt

COPY run.py /sandbox/run.py
COPY scripts/ /sandbox/scripts/
RUN chown -R 1000:1000 /sandbox

USER 1000:1000
WORKDIR /sandbox
ENTRYPOINT ["python", "/sandbox/run.py"]
