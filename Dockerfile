FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.8.14
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra ui
COPY .streamlit ./.streamlit
COPY app ./app
COPY benchmarks ./benchmarks
COPY configs ./configs
COPY docs ./docs
COPY examples ./examples
COPY reports ./reports
COPY schemas ./schemas
COPY scripts ./scripts

EXPOSE 8501
ENTRYPOINT ["uv", "run"]
CMD ["synthaudit", "version"]
