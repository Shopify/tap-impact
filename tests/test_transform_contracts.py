"""Tests for transform_contracts based on real Impact API response shapes."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tap_impact.transform import transform_json

# Real API response shape (after camelCase → snake_case via convert_json)
SAMPLE_API_RESPONSE = {
    "contracts": [
        {
            "id": "S-26838993",
            "status": "A",
            "template_terms": {
                "change_notification_period": "1",
                "currency": "USD",
                "custom_creative_payer": "ADVERTISER",
                "max_return_percentage": "100",
                "name": "Public Terms",
                "template_id": "351581",
                "version_id": "810182",
                "return_policy": "ALWAYS_OK",
                "action_limit": None,
                "action_limit_period": None,
                "contract_start_slotting_fee": None,
                "first_action_slotting_fee": None,
                "min_earning_per_click": None,
                "monthly_slotting_fee": None,
                "spend_limit": None,
                "spend_limit_period": None,
                "labels": ["/affiliates page"],
                "special_terms_list": None,
                "promotional_terms": [{"some": "data"}],
                "events_payouts": [
                    {
                        "event_type_id": "57793",
                        "event_type_name": "Retained Full Price Shops: 6 Mo",
                        "event_category": "SALE",
                        "default_payout": "0.00",
                        "default_payout_rate": None,
                        "credit_policy": "PARENT_ACTION",
                        "payout_level": "ITEM",
                        "location_requirement_type": None,
                        "location_requirement_countries": None,
                        # Single dict where schema expects array
                        "locking": {"basis": "TRACKED", "period": "MONTH",
                                    "month_offset": "0", "day_offset": "21"},
                        # Single dict where schema expects array
                        "payout_scheduling": {"basis": "LOCKED", "period": "END_OF_DAY",
                                              "day_offset": "1"},
                        "valid_referrals": [
                            {"type": "PARENT_ACTIONS", "window": "600", "window_unit": "DAY"}
                        ],
                        "limits": None,
                        "payouts_adjustments": None,
                        "payouts_groups": [
                            {"id": "abc", "rank": "1", "rules": []}
                        ],
                        "payout_restrictions": None,
                        "performance_bonus": None,
                    }
                ],
            },
        }
    ]
}


def test_transform_contracts_type_coercion():
    """Top-level template_terms string→int/float coercion."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    tt = result[0]['template_terms']

    assert tt['template_id'] == 351581, f"Expected int 351581, got {tt['template_id']!r}"
    assert tt['version_id'] == 810182
    assert tt['change_notification_period'] == 1
    assert tt['max_return_percentage'] == 100.0
    assert isinstance(tt['max_return_percentage'], float)
    # None stays None
    assert tt['action_limit'] is None
    assert tt['spend_limit'] is None
    print("  ✅ type coercion")


def test_transform_contracts_events_payouts_preserved():
    """events_payouts array should survive with coerced types."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    tt = result[0]['template_terms']
    ep = tt['events_payouts']

    assert isinstance(ep, list), f"Expected list, got {type(ep)}"
    assert len(ep) == 1, f"Expected 1 item, got {len(ep)}"

    item = ep[0]
    assert item['event_type_id'] == 57793, f"Expected int 57793, got {item['event_type_id']!r}"
    assert item['default_payout'] == 0.0
    assert isinstance(item['default_payout'], float)
    print("  ✅ events_payouts preserved + coerced")


def test_transform_contracts_dict_to_list():
    """Single dict values should be wrapped in a list."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    ep = result[0]['template_terms']['events_payouts'][0]

    # locking was a dict, should now be [dict]
    assert isinstance(ep['locking'], list), f"Expected list, got {type(ep['locking'])}"
    assert len(ep['locking']) == 1
    assert ep['locking'][0]['basis'] == 'TRACKED'
    assert ep['locking'][0]['month_offset'] == 0  # coerced from "0"
    assert ep['locking'][0]['day_offset'] == 21   # coerced from "21"

    # payout_scheduling was a dict, should now be [dict]
    assert isinstance(ep['payout_scheduling'], list)
    assert len(ep['payout_scheduling']) == 1
    assert ep['payout_scheduling'][0]['day_offset'] == 1
    print("  ✅ dict→list wrapping + nested int coercion")


def test_transform_contracts_valid_referrals():
    """valid_referrals window should be coerced to int."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    vr = result[0]['template_terms']['events_payouts'][0]['valid_referrals']

    assert isinstance(vr, list)
    assert vr[0]['window'] == 600, f"Expected int 600, got {vr[0]['window']!r}"
    print("  ✅ valid_referrals window coerced")


def test_transform_contracts_none_to_empty_list():
    """None array fields should become []."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    tt = result[0]['template_terms']
    ep = tt['events_payouts'][0]

    assert tt['special_terms_list'] == []
    assert ep['limits'] == []
    assert ep['payouts_adjustments'] == []
    assert ep['payout_restrictions'] == []
    assert ep['performance_bonus'] == []
    print("  ✅ None→[] for array fields")


def test_transform_contracts_drops_promotional_terms():
    """promotional_terms not in schema, should be dropped."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    tt = result[0]['template_terms']

    assert 'promotional_terms' not in tt, "promotional_terms should be dropped"
    print("  ✅ promotional_terms dropped")


def test_transform_contracts_labels_passthrough():
    """labels (simple string array) should pass through unchanged."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    tt = result[0]['template_terms']

    assert tt['labels'] == ["/affiliates page"]
    print("  ✅ labels passthrough")


def test_transform_contracts_extraction_date_added():
    """extraction_date should be added to the record."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    assert 'extraction_date' in result[0]
    print("  ✅ extraction_date added")


if __name__ == '__main__':
    print("Running transform_contracts tests...")
    test_transform_contracts_type_coercion()
    test_transform_contracts_events_payouts_preserved()
    test_transform_contracts_dict_to_list()
    test_transform_contracts_valid_referrals()
    test_transform_contracts_none_to_empty_list()
    test_transform_contracts_drops_promotional_terms()
    test_transform_contracts_labels_passthrough()
    test_transform_contracts_extraction_date_added()
    print("\n✅ All 8 tests passed!")
