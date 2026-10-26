"""Which picked day gets which role in a week."""


def _dist(a: int, b: int) -> int:
    return min(abs(a - b), 7 - abs(a - b))


def layout(days_pos: list[int], n_quality: int) -> dict[int, str]:
    """Roles per Egyptian-week position (Saturday = 0 ... Friday = 6).

    Long run on Friday if picked, else Saturday, else the last picked day. Hard days go
    on the picked day furthest from the hard days already placed; a second hard day
    only with at least one day gap.
    """
    pos = sorted(days_pos)
    roles: dict[int, str] = {}
    long_day = 6 if 6 in pos else 0 if 0 in pos else pos[-1]
    roles[long_day] = "long"
    picked = [long_day]
    for q in range(n_quality):
        cands = sorted(
            ((p, min(_dist(p, x) for x in picked)) for p in pos if p not in picked),
            key=lambda c: (-c[1], c[0]),
        )
        if not cands:
            break
        if q > 0 and cands[0][1] < 2:
            break
        roles[cands[0][0]] = "q1" if q == 0 else "q2"
        picked.append(cands[0][0])
    for p in pos:
        roles.setdefault(p, "easy")
    return roles
