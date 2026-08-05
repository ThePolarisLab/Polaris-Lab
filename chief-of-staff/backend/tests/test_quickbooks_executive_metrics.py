from __future__ import annotations

from app.api.quickbooks_financials import get_balance_sheet_metric


def _col(label: str, value: str = "") -> list[dict[str, str]]:
    return [{"value": label}, {"value": value}]


def _row(label: str, value: str = "", *, children: list[dict] | None = None, summary: str | None = None) -> dict:
    row: dict = {"Header": {"ColData": _col(label)}}
    if value:
        row["ColData"] = _col(label, value)
    if children is not None:
        row["Rows"] = {"Row": children}
    if summary is not None:
        row["Summary"] = {"ColData": _col(f"Total {label}", summary)}
    return row


def _payload(rows: list[dict]) -> dict:
    return {
        "Header": {
            "ReportName": "BalanceSheet",
            "Currency": "CAD",
            "ReportBasis": "Accrual",
            "EndPeriod": "2026-08-04",
        },
        "Rows": {"Row": rows},
    }


def test_balance_sheet_metric_uses_total_row_for_single_currency():
    payload = _payload(
        [
            _row("Accounts Receivable (A/R)", "125.00"),
            _row("Total Accounts Receivable (A/R)", "125.00"),
        ]
    )

    metric = get_balance_sheet_metric(payload, "Accounts Receivable")

    assert metric is not None
    assert metric.label == "Total Accounts Receivable (A/R)"
    assert metric.value == "125.00"


def test_balance_sheet_metric_uses_quickbooks_total_for_multi_currency():
    payload = _payload(
        [
            _row("Accounts Receivable (A/R)", "519437.59"),
            _row("Accounts Receivable (A/R) - USD", "356991.70"),
            _row("Accounts Receivable (A/R) - EUR", "1000.25"),
            _row("Total Accounts Receivable (A/R)", "877429.54"),
        ]
    )

    metric = get_balance_sheet_metric(payload, "Accounts Receivable")

    assert metric is not None
    assert metric.value == "877429.54"


def test_balance_sheet_metric_does_not_fall_back_to_child_row():
    payload = _payload(
        [
            _row("Accounts Receivable (A/R)", "519437.59"),
            _row("Accounts Payable (A/P)", "354588.49"),
        ]
    )

    assert get_balance_sheet_metric(payload, "Accounts Receivable") is None
    assert get_balance_sheet_metric(payload, "Accounts Payable") is None


def test_balance_sheet_metric_finds_nested_summary_total_rows():
    payload = _payload(
        [
            _row(
                "Liabilities and Equity",
                children=[
                    _row(
                        "Liabilities",
                        children=[
                            _row(
                                "Current Liabilities",
                                children=[
                                    _row(
                                        "Accounts Payable (A/P)",
                                        children=[
                                            _row("Accounts Payable (A/P)", "354588.49"),
                                            _row("Accounts Payable (A/P) - USD", "104114.99"),
                                        ],
                                        summary="458703.48",
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ]
    )

    metric = get_balance_sheet_metric(payload, "Accounts Payable")

    assert metric is not None
    assert metric.label == "Total Accounts Payable (A/P)"
    assert metric.value == "458703.48"


def test_balance_sheet_metric_handles_nested_direct_total_rows():
    payload = _payload(
        [
            _row(
                "Assets",
                children=[
                    _row(
                        "Current Assets",
                        children=[
                            _row("Accounts Receivable (A/R)", "519437.59"),
                            _row("Accounts Receivable (A/R) - USD", "356991.70"),
                            _row("Total Accounts Receivable (A/R)", "876429.29"),
                        ],
                    )
                ],
            )
        ]
    )

    metric = get_balance_sheet_metric(payload, "Accounts Receivable")

    assert metric is not None
    assert metric.value == "876429.29"
