"""
KINEMATICS CORE v1 — Pure Technical Agent
==========================================
Sıfırdan yazılıb. Yalnız texniki bacarıqları test edir:

KINEMATIKA:
  ✓ Statik planeti vurmaq
  ✓ Hansı planetlərin fırlandığını təyin etmək
  ✓ Fırlanan planeti vurmaq (iterativ interception)
  ✓ Kometi vurmaq (həm statik, həm fırlanan planetdən)
  ✓ Kometdən planeti vurmaq (həm fırlanan, həm statik)

DÖYÜŞ QİYMƏTLƏNDİRMƏSİ:
  ✓ Hədəf planetdəki garrison + production * travel_time
  ✓ Hədəfə doğru yol alan bütün fleetlərin ray-tracing ilə təxmini
  ✓ 4-nəfərlik oyunda düşmən fleetlərinin gücləndirici/zəifldici effekti
  ✓ İterativ həll: göndərilən gəmi sayı → sürət → vaxt → lazım olan gəmi

TEST REJİMİ:
  Hər planetdən hər hədəfə 1-5 gəmilik problar göndərir.
  Kometlər tutulduqda onlardan da planetlərə atəş açılır.
"""

import math
from collections import defaultdict, namedtuple

# =============================================================================
# 1. CONSTANTS
# =============================================================================
BOARD = 100.0
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
SUN_MARGIN = 1.5          # fleetlərin günəşə toxunmaması üçün əlavə
MAX_SPEED = 6.0
PROBE_SHIPS = 3           # test fleeti ölçüsü

Planet = namedtuple("Planet", "id owner x y radius ships production")
Fleet  = namedtuple("Fleet",  "id owner x y angle from_planet_id ships")


# =============================================================================
# 2. MATH PRIMITIVES
# =============================================================================
def dist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def fleet_speed(n):
    """Oyunun rəsmi sürət formulu: 1 gəmi=1/tur, 1000 gəmi=6/tur."""
    if n <= 1:
        return 1.0
    ratio = max(0.0, min(1.0, math.log(n) / math.log(1000)))
    return 1.0 + 5.0 * (ratio ** 1.5)

def seg_point_dist(px, py, ax, ay, bx, by):
    """Nöqtənin xətt seqmentinə ən yaxın məsafəsi."""
    dx, dy = bx - ax, by - ay
    L2 = dx*dx + dy*dy
    if L2 < 1e-12:
        return dist(px, py, ax, ay)
    t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / L2))
    return dist(px, py, ax + t*dx, ay + t*dy)

def sun_blocks(sx, sy, tx, ty):
    """Fleet yolu günəşdən keçirsə True."""
    return seg_point_dist(SUN_X, SUN_Y, sx, sy, tx, ty) < (SUN_R + SUN_MARGIN)


# =============================================================================
# 3. OBSERVATION PARSER
# =============================================================================
def _get(obs, key, default=None):
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)

class World:
    """Observation-dan bütün lazımi məlumatı çıxarır."""

    def __init__(self, obs):
        self.player    = _get(obs, "player", 0)
        self.step      = _get(obs, "step", 0)
        self.ang_vel   = _get(obs, "angular_velocity", 0.0)

        raw_p = _get(obs, "planets", [])
        raw_f = _get(obs, "fleets", [])
        raw_i = _get(obs, "initial_planets", [])
        raw_c = _get(obs, "comets", [])
        raw_cids = _get(obs, "comet_planet_ids", [])

        self.planets = {p[0]: Planet(*p) for p in raw_p}
        self.fleets  = [Fleet(*f) for f in raw_f]
        self.initial = {p[0]: Planet(*p) for p in raw_i}

        # Comet tracking
        self.comet_ids = set(int(x) for x in raw_cids)
        self.comets_raw = raw_c    # path data
        self.comet_paths = {}      # pid → (path_list, path_index)
        for group in raw_c:
            pids = _get(group, "planet_ids", [])
            paths = _get(group, "paths", [])
            pidx  = _get(group, "path_index", 0)
            for i, pid in enumerate(pids):
                if i < len(paths):
                    self.comet_paths[pid] = (paths[i], pidx)

        # Orbital classification: once per planet, based on initial position
        self.orbital = {}   # pid → bool
        for pid, init_p in self.initial.items():
            if pid in self.comet_ids:
                self.orbital[pid] = False
                continue
            r = dist(init_p.x, init_p.y, SUN_X, SUN_Y)
            # Oyunun qaydası: iç planetlər fırlanır. Sərhəd ≈ 45 (radius daxil)
            self.orbital[pid] = (r + init_p.radius < 45.0)


