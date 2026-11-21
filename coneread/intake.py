READINGS = {'upright', 'bending', 'fallen', 'unreadable'}


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be nonempty text')
    return value


def parse_named(document):
    """Parse the unchanged input contract, keeping each witness's cone name."""
    maximum = document['rank_ceiling']
    if type(maximum) is not int or not 2 <= maximum <= 999:
        raise ValueError('rank_ceiling must be 2 through 999')
    band = document['band']
    if (len(band) != 2 or any(type(v) is not int for v in band)
        or not 0 <= band[0] <= band[1] <= maximum):
        raise ValueError('invalid target band')
    catalog = document['cone_ranks']
    if not catalog or any(not text(name, 'cone') or type(rank) is not int or not 1 <= rank <= maximum
                          for name, rank in catalog.items()):
        raise ValueError('cone ranks must be within 1..rank_ceiling')
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
            rows.append((ticket, cone, reading, catalog[cone]))
        racks[name] = sorted(rows)
    if not racks:
        raise ValueError('expect at least one rack')
    return maximum, band, catalog, racks


def parse(document):
    maximum, band, _catalog, named_racks = parse_named(document)
    racks = {name: [(ticket, reading, rank)
                    for ticket, _cone, reading, rank in rows]
             for name, rows in named_racks.items()}
    return maximum, band, racks
