import re
import singer
from datetime import datetime

LOGGER = singer.get_logger()

# Convert camelCase to snake_case
def convert(name):
    regsub = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', regsub).lower()


# Convert keys in json array
def convert_array(arr):
    new_arr = []
    for i in arr:
        if isinstance(i, list):
            new_arr.append(convert_array(i))
        elif isinstance(i, dict):
            new_arr.append(convert_json(i))
        else:
            new_arr.append(i)
    return new_arr


# Convert keys in json
def convert_json(this_json):
    out = {}
    for key in this_json:
        new_key = convert(key)
        if isinstance(this_json[key], dict):
            out[new_key] = convert_json(this_json[key])
        elif isinstance(this_json[key], list):
            out[new_key] = convert_array(this_json[key])
        else:
            out[new_key] = this_json[key]
    return out

# Add a field to each record to keep track of the extraction date
def add_extraction_date(records):
    for record in records:
        record["extraction_date"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return records


# Replace system/reserved field 'oid' with 'order_id'
def replace_order_id(this_json, data_key):
    i = 0
    for record in this_json[data_key]:
        order_id = record.get('oid')
        this_json[data_key][i]['order_id'] = order_id
        this_json[data_key][i].pop('oid', None)
        i = i + 1
    return this_json


# Replace system/reserved field 'oid' with 'order_id' in nested events
# Also adjust events sub-node to always by a list/array (instead of array AND dict)
def transform_conversion_paths(this_json, data_key):
    i = 0
    for record in this_json[data_key]:
        events = record.get('events')
        events_list = []
        if isinstance(events, list):
            events_list = events
        elif isinstance(events, dict):
            event = events.get('event')
            events_list.append(event)
        this_json[data_key][i].pop('events', None)
        this_json[data_key][i]['events'] = []
        for event in events_list:
            if isinstance(event, dict):
                order_id = event.get('oid')
                event.pop('oid', None)
                event['order_id'] = order_id
                this_json[data_key][i]['events'].append(event)

        referral_counts = record.get('referral_counts')
        referral_counts_list = []
        if isinstance(referral_counts, list):
            referral_counts_list = referral_counts
        elif isinstance(referral_counts, dict):
            referral_count = referral_counts.get('referral_count')
            referral_counts_list.append(referral_count)
        this_json[data_key][i].pop('referral_counts', None)
        this_json[data_key][i]['referral_counts'] = []
        for referral_count in referral_counts_list:
            if isinstance(referral_count, dict):
                this_json[data_key][i]['referral_counts'].append(referral_count)

        i = i + 1
    return this_json


# Safely coerce a string value to int, returning None on failure.
def _safe_int(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        LOGGER.warning('_safe_int: could not coerce %r to int, returning None', value)
        return None


# Safely coerce a string value to float, returning None on failure.
def _safe_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        LOGGER.warning('_safe_float: could not coerce %r to float, returning None', value)
        return None


# Ensure a value is a list.  Handles:
#   None          -> []
#   [items]       -> [items]          (already a list)
#   {single_obj}  -> [{single_obj}]   (API returns single object instead of array)
def _ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


# Transform contracts to fix mismatches between the Impact API response
# and the Singer schema.
#
# Key issues:
# 1. Field name mismatch: API returns "EventPayouts" which convert_json
#    turns into "event_payouts", but schema expects "events_payouts".
#    Same for "SpecialTermsList" -> "special_terms_list" (OK) and
#    "PromotionalTerms" -> "promotional_terms" (not in schema).
# 2. Type mismatches: API returns numerics as strings, single nested
#    objects as dicts where schema expects arrays.
# 3. additionalProperties: false means unrecognized fields cause drops.
def transform_contracts(this_json, data_key):
    for record in this_json[data_key]:
        template_terms = record.get('template_terms')
        if not template_terms or not isinstance(template_terms, dict):
            continue

        # --- fix field name: event_payouts -> events_payouts ---
        if 'event_payouts' in template_terms and 'events_payouts' not in template_terms:
            template_terms['events_payouts'] = template_terms.pop('event_payouts')

        # --- top-level template_terms: coerce string -> int/float ---
        template_terms['change_notification_period'] = _safe_int(
            template_terms.get('change_notification_period'))
        template_terms['max_return_percentage'] = _safe_float(
            template_terms.get('max_return_percentage'))
        template_terms['template_id'] = _safe_int(
            template_terms.get('template_id'))
        template_terms['version_id'] = _safe_int(
            template_terms.get('version_id'))
        template_terms['contract_start_slotting_fee'] = _safe_float(
            template_terms.get('contract_start_slotting_fee'))
        template_terms['first_action_slotting_fee'] = _safe_float(
            template_terms.get('first_action_slotting_fee'))
        template_terms['min_earning_per_click'] = _safe_float(
            template_terms.get('min_earning_per_click'))
        template_terms['monthly_slotting_fee'] = _safe_float(
            template_terms.get('monthly_slotting_fee'))
        template_terms['spend_limit'] = _safe_float(
            template_terms.get('spend_limit'))
        template_terms['action_limit'] = _safe_int(
            template_terms.get('action_limit'))

        # --- ensure array fields are lists (API may return None or single dict) ---
        template_terms['events_payouts'] = _ensure_list(
            template_terms.get('events_payouts'))
        template_terms['labels'] = _ensure_list(
            template_terms.get('labels'))
        template_terms['special_terms_list'] = _ensure_list(
            template_terms.get('special_terms_list'))

        # --- drop fields not in schema (additionalProperties: false) ---
        template_terms.pop('promotional_terms', None)

        # --- events_payouts items: coerce types + ensure nested arrays ---
        for ep in template_terms.get('events_payouts', []):
            if not isinstance(ep, dict):
                continue

            # string -> int / float coercions
            ep['event_type_id'] = _safe_int(ep.get('event_type_id'))
            ep['default_payout'] = _safe_float(ep.get('default_payout'))
            ep['default_payout_rate'] = _safe_float(ep.get('default_payout_rate'))

            # ensure sub-objects are always lists
            ep['limits'] = _ensure_list(ep.get('limits'))
            ep['locking'] = _ensure_list(ep.get('locking'))
            ep['payouts_adjustments'] = _ensure_list(ep.get('payouts_adjustments'))
            ep['payouts_groups'] = _ensure_list(ep.get('payouts_groups'))
            ep['payout_restrictions'] = _ensure_list(ep.get('payout_restrictions'))
            ep['payout_scheduling'] = _ensure_list(ep.get('payout_scheduling'))
            ep['performance_bonus'] = _ensure_list(ep.get('performance_bonus'))
            ep['valid_referrals'] = _ensure_list(ep.get('valid_referrals'))

            # coerce nested int fields inside sub-arrays
            for vr in ep.get('valid_referrals', []):
                if isinstance(vr, dict):
                    vr['window'] = _safe_int(vr.get('window'))

            for lock in ep.get('locking', []):
                if isinstance(lock, dict):
                    lock['month_offset'] = _safe_int(lock.get('month_offset'))
                    lock['day_offset'] = _safe_int(lock.get('day_offset'))

            for ps in ep.get('payout_scheduling', []):
                if isinstance(ps, dict):
                    ps['day_offset'] = _safe_int(ps.get('day_offset'))

        record['template_terms'] = template_terms
    return this_json


# Run all transforms: convert camelCase to snake_case for fieldname keys
def transform_json(this_json, stream_name, data_key):
    converted_json = convert_json(this_json)
    converted_data_key = convert(data_key)
    if stream_name in ('actions', 'action_updates'):
        transformed_json = replace_order_id(converted_json, converted_data_key)[converted_data_key]
    elif stream_name in ['conversion_paths']:
        transformed_json = transform_conversion_paths(converted_json, converted_data_key)[converted_data_key]
    elif stream_name == 'contracts':
        transformed_json = transform_contracts(converted_json, converted_data_key)[converted_data_key]
    else:
        transformed_json = converted_json[converted_data_key]
    
    records_with_timestamp = add_extraction_date(transformed_json)
    return records_with_timestamp
