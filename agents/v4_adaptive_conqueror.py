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
        
        best_score = -float('inf')
        best_target = None
        for t in targets:
            dist = math.hypot(src['x'] - t['x'], src['y'] - t['y'])
            if dist < 1e-5: continue
            score = t['prod'] / (dist ** 1.5)
            if score > best_score:
                best_score = score
                best_target = t
                
        if best_target:
            needed = int(best_target['ships']) + 1
            if avail >= needed:
                angle = math.atan2(best_target['y'] - src['y'], best_target['x'] - src['x'])
                moves.append([src['id'], angle, needed])
                used_ships[src['id']] += needed

    return moves
