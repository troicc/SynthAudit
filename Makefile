UV_CACHE_DIR ?= .uv-cache
export UV_CACHE_DIR
UV_RUN ?= uv run --no-sync

.PHONY: install quality format test smoke ui ui-smoke cli-smoke product-examples benchmark-small counterfactual-fixture prompt-fixture evidence-model-small prompt-benchmark-small route-prompt-small reactseq-conformance-small reproduce-small schemas

install:
	uv sync --all-extras --dev

quality:
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	$(UV_RUN) mypy src

format:
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

test:
	$(UV_RUN) pytest -m "not upstream and not slow and not gpu" --cov=synthaudit --cov-report=term-missing

smoke:
	$(UV_RUN) synthaudit version --json

ui:
	$(UV_RUN) --extra ui streamlit run app/Home.py

ui-smoke:
	$(UV_RUN) --extra ui synthaudit ui --check --json -

cli-smoke:
	$(UV_RUN) synthaudit audit-reaction --input examples/reaction-ir.json --json /private/tmp/synthaudit-cli-reaction.json
	$(UV_RUN) synthaudit audit-route --input examples/route-ir.json --json /private/tmp/synthaudit-cli-route.json

product-examples:
	$(UV_RUN) python scripts/build_product_examples.py

benchmark-small:
	$(UV_RUN) synthaudit benchmark counterfactuals --records benchmarks/counterfactual-v1/records.jsonl --manifest benchmarks/counterfactual-v1/manifest.json --splits benchmarks/counterfactual-v1/splits.json --human-review benchmarks/counterfactual-v1/human-review.csv --json

counterfactual-fixture:
	$(UV_RUN) python scripts/build_counterfactual_fixture.py

prompt-fixture:
	$(UV_RUN) python scripts/build_prompt_fixture.py

evidence-model-small:
	$(UV_RUN) synthaudit benchmark evidence-model-contract --json

prompt-benchmark-small:
	$(UV_RUN) synthaudit benchmark prompt-cases --cases benchmarks/prompt-robustness-v1/cases.jsonl --manifest benchmarks/prompt-robustness-v1/manifest.json --json

route-prompt-small:
	$(UV_RUN) synthaudit benchmark route-prompt-contract --json

reactseq-conformance-small:
	$(UV_RUN) synthaudit benchmark reactseq-conformance --fixture tests/fixtures/reactseq/golden.json --json

reproduce-small: quality test smoke ui-smoke cli-smoke benchmark-small evidence-model-small prompt-benchmark-small route-prompt-small reactseq-conformance-small

schemas:
	$(UV_RUN) python scripts/export_schemas.py
