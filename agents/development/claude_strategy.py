
def generate_strategy_moves(player, k_state, timeline, obs_fleets=None):
    """
    Lagrangian-Relaxation Strategy Layer.

    Solves (approximately) the ship-budget constrained integer programme via:
      1. Global state snapshot (economy, leader detection, aggression index)
      2. Per-plan score computation using the analytical J formula
      3. Optimal ship-count selection via T* crossover rule
      4. Greedy priority-ordered assignment with adaptive shadow prices (λ_i)

    Candidate types and their relative priority:
      DEFENCE   (×5.0 boost)  : reinforce my planets projected to fall
      ATTACK    (×1.0)        : capture enemy / neutral planets
      LOGISTICS (×0.35)       : backline surplus → frontline accumulation

    Parameters
    ----------
    player     : int
    k_state    : KinematicsState
    timeline   : TimelineSimulator
    obs_fleets : raw fleet list from obs (optional; used for extra threat data)

    Returns
    -------
    moves : list of [from_planet_id: int, angle: float, ships: int]
    """

    # ── Setup ──────────────────────────────────────────────────────────────────
    my_planets  = {pid: p for pid, p in k_state.planets.items() if p.owner == player}
    all_planets = list(k_state.planets.values())

    if not my_planets:
        return []

    committed   = defaultdict(int)   # ships committed per source planet
    T_h         = timeline.SIM_HORIZON

    # ── Phase 0: Global snapshot ───────────────────────────────────────────────
    (my_prod, my_ships,
     leader_id, leader_prod,
     aggression,
     player_prod, player_garrison) = _global_snapshot(k_state, player)

    # ── Phase 1: Threat triage ─────────────────────────────────────────────────
    threat_map = _build_threat_map(k_state, player)

    # Frontline classification: exposure ratio per my planet
    exposure = {
        pid: _frontline_score(p, all_planets, player)
        for pid, p in my_planets.items()
    }

    # ── Phase 2: Generate & score all candidate plans ──────────────────────────
    #
    # Lagrangian shadow prices λ_i per source planet.
    # Interpretation: λ_i is the current "scarcity premium" of 1 ship at planet i.
    # A plan is worth executing only if  J(plan) − λ_i · S > 0.
    #
    # Initial value: λ_i = 0  (no scarcity yet; any positive-J plan is acceptable).
    # Update rule after committing k ships:
    #   λ_i  ←  (ships_committed / ships_remaining) · γ
    # This captures the non-linear rise in scarcity as budget depletes.
    #
    lambda_price = {pid: 0.0 for pid in my_planets}

    all_candidates = []   # (roi, J, src, tgt, plan, kind)

    for src_id, src in my_planets.items():
        budget = max(0, int(src.ships) - 1)
        if budget < 1:
            continue

        src_exposure = exposure.get(src_id, 0.0)

        for tgt in all_planets:
            if tgt.id == src_id:
                continue

            avail = budget - committed[src_id]
            if avail < 1:
                continue

            t_owner  = tgt.owner
            is_mine  = (t_owner == player)
            is_enemy = (t_owner not in (-1, player))

            # ── Classify plan kind ────────────────────────────────────────────
            if is_mine:
                # Defence or logistics
                tgt_exposure = exposure.get(tgt.id, 0.0)
                tgt_threat   = threat_map.get(tgt.id, 0.0)

                # Defence: planet has incoming threat AND is more exposed than src
                if tgt_threat >= 5.0 and tgt_exposure >= src_exposure * 0.8:
                    kind = 'defense'
                # Logistics: backline → frontline (no threat necessary)
                elif (not exposure.get(src_id, False)    # src is backline (low exposure)
                      and src_exposure < 0.5
                      and tgt_exposure > src_exposure * 1.1
                      and avail >= LOGISTICS_MIN_SURPLUS):
                    kind = 'logistics'
                else:
                    continue   # No strategic reason to send ships here
            else:
                kind = 'attack'

            # ── Query predictive engine ───────────────────────────────────────
            plans = find_valid_plan(src, tgt, timeline, avail, player, k_state)
            if not plans:
                continue

            for plan in plans:
                S_plan = plan["ships"]
                T_plan = plan["T"]

                if S_plan > avail:
                    continue

                # ── Compute optimal ship count via T* crossover ───────────────
                if kind == 'attack':
                    S_opt = optimal_ship_count(src, tgt, T_plan, S_plan, avail)
                    # Cap at available; re-check plan validity is guaranteed by
                    # the engine (S_plan ≤ S_opt, so fortification does not
                    # violate the capture requirement)
                    if S_opt > avail:
                        S_opt = avail
                    adjusted_plan = {"T": T_plan, "ships": S_opt,
                                     "angle": plan["angle"]}
                else:
                    # Defence / logistics: send exactly what the engine recommends
                    S_opt = S_plan
                    adjusted_plan = plan

                # ── Score the plan ────────────────────────────────────────────
                roi, J = compute_plan_score(
                    src, tgt, adjusted_plan,
                    player, k_state, timeline, T_h,
                    leader_id, aggression)

                # Logistics discount
                if kind == 'logistics':
                    roi *= W_LOGISTICS_DISC
                    J   *= W_LOGISTICS_DISC

                all_candidates.append((roi, J, src, tgt, adjusted_plan, kind))

    # ── Phase 3: Lagrangian greedy assignment ──────────────────────────────────
    #
    # Sort by ROI (value per ship) descending.
    # For each candidate:
    #   (a) Check ship budget of source.
    #   (b) Net-value gate: J − λ_i · S > 0   (worth the shadow cost).
    #   (c) Deduplication: one fleet per target (defence can stack if needed).
    #   (d) Commit; update λ_i.
    #
    all_candidates.sort(key=lambda c: -c[0])

    moves      = []
    targeted   = set()   # targets already receiving an attack fleet
    defended   = set()   # targets already receiving a defence fleet
    logistics  = set()   # targets already receiving a logistics transfer

    for roi, J, src, tgt, plan, kind in all_candidates:
        S      = plan["ships"]
        src_id = src.id

        # ── Budget check ──────────────────────────────────────────────────────
        avail = int(my_planets[src_id].ships) - 1 - committed[src_id]
        if S > avail:
            continue

        # ── Deduplication ─────────────────────────────────────────────────────
        if kind == 'attack'   and tgt.id in targeted:   continue
        if kind == 'defense'  and tgt.id in defended:   continue
        if kind == 'logistics'and tgt.id in logistics:  continue

        # Cross-check: do not simultaneously attack AND defend the same target
        if kind == 'attack'  and tgt.id in defended:    continue
        if kind == 'defense' and tgt.id in targeted:    continue

        # ── Net-value Lagrangian gate ─────────────────────────────────────────
        # J − λ_i · S > 0  means the plan earns more than the opportunity cost
        # of the ships at their current scarcity price.
        net_value = J - lambda_price[src_id] * S
        if net_value <= 0:
            continue   # Not worth committing at current shadow price

        # ── Execute move ──────────────────────────────────────────────────────
        moves.append([int(src_id), float(plan["angle"]), int(S)])
        committed[src_id] += S

        # ── Update shadow price (scarcity premium) ────────────────────────────
        #
        # λ_i(k+1) = (committed_i / remaining_i) · γ
        #
        # As remaining → 0, λ → ∞ (scarce ships only go to top-priority plans).
        remaining = int(my_planets[src_id].ships) - 1 - committed[src_id]
        if remaining > 0:
            lambda_price[src_id] = (committed[src_id] / remaining) * W_OPP
        else:
            lambda_price[src_id] = float('inf')   # Budget exhausted

        # ── Register assignment ───────────────────────────────────────────────
        if   kind == 'attack':    targeted.add(tgt.id)
        elif kind == 'defense':   defended.add(tgt.id)
        elif kind == 'logistics': logistics.add(tgt.id)

    return moves


