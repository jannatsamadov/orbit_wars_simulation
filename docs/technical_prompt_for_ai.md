Act as an expert AI developer for Python and Kaggle Environments. I need you to write a single-file Python agent for a game called "Orbit Wars". 

Your task is to design and implement the most advanced, highly competitive, and state-of-the-art strategy to win this game against other strong agents. You have complete freedom to use advanced algorithms, predictive targeting, heuristics, or any other sophisticated mathematical approach. Output the valid Python code for the `agent(obs)` function that parses the environment correctly, respects the physics/mechanics of the game, and outputs the exact required action format.

### 1. Game Environment & Mechanics
- **Board:** 100x100 grid. The center is a Sun at `(50.0, 50.0)` with a radius of `10.0`.
- **Sun Collision:** Any fleet that passes through the Sun (distance to center < 10.0) is instantly destroyed.
- **Planets:** 
  - Inner planets orbit the Sun counter-clockwise at a constant `angular_velocity` (radians/turn).
  - Outer planets are static.
  - Comets may spawn. They travel in elliptical orbits and disappear when they leave the board. While owned, they produce ships.
- **Combat & Capture:**
  - When a fleet arrives at a planet, its ships subtract from the planet's garrison.
  - If the garrison drops below 0, the planet changes ownership to the fleet's owner.
  - Planets generate new ships every turn based on their `production` rate.
- **Fleet Speed (CRITICAL FORMULA):** 
  - Fleet speed scales logarithmically based on the number of ships.
  - `speed = 1.0` if `ships <= 1`.
  - `speed = 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5`
  - Max speed is 6.0.

### 2. Input Observation Format
Your agent function must be defined as `def agent(obs):`
The `obs` object (which might be a dictionary or a custom object depending on local vs Kaggle execution) contains:
- `obs.player` (or `obs["player"]`): Your player ID (0 to 3).
- `obs.angular_velocity` (or `obs["angular_velocity"]`): Rotation speed of orbiting planets (float).
- `obs.planets`: A list of lists representing planets. Each planet list contains:
  `[id, owner, x, y, radius, ships, production]`
  (Note: `owner == -1` means the planet is Neutral. `id` is a unique int).
- `obs.fleets`: A list of lists representing fleets currently in flight. Each fleet list contains:
  `[id, owner, x, y, angle, from_planet_id, ships]`

### 3. Output Action Format
- The function must return a Python list of moves: `[]`
- Each move is a list of exactly 3 elements: `[from_planet_id, angle_in_radians, num_ships]`
- Constraints for moves:
  1. `from_planet_id` must be a planet you own (`owner == obs.player`).
  2. `num_ships` must be an integer and cannot exceed the ships currently available on that planet.
  3. `angle_in_radians` is a float representing the exact angle (using `math.atan2(dy, dx)`) to launch the fleet. Once launched, fleets CANNOT change direction.

### 4. Code Structure Requirement
Your code must import `math` and handle both dictionary-style `obs` and object-style `obs`. Example structure:

```python
import math

def get_fleet_speed(ships: int) -> float:
    if ships <= 1: return 1.0
    return 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5

def agent(obs):
    # Safe parsing
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    angular_velocity = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    
    moves = []
    
    # YOUR LOGIC HERE:
    # 1. Parse raw_planets and raw_fleets into a usable format
    # 2. Design an advanced mathematical targeting and interception strategy
    # 3. Consider both short-term targets and long-term momentum
    # 4. Append to moves: [my_planet_id, angle, ships_to_send]
    
    return moves
```

Please generate the complete, ready-to-run `agent` function applying your most advanced and highly competitive strategic algorithms based on the physics constraints provided. Your code must be robust, bug-free, and capable of dominating other agents.
