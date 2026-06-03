"""
run_match.py -- Local test runner for Orbit Wars agents.

Usage:
    python run_match.py

Results are saved to:
    replays/  -- HTML replay files, open in any browser
    results/  -- text log of all match outcomes
"""

import sys
import os
import argparse
import importlib.util
import datetime

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
V1_PATH      = os.path.join(BASE_DIR, "agents", "v1_baseline.py")
V2_PATH      = os.path.join(BASE_DIR, "agents", "v2_sniper_plus.py")
V3_PATH      = os.path.join(BASE_DIR, "agents", "v3_precision_striker.py")
V4_PATH      = os.path.join(BASE_DIR, "agents", "v4_adaptive_conqueror.py")
V5_PATH      = os.path.join(BASE_DIR, "agents", "v5_swarm_intelligence.py")
REPLAY_DIR    = os.path.join(BASE_DIR, "replays")
RESULTS_DIR   = os.path.join(BASE_DIR, "results")

os.makedirs(REPLAY_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── load agents ───────────────────────────────────────────────────────────────

def load_agent_from_file(path: str):
    """Import agent() function from any .py file."""
    spec = importlib.util.spec_from_file_location("_agent_mod_" + os.path.basename(path), path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent

# Wong palette from renderer
COLORS = ['#0072B2', '#D55E00', '#009E73', '#F0E442', '#888888']

# ── run ───────────────────────────────────────────────────────────────────────

def run(agents_list, labels_list, match_label: str, save_replay: bool = True, seed: int = 42):
    from kaggle_environments import make

    print(f"\n{'='*60}")
    print(f"  {match_label}")
    print(f"{'='*60}")

    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run(agents_list)

    # ── print results ────────────────────────────────────────────────────────
    final = env.steps[-1]
    results = []
    for i, s in enumerate(final):
        results.append((i, s.reward, s.status))
        tag = "[WIN] " if s.reward == 1 else ("[LOSS]" if s.reward == -1 else "[DRAW]")
        print(f"  Player {i} ({labels_list[i]}): {tag}  reward={s.reward:+.0f}  status={s.status}")

    winner = max(results, key=lambda x: x[1])
    print(f"\n  >> Winner: Player {winner[0]} ({labels_list[winner[0]]})")

    if save_replay:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = match_label.replace(" ", "_").replace("/", "-").replace(":", "")
        html_path = os.path.join(REPLAY_DIR, f"{timestamp}_{safe_label}.html")

        html_content = env.render(mode="html", width=800, height=600)
        
        # We no longer inject the custom legend because the Web UI handles player mapping.
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"  Replay saved --> {html_path}")

    # ── append to results log ────────────────────────────────────────────────
    log_path = os.path.join(RESULTS_DIR, "match_log.txt")
    timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp_str}] {match_label} | seed={seed}\n")
        for i, reward, status in results:
            tag = "WIN " if reward == 1 else ("LOSS" if reward == -1 else "DRAW")
            f.write(f"  Player {i} ({labels_list[i]}): {tag}  reward={reward:+.0f}  status={status}\n")
        f.write(f"  Winner: Player {winner[0]} ({labels_list[winner[0]]})\n")

    return env, html_path if save_replay else None


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Orbit Wars local match runner")
    parser.add_argument("--no-render",  action="store_true", help="skip HTML replay")
    parser.add_argument("--seed",       type=int, default=42, help="random seed")
    args = parser.parse_args()

    save = not args.no_render
    seed = args.seed

    v1 = load_agent_from_file(V1_PATH)
    v2 = load_agent_from_file(V2_PATH)
    v3 = load_agent_from_file(V3_PATH)
    v4 = load_agent_from_file(V4_PATH)
    v5 = load_agent_from_file(V5_PATH)

    # 4-Player Match
    run(
        [v5, v4, v2, v1], 
        ["v5 (Swarm)", "v4 (Adaptive)", "v2 (Sniper+)", "v1 (Baseline)"], 
        "4-Player: v5 vs v4 vs v2 vs v1", 
        save, 
        seed
    )


if __name__ == "__main__":
    main()
