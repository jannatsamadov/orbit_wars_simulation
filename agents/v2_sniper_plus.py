"""
Orbit Wars — Agent v2: "Nearest Sniper Plus"

v1 (baseline) üzərindən ilk yenilikler:
  - Production-weighted priority (sadəcə yaxınlığa deyil, istehsala da baxır)
  - Min garrison qorunması (planetdə 10 gəmi qalır)
  - Multi-planet fire (bir neçə planetdən eyni anda göndərir)

Orbit prediction YOXDUR — bu v2-nin əsas zəifligidir.
Fırlanan planetlər üçün CARI mövqeyə atəş edir → çox vaxt misses.
(Bu xəta v3-də düzəldildi.)
"""

import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet

SUN_X, SUN_Y = 50.0, 50.0
SUN_R = 10.0
MIN_GARRISON = 10


def fleet_speed(ships):
    if ships <= 1:
        return 1.0
    return 1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5


def hits_sun(x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    fx, fy = x0 - SUN_X, y0 - SUN_Y
    a = dx*dx + dy*dy
    if a == 0:
        return math.hypot(fx, fy) < SUN_R
    t = max(0.0, min(1.0, -(fx*dx + fy*dy) / a))
    return math.hypot(x0 + t*dx - SUN_X, y0 + t*dy - SUN_Y) < SUN_R


def agent(obs):
    moves = []
    if isinstance(obs, dict):
        player = obs.get("player", 0)
        raw_planets = obs.get("planets", [])
    else:
        player = obs.player
        raw_planets = obs.planets

    planets = [Planet(*p) for p in raw_planets]
    my_planets = [p for p in planets if p.owner == player]
    targets = [p for p in planets if p.owner != player]

    if not targets:
        return moves

    targeted = set()

    for mine in my_planets:
        available = mine.ships - MIN_GARRISON
        if available <= 5:
            continue

        # Production² / distance scoring (cari mövqeye görə)
        best = None
        best_score = -1
        for t in targets:
            if t.id in targeted:
                continue
            dist = math.hypot(mine.x - t.x, mine.y - t.y)
            score = (t.production ** 2) / max(dist, 0.1)
            if score > best_score:
                best_score = score
                best = t

        if best is None:
            continue

        ships_needed = best.ships + 5
        if available < ships_needed:
            continue

        # Cari mövqeyə atəş (orbit prediction yoxdur!)
        if hits_sun(mine.x, mine.y, best.x, best.y):
            continue

        angle = math.atan2(best.y - mine.y, best.x - mine.x)
        moves.append([mine.id, angle, min(ships_needed, available)])
        targeted.add(best.id)

    return moves
