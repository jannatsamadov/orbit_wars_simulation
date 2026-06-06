import os
import glob
import json
import random
import time
import datetime
from collections import defaultdict
from kaggle_environments import make

STATE_FILE = "tournament_state.json"
AGENTS_DIR = "agents"
K_FACTOR = 32

def get_available_agents():
    # Only get .py files in agents directory, excluding agent_v2.py (example template)
    agents = []
    for filepath in glob.glob(os.path.join(AGENTS_DIR, "*.py")):
        basename = os.path.basename(filepath)
        if basename != "agent_v2.py":
            agents.append(filepath)
    return sorted(agents)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"elos": {}, "matches_played": 0, "agent_matches": defaultdict(int)}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def initialize_new_agents(state, available_agents):
    for agent in available_agents:
        if agent not in state["elos"]:
            state["elos"][agent] = 1200.0
        if agent not in state["agent_matches"]:
            state["agent_matches"][agent] = 0

def select_matchup(state, available_agents, is_phase_2=False):
    # Phase 2: only top 6 agents
    if is_phase_2 and len(available_agents) > 6:
        sorted_agents = sorted(available_agents, key=lambda a: state["elos"][a], reverse=True)
        pool = sorted_agents[:6]
    else:
        pool = available_agents
        
    # Decide 2-player or 4-player (50/50 chance, but require enough agents)
    num_players = 2 if random.random() < 0.5 or len(pool) < 4 else 4
    
    # Sort pool by Elo for matchmaking
    pool_sorted = sorted(pool, key=lambda a: state["elos"][a])
    
    # Pick a random pivot agent
    pivot_idx = random.randint(0, len(pool_sorted) - 1)
    
    # To mimic Kaggle, we pick players close to the pivot's Elo
    # For a simple local approach, we take a slice around the pivot
    half_window = max(1, num_players)
    start_idx = max(0, pivot_idx - half_window)
    end_idx = min(len(pool_sorted), pivot_idx + half_window + 1)
    
    candidates = pool_sorted[start_idx:end_idx]
    
    # If not enough candidates (e.g. at the edges), just take first or last num_players
    if len(candidates) < num_players:
        if pivot_idx < len(pool_sorted) // 2:
            candidates = pool_sorted[:num_players]
        else:
            candidates = pool_sorted[-num_players:]
            
    matchup = random.sample(candidates, num_players)
    # Shuffle so start positions are fair
    random.shuffle(matchup)
    return matchup

def compute_pairwise_elo(matchup, rewards, statuses, state):
    # Rank players based on reward. If status is not DONE, treat reward as -infinity
    ranked_players = []
    for i, agent in enumerate(matchup):
        status = statuses[i]
        reward = rewards[i] if rewards[i] is not None and status == "DONE" else -999999
        ranked_players.append({"agent": agent, "reward": reward, "original_idx": i})
        
    # Sort by reward descending (1st place first)
    ranked_players.sort(key=lambda x: x["reward"], reverse=True)
    
    # Assign ranks (handling ties)
    current_rank = 1
    for i, p in enumerate(ranked_players):
        if i > 0 and p["reward"] < ranked_players[i-1]["reward"]:
            current_rank = i + 1
        p["rank"] = current_rank
        
    print("\n--- Match Results ---")
    for p in ranked_players:
        print(f"Rank {p['rank']}: {os.path.basename(p['agent'])} | Reward: {p['reward']} | Status: {statuses[p['original_idx']]}")
    
    # Calculate Elo updates
    elo_changes = {agent: 0.0 for agent in matchup}
    num_players = len(matchup)
    
    for i, p1 in enumerate(ranked_players):
        a1 = p1["agent"]
        elo1 = state["elos"][a1]
        delta_sum = 0
        
        for j, p2 in enumerate(ranked_players):
            if i == j: continue
            a2 = p2["agent"]
            elo2 = state["elos"][a2]
            
            # Expected score for a1
            expected = 1.0 / (1.0 + 10.0 ** ((elo2 - elo1) / 400.0))
            
            # Actual score
            if p1["rank"] < p2["rank"]:
                actual = 1.0
            elif p1["rank"] > p2["rank"]:
                actual = 0.0
            else:
                actual = 0.5
                
            delta_sum += K_FACTOR * (actual - expected)
            
        # Average the delta to keep inflation bounded per match
        elo_changes[a1] = delta_sum / max(1, (num_players - 1))
        
    for agent, change in elo_changes.items():
        state["elos"][agent] += change
        state["agent_matches"][agent] += 1
        print(f"Elo Update [{os.path.basename(agent)}]: {change:+.2f} -> {state['elos'][agent]:.2f}")
        
    state["matches_played"] += 1
    
    # Append to match_log.txt
    try:
        os.makedirs("results", exist_ok=True)
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seed_val = state.get("last_seed", "unknown")
        match_label = f"{num_players}-Player Match"
        with open(os.path.join("results", "match_log.txt"), "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp_str}] {match_label} (Tournament #{state['matches_played']}) | seed={seed_val}\n")
            for p in ranked_players:
                agent_name = os.path.basename(p["agent"])
                tag = "WIN " if p["rank"] == 1 else "LOSS"
                f.write(f"  Rank {p['rank']} ({agent_name}): {tag}  reward={p['reward']}\n")
    except Exception as e:
        print(f"Failed to log match: {e}")

def print_leaderboard(state):
    print("\n" + "="*40)
    print(f"LEADERBOARD (Total Matches: {state['matches_played']})")
    print("="*40)
    sorted_elos = sorted(state["elos"].items(), key=lambda x: x[1], reverse=True)
    for i, (agent, elo) in enumerate(sorted_elos):
        name = os.path.basename(agent)
        matches = state["agent_matches"].get(agent, 0)
        print(f"{i+1}. {name.ljust(25)} | Elo: {elo:.1f} | Matches: {matches}")
    print("="*40 + "\n")

def run_tournament(matches_for_phase1=200, max_matches=None):
    print("Starting Orbit Wars Local Elo Tournament...")
    
    while True:
        state = load_state()
        if max_matches is not None and state["matches_played"] >= max_matches:
            print(f"Reached max_matches ({max_matches}). Exiting.")
            break
            
        available_agents = get_available_agents()
        
        if not available_agents:
            print("No agents found in agents/ folder!")
            time.sleep(5)
            continue
            
        initialize_new_agents(state, available_agents)
        
        # Decide Phase
        # We disable Phase 2 so all agents play evenly regardless of matches played
        is_phase_2 = False
            
        matchup = select_matchup(state, available_agents, is_phase_2)
        print(f"\nStarting match #{state['matches_played'] + 1} with {len(matchup)} players:")
        for a in matchup:
            print(f"- {os.path.basename(a)}")
            
        # Generate and save a seed
        seed = random.randint(0, 1000000)
        state["last_seed"] = seed
        
        # Run match
        env = make("orbit_wars", configuration={"seed": seed}, debug=False)
        try:
            start_time = time.time()
            env.run(matchup)
            duration = time.time() - start_time
            print(f"Match finished in {duration:.1f} seconds.")
            
            final_step = env.steps[-1]
            rewards = [st.reward for st in final_step]
            statuses = [st.status for st in final_step]
            
            compute_pairwise_elo(matchup, rewards, statuses, state)
            save_state(state)
            
            # Print leaderboard every 5 matches
            if state["matches_played"] % 5 == 0:
                print_leaderboard(state)
                
        except Exception as e:
            print(f"Error during match: {e}")
            time.sleep(2)

if __name__ == "__main__":
    # You can change matches_for_phase1 to delay Phase 2
    run_tournament(matches_for_phase1=100)
