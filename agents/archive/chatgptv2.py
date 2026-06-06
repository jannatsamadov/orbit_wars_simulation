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


def dist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def angle_to(x1, y1, x2, y2):
    return math.atan2(y2 - y1, x2 - x1)


def point_line_distance(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay

    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))

    cx = ax + t * dx
    cy = ay + t * dy

    return math.hypot(px - cx, py - cy)


def path_crosses_sun(x1, y1, x2, y2):
    return point_line_distance(
        SUN_X, SUN_Y,
        x1, y1,
        x2, y2
    ) < SUN_R


def orbit_planet_position(x, y, angular_velocity, turns):
    dx = x - SUN_X
    dy = y - SUN_Y

    r = math.hypot(dx, dy)

    if r < SUN_R + 1e-9:
        return x, y

    theta = math.atan2(dy, dx)
    theta += angular_velocity * turns

    return (
        SUN_X + r * math.cos(theta),
        SUN_Y + r * math.sin(theta)
    )


def estimate_arrival_time(x1, y1, x2, y2, ships):
    d = dist(x1, y1, x2, y2)
    speed = get_fleet_speed(ships)
    return d / max(speed, 1e-9)


def predict_target_position(source, target, ships, angular_velocity):
    tx = target["x"]
    ty = target["y"]

    arrival = estimate_arrival_time(
        source["x"],
        source["y"],
        tx,
        ty,
        ships
    )

    return orbit_planet_position(
        tx,
        ty,
        angular_velocity,
        arrival
    )


def incoming_strength(pid, fleets):
    total = 0
    for f in fleets:
        if f["target_guess"] == pid:
            total += f["ships"]
    return total


def agent(obs):

    player = (
        obs.get("player", 0)
        if isinstance(obs, dict)
        else obs.player
    )

    angular_velocity = (
        obs.get("angular_velocity", 0.0)
        if isinstance(obs, dict)
        else getattr(obs, "angular_velocity", 0.0)
    )

    raw_planets = (
        obs.get("planets", [])
        if isinstance(obs, dict)
        else getattr(obs, "planets", [])
    )

    raw_fleets = (
        obs.get("fleets", [])
        if isinstance(obs, dict)
        else getattr(obs, "fleets", [])
    )

    planets = []

    for p in raw_planets:
        planets.append({
            "id": int(p[0]),
            "owner": int(p[1]),
            "x": float(p[2]),
            "y": float(p[3]),
            "radius": float(p[4]),
            "ships": int(p[5]),
            "production": float(p[6]),
        })

    planet_by_id = {p["id"]: p for p in planets}

    fleets = []

    for f in raw_fleets:
        fleet = {
            "id": int(f[0]),
            "owner": int(f[1]),
            "x": float(f[2]),
            "y": float(f[3]),
            "angle": float(f[4]),
            "from_planet": int(f[5]),
            "ships": int(f[6]),
        }

        best_pid = None
        best_score = float("inf")

        for p in planets:
            dx = p["x"] - fleet["x"]
            dy = p["y"] - fleet["y"]

            target_angle = math.atan2(dy, dx)

            diff = abs(
                math.atan2(
                    math.sin(target_angle - fleet["angle"]),
                    math.cos(target_angle - fleet["angle"])
                )
            )

            if diff < best_score:
                best_score = diff
                best_pid = p["id"]

        fleet["target_guess"] = best_pid
        fleets.append(fleet)

    my_planets = [p for p in planets if p["owner"] == player]
    enemy_planets = [
        p for p in planets
        if p["owner"] not in (-1, player)
    ]
    neutral_planets = [
        p for p in planets
        if p["owner"] == -1
    ]

    moves = []

    reserved = {}

    for p in my_planets:
        enemy_pressure = 0

        for f in fleets:
            if (
                f["owner"] != player
                and f["target_guess"] == p["id"]
            ):
                enemy_pressure += f["ships"]

        reserve = max(
            10,
            int(enemy_pressure * 1.15)
        )

        reserved[p["id"]] = reserve

    targets = []

    for t in planets:

        if t["owner"] == player:
            continue

        pressure = incoming_strength(t["id"], fleets)

        effective_defense = max(
            0,
            t["ships"] + pressure
        )

        value = (
            8.0 * t["production"]
            - 0.08 * effective_defense
        )

        if t["owner"] == -1:
            value += 3.0

        targets.append((value, t))

    targets.sort(reverse=True, key=lambda x: x[0])

    used_sources = set()

    for _, target in targets:

        best_source = None
        best_score = -1e18
        best_send = None
        best_angle = None

        for source in my_planets:

            if source["id"] in used_sources:
                continue

            available = (
                source["ships"]
                - reserved[source["id"]]
            )

            if available <= 5:
                continue

            need = (
                target["ships"]
                + int(target["production"] * 3)
                + 5
            )

            send = min(
                available,
                max(need, int(available * 0.55))
            )

            if send <= 0:
                continue

            px, py = predict_target_position(
                source,
                target,
                send,
                angular_velocity
            )

            if path_crosses_sun(
                source["x"],
                source["y"],
                px,
                py
            ):
                continue

            d = dist(
                source["x"],
                source["y"],
                px,
                py
            )

            score = (
                15.0 * target["production"]
                - 0.4 * target["ships"]
                - 0.15 * d
            )

            if target["owner"] == -1:
                score += 5.0

            if score > best_score:
                best_score = score
                best_source = source
                best_send = send
                best_angle = angle_to(
                    source["x"],
                    source["y"],
                    px,
                    py
                )

        if best_source is None:
            continue

        moves.append([
            best_source["id"],
            float(best_angle),
            int(best_send)
        ])

        used_sources.add(best_source["id"])

    return moves