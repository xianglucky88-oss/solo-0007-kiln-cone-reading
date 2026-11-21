"""Input validation for the legacy rack report and the bundle/rack archive.

Both document shapes share the original catalog (``cone_ranks``) and the ticket
reading vocabulary.  The archive adds a candidate rack list per bundle, a
recipe band per rack and handoff tickets that narrow one bundle/rack pairing
to a closed integer ordinal interval.

Field aliases are accepted where the wording of an archive is ambiguous, e.g.
``bundles``/``packs`` or ``band``/``target_band``.  Every accepted document is
normalized to one internal shape, so the reporting code never re-parses input.
"""
READINGS = {'upright', 'bending', 'fallen', 'unreadable'}

# A witness row is a 4-tuple: (ticket id, reading, cone name, cone rank).
BUNDLE_KEYS = ('bundles', 'packs')
CANDIDATE_KEYS = ('candidates', 'candidate_racks', 'racks')
BAND_KEYS = ('band', 'target_band', 'recipe_band')
WITNESS_KEYS = ('witnesses', 'readings', 'tickets')
HANDOFF_KEYS = ('handoffs', 'handoff_tickets')
LOW_HIGH_KEYS = ('low', 'high')


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be nonempty text')
    return value


def _rank(value, field, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{field} must be an integer in 0..rank_ceiling')
    return value


def _common(document):
    if not isinstance(document, dict):
        raise ValueError('document must be a JSON object')
    for key in ('rank_ceiling', 'cone_ranks'):
        if key not in document:
            raise ValueError(f'document needs {key}')
    maximum = document['rank_ceiling']
    if type(maximum) is not int or not 2 <= maximum <= 999:
        raise ValueError('rank_ceiling must be 2 through 999')
    catalog = document['cone_ranks']
    if (not isinstance(catalog, dict) or not catalog
            or any(not text(name, 'cone') or type(rank) is not int or not 1 <= rank <= maximum
                   for name, rank in catalog.items())):
        raise ValueError('cone ranks must be within 1..rank_ceiling')
    return maximum, catalog


def _band(value, maximum, field):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(v) is not int for v in value)
            or not 0 <= value[0] <= value[1] <= maximum):
        raise ValueError(f'invalid {field}')
    return (value[0], value[1])


def _first(mapping, keys, what):
    present = [key for key in keys if key in mapping]
    if not present:
        raise ValueError(f'missing {what}')
    if len(present) > 1:
        raise ValueError(f'conflicting {what} fields: {", ".join(present)}')
    return mapping[present[0]]


def _witness_rows(rows, catalog, ticket_ids, where):
    """Validate witness rows for one bundle/rack; return sorted 4-tuples."""
    if not isinstance(rows, list):
        raise ValueError(f'{where} witnesses must be a list')
    parsed = []
    seen_cones = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f'invalid witness in {where}')
        ticket = text(row.get('ticket'), 'ticket id')
        cone = text(row.get('cone'), 'cone')
        reading = row.get('reading')
        if ticket in ticket_ids or cone in seen_cones or cone not in catalog or reading not in READINGS:
            raise ValueError(f'invalid or repeated witness: {where}/{ticket}')
        ticket_ids.add(ticket)
        seen_cones.add(cone)
        parsed.append((ticket, reading, cone, catalog[cone]))
    return sorted(parsed)


def parse_legacy(document):
    """Original rack-only document: each rack yields an independent interval."""
    maximum, catalog = _common(document)
    if 'band' not in document:
        raise ValueError('document needs band')
    band = _band(document['band'], maximum, 'target band')
    ticket_ids = set()
    racks = {}
    for rack in document['racks']:
        name = text(rack['id'], 'rack id')
        if name in racks:
            raise ValueError(f'duplicate rack {name}')
        rows = []
        seen = set()
        for row in rack['witnesses']:
            ticket = text(row['ticket'], 'ticket id')
            cone = text(row['cone'], 'cone')
            reading = row['reading']
            if ticket in ticket_ids or cone in seen or cone not in catalog or reading not in READINGS:
                raise ValueError(f'invalid or repeated witness: {name}/{ticket}')
            ticket_ids.add(ticket)
            seen.add(cone)
            rows.append((ticket, reading, catalog[cone]))
        racks[name] = sorted(rows)
    if not racks:
        raise ValueError('expect at least one rack')
    return maximum, band, racks


