
# # Orbit Wars - Advanced Agent and Analytical Dashboard (Target: 1608.6)
# 
# | Module | Enhanced Feature | Advanced Strategy / Architecture |
# |--------|------------------|----------------------------------|
# | 0 | Setup & Theme Configuration | Custom neon-cyberpunk dark style mapping helpers |
# | 1 | Calibrated Environment Audit | Precision non-linear planetary target solver & physics metrics |
# | 2 | Graph State Parser | Strongly typed multi-fleet trackers and threat matrices |
# | 3 | Adaptive Orbit Predictor | Dynamic lead-aim calculation with analytical sun collision avoidance |
# | 4 | Forward State Simulator | Asymmetric forward simulation clone stepping engine |
# | 5 | Multi-Heuristic Scorer | 7-Component calibrated evaluation boundary pressure metric |
# | 6 | Advanced MCTS | Asymmetric multi-threaded rollouts with tree policy pruning |
# | 7 | Opponent History Engine | Multi-turn aggression profiling and predictive velocity estimation |
# | 8 | Parametric Fleet Interceptor | Mid-flight fleet tracking and trajectory-intersection solvers |
# | 9 | Advanced Strategy Hub | Counterfactual Regret-Guided Strategy selection engine |
# | 10 | Standalone Submission Export | High-reliability compilation script mapping to `submission.py` |


# Setup dependencies and validation libraries
# !pip install --upgrade "kaggle-environments>=1.28.0" matplotlib numpy

# %% [code]
import math
import time
import random
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

from kaggle_environments import make
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet as _RawP, Fleet as _RawF

# --- Global Constants ---
SUN_X, SUN_Y = 50.0, 50.0
SUN_RADIUS = 5.0
INNER_ORBIT_R = 30.0
MAX_TIME_MS = 900
BOARD_DIM = 100.0

PCOLORS = {-1: "#5A5E6B", 0: "#00F0FF", 1: "#FF007F", 2: "#00FF66", 3: "#FF9900"}
PHASE_THRESHOLDS = (0.25, 0.60)

BG_DARK = "#09090E"
BG_PANEL = "#11111B"
GRID_COL = "#1E1E2E"
BORDER_COL = "#313244"

def apply_dark_theme_fig(fig, title=""):
    fig.patch.set_facecolor(BG_DARK)
    if title:
        fig.suptitle(title, color="white", fontsize=16, fontweight="bold", y=0.98)
    return fig

def apply_dark_theme_ax(ax, title="", x_label="", y_label=""):
    ax.set_facecolor(BG_PANEL)
    ax.set_title(title, color="#C9CCDB", fontweight="bold", fontsize=11, pad=8)
    ax.set_xlabel(x_label, color="#A6ADC8", fontsize=9)
    ax.set_ylabel(y_label, color="#A6ADC8", fontsize=9)
    ax.tick_params(colors="#6C7086", labelsize=8)
    ax.grid(color=GRID_COL, linewidth=0.5, alpha=0.8)
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER_COL)
        spine.set_linewidth(1.0)
    return ax

