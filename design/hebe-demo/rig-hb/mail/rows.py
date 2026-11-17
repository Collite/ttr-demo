"""Required mail-profile rows in addition to the unchanged engine-profile checks.

An absent observation stays OPEN. No phone, manual walk, previous substrate exit,
or other row may substitute for a required live observation.
"""
ROWS = ('mail-channels', 'mail-delivery', 'R1', 'R2', 'R3-person', 'R3-service',
        'R3-negative', 'mail-stranger', 'mail-threads')


def table(observations):
    if set(observations) - set(ROWS):
        raise ValueError('unknown mail-profile row')
    result = []
    for name in ROWS:
        observation = observations.get(name, ('OPEN', 'live evidence required'))
        status, detail = observation
        if status not in ('PASS', 'FAIL', 'OPEN') or not isinstance(detail, str) or not detail:
            raise ValueError('each row needs PASS/FAIL/OPEN and an explanation')
        result.append((name, status, detail))
    return result


def exit_code(rows):
    if any(status == 'FAIL' for _, status, _ in rows):
        return 1
    return 3 if any(status == 'OPEN' for _, status, _ in rows) else 0


def pre_walk(rows):
    """T2's explicitly partial gate; this is never a complete-profile PASS."""
    names = [name for name, _, _ in rows]
    if len(names) != len(ROWS) or set(names) != set(ROWS):
        return False
    allowed_open = {'R3-person', 'mail-stranger', 'mail-threads'}
    return all(status == 'PASS' or (status == 'OPEN' and name in allowed_open)
               for name, status, _ in rows)
