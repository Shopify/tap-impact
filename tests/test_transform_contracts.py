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
            # --- contract-level fields added in Phase 2 ---
            "campaign_id": "99999",
            "campaign_name": "Shopify Affiliate Program",
            "has_campaign_terms": "true",
            "zero_payout_hide_report": "false",
            "scheduled_terms": {"effective_date": "2026-01-01T00:00:00Z"},
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
                # --- promotional_terms now preserved, not dropped (Phase 2) ---
                "promotional_terms": [
                    {"terms_name": "Holiday Promo",
                     "terms_pdf_uri": "https://example.com/promo.pdf",
                     "terms_type": "STANDARD"}
                ],
                # --- cpc_payouts forward-compat ---
                "cpc_payouts": [{"event_type_id": "1234", "rate": "0.25"}],
                "event_payouts": [
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
                        # NOTE: these keys (payout_adjustments / payout_groups, singular
                        # "payout") are what convert_json() produces from the API's
                        # PayoutAdjustments / PayoutGroups. The schema expects them
                        # under payouts_adjustments / payouts_groups (plural "payouts").
                        # Using the post-convert_json names here ensures the test would
                        # catch a regression of the rename block in transform_contracts.
                        "payout_adjustments": None,
                        "payout_groups": [
                            {"id": "abc", "rank": "1", "rules": []}
                        ],
                        # payout_restrictions now exercises the new nested
                        # zero_payout_hide_report field (Phase 2).
                        "payout_restrictions": [
                            {"id": "pr-1", "zero_payout_hide_report": "1", "rules": []}
                        ],
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
    assert ep['performance_bonus'] == []
    print("  ✅ None→[] for array fields")


def test_transform_contracts_preserves_promotional_terms():
    """promotional_terms now declared in schema, should survive transform
    (regression test — was being explicitly .pop()'d before Phase 2)."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    tt = result[0]['template_terms']

    assert 'promotional_terms' in tt, "promotional_terms should be preserved"
    assert isinstance(tt['promotional_terms'], list)
    assert tt['promotional_terms'][0]['terms_name'] == 'Holiday Promo'
    assert tt['promotional_terms'][0]['terms_type'] == 'STANDARD'
    # cpc_payouts also forward-compat preserved
    assert isinstance(tt['cpc_payouts'], list)
    assert tt['cpc_payouts'][0]['event_type_id'] == '1234'
    print("  ✅ promotional_terms + cpc_payouts preserved")


def test_transform_contracts_new_contract_level_fields():
    """5 contract-level fields added in Phase 2 should survive transform."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    record = result[0]

    # campaign_id coerced from "99999" -> 99999
    assert record['campaign_id'] == 99999, f"Expected int 99999, got {record['campaign_id']!r}"
    assert isinstance(record['campaign_id'], int)

    # string passthroughs
    assert record['campaign_name'] == 'Shopify Affiliate Program'
    assert record['has_campaign_terms'] == 'true'
    assert record['zero_payout_hide_report'] == 'false'

    # scheduled_terms is an object — survives untouched
    assert isinstance(record['scheduled_terms'], dict)
    assert record['scheduled_terms']['effective_date'] == '2026-01-01T00:00:00Z'
    print("  ✅ 5 contract-level fields preserved + campaign_id coerced")


def test_transform_contracts_payout_restrictions_nested_field():
    """zero_payout_hide_report nested inside payout_restrictions[] should
    survive transform (Phase 2 — newly declared in schema)."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    pr = result[0]['template_terms']['events_payouts'][0]['payout_restrictions']

    assert isinstance(pr, list) and len(pr) == 1
    assert pr[0]['id'] == 'pr-1'
    assert pr[0]['zero_payout_hide_report'] == '1'
    print("  ✅ payout_restrictions[].zero_payout_hide_report preserved")


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


def test_transform_contracts_unknown_nested_fields_ride_through():
    """Unknown sub-fields inside the 8 sub-arrays under events_payouts[]
    (payouts_groups, payouts_adjustments, payout_restrictions,
    payout_scheduling, performance_bonus, limits, locking, valid_referrals)
    + promotional_terms[] should survive the Singer Transformer roundtrip,
    since those nested item schemas are now opaque {type: object} instead
    of strict-with-properties.

    Regression test for the dropped-data class of bug Phase 2 closes:
    future Impact API additions inside these sub-arrays must land in BQ."""
    import json, os
    from singer.transform import Transformer

    schema_path = os.path.join(os.path.dirname(__file__), '..',
                               'tap_impact', 'schemas', 'contracts.json')
    schema = json.load(open(schema_path))

    # Synthetic record with unknown sub-fields planted inside opaque containers.
    # CamelCase intentionally — mimics the real API shape pre-convert_json.
    synthetic = {
        "Contracts": [{
            "Id": "ride-through-test",
            "TemplateTerms": {
                "EventPayouts": [{
                    "EventTypeId": "1",
                    "PayoutGroups": [{
                        "Id": "pg-1",
                        "FutureImpactField": "should survive",
                        "DeepArray": [{"x": 1}]
                    }],
                    "Locking": {"basis": "TRACKED", "future_locking_field": "new"},
                    "ValidReferrals": [{"type": "X", "brand_new_field": "v"}]
                }]
            }
        }]
    }

    records = transform_json(synthetic, 'contracts', 'Contracts')
    out = Transformer().transform(records[0], schema)
    ep = out['template_terms']['events_payouts'][0]

    pg = ep['payouts_groups'][0]
    assert pg['future_impact_field'] == 'should survive', \
        f"Unknown nested field dropped — opacify regressed. Got: {pg}"
    assert pg['deep_array'] == [{'x': 1}]

    lock = ep['locking'][0]
    assert lock['future_locking_field'] == 'new'

    vr = ep['valid_referrals'][0]
    assert vr['brand_new_field'] == 'v'

    print("  ✅ unknown nested fields ride through opaque sub-array items")


def test_transform_contracts_renames_payout_groups_and_adjustments():
    """payout_groups/payout_adjustments (from convert_json) should be
    renamed to payouts_groups/payouts_adjustments (schema names), with
    data preserved. Regression test for the silent-data-loss bug where
    PayoutGroups/PayoutAdjustments arrived empty in BigQuery."""
    result = transform_json(SAMPLE_API_RESPONSE, 'contracts', 'Contracts')
    ep = result[0]['template_terms']['events_payouts'][0]

    # post-convert_json names should be gone
    assert 'payout_groups' not in ep, "payout_groups should be renamed to payouts_groups"
    assert 'payout_adjustments' not in ep, "payout_adjustments should be renamed to payouts_adjustments"

    # schema names should hold the original data (not lost to additionalProperties: false)
    assert isinstance(ep['payouts_groups'], list)
    assert len(ep['payouts_groups']) == 1, f"Expected 1 payouts_groups entry, got {len(ep['payouts_groups'])}"
    assert ep['payouts_groups'][0]['id'] == 'abc'

    # payout_adjustments was None in fixture; should become [] after rename + _ensure_list
    assert ep['payouts_adjustments'] == []
    print("  ✅ payout_groups/payout_adjustments renamed to schema names")


if __name__ == '__main__':
    print("Running transform_contracts tests...")
    test_transform_contracts_type_coercion()
    test_transform_contracts_events_payouts_preserved()
    test_transform_contracts_dict_to_list()
    test_transform_contracts_valid_referrals()
    test_transform_contracts_none_to_empty_list()
    test_transform_contracts_preserves_promotional_terms()
    test_transform_contracts_new_contract_level_fields()
    test_transform_contracts_payout_restrictions_nested_field()
    test_transform_contracts_labels_passthrough()
    test_transform_contracts_extraction_date_added()
    test_transform_contracts_unknown_nested_fields_ride_through()
    test_transform_contracts_renames_payout_groups_and_adjustments()
    print("\n✅ All 12 tests passed!")