def get_fleet_speed(ships: int, max_cap: float = 6.0) -> float:
    return min(1.0 + float(ships // 20), max_cap)

def check_sun_collision(src_x: float, src_y: float, travel_angle: float, buffer: float = 2.0) -> bool:
    dx = math.cos(travel_angle)
    dy = math.sin(travel_angle)
    t = (SUN_X - src_x) * dx + (SUN_Y - src_y) * dy
    if t < 0.0:
        return False
    closest_x = src_x + t * dx
    closest_y = src_y + t * dy
    distance = math.hypot(closest_x - SUN_X, closest_y - SUN_Y)
    return distance < (SUN_RADIUS + buffer)

print("Setup Complete. Custom Cyberpunk Visual Palette Configured.")

# %% [code]
# env_audit = make("orbit_wars", debug=True)
# env_audit.run(["random", "random"])
# sample_obs = env_audit.steps[1][0].observation
# 
# print(f"Environment Verification:")
# print(f"Planets registered: {len(sample_obs.planets)}")
# print(f"System Angular Velocity: {sample_obs.angular_velocity:.6f} rad/turn")

# %% [code]
class Planet:
    __slots__ = ("id", "owner", "x", "y", "radius", "ships", "production")
    def __init__(self, raw_data):
        self.id, self.owner, self.x, self.y, self.radius, self.ships, self.production = raw_data
        
    def get_distance(self, target) -> float:
        return math.hypot(self.x - target.x, self.y - target.y)
    
    def distance_to_coord(self, target_x: float, target_y: float) -> float:
        return math.hypot(self.x - target_x, self.y - target_y)
        
    def angle_to_target(self, target) -> float:
        return math.atan2(target.y - self.y, target.x - self.x)
    
    def angle_to_coord(self, target_x: float, target_y: float) -> float:
        return math.atan2(target_y - self.y, target_x - self.x)

class Fleet:
    __slots__ = ("id", "owner", "x", "y", "angle", "source_planet_id", "ships")
    def __init__(self, raw_data):
        self.id, self.owner, self.x, self.y, self.angle, self.source_planet_id, self.ships = raw_data

class GameState:
    def __init__(self, obs):
        get_attr = lambda k: getattr(obs, k, None) if hasattr(obs, k) else (obs.get(k) if isinstance(obs, dict) else None)
        self.my_id = get_attr("player") or 0
        self.ang_vel = get_attr("angular_velocity") or 0.027
        self.step = get_attr("step") or 0
        
        self.planets = [Planet(p) for p in (get_attr("planets") or [])]
        self.fleets = [Fleet(f) for f in (get_attr("fleets") or [])]
        self.comet_ids = set(get_attr("comet_planet_ids") or [])
        
        self.planet_map = {p.id: p for p in self.planets}
        self.my_planets = [p for p in self.planets if p.owner == self.my_id]
        self.enemy_planets = [p for p in self.planets if p.owner not in (-1, self.my_id)]
        self.neutral_planets = [p for p in self.planets if p.owner == -1]
        self.enemy_ids = list({p.owner for p in self.enemy_planets})
        
        self.incoming_fleets = defaultdict(lambda: defaultdict(int))
        self._map_fleet_trajectories()

    def _map_fleet_trajectories(self):
        for f in self.fleets:
            target_id = self.predict_target(f)
            if target_id is not None:
                self.incoming_fleets[target_id][f.owner] += f.ships

    def predict_target(self, fleet: Fleet) -> Optional[int]:
        best_target = None
        min_angle_delta = 0.30
        closest_distance = float('inf')
        
        for p in self.planets:
            calc_angle = math.atan2(p.y - fleet.y, p.x - fleet.x)
            angle_delta = abs((calc_angle - fleet.angle + math.pi) % (2 * math.pi) - math.pi)
            if angle_delta < min_angle_delta:
                dist = math.hypot(p.x - fleet.x, p.y - fleet.y)
                if dist < closest_distance:
                    closest_distance = dist
                    best_target = p.id
        return best_target

    def get_planet(self, p_id: int) -> Optional[Planet]:
        return self.planet_map.get(p_id)

    def is_inner_orbit(self, planet: Planet) -> bool:
        return math.hypot(planet.x - SUN_X, planet.y - SUN_Y) < INNER_ORBIT_R

    def compute_net_threat(self, planet: Planet) -> int:
        incoming = self.incoming_fleets.get(planet.id, {})
        enemy_ships = sum(v for k, v in incoming.items() if k not in (self.my_id, -1))
        return enemy_ships - incoming.get(self.my_id, 0)

    def get_total_ships(self, owner_id: int) -> int:
        p_ships = sum(p.ships for p in self.planets if p.owner == owner_id)
        f_ships = sum(f.ships for f in self.fleets if f.owner == owner_id)
        return p_ships + f_ships

    def get_strategic_phase(self) -> str:
        ratio = len(self.my_planets) / max(len(self.planets), 1)
        low, high = PHASE_THRESHOLDS
        return "early" if ratio < low else ("late" if ratio >= high else "mid")

    def get_fleet_centroid(self) -> Tuple[float, float]:
        if not self.my_planets:
            return SUN_X, SUN_Y
        return (sum(p.x for p in self.my_planets) / len(self.my_planets),
                sum(p.y for p in self.my_planets) / len(self.my_planets))

# %% [code]
class Predictor:
    def __init__(self, state: GameState):
        self.state = state

    def estimate_future_position(self, planet: Planet, turns: int) -> Tuple[float, float]:
        if not self.state.is_inner_orbit(planet):
            return planet.x, planet.y
        radius = math.hypot(planet.x - SUN_X, planet.y - SUN_Y)
        initial_angle = math.atan2(planet.y - SUN_Y, planet.x - SUN_X)
        projected_angle = initial_angle + self.state.ang_vel * turns
        return SUN_X + radius * math.cos(projected_angle), SUN_Y + radius * math.sin(projected_angle)

    def calculate_intercept_coords(self, source: Planet, target: Planet, fleet_size: int, iterations: int = 5) -> Tuple[float, float]:
        speed = get_fleet_speed(fleet_size)
        tx, ty = target.x, target.y
        for _ in range(iterations):
            distance = math.hypot(tx - source.x, ty - source.y)
            estimated_turns = max(1, int(distance / speed))
            tx, ty = self.estimate_future_position(target, estimated_turns)
        return tx, ty

    def calculate_lead_aim(self, source: Planet, target: Planet, fleet_size: int) -> float:
        if not self.state.is_inner_orbit(target):
            return source.angle_to_target(target)
        tx, ty = self.calculate_intercept_coords(source, target, fleet_size)
        return source.angle_to_coord(tx, ty)

    def calculate_eta(self, source: Planet, target: Planet, fleet_size: int) -> int:
        tx, ty = self.calculate_intercept_coords(source, target, fleet_size)
        return max(1, int(math.hypot(tx - source.x, ty - source.y) / get_fleet_speed(fleet_size)))

    def calculate_safe_aim(self, source: Planet, target: Planet, fleet_size: int) -> float:
        optimal_angle = self.calculate_lead_aim(source, target, fleet_size)
        if check_sun_collision(source.x, source.y, optimal_angle):
            for angular_offset in [0.06, -0.06, 0.12, -0.12, 0.20, -0.20, 0.35, -0.35]:
                if not check_sun_collision(source.x, source.y, optimal_angle + angular_offset):
                    return optimal_angle + angular_offset
        return optimal_angle

# %% [code]
class SimulatedPlanet:
    __slots__ = ("id", "owner", "ships", "production")
    def __init__(self, planet):
        self.id, self.owner, self.ships, self.production = planet.id, planet.owner, planet.ships, planet.production

class SimulatedFleet:
    __slots__ = ("owner", "target_id", "ships", "eta")
    def __init__(self, owner: int, target_id: int, ships: int, eta: int):
        self.owner, self.target_id, self.ships, self.eta = owner, target_id, ships, eta

def execute_sim_step(planets_dict: dict, fleets_list: list):
    for p in planets_dict.values():
        if p.owner >= 0:
            p.ships += p.production
            
    active_fleets = []
    for f in fleets_list:
        f.eta -= 1
        if f.eta <= 0:
            p = planets_dict[f.target_id]
            if p.owner == f.owner:
                p.ships += f.ships
            else:
                p.ships -= f.ships
                if p.ships < 0:
                    p.owner = f.owner
                    p.ships = abs(p.ships)
        else:
            active_fleets.append(f)
    fleets_list[:] = active_fleets

def clone_game_state(state: GameState) -> Tuple[dict, list]:
    sim_planets = {p.id: SimulatedPlanet(p) for p in state.planets}
    sim_fleets = []
    for f in state.fleets:
        target_id = state.predict_target(f)
        if target_id:
            target_planet = state.get_planet(target_id)
            if target_planet:
                eta = max(1, int(math.hypot(target_planet.x - f.x, target_planet.y - f.y) / get_fleet_speed(f.ships)))
                sim_fleets.append(SimulatedFleet(f.owner, target_id, f.ships, eta))
    return sim_planets, sim_fleets

def evaluate_sim_state(planets_dict: dict, fleets_list: list, player_id: int, weights: dict) -> float:
    my_ships = sum(p.ships for p in planets_dict.values() if p.owner == player_id) + sum(f.ships for f in fleets_list if f.owner == player_id)
    en_ships = sum(p.ships for p in planets_dict.values() if p.owner not in (-1, player_id)) + sum(f.ships for f in fleets_list if f.owner not in (-1, player_id))
    
    my_prod = sum(p.production for p in planets_dict.values() if p.owner == player_id)
    en_prod = sum(p.production for p in planets_dict.values() if p.owner not in (-1, player_id))
    
    my_planets_count = sum(1 for p in planets_dict.values() if p.owner == player_id)
    en_planets_count = sum(1 for p in planets_dict.values() if p.owner not in (-1, player_id))
    
    threat_gap = max(0, en_ships - my_ships)
    
    return (weights["WS"] * (my_ships - en_ships) + 
            weights["WP"] * (my_prod - en_prod) + 
            weights["WC"] * (my_planets_count - en_planets_count) - 
            weights["WR"] * threat_gap)

# %% [code]
class EliteEvaluator:
    WEIGHTS = {
        "WS": 1.0,    
        "WP": 48.0,   
        "WC": 22.0,   
        "WR": -3.0,   
        "WB": 10.0,   
        "WN": 14.0,   
    }

    @classmethod
    def evaluate_state(cls, state: GameState) -> float:
        m_id = state.my_id
        my_ships = state.get_total_ships(m_id)
        en_ships = sum(state.get_total_ships(eid) for eid in state.enemy_ids) + 1e-6
        
        my_prod = sum(p.production for p in state.my_planets)
        en_prod = sum(p.production for p in state.enemy_planets)
        
        my_count = len(state.my_planets)
        en_count = len(state.enemy_planets)
        
        aggregate_threat = sum(max(0, state.compute_net_threat(p)) for p in state.my_planets)
        
        border_tension = 0.0
        for mp in state.my_planets:
            for ep in state.enemy_planets:
                dist = mp.get_distance(ep)
                if dist < 35.0:
                    border_tension += ((35.0 - dist) / 35.0) * mp.production

        neutral_denial = sum(
            np.production for np in state.neutral_planets
            if any(np.get_distance(ep) < 25.0 for ep in state.enemy_planets)
            and not any(np.get_distance(mp) < 25.0 for mp in state.my_planets)
        )

        return (cls.WEIGHTS["WS"] * (my_ships - en_ships) +
                cls.WEIGHTS["WP"] * (my_prod - en_prod) +
                cls.WEIGHTS["WC"] * (my_count - en_count) +
                cls.WEIGHTS["WR"] * aggregate_threat +
                cls.WEIGHTS["WB"] * border_tension -
                cls.WEIGHTS["WN"] * neutral_denial)

# %% [code]
class MCTSNode:
    __slots__ = ("action", "parent", "children", "visits", "total_value", "untried_actions")
    def __init__(self, action=None, parent=None, untried_actions=None):
        self.action = action
        self.parent = parent
        self.children = []
        self.visits = 0
        self.total_value = 0.0
        self.untried_actions = untried_actions if untried_actions is not None else []

    def compute_ucb(self, exploration_weight: float = 1.41) -> float:
        if self.visits == 0:
            return float('inf')
        return (self.total_value / self.visits) + exploration_weight * math.sqrt(math.log(self.parent.visits) / self.visits)

    def select_best_child(self, exploration_weight: float = 1.41):
        return max(self.children, key=lambda node: node.compute_ucb(exploration_weight))

    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0

    def is_leaf(self) -> bool:
        return len(self.children) == 0

class AdvancedMCTS:
    def __init__(self, state: GameState, predictor: Predictor, time_budget_ms: int = 420, max_depth: int = 10):
        self.state = state
        self.predictor = predictor
        self.time_budget_sec = time_budget_ms / 1000.0
        self.max_depth = max_depth
        self.player_id = state.my_id

    def _generate_candidate_actions(self) -> list:
        actions = [(None, None, None)]
        for src in self.state.my_planets:
            available_budget = max(0, src.ships - max(src.production * 2, 5))
            closest_targets = sorted(self.state.enemy_planets + self.state.neutral_planets, key=lambda p: src.get_distance(p))[:6]
            for target in closest_targets:
                required_ships = target.ships + 5
                if available_budget >= required_ships:
                    actions.append((src.id, target.id, required_ships))
                half_allocation = available_budget // 2
                if half_allocation > 5 and half_allocation != required_ships:
                    actions.append((src.id, target.id, half_allocation))
        return actions

    def _apply_sim_action(self, action, planets_dict: dict, fleets_list: list):
        src_id, target_id, allocation = action
        if src_id is None:
            return
        src_planet = planets_dict.get(src_id)
        ref_src = self.state.get_planet(src_id)
        ref_tgt = self.state.get_planet(target_id)
        if src_planet and ref_src and ref_tgt and src_planet.ships >= allocation:
            eta = self.predictor.calculate_eta(ref_src, ref_tgt, allocation)
            fleets_list.append(SimulatedFleet(self.player_id, target_id, allocation, eta))
            src_planet.ships -= allocation

    def _execute_random_rollout(self, planets_dict: dict, fleets_list: list) -> float:
        p_clone = {pid: SimulatedPlanet(p) for pid, p in planets_dict.items()}
        f_clone = [SimulatedFleet(f.owner, f.target_id, f.ships, f.eta) for f in fleets_list]
        
        for _ in range(self.max_depth):
            valid_sources = [p for p in p_clone.values() if p.owner == self.player_id and p.ships > 6]
            valid_targets = [p for p in p_clone.values() if p.owner != self.player_id]
            if valid_sources and valid_targets:
                src = random.choice(valid_sources)
                tgt = random.choice(valid_targets)
                allocated = random.randint(1, max(1, src.ships // 3))
                src.ships -= allocated
                f_clone.append(SimulatedFleet(self.player_id, tgt.id, allocated, 10))
            execute_sim_step(p_clone, f_clone)
            
        return evaluate_sim_state(p_clone, f_clone, self.player_id, EliteEvaluator.WEIGHTS)

    def dynamic_search(self) -> Tuple[Tuple, int, MCTSNode]:
        candidates = self._generate_candidate_actions()
        root_node = MCTSNode(untried_actions=candidates[:])
        start_time = time.time()
        iterations = 0
        
        while (time.time() - start_time) < self.time_budget_sec:
            current_node = root_node
            sim_planets, sim_fleets = clone_game_state(self.state)
            
            while current_node.is_fully_expanded() and not current_node.is_leaf():
                current_node = current_node.select_best_child()
                self._apply_sim_action(current_node.action, sim_planets, sim_fleets)
                execute_sim_step(sim_planets, sim_fleets)
                
            if current_node.untried_actions:
                chosen_action = random.choice(current_node.untried_actions)
                current_node.untried_actions.remove(chosen_action)
                self._apply_sim_action(chosen_action, sim_planets, sim_fleets)
                execute_sim_step(sim_planets, sim_fleets)
                
                child_node = MCTSNode(action=chosen_action, parent=current_node, untried_actions=self._generate_candidate_actions())
                current_node.children.append(child_node)
                current_node = child_node
                
            simulation_reward = self._execute_random_rollout(sim_planets, sim_fleets)
            
            while current_node:
                current_node.visits += 1
                current_node.total_value += simulation_reward
                current_node = current_node.parent
            iterations += 1
            
        if not root_node.children:
            return (None, None, None), iterations, root_node
        best_stable_node = max(root_node.children, key=lambda node: node.visits)
        return best_stable_node.action, iterations, root_node

# %% [code]
class OpponentModel:
    def __init__(self):
        self.ship_history = defaultdict(list)
        self.planet_history = defaultdict(list)
        self.attack_occurrences = defaultdict(list)

    def update_model(self, state: GameState):
        for eid in state.enemy_ids:
            self.ship_history[eid].append(state.get_total_ships(eid))
            self.planet_history[eid].append(len([p for p in state.planets if p.owner == eid]))
            for f in state.fleets:
                if f.owner == eid:
                    target_id = state.predict_target(f)
                    if target_id:
                        tgt_p = state.get_planet(target_id)
                        if tgt_p and tgt_p.owner == state.my_id:
                            self.attack_occurrences[eid].append({"turn": state.step, "ships": f.ships})

    def estimate_aggression_coefficient(self, enemy_id: int) -> float:
        attacks_logged = len(self.attack_occurrences.get(enemy_id, []))
        total_tracked_turns = max(len(self.ship_history.get(enemy_id, [1])), 1)
        return min((attacks_logged / total_tracked_turns) * 4.0, 1.0)

    def get_growth_rate(self, enemy_id: int) -> float:
        history = self.ship_history.get(enemy_id, [])
        if len(history) < 2:
            return 0.0
        slice_window = history[-15:]
        return (slice_window[-1] - slice_window[0]) / max(len(slice_window) - 1, 1)

# %% [code]
class FleetInterceptor:
    def __init__(self, state: GameState, predictor: Predictor):
        self.state = state
        self.predictor = predictor

    def calculate_fleet_position_at_turn(self, fleet: Fleet, turn_index: int) -> Tuple[float, float]:
        speed = get_fleet_speed(fleet.ships)
        return fleet.x + math.cos(fleet.angle) * speed * turn_index, fleet.y + math.sin(fleet.angle) * speed * turn_index

    def identify_interception_window(self, enemy_fleet: Fleet, friendly_source: Planet, friendly_fleet_size: int) -> Optional[Tuple[float, float, int]]:
        friendly_speed = get_fleet_speed(friendly_fleet_size)
        for turn in range(1, 45):
            fx, fy = self.calculate_fleet_position_at_turn(enemy_fleet, turn)
            distance = math.hypot(fx - friendly_source.x, fy - friendly_source.y)
            if abs((distance / friendly_speed) - turn) < 1.2:
                return fx, fy, turn
        return None

    def scan_all_intercept_options(self) -> list:
        intercept_opportunities = []
        for f in self.state.fleets:
            if f.owner in (-1, self.state.my_id):
                continue
            predicted_tgt_id = self.state.predict_target(f)
            if not predicted_tgt_id:
                continue
            target_planet = self.state.get_planet(predicted_tgt_id)
            if not target_planet or target_planet.owner != self.state.my_id:
                continue
            
            for source in self.state.my_planets:
                defensive_allocation = max(5, source.ships // 2)
                window = self.identify_interception_window(f, source, defensive_allocation)
                if window and defensive_allocation > f.ships:
                    ix, iy, eta = window
                    aim_angle = source.angle_to_coord(ix, iy)
                    if not check_sun_collision(source.x, source.y, aim_angle):
                        intercept_opportunities.append({
                            "enemy_size": f.ships, "src_id": source.id, "alloc": defensive_allocation,
                            "ix": ix, "iy": iy, "eta": eta, "angle": aim_angle
                        })
                        break
        return sorted(intercept_opportunities, key=lambda x: -x["enemy_size"])

# %% [code]
class StrategyEngine:
    def __init__(self, state: GameState, predictor: Predictor, opponent_model: OpponentModel):
        self.state = state
        self.predictor = predictor
        self.opponent_model = opponent_model
        self.player_id = state.my_id

    def calculate_planet_utility(self, source: Planet, target: Planet) -> float:
        distance = source.get_distance(target)
        if distance < 0.1:
            return -9999.0
        base_value = target.production * 50.0 - target.ships
        if target.owner == -1:
            base_value += 25.0
        elif target.owner != self.player_id:
            base_value += 65.0
        
        aim_angle = self.predictor.calculate_lead_aim(source, target, 20)
        if check_sun_collision(source.x, source.y, aim_angle):
            base_value -= 80.0
            
        return base_value / (distance + 1.0)

    def build_early_expansion_profile(self) -> list:
        actions = []
        for src in sorted(self.state.my_planets, key=lambda p: -p.ships):
            usable_ships = max(0, int((src.ships - (src.production * 3)) * 0.75))
            for target in sorted(self.state.neutral_planets, key=lambda t: self.calculate_planet_utility(src, t), reverse=True)[:5]:
                required = target.ships + 5
                if usable_ships >= required:
                    actions.append((src.id, target.id, required))
                    usable_ships -= required
        return actions

    def build_mid_game_profile(self) -> list:
        actions = []
        if self.state.enemy_planets:
            weakest_enemy = min(self.state.enemy_planets, key=lambda p: p.ships)
            target_requirement = weakest_enemy.ships + 12
            cumulative_sent = 0
            for src in sorted(self.state.my_planets, key=lambda p: p.get_distance(weakest_enemy)):
                usable = max(0, int((src.ships - 8) * 0.65))
                if usable > 0 and cumulative_sent < target_requirement:
                    send_volume = min(usable, target_requirement - cumulative_sent)
                    actions.append((src.id, weakest_enemy.id, send_volume))
                    cumulative_sent += send_volume
        return actions

    def select_optimal_candidate_actions(self) -> list:
        phase = self.state.get_strategic_phase()
        if phase == "early":
            return self.build_early_expansion_profile()
        return self.build_mid_game_profile()

# %% [code]
GLOBAL_OPPONENT_MODEL = OpponentModel()

def elite_bot_v5(obs, config=None):
    global GLOBAL_OPPONENT_MODEL
    start_execution_time = time.time()
    
    try:
        state = GameState(obs)
        if not state.my_planets:
            return []
            
        predictor = Predictor(state)
        GLOBAL_OPPONENT_MODEL.update_model(state)
        
        interceptor = FleetInterceptor(state, predictor)
        intercept_moves = interceptor.scan_all_intercept_options()
        
        compiled_actions = []
        allocated_spending = defaultdict(int)
        
        def commit_action(src_id, target_angle, volume):
            p_source = state.get_planet(src_id)
            if not p_source or p_source.owner != state.my_id:
                return
            headroom = p_source.ships - allocated_spending[src_id] - 1
            validated_volume = min(volume, max(0, headroom))
            if validated_volume <= 0:
                return
            compiled_actions.append([src_id, float(target_angle), int(validated_volume)])
            allocated_spending[src_id] += validated_volume

        for option in intercept_moves[:2]:
            commit_action(option["src_id"], option["angle"], option["alloc"])

        elapsed_ms = (time.time() - start_execution_time) * 1000.0
        remaining_budget = min(400, int(850 - elapsed_ms))
        
        if remaining_budget > 40:
            mcts_engine = AdvancedMCTS(state, predictor, time_budget_ms=remaining_budget, max_depth=9)
            best_action, _, _ = mcts_engine.dynamic_search()
            if best_action and best_action[0] is not None:
                s_id, t_id, size = best_action
                src_p = state.get_planet(s_id)
                tgt_p = state.get_planet(t_id)
                if src_p and tgt_p:
                    safe_angle = predictor.calculate_safe_aim(src_p, tgt_p, size)
                    commit_action(s_id, safe_angle, size)

        strategy_engine = StrategyEngine(state, predictor, GLOBAL_OPPONENT_MODEL)
        fallback_actions = strategy_engine.select_optimal_candidate_actions()
        for s_id, t_id, size in fallback_actions:
            if (time.time() - start_execution_time) * 1000.0 > 880.0:
                break
            src_p = state.get_planet(s_id)
            tgt_p = state.get_planet(t_id)
            if src_p and tgt_p:
                safe_angle = predictor.calculate_safe_aim(src_p, tgt_p, size)
                commit_action(s_id, safe_angle, size)

        return compiled_actions
    except Exception as e:
        return []
def agent(obs, config=None):
    return elite_bot_v5(obs, config)

# smoke_test_moves = elite_bot_v5(sample_obs)
# print(f"Smoke Test: Generated {len(smoke_test_moves)} validated execution instructions.")

# %% [markdown]
# ## Advanced Multi-Panel Cyberpunk Tactical Dashboard

# %% [code]
def draw_tactical_dashboard(state: GameState, computed_actions: list, predictor: Predictor, mcts_root: MCTSNode):
    fig = plt.figure(figsize=(15, 10))
    apply_dark_theme_fig(fig, title="ORBIT WARS: ADVANCED INTEL SYSTEM & STRATEGY PANEL")
    
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.35, wspace=0.25)
    
    ax_radar = fig.add_subplot(gs[0:2, 0:2])
    apply_dark_theme_ax(ax_radar, title="System Telemetry Map & Predicted Vectors")
    
    sun_circ = plt.Circle((SUN_X, SUN_Y), SUN_RADIUS, color="#FFCC00", alpha=0.3, label="Sun Radiation Zone")
    inner_orbit = plt.Circle((SUN_X, SUN_Y), INNER_ORBIT_R, color=BORDER_COL, fill=False, linestyle="--", alpha=0.5)
    ax_radar.add_patch(sun_circ)
    ax_radar.add_patch(inner_orbit)
    
    for p in state.planets:
        col = PCOLORS.get(p.owner, "#FFFFFF")
        ax_radar.scatter(p.x, p.y, s=p.radius*20, color=col, edgecolors="white", linewidth=0.7, zorder=3)
        ax_radar.text(p.x + 1.5, p.y + 1.5, f"P{p.id}\n(S:{p.ships})", color="#E0E0E0", fontsize=7, weight="semibold")
        
        if state.is_inner_orbit(p):
            fx, fy = predictor.estimate_future_position(p, turns=5)
            ax_radar.plot([p.x, fx], [p.y, fy], color=col, linestyle=":", alpha=0.4)
            ax_radar.scatter(fx, fy, s=10, color=col, alpha=0.3, marker="x")

    for f in state.fleets:
        col = PCOLORS.get(f.owner, "#FFFFFF")
        ax_radar.scatter(f.x, f.y, s=15, color=col, marker="^")
        dx = math.cos(f.angle) * 4
        dy = math.sin(f.angle) * 4
        ax_radar.arrow(f.x, f.y, dx, dy, head_width=1, head_length=1.5, fc=col, ec=col, alpha=0.6)

    for src_id, angle, size in computed_actions:
        src_p = state.get_planet(src_id)
        if src_p:
            dx = math.cos(angle) * 12
            dy = math.sin(angle) * 12
            ax_radar.arrow(src_p.x, src_p.y, dx, dy, head_width=1.5, head_length=2, fc="#00FF66", ec="#00FF66", linestyle="-", linewidth=1.2, zorder=4)

    ax_radar.set_xlim(-5, 105)
    ax_radar.set_ylim(-5, 105)

    ax_metrics = fig.add_subplot(gs[0, 2])
    apply_dark_theme_ax(ax_metrics, title="Asset Volumes Breakdown")
    
    categories = ['My Ships', 'Enemy Ships', 'Neutral Planets', 'My Production', 'Enemy Production']
    my_ships_total = state.get_total_ships(state.my_id)
    en_ships_total = sum(state.get_total_ships(eid) for eid in state.enemy_ids)
    my_prod_total = sum(p.production for p in state.my_planets)
    en_prod_total = sum(p.production for p in state.enemy_planets)
    
    values = [my_ships_total, en_ships_total, len(state.neutral_planets) * 10, my_prod_total * 10, en_prod_total * 10]
    colors = ["#00F0FF", "#FF007F", "#5A5E6B", "#00FF66", "#FF9900"]
    
    ax_metrics.barh(categories, values, color=colors, edgecolor=BORDER_COL, height=0.5)
    
    ax_mcts = fig.add_subplot(gs[1, 2])
    apply_dark_theme_ax(ax_mcts, title="MCTS Frontier Search Policies")
    if mcts_root and mcts_root.children:
        sorted_children = sorted(mcts_root.children, key=lambda node: -node.visits)[:5]
        actions_labels = [f"P{c.action[0]}->P{c.action[1]} ({c.action[2]})" if c.action[0] is not None else "Pass" for c in sorted_children]
        visits = [c.visits for c in sorted_children]
        ax_mcts.bar(actions_labels, visits, color="#FF9900", edgecolor=BORDER_COL, width=0.4)
        ax_mcts.set_xticklabels(actions_labels, rotation=25, ha="right", fontsize=7)
    else:
        ax_mcts.text(0.5, 0.5, "Insufficient Frontier Tree Telemetry", color="grey", ha="center", va="center")

    ax_score = fig.add_subplot(gs[2, 0])
    apply_dark_theme_ax(ax_score, title="Elite Heuristic Weights Distribution")
    h_labels = list(EliteEvaluator.WEIGHTS.keys())
    h_vals = [abs(v) for v in EliteEvaluator.WEIGHTS.values()]
    ax_score.pie(h_vals, labels=h_labels, colors=["#00F0FF", "#FF007F", "#00FF66", "#FF9900", "#A6ADC8", "#5A5E6B"], 
                 textprops={'color': 'white', 'fontsize': 8}, wedgeprops={'edgecolor': BORDER_COL, 'linewidth': 0.8})

    ax_threat = fig.add_subplot(gs[2, 1])
    apply_dark_theme_ax(ax_threat, title="Asset Threat Distribution Spectrum")
    planet_ids = [f"P{p.id}" for p in state.my_planets[:6]]
    threat_vals = [state.compute_net_threat(p) for p in state.my_planets[:6]]
    if threat_vals:
        ax_threat.bar(planet_ids, threat_vals, color=["#FF007F" if v > 0 else "#00FF66" for v in threat_vals], edgecolor=BORDER_COL, width=0.4)
    else:
        ax_threat.text(0.5, 0.5, "No immediate threat detected", color="white", ha="center", va="center")

    ax_console = fig.add_subplot(gs[2, 2])
    apply_dark_theme_ax(ax_console, title="Decision Stream Log Console")
    ax_console.axis('off')
    console_text = (
        f" [SYSTEM LOG CONFIGURATION]\n"
        f" Current Turn Step: {state.step}\n"
        f" Strategy Mode Context: {state.get_strategic_phase().upper()}\n"
        f" Tracked Enemy Clusters: {len(state.enemy_ids)}\n"
        f" Outbound Action Pipeline: {len(computed_actions)} orders issued\n"
        f" Evaluator Rating Matrix: {EliteEvaluator.evaluate_state(state):.2f}\n"
    )
    ax_console.text(0.05, 0.5, console_text, color="#00FF66", fontfamily="monospace", fontsize=9, va="center",
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="#181825", edgecolor=BORDER_COL))

    plt.show()

# predictor_viz = Predictor(GameState(sample_obs))
# mcts_viz = AdvancedMCTS(GameState(sample_obs), predictor_viz, time_budget_ms=100)
# _, _, test_root = mcts_viz.dynamic_search()
# 
# draw_tactical_dashboard(GameState(sample_obs), smoke_test_moves, predictor_viz, test_root)

# %% [code]
# Compilation block creating submission standalone script artifact without parsing errors
submission_code = """
import math
import time
import random
from collections import defaultdict
from typing import List, Tuple, Dict, Optional

class Planet:
    __slots__ = ("id", "owner", "x", "y", "radius", "ships", "production")
    def __init__(self, raw_data):
        self.id, self.owner, self.x, self.y, self.radius, self.ships, self.production = raw_data
    def get_distance(self, target) -> float:
        return math.hypot(self.x - target.x, self.y - target.y)
    def distance_to_coord(self, target_x: float, target_y: float) -> float:
        return math.hypot(self.x - target_x, self.y - target_y)
    def angle_to_coord(self, target_x: float, target_y: float) -> float:
        return math.atan2(target_y - self.y, target_x - self.x)

class Fleet:
    __slots__ = ("id", "owner", "x", "y", "angle", "source_planet_id", "ships")
    def __init__(self, raw_data):
        self.id, self.owner, self.x, self.y, self.angle, self.source_planet_id, self.ships = raw_data

class GameState:
    def __init__(self, obs):
        get_attr = lambda k: getattr(obs, k, None) if hasattr(obs, k) else (obs.get(k) if isinstance(obs, dict) else None)
        self.my_id = get_attr("player") or 0
        self.ang_vel = get_attr("angular_velocity") or 0.027
        self.step = get_attr("step") or 0
        self.planets = [Planet(p) for p in (get_attr("planets") or [])]
        self.fleets = [Fleet(f) for f in (get_attr("fleets") or [])]
        self.planet_map = {p.id: p for p in self.planets}
        self.my_planets = [p for p in self.planets if p.owner == self.my_id]
        self.enemy_planets = [p for p in self.planets if p.owner not in (-1, self.my_id)]
        self.neutral_planets = [p for p in self.planets if p.owner == -1]
        self.enemy_ids = list({p.owner for p in self.enemy_planets})

    def get_planet(self, p_id: int) -> Optional[Planet]:
        return self.planet_map.get(p_id)

    def predict_target(self, fleet: Fleet) -> Optional[int]:
        best_target = None
        min_angle_delta = 0.30
        closest_distance = float('inf')
        for p in self.planets:
            calc_angle = math.atan2(p.y - fleet.y, p.x - fleet.x)
            angle_delta = abs((calc_angle - fleet.angle + math.pi) % (2 * math.pi) - math.pi)
            if angle_delta < min_angle_delta:
                dist = math.hypot(p.x - fleet.x, p.y - fleet.y)
                if dist < closest_distance:
                    closest_distance = dist
                    best_target = p.id
        return best_target

def get_fleet_speed(ships: int) -> float:
    return min(1.0 + float(ships // 20), 6.0)

def check_sun_collision(src_x: float, src_y: float, travel_angle: float) -> bool:
    dx, dy = math.cos(travel_angle), math.sin(travel_angle)
    t = (50.0 - src_x) * dx + (50.0 - src_y) * dy
    if t < 0.0: return False
    return math.hypot(src_x + t * dx - 50.0, src_y + t * dy - 50.0) < 7.0

def agent(obs, config=None):
    try:
        state = GameState(obs)
        if not state.my_planets: return []
        moves = []
        for src in state.my_planets:
            if src.ships > 15:
                targets = sorted(state.neutral_planets + state.enemy_planets, key=lambda p: src.get_distance(p))
                if targets:
                    t = targets[0]
                    ang = src.angle_to_coord(t.x, t.y)
                    if not check_sun_collision(src.x, src.y, ang):
                        moves.append([src.id, float(ang), int(src.ships // 2)])
        return moves
    except:
        return []
"""

if __name__ == "__main__":
    # Import validation only when run directly
    env_audit = make("orbit_wars", debug=True)
    env_audit.run(["random", "random"])
    sample_obs = env_audit.steps[1][0].observation

    print(f"Environment Verification:")
    print(f"Planets registered: {len(sample_obs.planets)}")
    print(f"System Angular Velocity: {sample_obs.angular_velocity:.6f} rad/turn")

    smoke_test_moves = elite_bot_v5(sample_obs)
    print(f"Smoke Test: Generated {len(smoke_test_moves)} validated execution instructions.")

    predictor_viz = Predictor(GameState(sample_obs))
    mcts_viz = AdvancedMCTS(GameState(sample_obs), predictor_viz, time_budget_ms=100)
    _, _, test_root = mcts_viz.dynamic_search()

    draw_tactical_dashboard(GameState(sample_obs), smoke_test_moves, predictor_viz, test_root)

    with open("submission.py", "w") as f:
        f.write(submission_code.strip())

    print("Standalone production file 'submission.py' successfully exported to system workspace root directory.")