# =============================================================================
# 4. POSITION PREDICTION ENGINE
# =============================================================================
def predict_pos(w: World, pid, turns_ahead):
    """
    pid-in `turns_ahead` tur sonrakı (x,y) koordinatını qaytarır.
    Statik planet → cari yer.
    Orbital planet → init_phase + ang_vel * (step + turns_ahead).
    Comet → path array-dən lookup.
    """
    # --- Comet ---
    if pid in w.comet_paths:
        path, pidx = w.comet_paths[pid]
        future = int(pidx) + int(turns_ahead)
        if 0 <= future < len(path):
            return float(path[future][0]), float(path[future][1])
        return None   # komet xəritədən çıxıb

    p = w.planets.get(pid)
    if p is None:
        return None

    # --- Static ---
    if not w.orbital.get(pid, False):
        return p.x, p.y

    # --- Orbital ---
    init_p = w.initial.get(pid)
    if init_p is None:
        return p.x, p.y

    r = dist(init_p.x, init_p.y, SUN_X, SUN_Y)
    init_phase = math.atan2(init_p.y - SUN_Y, init_p.x - SUN_X)
    total_turns = w.step + turns_ahead
    new_phase = init_phase + w.ang_vel * total_turns
    return SUN_X + r * math.cos(new_phase), SUN_Y + r * math.sin(new_phase)


# =============================================================================
# 5. ITERATIVE INTERCEPTION SOLVER
# =============================================================================
def solve_intercept(w: World, src_pid, tgt_pid, num_ships, max_horizon=60):
    """
    Mənbə planetdən hədəfə num_ships gəmi ilə atəş bucağını və uçuş
    müddətini iterativ şəkildə tapır.

    src mövqeyi atəş anındakı real mövqedir (fırlanan ola bilər).
    tgt mövqeyi gələcəkdəki predicted mövqedir.

    Returns: (angle, flight_turns)  və ya  None
    """
    src = w.planets.get(src_pid)
    if src is None:
        return None

    speed = fleet_speed(num_ships)
    sx, sy = src.x, src.y

    # İlkin təxmini: cari hədəf mövqeyinə düz xətt
    tgt_now = predict_pos(w, tgt_pid, 0)
    if tgt_now is None:
        return None
    tx, ty = tgt_now
    est = max(1.0, dist(sx, sy, tx, ty) / speed)

    # Iterativ convergence: hədəfin gələcək mövqeyini hesabla, məsafəni yenilə
    for _ in range(10):
        future = predict_pos(w, tgt_pid, est)
        if future is None:
            return None
        fx, fy = future
        d = dist(sx, sy, fx, fy)
        new_est = max(1.0, d / speed)
        if abs(new_est - est) < 0.05:
            est = new_est
            break
        est = 0.6 * est + 0.4 * new_est    # damped update

    flight = int(math.ceil(est))
    if flight > max_horizon:
        return None

    # Final position at flight turn
    final = predict_pos(w, tgt_pid, flight)
    if final is None:
        return None
    fx, fy = final

    # Sun check
    if sun_blocks(sx, sy, fx, fy):
        return None

    angle = math.atan2(fy - sy, fx - sx)
    return angle, flight


