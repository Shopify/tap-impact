"""Pins the contracts stream's Status param to the values verified against
api.impact.com on 2026-05-20.

Without Status, the Impact API defaults to ACTIVE-only, silently dropping
EXPIRED, PENDING, and UPCOMING contracts. The RestContractStatus enum accepts
exactly 5 values: ACTIVE, EXPIRED, PENDING, UPCOMING, DECLINED. DECLINED is
intentionally excluded as it represents partner-rejected proposals that never
went live.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tap_impact.streams import STREAMS


VALID_STATES = {'ACTIVE', 'EXPIRED', 'PENDING', 'UPCOMING'}
DECLINED_INTENTIONALLY_EXCLUDED = {'DECLINED'}
INVALID_ENUM_VALUES = {'SCHEDULED', 'TERMINATED', 'INACTIVE', 'ALL', 'ANY'}


def _contracts_config():
    return STREAMS['campaigns']['children']['contracts']


def test_contracts_stream_passes_status_param():
    params = _contracts_config().get('params', {})
    assert 'Status' in params, (
        "contracts stream must pass Status param; without it the Impact API "
        "defaults to ACTIVE-only and drops EXPIRED + PENDING + UPCOMING contracts."
    )


def test_contracts_status_param_includes_all_required_states():
    values = {s.strip() for s in _contracts_config()['params']['Status'].split(',')}
    assert values == VALID_STATES, (
        f"Status must be exactly {VALID_STATES}; got {values}. "
        f"These are the 4 RestContractStatus enum values that should land in BQ — "
        f"DECLINED is the 5th valid value but is intentionally excluded as rejection-noise."
    )


def test_contracts_status_param_excludes_declined():
    values = {s.strip() for s in _contracts_config()['params']['Status'].split(',')}
    assert not (values & DECLINED_INTENTIONALLY_EXCLUDED), (
        "DECLINED is intentionally excluded — partner-rejected proposals that "
        "never went live; revisit if rejection-pipeline visibility is needed."
    )


def test_contracts_status_param_excludes_invalid_enum_values():
    values = {s.strip() for s in _contracts_config()['params']['Status'].split(',')}
    bad = values & INVALID_ENUM_VALUES
    assert not bad, (
        f"Status must not include {bad} — these raise a RestContractStatus binding "
        f"error from the API."
    )
