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
    
    best_target = max(targets, key=lambda t: t['prod'])
    
    total_avail = sum(int(m['ships']) for m in mine)
    needed = int(best_target['ships']) + 1
    
    if total_avail >= needed:
        for src in mine:
            avail = int(src['ships'])
            if avail <= 0: continue
            angle = math.atan2(best_target['y'] - src['y'], best_target['x'] - src['x'])
            moves.append([src['id'], angle, avail])

    return moves