# =============================================================================
# 6. RAY TRACING — Fleet Destination Prediction
# =============================================================================
def trace_fleet(w: World, f: Fleet, max_t=80):
    """
    Uçuşda olan bir fleetin hara enəcəyini və neçə turda çatacağını təxmin edir.
    Fleetin cari mövqeyindən düz xətt istiqamətlə hər tur addımlayır,
    hər turda bütün planetlərin (o cümlədən fırlananların/kometlərin)
    gələcək mövqeyi ilə toqquşma yoxlayır.

    Returns: (target_pid, eta)  və ya  (None, None)
    """
    speed = fleet_speed(f.ships)
    vx = speed * math.cos(f.angle)
    vy = speed * math.sin(f.angle)

    for t in range(1, max_t + 1):
        fx = f.x + vx * t
        fy = f.y + vy * t

        # Off-board check
        if fx < -5 or fx > 105 or fy < -5 or fy > 105:
            return None, None

        # Sun destruction
        if dist(fx, fy, SUN_X, SUN_Y) <= SUN_R:
            return None, None

        # Planet collision
        for pid, p in w.planets.items():
            pos = predict_pos(w, pid, t)
            if pos is None:
                continue
            px, py = pos
            if dist(fx, fy, px, py) <= p.radius:
                return pid, t

    return None, None


def trace_all_fleets(w: World):
    """
    Bütün fleetlərin hədəflərini ray-trace edir.
    Returns: dict  target_pid → list of (eta, owner, ships)
    """
    arrivals = defaultdict(list)
    for f in w.fleets:
        tgt, eta = trace_fleet(w, f)
        if tgt is not None:
            arrivals[tgt].append((eta, f.owner, f.ships))
    return arrivals


# =============================================================================
# 7. COMBAT ESTIMATOR — Planet Capture Cost
# =============================================================================
def estimate_capture_cost(w: World, tgt_pid, arrival_turn, player, arrivals_map):
    """
    Verilmiş turda hədəf planeti fəth etmək üçün nə qədər gəmi lazım
    olduğunu hesablayır.

    Nəzərə alınır:
    - Cari garrison
    - Production (əgər fəth olunubsa, yəni owner != -1)
    - Hədəfə doğru yol alan BÜTÜN fleetlər (öz və rəqib)
    - 4 oyunçulu oyunda: rəqib A-nın fleeti planeti gücləndirir,
      rəqib B-nin fleeti isə zəiflədir (bir-birlərini vurarlar)

    Returns: int — lazım olan minimum gəmi sayı (>0: lazımdır, 0: artıq bizimdir)
    """
    tgt = w.planets.get(tgt_pid)
    if tgt is None:
        return 9999

    owner = tgt.owner
    garrison = float(tgt.ships)
    prod = tgt.production if owner != -1 else 0

    # Forward simulate turn-by-turn
    for t in range(1, arrival_turn + 1):
        # Production
        if owner != -1:
            garrison += prod

        # Arriving fleets at this turn
        turn_arrivals = [a for a in arrivals_map.get(tgt_pid, []) if a[0] == t]
        if not turn_arrivals:
            continue

        # Group by owner
        forces = defaultdict(int)
        forces[owner] = int(garrison) if owner != -1 else 0
        if owner == -1:
            forces[-1] = int(garrison)

        for _, fl_owner, fl_ships in turn_arrivals:
            forces[fl_owner] += fl_ships

        # Resolve combat: strongest wins, difference remains
        sorted_f = sorted(forces.items(), key=lambda x: -x[1])
        if len(sorted_f) == 1:
            owner = sorted_f[0][0]
            garrison = sorted_f[0][1]
        else:
            w1_owner, w1_ships = sorted_f[0]
            w2_owner, w2_ships = sorted_f[1]
            if w1_ships == w2_ships:
                owner = -1
                garrison = 0
            else:
                owner = w1_owner
                garrison = w1_ships - w2_ships

    # Now: at arrival_turn, the planet has `garrison` ships owned by `owner`
    if owner == player:
        return 0   # artıq bizimdir
    return int(garrison) + 1


