FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN pip install --no-cache-dir uv==0.12.7

WORKDIR /workspaces/SynthAudit