def _rack_entries(document):
    """Yield ``(name, band_source)`` for list or mapping rack declarations."""
    declared = document['racks']
    if isinstance(declared, dict):
        for name, source in declared.items():
            if source is None:
                source = {}
            elif isinstance(source, (list, tuple)):
                source = {'band': source}
            if not isinstance(source, dict):
                raise ValueError('rack entries must be objects')
            yield text(name, 'rack id'), source
        return
    for rack in declared:
        if isinstance(rack, dict):
            name = text(rack.get('id'), 'rack id')
            yield name, rack
        else:
            name = text(rack, 'rack id')
            yield name, {}


def _rack_band(name, source, declared, default_band, maximum):
    for key in BAND_KEYS:
        if key in source:
            return _band(source[key], maximum, f'target band for rack {name}')
    if declared is not None and name in declared:
        return _band(declared[name], maximum, f'target band for rack {name}')
    return default_band


def _candidates(bundle, racks, name):
    value = _first(bundle, CANDIDATE_KEYS, f'candidate racks for bundle {name}')
    if not isinstance(value, list) or not value:
        raise ValueError(f'candidate racks for bundle {name} must be a nonempty list')
    candidates = []
    for item in value:
        candidate = text(item, 'candidate rack')
        if candidate not in racks:
            raise ValueError(f'unknown candidate rack {candidate} for bundle {name}')
        if candidate in candidates:
            raise ValueError(f'repeated candidate rack {candidate} for bundle {name}')
        candidates.append(candidate)
    return candidates


def _bundle_entries(document):
    """Yield ``(name, bundle object)`` for list or mapping bundle declarations."""
    for key in BUNDLE_KEYS:
        if key in document:
            declared = document[key]
            break
    else:
        raise ValueError('archive needs bundles')
    if isinstance(declared, dict):
        for name, bundle in declared.items():
            if not isinstance(bundle, dict):
                raise ValueError('bundle entries must be objects')
            yield text(name, 'bundle id'), bundle
    else:
        for bundle in declared:
            if not isinstance(bundle, dict):
                raise ValueError('bundle entries must be objects')
            yield text(bundle.get('id'), 'bundle id'), bundle


def _handoff_interval(ticket, label, maximum):
    if 'interval' in ticket and not any(key in ticket for key in LOW_HIGH_KEYS):
        interval = ticket['interval']
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            raise ValueError(f'{label} interval must be [low, high]')
        low, high = interval
    elif all(key in ticket for key in LOW_HIGH_KEYS):
        low, high = ticket['low'], ticket['high']
    else:
        raise ValueError(f'{label} needs low/high or interval')
    low = _rank(low, f'{label} low', maximum)
    high = _rank(high, f'{label} high', maximum)
    if low > high:
        raise ValueError(f'{label} needs an ascending interval')
    return low, high


def _handoff_entries(document, bundles):
    """Yield raw ``(bundle name, rack name, ticket)`` triples from all sources."""
    for source in (document.get(HANDOFF_KEYS[0], ()), document.get(HANDOFF_KEYS[1], ())):
        if not isinstance(source, (list, tuple)):
            raise ValueError('handoff tickets must be a list')
        for ticket in source:
            if not isinstance(ticket, dict):
                raise ValueError('handoff entries must be objects')
            bundle_name = text(ticket.get('bundle', ticket.get('pack')), 'handoff bundle')
            rack_name = text(ticket.get('rack'), 'handoff rack')
            yield bundle_name, rack_name, ticket
    for name, bundle in bundles.items():
        source = None
        for key in HANDOFF_KEYS:
            if key in bundle:
                source = bundle[key]
                break
        if source is None:
            continue
        if not isinstance(source, (list, tuple)):
            raise ValueError(f'handoff tickets for bundle {name} must be a list')
        for ticket in source:
            if not isinstance(ticket, dict):
                raise ValueError(f'handoff entries in bundle {name} must be objects')
            # A bundle-level entry names only the rack.
            yield name, text(ticket.get('rack'), 'handoff rack'), ticket


