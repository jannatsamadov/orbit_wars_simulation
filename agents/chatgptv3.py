import math

SUN_X = 50.0
SUN_Y = 50.0
SUN_R = 10.0


def get_fleet_speed(ships: int) -> float:
    if ships <= 1:
        return 1.0
    return 1.0 + (6.0 - 1.0) * (
        math.log(max(ships, 1)) / math.log(1000)
    ) ** 1.5


def _get(obs, key, default=None):
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def dist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def angle_to(x1, y1, x2, y2):
    return math.atan2(y2 - y1, x2 - x1)


def predict_planet_position(planet, turns, angular_velocity):
    """
    Inner planets orbit the sun. Static planets remain static.
    Since the observation format does not explicitly indicate which planets
    orbit, we infer orbiting bodies as planets within a reasonable distance
    from the sun and leave very distant bodies effectively unchanged.
    """
    pid, owner, x, y, radius, ships, production = planet

    dx = x - SUN_X
    dy = y - SUN_Y
    r = math.hypot(dx, dy)

    # Heuristic: planets relatively close to the sun are assumed orbiting.
    if r <= 40.0 and r > SUN_R:
        theta = math.atan2(dy, dx)
        theta += angular_velocity * turns
        return (
            SUN_X + r * math.cos(theta),
            SUN_Y + r * math.sin(theta),
        )

    return (x, y)


def segment_hits_sun(x1, y1, x2, y2):
    """
    Check if a straight-line launch path intersects the sun.
    """
    dx = x2 - x1
    dy = y2 - y1

    a = dx * dx + dy * dy
    if a < 1e-9:
        return False

    t = ((SUN_X - x1) * dx + (SUN_Y - y1) * dy) / a
    t = max(0.0, min(1.0, t))

    px = x1 + t * dx
    py = y1 + t * dy

    return dist(px, py, SUN_X, SUN_Y) < (SUN_R + 0.5)


def estimate_future_strength(
    target_planet,
    arrival_turns,
    my_player,
):
    """
    Estimate ships on arrival.
    """
    _, owner, _, _, _, ships, production = target_planet

    future = ships + production * arrival_turns

    if owner == my_player:
        return future

    return future


def compute_target_score(
    source,
    target,
    arrival_turns,
    my_player,
):
    """
    Strategic valuation:
    - Prefer high production.
    - Prefer weak planets.
    - Prefer closer planets.
    - Prefer enemy over neutral.
    """
    _, owner, _, _, _, ships, production = target

    future_strength = estimate_future_strength(
        target,
        arrival_turns,
        my_player,
    )

    owner_bonus = 1.0
    if owner == -1:
        owner_bonus = 1.15
    elif owner != my_player:
        owner_bonus = 1.5

    return (
        owner_bonus
        * (production + 1.0) ** 2
        / (future_strength + 5.0)
        / (arrival_turns + 1.0)
    )


def choose_intercept(
    source,
    target,
    angular_velocity,
    send_ships,
):
    """
    Fixed-point interception estimate.
    """
    sx = source[2]
    sy = source[3]

    speed = get_fleet_speed(send_ships)

    tx = target[2]
    ty = target[3]

    travel_turns = max(1.0, dist(sx, sy, tx, ty) / speed)

    for _ in range(5):
        px, py = predict_planet_position(
            target,
            travel_turns,
            angular_velocity,
        )

        d = dist(sx, sy, px, py)
        travel_turns = max(1.0, d / speed)

    px, py = predict_planet_position(
        target,
        travel_turns,
        angular_velocity,
    )

    return px, py, travel_turns


def agent(obs):
    player = _get(obs, "player", 0)
    angular_velocity = _get(obs, "angular_velocity", 0.0)

    planets = _get(obs, "planets", []) or []
    fleets = _get(obs, "fleets", []) or []

    moves = []

    if not planets:
        return moves

    my_planets = [p for p in planets if p[1] == player]

    if not my_planets:
        return moves

    enemy_planets = [p for p in planets if p[1] not in (-1, player)]
    neutral_planets = [p for p in planets if p[1] == -1]

    # Track incoming friendly fleets.
    incoming_friendly = {}
    for f in fleets:
        fid, owner, x, y, angle, from_pid, ships = f
        if owner == player:
            incoming_friendly[from_pid] = incoming_friendly.get(from_pid, 0) + ships

    # Expansion / attack phase.
    for source in sorted(my_planets, key=lambda p: p[6], reverse=True):
        pid, owner, sx, sy, radius, ships, production = source

        if ships < 15:
            continue

        reserve = max(
            10,
            int(ships * 0.35),
        )

        available = ships - reserve

        if available < 8:
            continue

        candidates = []

        for target in planets:
            if target[0] == pid:
                continue

            if target[1] == player:
                continue

            # Initial estimate using medium fleet size.
            probe_size = max(8, min(available, 40))

            px, py, eta = choose_intercept(
                source,
                target,
                angular_velocity,
                probe_size,
            )

            if segment_hits_sun(sx, sy, px, py):
                continue

            score = compute_target_score(
                source,
                target,
                eta,
                player,
            )

            candidates.append((score, target, eta, px, py))

        if not candidates:
            continue

        candidates.sort(key=lambda x: x[0], reverse=True)

        best_score, target, eta, px, py = candidates[0]

        future_strength = estimate_future_strength(
            target,
            eta,
            player,
        )

        required = int(future_strength + 3)

        # Send only what is necessary.
        send = min(
            available,
            max(8, required),
        )

        if send > available:
            continue

        angle = angle_to(sx, sy, px, py)

        moves.append([
            int(pid),
            float(angle),
            int(send),
        ])

    # Reinforcement phase for strong production worlds.
    if len(moves) < 3:
        strong = sorted(
            my_planets,
            key=lambda p: (p[6], p[5]),
            reverse=True,
        )

        if strong:
            hub = strong[0]

            for source in my_planets:
                if source[0] == hub[0]:
                    continue

                ships = source[5]

                if ships < 40:
                    continue

                send = int(ships * 0.25)

                hx, hy = hub[2], hub[3]

                if segment_hits_sun(
                    source[2],
                    source[3],
                    hx,
                    hy,
                ):
                    continue

                moves.append([
                    int(source[0]),
                    float(angle_to(
                        source[2],
                        source[3],
                        hx,
                        hy
                    )),
                    int(send),
                ])

                if len(moves) >= 5:
                    break

    return moves