# ==============================================================================
# SECTION 7-H  ─  Modified Agent Entry Point
# ==============================================================================
#
# Drop-in replacement for the existing `agent()` function.
# Only the strategy section (previously the greedy loop) is replaced;
# all kinematics, ray-tracing, and timeline simulation code is UNCHANGED.
#
# How to integrate:
#   1. Paste sections 7-A through 7-H after section 6 in your file.
#   2. Replace the body of agent() from "moves = []" onward with the call below.
#
# ==============================================================================

def agent_v2(obs) -> list:
    """
    Orbit Wars agent with mathematical strategy layer.
    Sections 1-6 (kinematics + simulation) are identical to the original.
    Section 7 (strategy) uses Lagrangian optimisation.
    """
    # ── Parse ──────────────────────────────────────────────────────────────────
    _d      = isinstance(obs, dict)
    player  = obs.get("player", 0)      if _d else getattr(obs, "player", 0)
    obs_fl  = obs.get("fleets", [])     if _d else getattr(obs, "fleets", [])

    # ── Kinematics & simulation (UNCHANGED from original sections 3-5) ─────────
    k_state     = KinematicsState(obs)
    fleet_dests = predict_fleet_destinations(obs_fl, k_state)
    timeline    = TimelineSimulator(k_state, fleet_dests)

    # ── Mathematical strategy layer (Section 7) ────────────────────────────────
    return generate_strategy_moves(player, k_state, timeline, obs_fleets=obs_fl)