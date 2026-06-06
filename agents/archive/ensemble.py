import math

# Constants
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0

def fleet_speed(n):
    if n <= 1: return 1.0
    return 1.0 + 5.0 * (math.log(max(n, 1)) / math.log(1000)) ** 1.5

def eta(dist, n):
    s = fleet_speed(max(1, n))
    return dist / s if s > 0 else float('inf')

def edist(x1, y1, x2, y2):
    return math.sqrt((x1-x2)**2 + (y1-y2)**2)

def seg_pt_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d2 = dx*dx + dy*dy
    if d2 < 1e-12: return edist(px, py, ax, ay)
    t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy)/d2))
    return edist(px, py, ax+t*dx, ay+t*dy)

def path_thru_sun(sx, sy, tx, ty):
    return seg_pt_dist(SUN_X, SUN_Y, sx, sy, tx, ty) < SUN_R + 1.5

def orbit_xy(ox, oy, omega, t):
    dx, dy = ox - SUN_X, oy - SUN_Y
    r = math.hypot(dx, dy)
    theta = math.atan2(dy, dx) + omega * t
    return SUN_X + r * math.cos(theta), SUN_Y + r * math.sin(theta)

def intercept_pos(sx, sy, px, py, omega, n, is_orb, iters=30):
    if not is_orb or abs(omega) < 1e-9:
        d = edist(sx, sy, px, py)
        return px, py, math.atan2(py-sy, px-sx) if d > 1e-9 else 0.0, d
    
    tx, ty = float(px), float(py)
    for _ in range(iters):
        d = edist(sx, sy, tx, ty)
        if d < 1e-9: break
        t = eta(d, n)
        nx, ny = orbit_xy(px, py, omega, t)
        if edist(tx, ty, nx, ny) < 5e-4:
            tx, ty = nx, ny
            break
        tx, ty = 0.5 * tx + 0.5 * nx, 0.5 * ty + 0.5 * ny
    d = edist(sx, sy, tx, ty)
    return tx, ty, math.atan2(ty-sy, tx-sx) if d > 1e-9 else 0.0, d

def agent(obs):
    _d = isinstance(obs, dict)
    P = obs.get("player", 0) if _d else obs.player
    W = obs.get("angular_velocity", 0.0) if _d else getattr(obs, "angular_velocity", 0.0)
    raw_planets = obs.get("planets", []) if _d else obs.planets
    raw_fleets = obs.get("fleets", []) if _d else getattr(obs, "fleets", [])

    planets = []
    unique_owners = set()
    for p in raw_planets:
        try:
            pl = {
                'id': int(p[0]), 'owner': int(p[1]),
                'x': float(p[2]), 'y': float(p[3]),
                'radius': float(p[4]), 'ships': float(p[5]), 'prod': float(p[6])
            }
            sr = math.hypot(pl['x'] - SUN_X, pl['y'] - SUN_Y)
            pl['orb'] = abs(W) > 1e-9 and 10.0 < sr < 42.0
            pl['dist_to_sun'] = sr
            planets.append(pl)
            if pl['owner'] != -1: unique_owners.add(pl['owner'])
        except: pass

    # Detect 4v4 vs 1v1
    is_4_player = len(unique_owners) > 2

    # Incoming fleets
    my_in = {p['id']: 0.0 for p in planets}
    opp_in = {p['id']: 0.0 for p in planets}
    for f in raw_fleets:
        try:
            # simple destination guess based on distance and angle
            fx, fy, fa, fships = float(f[2]), float(f[3]), float(f[4]), float(f[6])
            best_dest = None
            best_d = float('inf')
            for pl in planets:
                d = edist(fx, fy, pl['x'], pl['y'])
                angle_to_p = math.atan2(pl['y']-fy, pl['x']-fx)
                if abs(math.atan2(math.sin(angle_to_p - fa), math.cos(angle_to_p - fa))) < 0.2:
                    if d < best_d:
                        best_d = d
                        best_dest = pl['id']
            if best_dest is not None:
                if int(f[1]) == P: my_in[best_dest] += fships
                else: opp_in[best_dest] += fships
        except: pass

    mine = [p for p in planets if p['owner'] == P]
    targets = [p for p in planets if p['owner'] != P]

    moves = []
    used_ships = {p['id']: 0 for p in mine}

    # Emergency Defense (Claude's strength)
    for p in mine:
        deficit = opp_in[p['id']] - p['ships'] - my_in[p['id']]
        if deficit > 0:
            need = int(deficit) + 2
            # find closest ally
            allies = sorted([a for a in mine if a['id'] != p['id']], key=lambda a: edist(a['x'],a['y'],p['x'],p['y']))
            for a in allies:
                avail = int(a['ships']) - used_ships[a['id']] - 1
                if avail >= need:
                    tx, ty, angle, d = intercept_pos(a['x'], a['y'], p['x'], p['y'], W, need, p['orb'])
                    if not path_thru_sun(a['x'], a['y'], tx, ty):
                        moves.append([a['id'], angle, need])
                        used_ships[a['id']] += need
                        break

    # Offensive / Expansion
    for src in mine:
        avail = int(src['ships']) - used_ships[src['id']] - max(1, int(opp_in[src['id']]))
        
        # Accumulate large fleets instead of sending trickles
        # Don't send unless we have at least 20% of the planet's capacity or 15 ships
        if avail < min(15, int(src['radius'] * 0.5)):
            continue

        best_score = -1
        best_target = None
        best_send = 0
        best_angle = 0
        
        for tgt in targets:
            tx, ty, angle, d = intercept_pos(src['x'], src['y'], tgt['x'], tgt['y'], W, avail, tgt['orb'])
            if d < 1e-6 or path_thru_sun(src['x'], src['y'], tx, ty): continue
            
            t_fly = eta(d, avail)
            g = tgt['ships'] + tgt['prod'] * t_fly + opp_in[tgt['id']] - my_in[tgt['id']]
            needed = max(1, int(g) + 2)
            
            if avail < needed: continue
            
            # Base economic score: favor HIGH production rate and low distance
            score = (tgt['prod'] ** 1.5) / (needed * (1.0 + d / 40.0))
            
            if tgt['owner'] == -1:
                score *= 1.5 # Neutral expansion
            else:
                score *= 1.2 # Enemy attack
                
            # 4-Player Strategy: Avoid center planets initially, go for outer high-prod planets
            if is_4_player:
                step = obs.get("step", 0) if _d else getattr(obs, "step", 0)
                if tgt['dist_to_sun'] < 30.0:
                    if step < 30:
                        continue # DO NOT ATTACK center at all for the first 30 turns
                    score *= 0.3 # Heavily penalize inner planets (center of attention)
                else:
                    score *= 1.8 # Reward outer planets
            else:
                # 1v1 strategy: just go for it
                if tgt['owner'] != -1: score *= 1.5
                
            if score > best_score:
                best_score = score
                best_target = tgt
                # Send a bit more than needed for speed, but don't waste everything
                best_send = max(needed, min(avail, int(needed * 1.3) + 5))
                best_angle = angle

        if best_target and best_score > 0.01:
            moves.append([src['id'], best_angle, best_send])
            used_ships[src['id']] += best_send

    return moves
