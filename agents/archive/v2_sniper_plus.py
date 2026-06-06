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
                'ships': float(p[5])
            })
        except: pass

    mine = [p for p in planets if p['owner'] == P]
    targets = [p for p in planets if p['owner'] != P]

    if not targets or not mine: return []

    moves = []
    for src in mine:
        avail = int(src['ships'])
        if avail <= 0: continue
        
        # Sniper+ looks for the closest target and attacks if it has enough ships
        nearest = min(targets, key=lambda t: math.hypot(src['x'] - t['x'], src['y'] - t['y']))
        needed = int(nearest['ships']) + 1
        
        if avail >= needed:
            angle = math.atan2(nearest['y'] - src['y'], nearest['x'] - src['x'])
            moves.append([src['id'], angle, needed])

    return moves
