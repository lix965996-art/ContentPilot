from app.prompt_regression.evaluator import _score, load_cases, run_regression


def test_contradictory_numbers_and_dates_do_not_receive_full_factual_score() -> None:
    case = {
        "source": "活动预算 100 万元，日期为 10 月 20 日。",
        "expected_facts": ["100 万元", "10 月 20 日"],
    }
    factual, completeness, _, evidence = _score(
        case, {"content": "预算 1 亿元，日期为 12 月 31 日。"}
    )

    assert factual is not None and factual < 100
    assert completeness == 0
    assert evidence["contradictions"]


def test_empty_expected_facts_are_unknown_not_full_marks() -> None:
    factual, completeness, _, _ = _score(
        {"source": "原文", "expected_facts": []},
        {"content": "完全不同的输出"},
    )

    assert factual is None
    assert completeness is None


def test_missing_fact_reduces_completeness_but_not_factual_consistency() -> None:
    factual, completeness, _, _ = _score(
        {
            "source": "活动预算 100 万元，日期为 10 月 20 日。",
            "expected_facts": ["100 万元", "10 月 20 日"],
        },
        {"content": "活动预算 100 万元。"},
    )

    assert factual == 100
    assert completeness == 50


def test_negation_reversal_is_reported() -> None:
    factual, _, _, evidence = _score(
        {"source": "活动不收取报名费。", "expected_facts": ["不收取报名费"]},
        {"content": "活动收取报名费。"},
    )

    assert factual is not None and factual < 100
    assert any("否定" in item for item in evidence["contradictions"])


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
