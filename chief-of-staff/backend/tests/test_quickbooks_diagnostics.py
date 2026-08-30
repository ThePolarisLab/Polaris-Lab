from __future__ import annotations

from app.api.quickbooks_diagnostics import _group_summaries


def _col(label: str, value: str = "") -> list[dict[str, str]]:
    return [{"value": label}, {"value": value}]


def test_group_summaries_returns_provider_authored_totals_only():
    payload = {
        "Rows": {
            "Row": [
                {
                    "group": "Income",
                    "Summary": {"ColData": _col("Total Income", "3976670.07")},
                    "Rows": {
                        "Row": [
                            {"ColData": _col("Sales of Product Income", "3975160.76")},
                        ]
                    },
                },
                {
                    "group": "COGS",
                    "Summary": {"ColData": _col("Total Cost of Goods Sold", "398552.97")},
                },
                {
                    "group": "NetIncome",
                    "Summary": {"ColData": _col("PROFIT", "650.94")},
                },
            ]
        }
    }

    assert _group_summaries(payload) == [
        {"group": "Income", "label": "Total Income", "value": "3976670.07"},
        {"group": "COGS", "label": "Total Cost of Goods Sold", "value": "398552.97"},
        {"group": "NetIncome", "label": "PROFIT", "value": "650.94"},
    ]


def test_group_summaries_does_not_derive_missing_gross_profit():
    payload = {
        "Rows": {
            "Row": [
                {"group": "Income", "Summary": {"ColData": _col("Total Income", "3976670.07")}},
                {"group": "COGS", "Summary": {"ColData": _col("Total Cost of Goods Sold", "398552.97")}},
            ]
        }
    }

    summaries = _group_summaries(payload)

    assert all(item["group"] != "GrossProfit" for item in summaries)
    assert all(item["label"] != "Gross Profit" for item in summaries)
