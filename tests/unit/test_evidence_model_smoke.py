from __future__ import annotations

from synthaudit.evaluation import run_evidence_model_contract_smoke


def test_authored_evidence_model_smoke_reports_contracts_not_performance() -> None:
    result = run_evidence_model_contract_smoke()
    assert result.stage_model_count == 4
    assert result.bootstrap_member_count == 3
    assert result.missing_flags_exercised
    assert result.provider_disagreement_exercised
    assert result.abstention_exercised
    assert result.ood_evaluation_contract_exercised
    assert result.ablation_contract_count == 2
    assert result.metrics_status == "not_reportable_software_fixture"
