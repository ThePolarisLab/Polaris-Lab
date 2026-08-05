from __future__ import annotations

from app.api.quickbooks_financials import _first, _first_report_metric, _report_metrics, _report_values, get_balance_sheet_metric


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


def test_profit_loss_net_income_accepts_quickbooks_profit_footer_label():
    payload = _payload(
        [
            _row("Total Income", "3643863.42"),
            _row("Total Expenses", "3173824.00"),
            _row("Profit", "86284.11"),
        ]
    )
    values = _report_values(payload)
    metrics = _report_metrics(payload)

    assert _first(values, "net income", "net operating income", "profit") == "86284.11"
    metric = _first_report_metric(metrics, "net income", "net operating income", "profit")
    assert metric is not None
    assert metric.label == "Profit"
    assert metric.value == "86284.11"


def test_profit_loss_net_income_fails_closed_when_profit_label_is_absent():
    values = _report_values(_payload([_row("Total Income", "3643863.42")]))

    assert _first(values, "net income", "net operating income", "profit") is None


def test_balance_sheet_cash_position_accepts_quickbooks_total_cash_equivalent_label():
    payload = _payload(
        [
            _row(
                "Cash and Cash Equivalent",
                children=[
                    _row("BANK CAD", children=[_row("CIBC CAD", "5668.63")], summary="6150.83"),
                    _row("BANK USD", children=[_row("CIBC USD", "12303.41")], summary="12304.91"),
                    _row("Cash", "8761.04"),
                    _row("Petty Cash", "878.69"),
                    _row("Undeposited Funds", "2418.30"),
                ],
                summary="30513.77",
            )
        ]
    )
    values = _report_values(payload)
    metrics = _report_metrics(payload)

    assert _first(values, "total bank accounts", "total cash and cash equivalent", "cash and cash equivalents", "bank accounts") == "30513.77"
    metric = _first_report_metric(metrics, "total bank accounts", "total cash and cash equivalent", "cash and cash equivalents", "bank accounts")
    assert metric is not None
    assert metric.label == "Total Cash and Cash Equivalent"
    assert metric.value == "30513.77"


def test_balance_sheet_cash_position_fails_closed_when_total_cash_label_is_absent():
    values = _report_values(_payload([_row("Cash and Cash Equivalent")]))

    assert _first(values, "total bank accounts", "total cash and cash equivalent", "cash and cash equivalents", "bank accounts") is None


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
