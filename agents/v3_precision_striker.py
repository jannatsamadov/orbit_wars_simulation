import math

def agent(obs):
    _d = isinstance(obs, dict)
    P = obs.get("player", 0) if _d else obs.player
    raw_planets = obs.get("planets", []) if _d else obs.planets

    planets = []
    for p in raw_planets:
        try:
            planets.append({
                'id': int(p[0]), 'owner': int(p[1]),
                'x': float(p[2]), 'y': float(p[3]),
                'ships': float(p[5]), 'prod': float(p[6])
            })
        except: pass

    mine = [p for p in planets if p['owner'] == P]
    targets = [p for p in planets if p['owner'] != P]

    if not targets or not mine: return []

    moves = []
    used_ships = {p['id']: 0 for p in mine}

    for src in mine:
        avail = int(src['ships']) - used_ships[src['id']]
        if avail <= 0: continue
        
        nearest = min(targets, key=lambda t: math.hypot(src['x'] - t['x'], src['y'] - t['y']))
        dist = math.hypot(src['x'] - nearest['x'], src['y'] - nearest['y'])
        eta = int(dist / 2.0)
        needed = int(nearest['ships']) + (int(nearest['prod']) * eta) + 1
        
        if avail >= needed:
            angle = math.atan2(nearest['y'] - src['y'], nearest['x'] - src['x'])
            moves.append([src['id'], angle, needed])
            used_ships[src['id']] += needed

    return moves
