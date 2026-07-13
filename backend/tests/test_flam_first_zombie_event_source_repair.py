from __future__ import annotations

import pytest
from repair_flam_first_zombie_event_sources import (
    repair_summary,
    source_distribution,
    validate_target_mappings,
)


def _target_mappings(source_field: str = "personal") -> list[dict]:
    return [
        {
            "event_name": "ServerPayLog",
            "properties": [
                {
                    "property_name": f"{source_field}.money",
                    "source_field": source_field,
                    "json_path": "$.money",
                },
                {
                    "property_name": f"{source_field}.orderId",
                    "source_field": source_field,
                    "json_path": "$.orderId",
                },
                {
                    "property_name": f"{source_field}.productid",
                    "source_field": source_field,
                    "json_path": "$.productid",
                },
            ],
        }
    ]


def test_source_distribution_counts_event_properties() -> None:
    mappings = _target_mappings()
    mappings.append(
        {
            "event_name": "BattleEnd",
            "properties": [
                {
                    "property_name": "ext.result",
                    "source_field": "ext",
                    "json_path": "$.result",
                }
            ],
        }
    )

    assert source_distribution(mappings) == {"personal": 3, "ext": 1}


def test_validate_target_mappings_requires_verified_payment_sources() -> None:
    with pytest.raises(ValueError, match="ServerPayLog.money.*personal"):
        validate_target_mappings(
            _target_mappings(source_field="ext"),
            expected_total=3,
            expected_distribution={"ext": 3},
        )


def test_validate_target_mappings_accepts_expected_distribution() -> None:
    result = validate_target_mappings(
        _target_mappings(),
        expected_total=3,
        expected_distribution={"personal": 3},
    )

    assert result == {"personal": 3}


def test_repair_summary_reports_idempotent_state() -> None:
    mappings = _target_mappings()

    assert repair_summary(mappings, mappings)["changed"] is False
    assert repair_summary([], mappings)["changed"] is True
