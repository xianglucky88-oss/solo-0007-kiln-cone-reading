READINGS = {'upright', 'bending', 'fallen', 'unreadable'}


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be nonempty text')
    return value


def _ceiling(document):
    maximum = document['rank_ceiling']
    if type(maximum) is not int or not 2 <= maximum <= 999:
        raise ValueError('rank_ceiling must be 2 through 999')
    return maximum


def _band(document, maximum):
    band = document['band']
    if (len(band) != 2 or any(type(v) is not int for v in band)
            or not 0 <= band[0] <= band[1] <= maximum):
        raise ValueError('invalid target band')
    return [band[0], band[1]]


def _catalog(document, maximum):
    catalog = document['cone_ranks']
    if not catalog or any(not text(name, 'cone') or type(rank) is not int or not 1 <= rank <= maximum
                          for name, rank in catalog.items()):
        raise ValueError('cone ranks must be within 1..rank_ceiling')
    return catalog


def _budget(document, field):
    for key in ('budget', 'k', 'discard'):
        if key in document:
            value = document[key]
            if type(value) is not int or value < 0:
                raise ValueError(f'{field} must be a nonnegative integer')
            return value
    return None


def parse(document):
    """Parse the original single-ticket-per-cone document."""
    maximum = _ceiling(document)
    band = _band(document, maximum)
    catalog = _catalog(document, maximum)
    racks = {}
    ticket_ids = set()
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


def is_v2_document(document):
    """The archive mode is opt-in through an explicit version/mode or discard budget."""
    if not isinstance(document, dict):
        return False
    version = document.get('version')
    if version not in (None, 1, 2):
        raise ValueError('unsupported version')
    if version == 2 or document.get('mode') == 'archive':
        return True
    if _budget(document, 'budget') is not None:
        return True
    racks = document.get('racks')
    return isinstance(racks, list) and any(
        isinstance(rack, dict) and _budget(rack, 'rack budget') is not None
        for rack in racks)


def parse_v2(document):
    """Parse a multi-ticket archive document or an archive snapshot."""
    maximum = _ceiling(document)
    band = _band(document, maximum)
    catalog = dict(sorted(_catalog(document, maximum).items()))
    top_budget = _budget(document, 'budget')
    default_budget = 0 if top_budget is None else top_budget
    rack_rows = document['racks']
    if not isinstance(rack_rows, list):
        raise ValueError('racks must be a list')
    ticket_ids = set()
    rack_names = set()
    racks = []
    for rack in rack_rows:
        if not isinstance(rack, dict):
            raise ValueError('invalid rack')
        name = text(rack['id'], 'rack id')
        if name in rack_names:
            raise ValueError(f'duplicate rack {name}')
        rack_names.add(name)
        own_budget = _budget(rack, f'budget for rack {name}')
        budget = default_budget if own_budget is None else own_budget
        witnesses = rack['witnesses']
        if not isinstance(witnesses, list):
            raise ValueError(f'invalid witnesses for rack {name}')
        rows = []
        for row in witnesses:
            if not isinstance(row, dict):
                raise ValueError(f'invalid witness in rack {name}')
            ticket = text(row['ticket'], 'ticket id')
            cone = text(row['cone'], 'cone')
            reading = row['reading']
            if ticket in ticket_ids:
                raise ValueError(f'invalid or repeated witness: {name}/{ticket}')
            if cone not in catalog or reading not in READINGS:
                raise ValueError(f'invalid or repeated witness: {name}/{ticket}')
            ticket_ids.add(ticket)
            rows.append({'ticket': ticket, 'cone': cone, 'reading': reading})
        rows.sort(key=lambda row: row['ticket'])
        racks.append({'id': name, 'budget': budget, 'witnesses': rows})
    if not racks:
        raise ValueError('expect at least one rack')
    racks.sort(key=lambda rack: rack['id'])
    return {'version': 2, 'rank_ceiling': maximum, 'band': band,
            'cone_ranks': catalog, 'budget': default_budget, 'racks': racks}


def parse_archive(document):
    """Recover an archive snapshot from a saved report, without the source document."""
    if not isinstance(document, dict):
        raise ValueError('archive must be an object')
    if 'archive' in document:
        snapshot = document['archive']
    elif document.get('version') == 2:
        # A bare version-2 archive document is itself the complete snapshot.
        snapshot = {key: value for key, value in document.items()
                    if key not in ('amendments', 'corrections', 'retractions')}
    else:
        raise ValueError('archive snapshot missing')
    if not isinstance(snapshot, dict) or snapshot.get('version') != 2:
        raise ValueError('unsupported archive snapshot')
    return parse_v2(snapshot)


def parse_amendments(document):
    """Parse a batch of reading corrections and ticket retractions.

    Corrections are keyed by ticket number only; a correction may optionally
    move the ticket to another cone, but never changes which rack owns it.
    """
    if not isinstance(document, dict):
        raise ValueError('amendments must be an object')
    correction_rows = document.get('corrections', [])
    retraction_rows = document.get('retractions', [])
    if not isinstance(correction_rows, list) or not isinstance(retraction_rows, list):
        raise ValueError('corrections and retractions must be lists')
    corrections = {}
    for row in correction_rows:
        if not isinstance(row, dict):
            raise ValueError('invalid correction')
        ticket = text(row['ticket'], 'ticket id')
        if ticket in corrections:
            raise ValueError(f'duplicate correction: {ticket}')
        reading = row['reading']
        if reading not in READINGS:
            raise ValueError(f'invalid reading for {ticket}')
        cone = text(row['cone'], 'cone') if 'cone' in row else None
        corrections[ticket] = {'reading': reading, 'cone': cone}
    retractions = set()
    for value in retraction_rows:
        ticket = text(value, 'ticket id')
        if ticket in retractions:
            raise ValueError(f'duplicate retraction: {ticket}')
        retractions.add(ticket)
    overlap = sorted(set(corrections) & retractions)
    if overlap:
        raise ValueError(f'conflicting amendment: {overlap[0]}')
    return corrections, retractions


def apply_amendments(state, corrections, retractions):
    """Apply amendments to a parsed state; return the new state and touched rack ids."""
    catalog = state['cone_ranks']
    for ticket, change in corrections.items():
        if change['cone'] is not None and change['cone'] not in catalog:
            raise ValueError(f'unknown cone for {ticket}')
    known = {row['ticket'] for rack in state['racks'] for row in rack['witnesses']}
    missing = sorted((set(corrections) | retractions) - known)
    if missing:
        raise ValueError(f'unknown ticket: {missing[0]}')
    touched = []
    racks = []
    for rack in state['racks']:
        rows = []
        hit = False
        for witness in rack['witnesses']:
            ticket = witness['ticket']
            if ticket in retractions:
                hit = True
                continue
            if ticket in corrections:
                change = corrections[ticket]
                cone = change['cone'] if change['cone'] is not None else witness['cone']
                if (change['reading'], cone) != (witness['reading'], witness['cone']):
                    hit = True
                witness = {'ticket': ticket, 'cone': cone, 'reading': change['reading']}
            rows.append(witness)
        if hit:
            touched.append(rack['id'])
        racks.append({'id': rack['id'], 'budget': rack['budget'], 'witnesses': rows})
    return {'version': 2, 'rank_ceiling': state['rank_ceiling'], 'band': list(state['band']),
            'cone_ranks': dict(state['cone_ranks']), 'budget': state['budget'],
            'racks': racks}, touched