def iterative_ship_solver(w: World, src_pid, tgt_pid, player, arrivals_map,
                          max_iter=8, max_horizon=60):
    """
    Göndəriləcək gəmi sayı ↔ sürət ↔ uçuş müddəti ↔ lazım olan gəmi
    arasındakı dairəvi asılılığı iterativ həll edir.

    Problem:
      ships_needed = f(travel_time)    (garrison + prod*t + incoming fleets)
      travel_time  = g(ships_sent)     (fleet_speed formulu)
      ships_sent   ≥ ships_needed

    Həll: fixed-point iteration
      1. İlkin təxmin: 5 gəmi ilə uçuş müddətini hesabla
      2. Həmin turda capture cost-u tap
      3. Cost ilə yenidən uçuş müddətini hesabla
      4. Konvergens olana qədər təkrarla

    Returns: (angle, flight_turns, ships_needed) və ya None
    """
    src = w.planets.get(src_pid)
    if src is None:
        return None

    # Start with a small probe to get initial estimate
    ships_guess = 5
    for _ in range(max_iter):
        result = solve_intercept(w, src_pid, tgt_pid, ships_guess, max_horizon)
        if result is None:
            return None
        angle, flight = result

        cost = estimate_capture_cost(w, tgt_pid, flight, player, arrivals_map)
        if cost <= 0:
            return angle, flight, 1   # artıq bizimdir, 1 gəmi kifayətdir
        if cost > 5000:
            return None   # çox bahadır

        # Check convergence
        if cost == ships_guess:
            return angle, flight, cost

        # Yeni gəmi sayı ilə sürəti yenilə
        old_guess = ships_guess
        ships_guess = cost

        # Əgər yeni sürət eyni uçuş müddəti verirsə, konvergens olub
        result2 = solve_intercept(w, src_pid, tgt_pid, ships_guess, max_horizon)
        if result2 is None:
            return None
        angle2, flight2 = result2

        if flight2 == flight:
            # Eyni vaxtda çatır, final cost-u hesabla
            final_cost = estimate_capture_cost(w, tgt_pid, flight2, player, arrivals_map)
            return angle2, flight2, max(final_cost, 1)

    # Konvergens olmadı, son nəticəni qaytar
    result = solve_intercept(w, src_pid, tgt_pid, ships_guess, max_horizon)
    if result is None:
        return None
    angle, flight = result
    cost = estimate_capture_cost(w, tgt_pid, flight, player, arrivals_map)
    return angle, flight, max(cost, 1)


# =============================================================================
# 8. TEST AGENT — Hər planetdən hər hədəfə 1-5 gəmilik problar
# =============================================================================
def agent(obs, config=None):
    w = World(obs)
    moves = []
    arrivals_map = trace_all_fleets(w)

    my_planets = [p for p in w.planets.values() if p.owner == w.player]
    all_targets = list(w.planets.values())

    # Hər planetdən sent edənlərə budget izləmə
    sent = defaultdict(int)

    for src in my_planets:
        budget = int(src.ships) - 1   # ən azı 1 gəmi saxla
        if budget < 1:
            continue

        for tgt in all_targets:
            if tgt.id == src.id:
                continue

            available = budget - sent[src.id]
            if available < 1:
                break

            # Probe ölçüsü: 1-5 arası, tgt statusuna görə
            probe = min(PROBE_SHIPS, available)
            if probe < 1:
                break

            # Interception həll et
            result = solve_intercept(w, src.id, tgt.id, probe)
            if result is None:
                continue

            angle, flight = result

            moves.append([int(src.id), float(angle), int(probe)])
            sent[src.id] += probe

    return moves
