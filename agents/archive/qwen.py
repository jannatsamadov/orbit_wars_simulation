import math

def get_fleet_speed(ships: int) -> float:
    """
    Calculate the fleet speed based on the number of ships.
    Formula: 1.0 + 5.0 * (log10(ships) / log10(1000)) ** 1.5, capped at 6.0.
    """
    if ships <= 1:
        return 1.0
    speed = 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5
    return min(speed, 6.0)

def is_sun_blocking(x1, y1, x2, y2):
    """
    Checks if the line segment from (x1, y1) to (x2, y2) intersects the Sun.
    Sun center: (50.0, 50.0), Radius: 10.0.
    """
    cx, cy = 50.0, 50.0
    r = 10.0
    dx = x2 - x1
    dy = y2 - y1
    fx = x1 - cx
    fy = y1 - cy
    
    a = dx**2 + dy**2
    if a == 0:
        return (fx**2 + fy**2) <= r**2
        
    b = 2 * (fx*dx + fy*dy)
    c = (fx**2 + fy**2) - r**2
    
    discriminant = b**2 - 4*a*c
    if discriminant < 0:
        return False
        
    sqrt_d = math.sqrt(discriminant)
    t1 = (-b - sqrt_d) / (2 * a)
    t2 = (-b + sqrt_d) / (2 * a)
    
    # Intersection occurs if the segment overlaps with the circle boundaries
    if (0 <= t1 <= 1) or (0 <= t2 <= 1) or (t1 < 0 and t2 > 1):
        return True
    return False

def predict_target_position(x, y, flight_time, angular_velocity, sun_x=50.0, sun_y=50.0):
    """
    Predicts the future position of a planet based on its orbit.
    Inner planets orbit counter-clockwise. 
    Note: The 'is_inner' heuristic should be updated based on actual game mechanics.
    """
    dist_to_sun = math.hypot(x - sun_x, y - sun_y)
    # Adjust threshold dynamically or replace with precise game logic
    is_inner = dist_to_sun < 30.0 
    
    if is_inner and angular_velocity > 0:
        dx = x - sun_x
        dy = y - sun_y
        current_angle = math.atan2(dy, dx)
        radius = math.hypot(dx, dy)
        future_angle = current_angle + (angular_velocity * flight_time)
        return sun_x + radius * math.cos(future_angle), sun_y + radius * math.sin(future_angle)
    return x, y

def solve_interception_angle(from_x, from_y, target_x, target_y, ships_sent, angular_velocity):
    """
    Iteratively solves for the interception angle, predicting target movement.
    """
    angle = math.atan2(target_y - from_y, target_x - from_x)
    
    # 5 iterations is usually sufficient for convergence in most interception scenarios
    for _ in range(5):
        dx = target_x - from_x
        dy = target_y - from_y
        dist = math.hypot(dx, dy)
        
        speed = get_fleet_speed(ships_sent)
        flight_time = dist / speed
        
        pred_x, pred_y = predict_target_position(target_x, target_y, flight_time, angular_velocity)
        
        dx = pred_x - from_x
        dy = pred_y - from_y
        angle = math.atan2(dy, dx)
        
        # Recalculate target for next iteration
        target_x, target_y = pred_x, pred_y
        
    return angle

def agent(obs):
    # Safe parsing supporting both dictionary and object representations
    if isinstance(obs, dict):
        player = obs.get("player", 0)
        angular_velocity = obs.get("angular_velocity", 0.0)
        raw_planets = obs.get("planets", [])
        raw_fleets = obs.get("fleets", [])
    else:
        player = getattr(obs, "player", 0)
        angular_velocity = getattr(obs, "angular_velocity", 0.0)
        raw_planets = getattr(obs, "planets", [])
        raw_fleets = getattr(obs, "fleets", [])

    moves = []
    
    # 1. Parse raw_planets into a usable format
    planets = {}
    for p in raw_planets:
        p_id, owner, x, y, radius, ships, production = p
        planets[p_id] = {
            "id": p_id, "owner": owner, "x": x, "y": y, 
            "radius": radius, "ships": ships, "production": production
        }
        
    fleets = []
    for f in raw_fleets:
        f_id, owner, x, y, angle, from_planet_id, ships = f
        fleets.append({
            "id": f_id, "owner": owner, "x": x, "y": y,
            "angle": angle, "from_planet_id": from_planet_id, "ships": ships
        })
        
    # --- YOUR CUSTOM LOGIC STARTS HERE ---
    # 2. Select targets (Baseline heuristic)
    my_planets = [p for p in planets.values() if p["owner"] == player and p["ships"] > 1]
    enemy_planets = [p for p in planets.values() if p["owner"] != player]
    
    for my_p in my_planets:
        if not enemy_planets:
            break
            
        # Find closest enemy planet
        target = min(enemy_planets, key=lambda t: math.hypot(t["x"] - my_p["x"], t["y"] - my_p["y"]))
        
        ships_to_send = my_p["ships"] - 1
        if ships_to_send <= 0:
            continue
            
        # 3. Calculate interception angles
        # Preliminary check if direct path is blocked by the sun
        if is_sun_blocking(my_p["x"], my_p["y"], target["x"], target["y"]):
            continue 
            
        angle = solve_interception_angle(
            my_p["x"], my_p["y"], 
            target["x"], target["y"], 
            ships_to_send, 
            angular_velocity
        )
        
        # Final safety check against sun using a ray extending across the board
        ray_end_x = my_p["x"] + math.cos(angle) * 200.0
        ray_end_y = my_p["y"] + math.sin(angle) * 200.0
        if is_sun_blocking(my_p["x"], my_p["y"], ray_end_x, ray_end_y):
            continue
            
        # 4. Append to moves: [from_planet_id, angle_in_radians, num_ships]
        moves.append([my_p["id"], angle, ships_to_send])
        
    # --- YOUR CUSTOM LOGIC ENDS HERE ---
    
    return moves