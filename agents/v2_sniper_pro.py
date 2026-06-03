import math

SUN_X, SUN_Y = 50.0, 50.0

def fleet_speed(n):
    if n <= 1: return 1.0
    return 1.0 + 5.0 * (math.log(max(n, 1)) / math.log(1000)) ** 1.5

def eta(dist, n):
    s = fleet_speed(max(1, n))
    return dist / s if s > 0 else float('inf')

def orbit_xy(ox, oy, omega, t):
    dx, dy = ox - SUN_X, oy - SUN_Y
    r = math.hypot(dx, dy)
    theta = math.atan2(dy, dx) + omega * t
    return SUN_X + r * math.cos(theta), SUN_Y + r * math.sin(theta)

def intercept_pos(sx, sy, px, py, omega, n, is_orb, iters=30):
    if not is_orb or abs(omega) < 1e-9:
        d = math.hypot(px - sx, py - sy)
        return px, py, math.atan2(py-sy, px-sx) if d > 1e-9 else 0.0, d
    
    tx, ty = float(px), float(py)
    for _ in range(iters):
        d = math.hypot(tx - sx, ty - sy)
        if d < 1e-9: break
        t = eta(d, n)
        nx, ny = orbit_xy(px, py, omega, t)
        if math.hypot(tx - nx, ty - ny) < 5e-4:
            tx, ty = nx, ny
            break
        tx, ty = 0.5 * tx + 0.5 * nx, 0.5 * ty + 0.5 * ny
    d = math.hypot(tx - sx, ty - sy)
    return tx, ty, math.atan2(ty-sy, tx-sx) if d > 1e-9 else 0.0, d

def agent(obs):
    _d = isinstance(obs, dict)
    P = obs.get("player", 0) if _d else obs.player
    W = obs.get("angular_velocity", 0.0) if _d else getattr(obs, "angular_velocity", 0.0)
    raw_planets = obs.get("planets", []) if _d else obs.planets

    planets = []
    for p in raw_planets:
        try:
            pl = {
                'id': int(p[0]), 'owner': int(p[1]),
                'x': float(p[2]), 'y': float(p[3]),
                'radius': float(p[4]), 'ships': float(p[5]), 'prod': float(p[6])
            }
            sr = math.hypot(pl['x'] - SUN_X, pl['y'] - SUN_Y)
            pl['orb'] = abs(W) > 1e-9 and 10.0 < sr < 42.0
            planets.append(pl)
        except: pass

    mine = [p for p in planets if p['owner'] == P]
    targets = [p for p in planets if p['owner'] != P]

    if not targets or not mine:
        return []

    moves = []
    used_ships = {p['id']: 0 for p in mine}

    for src in mine:
        avail = int(src['ships']) - used_ships[src['id']]
        if avail <= 0: continue

        # Find nearest target planet
        best_target = min(targets, key=lambda t: math.hypot(src['x'] - t['x'], src['y'] - t['y']))
        
        needed = int(best_target['ships']) + 1
        if avail >= needed:
            # Orbit interception added for Sniper Pro!
            tx, ty, angle, d = intercept_pos(src['x'], src['y'], best_target['x'], best_target['y'], W, needed, best_target['orb'])
            
            moves.append([src['id'], angle, needed])
            used_ships[src['id']] += needed

    return moves
