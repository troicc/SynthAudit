from synthaudit.evaluation.route_prompt_smoke import run_route_prompt_contract_smoke


def test_route_prompt_smoke_reports_contracts_without_model_metrics() -> None:
    result = run_route_prompt_contract_smoke()
    assert result.required_route_outputs_present
    assert result.all_route_perturbations_detected
    assert result.default_prompt_provider_unavailable
    assert result.prompt_variant_count == 5
    assert not result.route_success_probability_reported
    assert not result.expensive_provider_experiments_run
    assert result.metrics_status == "not_run"
