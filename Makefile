UV_CACHE_DIR ?= .uv-cache
export UV_CACHE_DIR

.PHONY: install quality format test smoke ui benchmark-small counterfactual-fixture prompt-fixture evidence-model-small prompt-benchmark-small route-prompt-small reactseq-conformance-small reproduce-small schemas

install:
	uv sync --all-extras --dev

quality:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest -m "not upstream and not slow and not gpu" --cov=synthaudit --cov-report=term-missing

smoke:
	uv run synthaudit version --json

ui:
	uv run --extra ui streamlit run app/Home.py

benchmark-small:
	uv run synthaudit benchmark counterfactuals --records benchmarks/counterfactual-v1/records.jsonl --manifest benchmarks/counterfactual-v1/manifest.json --splits benchmarks/counterfactual-v1/splits.json --human-review benchmarks/counterfactual-v1/human-review.csv --json

counterfactual-fixture:
	uv run python scripts/build_counterfactual_fixture.py

prompt-fixture:
	uv run python scripts/build_prompt_fixture.py

evidence-model-small:
	uv run synthaudit benchmark evidence-model-contract --json

prompt-benchmark-small:
	uv run synthaudit benchmark prompt-cases --cases benchmarks/prompt-robustness-v1/cases.jsonl --manifest benchmarks/prompt-robustness-v1/manifest.json --json

route-prompt-small:
	uv run synthaudit benchmark route-prompt-contract --json

reactseq-conformance-small:
	uv run synthaudit benchmark reactseq-conformance --fixture tests/fixtures/reactseq/golden.json --json

reproduce-small: quality test smoke benchmark-small evidence-model-small prompt-benchmark-small route-prompt-small reactseq-conformance-small

schemas:
	uv run python scripts/export_schemas.py
