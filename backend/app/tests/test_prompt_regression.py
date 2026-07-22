from app.prompt_regression.evaluator import load_cases, run_regression


def test_prompt_regression_dataset_and_comparison() -> None:
    cases = load_cases()
    assert len(cases) >= 20
    assert all(len(case["expected_facts"]) >= 3 for case in cases)

    report = run_regression()
    assert report["caseCount"] >= 20
    assert report["evaluationCount"] >= 60
    assert (
        report["newPrompt"]["platformFormatCompliance"]
        > report["oldPrompt"]["platformFormatCompliance"]
    )
    assert (
        report["newPrompt"]["informationCompleteness"]
        >= report["oldPrompt"]["informationCompleteness"]
    )
    for metrics in (report["oldPrompt"], report["newPrompt"]):
        assert set(metrics) == {
            "platformFormatCompliance",
            "factualConsistency",
            "informationCompleteness",
            "averageDurationMs",
            "tokenUsage",
            "manualEditRatio",
        }
