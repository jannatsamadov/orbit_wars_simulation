import math
import logging

W = {
    "temporal_discount": 0.96,       
    "min_deploy": 10,                
    "reserve_base": 1.0,             
    "defense_oversend": 2,           
}

# --- Core Classes ---
class Planet:
    __slots__ = ['id', 'owner', 'x', 'y', 'radius', 'ships', 'production']
    def __init__(self, p_id, owner, x, y, radius, ships, production):
        self.id = p_id
        self.owner = owner
        self.x = x
        self.y = y
        self.radius = radius
        self.ships = ships
        self.production = production

class Fleet:
    __slots__ = ['id', 'owner', 'x', 'y', 'angle', 'from_id', 'ships']
    def __init__(self, f_id, owner, x, y, angle, from_id, ships):
        self.id = f_id
        self.owner = owner
        self.x = x
        self.y = y
        self.angle = angle
        self.from_id = from_id
        self.ships = ships

class World:
    def __init__(self, obs):
        self.player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
        self.ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else obs.angular_velocity
        self.step = obs.get("step", 0) if isinstance(obs, dict) else obs.step
        
        self.planets = {}
        raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
        for p in raw_planets:
            self.planets[p[0]] = Planet(*p)
            
        self.fleets = []
        raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else obs.fleets
        for f in raw_fleets:
            self.fleets.append(Fleet(*f))
            
        self.comet_ids = set()
        comets = obs.get("comets", []) if isinstance(obs, dict) else obs.comets
        for c_group in comets:
            c_pids = c_group.get("planet_ids", []) if isinstance(c_group, dict) else []
            self.comet_ids.update(c_pids)
            
        self.initial_planets = {}
        # We assume initial state has id == index in standard Kaggle env
        for p in raw_planets:
            self.initial_planets[p[0]] = Planet(*p)

# --- Kinematics ---
def fleet_speed(ships: int) -> float:
    if ships <= 1: return 1.0
    ratio = max(0.0, min(1.0, math.log(ships) / math.log(1000.0)))
    return 1.0 + 5.0 * (ratio ** 1.5)

def dist(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)

def predict_pos(w: World, pid: int, turns: int) -> tuple:
    p = w.planets[pid]
    if pid in w.comet_ids:
        # Comet simple projection (linear for fallback, but ideally use paths)
        # Simplified: comets move, but we don't have the paths object easily. 
        # Actually Kaggle gives paths. Let's just use static for comets if no path, 
        # or ignore comets for now to avoid out-of-bounds complexity.
        return None 
        
    r = dist(p.x, p.y, 50.0, 50.0)
    if r + p.radius >= 50.0:
        return (p.x, p.y)
        
    init_p = w.initial_planets[pid]
    current_angle = math.atan2(p.y - 50.0, p.x - 50.0)
    new_angle = current_angle + w.ang_vel * turns
    return (50.0 + r * math.cos(new_angle), 50.0 + r * math.sin(new_angle))

def point_line_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx*dx + dy*dy
    if length_sq < 1e-6: return dist(px, py, x1, y1)
    t = max(0.0, min(1.0, ((px - x1)*dx + (py - y1)*dy) / length_sq))
    return dist(px, py, x1 + t*dx, y1 + t*dy)

def sun_blocks(sx, sy, tx, ty):
    return point_line_dist(50.0, 50.0, sx, sy, tx, ty) < 11.5

def solve_intercept(w: World, src_pid: int, tgt_pid: int, ships: int) -> tuple:
    if ships < 1: return None
    s = w.planets[src_pid]
    speed = fleet_speed(ships)
    
    # Iterative solver
    flight = math.ceil(dist(s.x, s.y, w.planets[tgt_pid].x, w.planets[tgt_pid].y) / speed)
    for _ in range(5):
        fp = predict_pos(w, tgt_pid, flight)
        if fp is None: return None
        if fp[0] < 0 or fp[0] > 100 or fp[1] < 0 or fp[1] > 100: return None
        new_flight = math.ceil(dist(s.x, s.y, fp[0], fp[1]) / speed)
        if new_flight == flight:
            if sun_blocks(s.x, s.y, fp[0], fp[1]): return None
            return math.atan2(fp[1] - s.y, fp[0] - s.x), flight
        flight = new_flight
    return None

# --- Timeline Simulation ---
def trace_fleets(w: World):
    arrivals = {}
    for f in w.fleets:
        tgt_pid = f.from_id # Simplification: Kaggle fleets don't track target directly. 
        # Actually Kaggle fleets just fly. Intersections are complex.
        # We need a proper arrival map. 
        # In this advanced agent, we use a robust spatial trace.
        fx, fy = f.x, f.y
        vx = math.cos(f.angle) * fleet_speed(f.ships)
        vy = math.sin(f.angle) * fleet_speed(f.ships)
        
        hit_turn = -1
        hit_pid = -1
        
        for turn in range(1, 100):
            fx += vx
            fy += vy
            if fx < 0 or fx > 100 or fy < 0 or fy > 100: break
            
            for pid, p in w.planets.items():
                ppos = predict_pos(w, pid, turn)
                if ppos and dist(fx, fy, ppos[0], ppos[1]) <= p.radius:
                    hit_turn = turn
                    hit_pid = pid
                    break
            if hit_turn != -1: break
            
        if hit_turn != -1:
            if hit_pid not in arrivals: arrivals[hit_pid] = []
            arrivals[hit_pid].append((hit_turn, f.owner, f.ships))
    return arrivals

