import math

# ---------- Game mechanics ----------
def get_fleet_speed(ships: int) -> float:
    if ships <= 1:
        return 1.0
    return 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5


# ---------- Helper functions ----------
def _get_planet_pos(planet, t, angular_velocity):
    """Return (x, y) of planet at time t."""
    if not planet['orbiting']:
        return (planet['x'], planet['y'])
    cx, cy = 50.0, 50.0
    r = planet['orbit_radius']
    theta = planet['orbit_theta0'] + angular_velocity * t
    return (cx + r * math.cos(theta), cy + r * math.sin(theta))


def _segment_circle_intersect(p1, p2, center, radius):
    """True if segment p1->p2 intersects circle (center, radius)."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    fx = p1[0] - center[0]
    fy = p1[1] - center[1]

    a = dx * dx + dy * dy
    if a == 0:
        return math.hypot(fx, fy) <= radius
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4 * a * c
    if disc < 0:
        return False
    disc = math.sqrt(disc)
    t1 = (-b - disc) / (2 * a)
    t2 = (-b + disc) / (2 * a)
    return (0 <= t1 <= 1) or (0 <= t2 <= 1)


def _find_intercept_time(source_pos, planet, ships, angular_velocity):
    """Time for fleet with `ships` to reach planet (moving or static)."""
    v = get_fleet_speed(ships)
    if not planet['orbiting']:
        dist = math.hypot(planet['x'] - source_pos[0], planet['y'] - source_pos[1])
        return dist / v

    def f(t):
        ppos = _get_planet_pos(planet, t, angular_velocity)
        dist = math.hypot(ppos[0] - source_pos[0], ppos[1] - source_pos[1])
        return v * t - dist

    # Bisection – the function is monotonic for sensible times
    t_low, t_high = 0.0, 200.0
    f_low = f(t_low)
    for _ in range(40):
        t_mid = (t_low + t_high) / 2
        f_mid = f(t_mid)
        if f_mid == 0:
            return t_mid
        if f_low * f_mid < 0:
            t_high = t_mid
        else:
            t_low = t_mid
            f_low = f_mid
    return (t_low + t_high) / 2


def _fleet_planet_collision_time(fleet, planet, angular_velocity):
    """Time when given fleet hits a planet (or None). Accounts for planet motion."""
    v_f = get_fleet_speed(fleet['ships'])
    ux = math.cos(fleet['angle'])
    uy = math.sin(fleet['angle'])
    F0 = (fleet['x'], fleet['y'])
    R = planet['radius']

    def dist_at(t):
        fx = F0[0] + v_f * t * ux
        fy = F0[1] + v_f * t * uy
        ppos = _get_planet_pos(planet, t, angular_velocity)
        return math.hypot(fx - ppos[0], fy - ppos[1]) - R

    t_low, t_high = 0.0, 200.0
    f_low = dist_at(t_low)
    f_high = dist_at(t_high)
    if f_low < 0 and f_high < 0:  # starts inside? unlikely but fallback
        return 0.0
    if f_low * f_high > 0:
        return None  # no sign change

    for _ in range(40):
        t_mid = (t_low + t_high) / 2
        f_mid = dist_at(t_mid)
        if f_mid == 0:
            return t_mid
        if f_low * f_mid < 0:
            t_high = t_mid
            f_high = f_mid
        else:
            t_low = t_mid
            f_low = f_mid
    t = (t_low + t_high) / 2
    return t if abs(dist_at(t)) < 1.0 else None


def _ray_circle_intersection_time(start, dir_x, dir_y, speed, center, radius):
    """Time when a ray hits a circle. Returns None if no hit."""
    fx = start[0] - center[0]
    fy = start[1] - center[1]
    a = (speed * dir_x) ** 2 + (speed * dir_y) ** 2
    if a == 0:
        return None
    b = 2 * (fx * speed * dir_x + fy * speed * dir_y)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    sqrt_disc = math.sqrt(disc)
    t1 = (-b - sqrt_disc) / (2 * a)
    t2 = (-b + sqrt_disc) / (2 * a)
    ts = [t for t in (t1, t2) if t >= 0]
    return min(ts) if ts else None


# ---------- Main agent ----------
def agent(obs):
    # Flexible parsing (dict or object)
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    angular_velocity = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else obs.fleets

    SUN_CENTER = (50.0, 50.0)
    SUN_RADIUS = 10.0
    ORBIT_DIST_THRESHOLD = 45.0  # planets inside this are considered inner (orbiting)

    # ----- Parse planets -----
    planets = []
    for p in raw_planets:
        pid, owner, x, y, radius, ships, prod = p
        dist_to_sun = math.hypot(x - 50, y - 50)
        orbiting = (angular_velocity > 0 and
                    dist_to_sun > SUN_RADIUS + 0.5 and
                    dist_to_sun < ORBIT_DIST_THRESHOLD)
        orbit_theta0 = math.atan2(y - 50, x - 50) if dist_to_sun > 0 else 0.0
        planets.append({
            'id': pid, 'owner': owner,
            'x': x, 'y': y, 'radius': radius,
            'ships': ships, 'production': prod,
            'orbiting': orbiting,
            'orbit_radius': dist_to_sun,
            'orbit_theta0': orbit_theta0
        })

    # ----- Parse fleets -----
    fleets = []
    for f in raw_fleets:
        fid, owner, x, y, angle, from_planet_id, ships = f
        fleets.append({
            'id': fid, 'owner': owner,
            'x': x, 'y': y, 'angle': angle,
            'from_planet': from_planet_id,
            'ships': ships
        })

    my_planets = [p for p in planets if p['owner'] == player]
    enemy_planets = [p for p in planets if p['owner'] != player and p['owner'] != -1]
    neutral_planets = [p for p in planets if p['owner'] == -1]
    # Only target planets we can predict: static outer or inner orbiting (exclude comets)
    target_planets = [p for p in enemy_planets + neutral_planets
                      if (p['orbiting'] or angular_velocity == 0)]

    # ----- Threat assessment -----
    threat_info = {p['id']: None for p in my_planets}  # planet_id -> {'time': t, 'ships': s}
    for fleet in fleets:
        if fleet['owner'] == player:
            continue
        v_f = get_fleet_speed(fleet['ships'])
        # Will this fleet die in the sun?
        t_sun = _ray_circle_intersection_time(
            (fleet['x'], fleet['y']),
            math.cos(fleet['angle']),
            math.sin(fleet['angle']),
            v_f, SUN_CENTER, SUN_RADIUS
        )
        for my_p in my_planets:
            t_coll = _fleet_planet_collision_time(fleet, my_p, angular_velocity)
            if t_coll is None:
                continue
            # Ignore if fleet hits the sun before reaching the planet
            if t_sun is not None and t_coll >= t_sun:
                continue
            if threat_info[my_p['id']] is None or t_coll < threat_info[my_p['id']]['time']:
                threat_info[my_p['id']] = {'time': t_coll, 'ships': fleet['ships']}

    # ----- Max launchable ships per planet (defence constraint) -----
    available = {}  # planet_id -> max ships we can send away
    for p in my_planets:
        cur = p['ships']
        threat = threat_info[p['id']]
        if threat is not None:
            t_threat = threat['time']
            enemy_ships = threat['ships']
            # ships left at impact must be > enemy_ships
            max_launch = cur + p['production'] * t_threat - enemy_ships - 1
            available[p['id']] = max(0, int(max_launch))
        else:
            available[p['id']] = max(0, cur - 1)  # keep at least 1 for safety

    # ----- Generate candidate moves -----
    candidates = []  # (priority_score, move_dict)

    # 1. Offensive moves
    for src in my_planets:
        src_id = src['id']
        if available[src_id] <= 0:
            continue
        source_pos = (src['x'], src['y'])
        for tgt in target_planets:
            # Rough estimate of required ships
            dist_static = math.hypot(tgt['x'] - src['x'], tgt['y'] - src['y'])
            est_t = dist_static / 3.0
            required_init = tgt['ships'] + tgt['production'] * est_t + 5  # margin
            max_send = available[src_id]
            if required_init > max_send:
                continue

            ships_to_send = min(int(required_init), max_send)
            t_arr = _find_intercept_time(source_pos, tgt, ships_to_send, angular_velocity)
            if t_arr is None or t_arr <= 0:
                continue
            # Recalculate required with actual arrival time
            required = tgt['ships'] + tgt['production'] * t_arr + 2
            if required > ships_to_send:
                ships_to_send = min(int(required), max_send)
                if ships_to_send > max_send:
                    continue
                t_arr = _find_intercept_time(source_pos, tgt, ships_to_send, angular_velocity)
                if t_arr is None:
                    continue
            # Sun safety
            future_pos = _get_planet_pos(tgt, t_arr, angular_velocity)
            if _segment_circle_intersect(source_pos, future_pos, SUN_CENTER, SUN_RADIUS):
                continue
            angle = math.atan2(future_pos[1] - source_pos[1], future_pos[0] - source_pos[0])

            # Score: value production, penalise distance, boost neutral planets
            score = tgt['production'] * 50 - ships_to_send - t_arr * 0.5
            if tgt['owner'] == -1:
                score += 20
            candidates.append((score, {
                'type': 'attack',
                'src': src_id,
                'tgt_id': tgt['id'],
                'angle': angle,
                'ships': ships_to_send,
                't_arr': t_arr
            }))

    # 2. Defensive reinforcements
    for my_p in my_planets:
        threat = threat_info[my_p['id']]
        if threat is None:
            continue
        t_threat = threat['time']
        enemy_ships = threat['ships']
        current_defense = my_p['ships'] + my_p['production'] * t_threat
        if current_defense > enemy_ships:
            continue  # no help needed
        needed = enemy_ships - current_defense + 2  # margin

        for src in my_planets:
            if src['id'] == my_p['id'] or available[src['id']] <= 0:
                continue
            send = min(available[src['id']], needed + 5)
            source_pos = (src['x'], src['y'])
            t_reinf = _find_intercept_time(source_pos, my_p, send, angular_velocity)
            if t_reinf is None or t_reinf > t_threat - 1.0:
                continue
            future_pos = _get_planet_pos(my_p, t_reinf, angular_velocity)
            if _segment_circle_intersect(source_pos, future_pos, SUN_CENTER, SUN_RADIUS):
                continue
            angle = math.atan2(future_pos[1] - source_pos[1], future_pos[0] - source_pos[0])
            # High priority, proportional to urgency
            candidates.append((1000 + needed, {
                'type': 'defend',
                'src': src['id'],
                'tgt_id': my_p['id'],
                'angle': angle,
                'ships': send,
                't_arr': t_reinf
            }))

    # ----- Execute moves (greedy, best first) -----
    candidates.sort(key=lambda x: x[0], reverse=True)
    moves = []
    used_attacked = set()
    # Track remaining launchable ships after each commitment
    remaining = available.copy()

    for score, c in candidates:
        src_id = c['src']
        if remaining[src_id] < c['ships']:
            continue
        if c['type'] == 'attack':
            if c['tgt_id'] in used_attacked:
                continue
            used_attacked.add(c['tgt_id'])
        # Commit move
        remaining[src_id] -= c['ships']
        moves.append([src_id, c['angle'], c['ships']])

    return moves