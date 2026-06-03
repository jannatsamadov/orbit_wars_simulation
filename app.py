from flask import Flask, render_template, request, jsonify, send_file
import os
import run_match
import analytics

app = Flask(__name__)

import glob

# Map readable names to file paths
MODELS = {
    "v1_baseline": "v1 (Baseline)",
    "v2_sniper_plus": "v2 (Sniper+)",
    "v3_precision_striker": "v3 (Precision)",
    "v4_adaptive_conqueror": "v4 (Adaptive)",
    "v5_swarm_intelligence": "v5 (Swarm)",
    "v5_1_macro_swarm": "v5.1 (Macro Swarm)",
    "random": "Random"
}

# Auto-detect new agents dynamically on page load
@app.route('/')
def index():
    agent_files = glob.glob(os.path.join(run_match.BASE_DIR, "agents", "*.py"))
    print(f"DEBUG: Found {len(agent_files)} files: {agent_files}")
    for f in agent_files:
        basename = os.path.basename(f)
        if not basename.startswith("__") and basename != "agent_v2.py":
            key = basename[:-3]
            if key not in MODELS:
                MODELS[key] = key.replace("_", " ").title()
                
    # Load Tournament Leaderboard Data
    leaderboard = []
    matches_played = 0
    state_file = os.path.join(run_match.BASE_DIR, "tournament_state.json")
    if os.path.exists(state_file):
        import json
        with open(state_file, 'r') as sf:
            state = json.load(sf)
            matches_played = state.get("matches_played", 0)
            elos = state.get("elos", {})
            agent_matches = state.get("agent_matches", {})
            for agent, elo in elos.items():
                name = os.path.basename(agent)[:-3]  # remove .py
                display_name = MODELS.get(name, name.title())
                leaderboard.append({
                    "name": display_name,
                    "elo": round(elo, 1),
                    "matches": agent_matches.get(agent, 0)
                })
                
    # Ensure all available models (even if not in tournament state yet) appear in leaderboard
    leaderboard_names = {p["name"] for p in leaderboard}
    for key, display_name in MODELS.items():
        if key == "random": continue
        if display_name not in leaderboard_names:
            leaderboard.append({
                "name": display_name,
                "elo": 1200.0,
                "matches": 0
            })
            
    # Sort by Elo descending
    leaderboard.sort(key=lambda x: x["elo"], reverse=True)
    # Add rank
    for i, p in enumerate(leaderboard):
        p["rank"] = i + 1
    
    return render_template('index.html', models=MODELS, leaderboard=leaderboard, total_matches=matches_played)

@app.route('/run', methods=['POST'])
def run_game():
    data = request.json
    mode = data.get('mode', '1v1')
    p1 = data.get('p1', 'random')
    p2 = data.get('p2', 'random')
    p3 = data.get('p3', 'random')
    p4 = data.get('p4', 'random')
    seed = int(data.get('seed', 42))

    agents = []
    labels = []
    
    def get_agent(name):
        if name == "random": return "random"
        return run_match.load_agent_from_file(os.path.join(run_match.BASE_DIR, "agents", f"{name}.py"))

    agents.append(get_agent(p1))
    labels.append(MODELS.get(p1, "Unknown"))
    agents.append(get_agent(p2))
    labels.append(MODELS.get(p2, "Unknown"))

    if mode == 'ffa':
        agents.append(get_agent(p3))
        labels.append(MODELS.get(p3, "Unknown"))
        agents.append(get_agent(p4))
        labels.append(MODELS.get(p4, "Unknown"))

    match_label = f"{mode.upper()}: " + " vs ".join(labels)
    
    try:
        env, html_path = run_match.run(agents, labels, match_label, save_replay=True, seed=seed)
        
        # Extract final scores from the environment
        final_state = env.steps[-1][0].observation
        # In Orbit Wars, the final reward is usually just +1 or -1, but we can look at the ships
        # The easiest way is to just return the results we wrote to log (WIN/LOSS)
        results = [(i, s.reward) for i, s in enumerate(env.steps[-1])]
        
        scores_text = []
        for i, reward in results:
            status = "Qalib 🏆" if reward == 1 else "Məğlub 💀"
            scores_text.append(f"P{i}: {status}")

        filename = os.path.basename(html_path)
        return jsonify({"success": True, "replay_url": f"/replays/{filename}", "scores": scores_text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/replays/<filename>')
def serve_replay(filename):
    replay_dir = os.path.join(run_match.BASE_DIR, "replays")
    return send_file(os.path.join(replay_dir, filename))

@app.route('/api/stats')
def api_stats():
    log_path = os.path.join(run_match.BASE_DIR, "results", "match_log.txt")
    stats = analytics.analyze_matches(log_path)
    return jsonify(stats)

@app.route('/api/restart_tournament', methods=['POST'])
def restart_tournament():
    try:
        import time
        state_file = os.path.join(run_match.BASE_DIR, "tournament_state.json")
        if os.path.exists(state_file):
            backup_file = os.path.join(run_match.BASE_DIR, f"tournament_state_backup_{int(time.time())}.json")
            os.rename(state_file, backup_file)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html', models=MODELS)

if __name__ == '__main__':
    app.run(debug=True, port=5005, use_reloader=False)
