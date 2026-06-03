import os
import re

def analyze_matches(log_path):
    head_to_head = {}
    size_perf = {}
    
    # Check if file exists
    if not os.path.exists(log_path):
        return {"head_to_head": {}, "size_perf": {}, "total_matches": 0, "unique_seeds": 0}

    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_match_type = None
    current_seed = None
    current_players = []
    
    unique_seeds = set()
    total_matches = 0

    match_header_re = re.compile(r"\[.*?\] (\d+)-Player Match .*? \| seed=(\d+)")
    player_re = re.compile(r"Rank \d+ \((.*?)\.py\): (WIN|LOSS)")

    for line in lines:
        line = line.strip()
        if not line:
            # End of match block
            if current_match_type and current_players:
                total_matches += 1
                if current_seed:
                    unique_seeds.add(current_seed)
                    
                # Size Performance
                for p, result in current_players:
                    if p not in size_perf:
                        size_perf[p] = {"2": {"wins":0, "matches":0}, "4": {"wins":0, "matches":0}}
                    
                    # Ignore invalid match types just in case
                    if current_match_type in size_perf[p]:
                        size_perf[p][current_match_type]["matches"] += 1
                        if result == "WIN":
                            size_perf[p][current_match_type]["wins"] += 1
                
                # Head-to-Head (Only calculate pure 1v1 interactions for clarity)
                if current_match_type == "2" and len(current_players) == 2:
                    p1, res1 = current_players[0]
                    p2, res2 = current_players[1]
                    
                    if p1 not in head_to_head: head_to_head[p1] = {}
                    if p2 not in head_to_head[p1]: head_to_head[p1][p2] = {"wins":0, "matches":0}
                    
                    if p2 not in head_to_head: head_to_head[p2] = {}
                    if p1 not in head_to_head[p2]: head_to_head[p2][p1] = {"wins":0, "matches":0}
                    
                    head_to_head[p1][p2]["matches"] += 1
                    head_to_head[p2][p1]["matches"] += 1
                    
                    if res1 == "WIN":
                        head_to_head[p1][p2]["wins"] += 1
                    elif res2 == "WIN":
                        head_to_head[p2][p1]["wins"] += 1

            current_match_type = None
            current_seed = None
            current_players = []
            continue

        match_head = match_header_re.search(line)
        if match_head:
            current_match_type = match_head.group(1)
            current_seed = match_head.group(2)
            continue
        
        player_match = player_re.search(line)
        if player_match:
            agent = player_match.group(1)
            result = player_match.group(2)
            current_players.append((agent, result))

    # Calculate win rates for easier front-end usage
    for model, modes in size_perf.items():
        for mode in ["2", "4"]:
            m_stats = modes[mode]
            if m_stats["matches"] > 0:
                m_stats["win_rate"] = round((m_stats["wins"] / m_stats["matches"]) * 100, 1)
            else:
                m_stats["win_rate"] = 0.0
                
    for m1, opps in head_to_head.items():
        for m2, stats in opps.items():
            if stats["matches"] > 0:
                stats["win_rate"] = round((stats["wins"] / stats["matches"]) * 100, 1)
            else:
                stats["win_rate"] = 0.0

    return {
        "head_to_head": head_to_head,
        "size_perf": size_perf,
        "total_matches_analyzed": total_matches,
        "unique_seeds": len(unique_seeds)
    }
