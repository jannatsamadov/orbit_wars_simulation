import math

def get_fleet_speed(ships: int) -> float:
    """Calculate fleet speed based on the number of ships."""
    if ships <= 1:
        return 1.0
    return 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5

def agent(obs):
    """
    Orbit Wars agent.
    Handles both dictionary-style and object-style observations.
    Returns a list of moves: [[from_planet_id, angle, ships], ...]
    """
    # --- 1. Safe observation parsing ---
    if isinstance(obs, dict):
        player = obs.get("player", 0)
        angular_velocity = obs.get("angular_velocity", 0.0)
        planets_raw = obs.get("planets", [])
        fleets_raw = obs.get("fleets", [])
    else:
        player = getattr(obs, "player", 0)
        angular_velocity = getattr(obs, "angular_velocity", 0.0)
        planets_raw = getattr(obs, "planets", [])
        fleets_raw = getattr(obs, "fleets", [])

    # Convert raw planet data into a more usable structure
    planets = []
    for p in planets_raw:
        planets.append({
            "id": p[0],
            "owner": p[1],
            "x": p[2],
            "y": p[3],
            "radius": p[4],
            "ships": p[5],
            "production": p[6]
        })

    # Separate my planets, enemy/neutral planets
    my_planets = [p for p in planets if p["owner"] == player]
    other_planets = [p for p in planets if p["owner"] != player]

    if not my_planets:
        return []   # no planets owned, no moves possible

    moves = []

    # --- 2. Simple heuristic: attack nearest target with low ships ---
    for src in my_planets:
        available = src["ships"]
        if available <= 1:   # keep at least 1 for defence / production
            continue

        # Decide how many ships to send (here: half of the available ships)
        send_count = max(1, available // 2)

        # Find the best target among other planets (neutral or enemy)
        best_target = None
        best_score = float("inf")  # lower is better
        src_x, src_y = src["x"], src["y"]

        for tgt in other_planets:
            # Skip if target is out of reach (optional)
            dx = tgt["x"] - src_x
            dy = tgt["y"] - src_y
            dist = math.hypot(dx, dy)
            if dist < 1e-6:
                continue   # same position, unlikely

            # Compute fleet speed for this number of ships
            speed = get_fleet_speed(send_count)
            travel_time = dist / speed

            # Simple scoring: prefer closer planets with fewer defending ships
            # Lower score = better target
            score = dist + tgt["ships"] * 5.0  # weight ships higher
            # You can add more heuristics (e.g., prefer neutral, avoid strong enemies)

            if score < best_score:
                best_score = score
                best_target = tgt

        if best_target is None:
            continue

        # Compute angle to the target (stationary assumption – replace with lead computation if needed)
        dx = best_target["x"] - src_x
        dy = best_target["y"] - src_y
        angle = math.atan2(dy, dx)

        # Add the move
        moves.append([src["id"], angle, send_count])

    return moves