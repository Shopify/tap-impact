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


# Unwrap XML-style container objects into flat arrays.
# The Impact API returns nested arrays wrapped in container objects, e.g.:
#   "EventPayouts": {"EventPayout": [{...}, ...]}  (multiple items)
#   "EventPayouts": {"EventPayout": {...}}          (single item as dict)
# After camelCase conversion this becomes:
#   "events_payouts": {"event_payout": [{...}, ...]}
# But the schema expects events_payouts to be a flat array.
def unwrap_container(value, singular_key):
    """Unwrap a container object into a list.

    Args:
        value: The field value (could be list, dict-wrapper, or None).
        singular_key: The snake_case singular key inside the wrapper dict.

    Returns:
        A list of items.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        inner = value.get(singular_key, [])
        if isinstance(inner, list):
            return inner
        elif isinstance(inner, dict):
            return [inner]
        return []
    return []


# Unwrap nested arrays in contract template_terms that use XML-style wrappers.
# Affected fields: events_payouts, labels, special_terms_list, and nested arrays
# within events_payouts items (limits, locking, payouts_adjustments, payouts_groups,
# payout_restrictions, payout_scheduling, performance_bonus, valid_referrals).
def transform_contracts(this_json, data_key):
    for record in this_json[data_key]:
        template_terms = record.get('template_terms')
        if not template_terms or not isinstance(template_terms, dict):
            continue

        # Unwrap top-level arrays in template_terms
        template_terms['events_payouts'] = unwrap_container(
            template_terms.get('events_payouts'), 'event_payout')
        template_terms['labels'] = unwrap_container(
            template_terms.get('labels'), 'label')
        template_terms['special_terms_list'] = unwrap_container(
            template_terms.get('special_terms_list'), 'special_terms')

        # Unwrap nested arrays within each event_payout item
        for ep in template_terms.get('events_payouts', []):
            if not isinstance(ep, dict):
                continue
            ep['limits'] = unwrap_container(ep.get('limits'), 'limit')
            ep['locking'] = unwrap_container(ep.get('locking'), 'locking')
            ep['payouts_adjustments'] = unwrap_container(
                ep.get('payouts_adjustments'), 'payouts_adjustment')
            ep['payouts_groups'] = unwrap_container(
                ep.get('payouts_groups'), 'payouts_group')
            ep['payout_restrictions'] = unwrap_container(
                ep.get('payout_restrictions'), 'payout_restriction')
            ep['payout_scheduling'] = unwrap_container(
                ep.get('payout_scheduling'), 'payout_schedule')
            ep['performance_bonus'] = unwrap_container(
                ep.get('performance_bonus'), 'performance_bonus')
            ep['valid_referrals'] = unwrap_container(
                ep.get('valid_referrals'), 'valid_referral')

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