def simulate_timeline(w: World, pid: int, arrivals: dict, max_turns=50):
    timeline = []
    p = w.planets[pid]
    owner = p.owner
    garrison = p.ships
    
    arrs = arrivals.get(pid, [])
    turn_arrs = {}
    for t, o, s in arrs:
        if t not in turn_arrs: turn_arrs[t] = {0:0, 1:0, 2:0, 3:0}
        turn_arrs[t][o] += s
        
    for turn in range(1, max_turns + 1):
        if owner != -1: garrison += p.production
        
        if turn in turn_arrs:
            forces = turn_arrs[turn]
            forces[owner] = forces.get(owner, 0) + garrison
            
            # Combat resolution
            sorted_forces = sorted(forces.items(), key=lambda x: x[1], reverse=True)
            top_o, top_s = sorted_forces[0]
            sec_s = sorted_forces[1][1] if len(sorted_forces) > 1 else 0
            
            survivors = top_s - sec_s
            if top_o != owner:
                if survivors > 0:
                    owner = top_o
                    garrison = survivors
                else:
                    garrison = 0
            else:
                garrison = survivors
                
        timeline.append((owner, garrison))
    return timeline

# --- Wavefront Core ---
def agent(obs):
    w = World(obs)
    moves = []
    
    my_planets = [p for p in w.planets.values() if p.owner == w.player]
    if not my_planets: return []
    
    arrivals = trace_fleets(w)
    
    # 1. Defense Phase (Self-Preservation)
    allocated = {p.id: 0 for p in my_planets}
    deployable = {}
    for p in my_planets:
        tl = simulate_timeline(w, p.id, arrivals, 30)
        min_gar = min([g for o, g in tl if o == w.player] + [0])
        safe = p.ships
        if any(o != w.player for o, g in tl):
            safe = 0 # Need help
        else:
            reserve = int(p.production * W["reserve_base"])
            safe = max(0, p.ships - reserve)
        deployable[p.id] = safe
        
    # 2. Target Evaluation
    candidate_actions = []
    for tgt in w.planets.values():
        tl = simulate_timeline(w, tgt.id, arrivals, 50)
        
        for T in range(1, 50):
            proj_o, proj_g = tl[T-1]
            if proj_o == w.player: continue
            
            req = proj_g + (5 if proj_o != -1 else 1)
            
            # Find planets that can hit at exactly T or earlier
            can_hit_now = []
            can_hit_later = []
            
            for src in my_planets:
                if deployable[src.id] < W["min_deploy"]: continue
                # We will send AT LEAST min_deploy ships, so calculate speed based on that
                res = solve_intercept(w, src.id, tgt.id, max(W["min_deploy"], req))
                if not res: continue
                angle, turns = res
                
                if turns == T:
                    can_hit_now.append((src.id, deployable[src.id], angle))
                elif turns < T:
                    can_hit_later.append((src.id, deployable[src.id]))
                    
            now_force = sum(s for _, s, _ in can_hit_now)
            later_force = sum(s for _, s in can_hit_later)
            
            if now_force + later_force >= req and now_force > 0:
                # We can form a wavefront!
                req_with_overkill = int(req * 1.5)  # Overkill to crush Hammers
                strict_need = req - later_force
                need_from_now = max(strict_need, min(now_force, req_with_overkill - later_force))
                need_from_now = max(W["min_deploy"], need_from_now)
                
                if need_from_now <= now_force:
                    owner_mult = 1.9 if proj_o != -1 else 1.3
                    score = (((tgt.production + 1.0) ** 2) * owner_mult * (W["temporal_discount"] ** T)) / max(1.0, req)
                    
                    candidate_actions.append({
                        'tgt': tgt.id,
                        'T': T,
                        'score': score,
                        'need_from_now': need_from_now,
                        'sources_now': can_hit_now
                    })
                    break # Optimal T found for this target
                    
    # 3. Execution (Greedy Wavefront Resolution)
    candidate_actions.sort(key=lambda x: x['score'], reverse=True)
    
    for action in candidate_actions:
        rem_need = action['need_from_now']
        
        # Check if sources still have enough deployable
        actual_now_force = sum(deployable[sid] for sid, _, _ in action['sources_now'])
        if actual_now_force < rem_need: continue
        
        # Execute
        for sid, _, angle in action['sources_now']:
            if rem_need <= 0: break
            avail = deployable[sid]
            if avail < W["min_deploy"]: continue
            
            send = min(avail, rem_need)
            if send >= W["min_deploy"]:
                moves.append([int(sid), float(angle), int(send)])
                deployable[sid] -= send
                rem_need -= send
                
    # 4. Logistics Gradient Flow (Backline Drain via Potential Fields)
    potentials = {}
    enemies = [p for p in w.planets.values() if p.owner != w.player]
    for p in my_planets:
        # High potential = frontline (close to enemies) + high production
        pot = p.production * 10.0
        for e in enemies:
            d = max(1.0, dist(p.x, p.y, e.x, e.y))
            pot += (e.production * 100.0) / d
        potentials[p.id] = pot

    for p in my_planets:
        avail = deployable[p.id]
        if avail >= W["min_deploy"]:
            best_friend = None
            best_grad = 0.0
            for friend in my_planets:
                if friend.id == p.id: continue
                if potentials[friend.id] > potentials[p.id] * 1.2: # Must be significantly higher potential
                    d = max(1.0, dist(p.x, p.y, friend.x, friend.y))
                    grad = (potentials[friend.id] - potentials[p.id]) / d
                    if grad > best_grad:
                        best_grad = grad
                        best_friend = friend
            
            if best_friend:
                res = solve_intercept(w, p.id, best_friend.id, avail)
                if res:
                    angle, _ = res
                    moves.append([int(p.id), float(angle), int(avail)])
                    deployable[p.id] = 0
                
    return moves