def parse_archive(document):
    """Bundle/rack archive with candidate racks, per-rack bands and handoffs.

    Returns ``(maximum, bundles, racks, handoffs)`` where ``bundles`` maps a
    bundle id to ``{'readings': rows, 'candidates': [rack ids]}``, ``racks``
    maps a rack id to its target band and ``handoffs`` maps a
    ``(bundle, rack)`` pair to its list of ``(ticket, low, high)`` entries.
    """
    maximum, catalog = _common(document)
    if 'racks' not in document:
        raise ValueError('archive needs racks')

    default_band = None
    for key in BAND_KEYS:
        if key in document:
            default_band = _band(document[key], maximum, 'target band')
            break
    declared_bands = document.get('bands')
    if declared_bands is not None and not isinstance(declared_bands, dict):
        raise ValueError('bands must map rack ids to target bands')

    racks = {}
    for name, source in _rack_entries(document):
        if name in racks:
            raise ValueError(f'duplicate rack {name}')
        if 'witnesses' in source or 'readings' in source:
            raise ValueError(f'archive racks do not carry witnesses: rack {name}')
        band = _rack_band(name, source, declared_bands, default_band, maximum)
        if band is None:
            raise ValueError(f'rack {name} needs a target band')
        racks[name] = band
    if not racks:
        raise ValueError('expect at least one rack')

    ticket_ids = set()
    bundles = {}
    for name, bundle in _bundle_entries(document):
        if name in bundles:
            raise ValueError(f'duplicate bundle {name}')
        rows = _first(bundle, WITNESS_KEYS, f'witnesses for bundle {name}')
        readings = _witness_rows(rows, catalog, ticket_ids, f'bundle {name}')
        bundles[name] = {'readings': readings,
                         'candidates': _candidates(bundle, racks, name)}
    if not bundles:
        raise ValueError('expect at least one bundle')
    if len(bundles) != len(racks):
        raise ValueError('expect as many bundles as racks: each is used exactly once')

    handoffs = {}
    seen_pairs = set()
    owners = {row[0]: name for name, bundle in bundles.items() for row in bundle['readings']}
    for bundle_name, rack_name, ticket in _handoff_entries(document, bundles):
        if bundle_name not in bundles:
            raise ValueError(f'unknown handoff bundle {bundle_name}')
        if rack_name not in racks:
            raise ValueError(f'unknown handoff rack {rack_name}')
        if rack_name not in bundles[bundle_name]['candidates']:
            raise ValueError(f'handoff for {bundle_name}/{rack_name} is not a candidate pairing')
        label = f'handoff for {bundle_name}/{rack_name}'
        raw_identifier = ticket.get('ticket', ticket.get('id'))
        if raw_identifier is None:
            raise ValueError(f'{label} needs a ticket id')
        identifier = text(raw_identifier, 'handoff ticket id')
        owner = owners.get(identifier)
        if owner is not None and owner != bundle_name:
            raise ValueError(f'handoff ticket {identifier} belongs to bundle {owner}')
        if (bundle_name, rack_name, identifier) in seen_pairs:
            raise ValueError(f'repeated handoff ticket {identifier} for {bundle_name}/{rack_name}')
        seen_pairs.add((bundle_name, rack_name, identifier))
        low, high = _handoff_interval(ticket, label, maximum)
        handoffs.setdefault((bundle_name, rack_name), []).append((identifier, low, high))
    return maximum, bundles, racks, handoffs


# The original rack-only parser keeps its historical name.
parse = parse_legacy
