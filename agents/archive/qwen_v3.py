import math
from collections import defaultdict, namedtuple

BOARD_SIZE = 100.0
SUN_X, SUN_Y = 50.0, 50.0
SUN_R = 10.0
MAX_SPEED = 6.0
ROTATION_LIMIT = 50.0

Planet = namedtuple("Planet", ["id", "owner", "x", "y", "radius", "ships", "production"])
Fleet = namedtuple("Fleet", ["id", "owner", "x", "y", "angle", "from_planet_id", "ships"])

def get_speed(ships):
    if ships <= 1: return 1.0
    return 1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000.0)) ** 1.5

def dist(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)

def point_to_segment_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    seg_sq = dx*dx + dy*dy
    if seg_sq < 1e-9: return dist(px, py, x1, y1)
    t = max(0.0, min(1.0, ((px - x1)*dx + (py - y1)*dy) / seg_sq))
    return dist(px, py, x1 + t*dx, y1 + t*dy)

def hits_sun(x1, y1, x2, y2):
    return point_to_segment_dist(SUN_X, SUN_Y, x1, y1, x2, y2) < SUN_R + 0.5

class NemesisAgent:
    def __init__(self):
        self.turn = 0
        self.initial_planets = {}
        self.ang_vel = 0.0
        self.prev_enemy_fleets = set()
        self.my_commitments = defaultdict(int)

    def parse_obs(self, obs):
        player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
        self.ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
        
        raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
        raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
        
        planets = [Planet(*p) for p in raw_planets]
        fleets = [Fleet(*f) for f in raw_fleets]
        
        if self.turn == 0:
            for p in planets:
                self.initial_planets[p.id] = p
                
        return player, planets, fleets

    def predict_pos(self, p, turns):
        if p.id not in self.initial_planets:
            return p.x, p.y
        init = self.initial_planets[p.id]
        r = dist(init.x, init.y, SUN_X, SUN_Y)
        if r + init.radius >= ROTATION_LIMIT:
            return p.x, p.y
        cur_theta = math.atan2(init.y - SUN_Y, init.x - SUN_X)
        new_theta = cur_theta + self.ang_vel * turns
        return SUN_X + r * math.cos(new_theta), SUN_Y + r * math.sin(new_theta)

    def aim(self, src, tgt_id, tgt_radius, ships, planets_dict):
        tx, ty = planets_dict[tgt_id].x, planets_dict[tgt_id].y
        angle = math.atan2(ty - src.y, tx - src.x)
        turns = 100
        
        for _ in range(5):
            speed = get_speed(ships)
            tx, ty = self.predict_pos(planets_dict[tgt_id], turns)
            
            lx = src.x + math.cos(angle) * (src.radius + 0.1)
            ly = src.y + math.sin(angle) * (src.radius + 0.1)
            
            if hits_sun(lx, ly, tx, ty):
                return None, None, None
                
            d = dist(lx, ly, tx, ty)
            new_turns = max(1, int(math.ceil(d / speed)))
            
            if abs(new_turns - turns) <= 1:
                return angle, new_turns, (tx, ty)
            turns = new_turns
            angle = math.atan2(ty - src.y, tx - src.x)
            
        return None, None, None

    def find_fleet_target(self, fleet, planets_dict):
        speed = get_speed(fleet.ships)
        vx = math.cos(fleet.angle) * speed
        vy = math.sin(fleet.angle) * speed
        
        for t in range(1, 100):
            fx = fleet.x + vx * t
            fy = fleet.y + vy * t
            
            if hits_sun(fleet.x, fleet.y, fx, fy):
                return None, None
                
            for pid, p in planets_dict.items():
                if pid == fleet.from_planet_id: continue
                px, py = self.predict_pos(p, t)
                if dist(fx, fy, px, py) <= p.radius + 0.5:
                    return pid, t
        return None, None

    def get_moves(self, obs):
        self.turn += 1
        player, planets, fleets = self.parse_obs(obs)
        planets_dict = {p.id: p for p in planets}
        
        my_planets = [p for p in planets if p.owner == player]
        enemy_planets = [p for p in planets if p.owner != -1 and p.owner != player]
        neutral_planets = [p for p in planets if p.owner == -1]
        
        moves = []
        
        current_enemy_fleets = {f.id for f in fleets if f.owner != player and f.owner != -1}
        new_fleets = [f for f in fleets if f.id in current_enemy_fleets and f.id not in self.prev_enemy_fleets]
        self.prev_enemy_fleets = current_enemy_fleets
        
        # PRIORITY 1: The Timing Snipe (Exploit Melis's capture evaluation)
        for f in new_fleets:
            target_id, t_arr = self.find_fleet_target(f, planets_dict)
            if target_id is None: continue
            
            target = planets_dict.get(target_id)
            if not target or target.owner != -1: continue
            
            target_garrison = target.ships + target.production * t_arr
            if f.ships <= target_garrison: continue
            
            post_capture = f.ships - target_garrison
            t_snipe = t_arr + 2
            snipe_needed = post_capture + target.production * (t_snipe - t_arr) + 1
            
            for src in my_planets:
                avail = src.ships - self.my_commitments[src.id]
                tx, ty = self.predict_pos(target, t_snipe)
                d = dist(src.x, src.y, tx, ty) - src.radius - target.radius
                if d <= 0: continue
                
                req_speed = d / t_snipe
                req_ships = 1
                while get_speed(req_ships) < req_speed and req_ships < 1000:
                    req_ships += 1
                    
                if avail >= req_ships + snipe_needed:
                    angle, turns, _ = self.aim(src, target_id, target.radius, req_ships + snipe_needed, planets_dict)
                    if angle is not None and turns <= t_snipe + 1:
                        moves.append([src.id, angle, req_ships + snipe_needed])
                        self.my_commitments[src.id] += req_ships + snipe_needed
                        break

        # PRIORITY 2: Destroy Enemy Stockpiles (Mega-Hammer Disruption)
        for src in my_planets:
            avail = src.ships - self.my_commitments[src.id]
            if avail < 30: continue
            
            best_target = None
            best_score = -1
            
            for ep in enemy_planets:
                if ep.ships > 40 and ep.production < 3:
                    angle, turns, _ = self.aim(src, ep.id, ep.radius, avail, planets_dict)
                    if angle is not None:
                        score = ep.ships * 2 - turns
                        if score > best_score:
                            best_score = score
                            best_target = (ep, angle, turns, avail)
                            
            if best_target:
                ep, angle, turns, ships = best_target
                moves.append([src.id, angle, ships])
                self.my_commitments[src.id] += ships
                continue

        # PRIORITY 3: Safe Expansion & Tempo Captures
        for src in my_planets:
            avail = src.ships - self.my_commitments[src.id]
            if avail < 15: continue
            
            best_target = None
            best_score = -1
            
            for np in neutral_planets:
                min_enemy_dist = min([dist(np.x, np.y, ep.x, ep.y) for ep in enemy_planets] or [100])
                if min_enemy_dist < 20: continue
                
                needed = np.ships + np.production * 10 + 1
                if avail >= needed:
                    angle, turns, _ = self.aim(src, np.id, np.radius, avail, planets_dict)
                    if angle is not None:
                        score = np.production * 10 - turns
                        if score > best_score:
                            best_score = score
                            best_target = (np, angle, turns, needed)
                            
            if best_target:
                np, angle, turns, ships = best_target
                moves.append([src.id, angle, ships])
                self.my_commitments[src.id] += ships
                
        return moves

agent_instance = NemesisAgent()
def agent(obs):
    return agent_instance.get_moves(obs)