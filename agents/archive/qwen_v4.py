import math
import time

# --- SABİTLƏR ---
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
BOARD_SIZE = 100.0
MAX_SPEED = 6.0
SIMULATION_HORIZON = 12 # Gələcəyi görmə dərinliyi

class OrbitTitan:
    def __init__(self):
        self.turn = 0
        self.history = {}

    def get_speed(self, ships):
        if ships <= 1: return 1.0
        return min(MAX_SPEED, 1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5)

    def predict_pos(self, x, y, ang_vel, t):
        dist_sun = math.hypot(x - SUN_X, y - SUN_Y)
        # Günəşə yaxın planetlər orbit edir
        if 12.0 < dist_sun < 45.0 and abs(ang_vel) > 1e-6:
            theta = math.atan2(y - SUN_Y, x - SUN_X) + ang_vel * t
            return SUN_X + dist_sun * math.cos(theta), SUN_Y + dist_sun * math.sin(theta)
        return x, y

    def check_sun_collision(self, sx, sy, tx, ty):
        # Günəş toqquşması yoxlanışı (Xətt seqmenti və dairə)
        dx, dy = tx - sx, ty - sy
        l2 = dx*dx + dy*dy
        if l2 < 1e-9: return False
        t = max(0.0, min(1.0, ((SUN_X - sx)*dx + (SUN_Y - sy)*dy) / l2))
        proj_x, proj_y = sx + t*dx, sy + t*dy
        return math.hypot(proj_x - SUN_X, proj_y - SUN_Y) < (SUN_R + 1.0)

    def intercept(self, sx, sy, tx, ty, ang_vel, ships, iters=6):
        # Hədəfin gələcək mövqeyinə görə bucaq tapılması
        speed = self.get_speed(ships)
        px, py = tx, ty
        t = math.hypot(px - sx, py - sy) / speed if speed > 0 else 999.0
        
        for _ in range(iters):
            px, py = self.predict_pos(tx, ty, ang_vel, t)
            dist = math.hypot(px - sx, py - sy)
            t = dist / speed
            
        px, py = self.predict_pos(tx, ty, ang_vel, t)
        if self.check_sun_collision(sx, sy, px, py):
            return None, None, None
            
        angle = math.atan2(py - sy, px - sx)
        return angle, t, (px, py)

    def simulate_future(self, my_planets, enemy_planets, neutrals, fleets, ang_vel, my_move, horizon):
        # Sadələşdirilmiş Gələcək Simulyasiyası
        # Bu funksiya verilən gedişin (my_move) uzunmüddətli nəticəsini hesablayır
        
        # Vəziyyəti klonla
        state = {p[0]: {"owner": p[1], "ships": p[5], "prod": p[6], "x": p[2], "y": p[3]} 
                 for p in my_planets + enemy_planets + neutrals}
        
        # Mənim gedişimi tətbiq et
        if my_move:
            src_id, angle, ships = my_move
            if src_id in state and state[src_id]["owner"] == self.player_id:
                state[src_id]["ships"] -= ships
                # Donanmanı "uçuşda" kimi qeyd et (sadəlik üçün hədəfə əlavə edirik, lakin gecikmə ilə)
                # Dəqiq simulyasiya üçün vaxt lazımdır, lakin burada "anında təsir" fərziyyəsi ilə aqressivlik yaradırıq
                # Əslində gəmilər yolda olacaq, amma "təsir potensialı" kimi baxırıq
        
        # Rəqibin "phantom" (xəyali) cavablarını simulyasiya et (Melis botunun etdiyi kimi)
        # Rəqib ən yaxın hədəflərimizə hücum edəcək
        for t_step in range(1, horizon):
            # İstehsal
            for pid, data in state.items():
                if data["owner"] != -1:
                    data["ships"] += data["prod"]
            
            # Sadə döyüş məntiqi (əgər donanmalar varsa)
            # Burada mürəkkəb fizika əvəzinə "Təhdid Xəritəsi" yaradırıq
            pass 

        # Xal hesabla: (Mənim Gücüm - Rəqibin Gücü) + (Mənim İstehsalım - Rəqibin İstehsalım) * 10
        my_score = sum(d["ships"] + d["prod"]*10 for d in state.values() if d["owner"] == self.player_id)
        enemy_score = sum(d["ships"] + d["prod"]*10 for d in state.values() if d["owner"] != self.player_id and d["owner"] != -1)
        
        return my_score - enemy_score

    def agent(self, obs):
        self.turn += 1
        self.player_id = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
        ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
        
        raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
        raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
        
        my_planets = [p for p in raw_planets if p[1] == self.player_id]
        enemy_planets = [p for p in raw_planets if p[1] not in (self.player_id, -1)]
        neutrals = [p for p in raw_planets if p[1] == -1]
        
        moves = []
        if not my_planets: return moves

        # --- STRATEJİ MƏRHƏLƏ ---
        
        # 1. Təhdidləri Təhlil Et (Müdafiə)
        # Rəqib donanmaları hara gedir?
        incoming_threats = {p[0]: 0 for p in my_planets}
        for f in raw_fleets:
            if f[1] != self.player_id and f[1] != -1:
                # Təxmini hədəf (ən yaxın planet)
                # Dəqiq hesablama üçün vaxt azdır, ona görə sadə məsafə
                min_d = 999
                target_id = -1
                for p in my_planets:
                    d = math.hypot(p[2]-f[2], p[3]-f[3])
                    if d < min_d:
                        min_d = d
                        target_id = p[0]
                if target_id != -1:
                    incoming_threats[target_id] += f[6]

        # 2. Həmlə Hədəfləri (Hücum)
        candidates = []
        
        # A. Anbar Reydləri (Rəqibin yığım məntəqələri)
        for ep in enemy_planets:
            if ep[5] > 40 and ep[6] < 5: # Çox gəmi, az istehsal = Hammer hazırlığı
                candidates.append({"target": ep, "type": "RAID", "priority": 100})
            else:
                candidates.append({"target": ep, "type": "ATTACK", "priority": 50 + ep[6]})

        # B. Neytral Planetlər (Genişlənmə)
        for np in neutrals:
            # ROI = İstehsal / (Gəmi + Məsafə)
            dist = min([math.hypot(mp[2]-np[2], mp[3]-np[3]) for mp in my_planets])
            roi = np[6] / (np[5] + dist*0.5 + 1)
            candidates.append({"target": np, "type": "EXPAND", "priority": 30 + roi*10})

        # 3. Qərar Vermə (Greedy + Lookahead)
        # Hər planet üçün ən yaxşı hədəfi tap
        
        # Planetləri "Cəbhə" və "Arxa Cəbhə" olaraq böl
        frontline = []
        backline = []
        for mp in my_planets:
            min_enemy_dist = min([math.hypot(mp[2]-ep[2], mp[3]-ep[3]) for ep in enemy_planets] or [999])
            if min_enemy_dist < 35.0:
                frontline.append(mp)
            else:
                backline.append(mp)

        # Arxa cəbhədən ön cəbhəyə daşıma (Logistika)
        for bl in backline:
            if bl[5] > 10:
                # Ən yaxın ön cəbhə planetini tap
                target_fl = min(frontline, key=lambda f: math.hypot(f[2]-bl[2], f[3]-bl[3]), default=None)
                if target_fl:
                    angle, t, _ = self.intercept(bl[2], bl[3], target_fl[2], target_fl[3], ang_vel, bl[5])
                    if angle is not None:
                        moves.append([bl[0], angle, int(bl[5]*0.8)]) # 80% göndər

        # Ön cəbhədən hücum
        for fl in frontline:
            available = fl[5] - incoming_threats.get(fl[0], 0) - 5 # Müdafiə üçün ehtiyat
            if available < 8: continue

            best_move = None
            best_score = -9999

            for cand in candidates:
                tgt = cand["target"]
                # Lazımi gəmi sayı
                dist = math.hypot(fl[2]-tgt[2], fl[3]-tgt[3])
                speed = self.get_speed(available)
                t_arr = dist / speed
                required = tgt[5] + (tgt[6] * t_arr if tgt[1] != -1 else 0) + 2
                
                if required > available: continue # Gücümüz çatmır

                angle, t, pos = self.intercept(fl[2], fl[3], tgt[2], tgt[3], ang_vel, required)
                if angle is None: continue

                # Simulyasiya Xalı (Lookahead)
                # Sadə hevristika: Prioritet + (İstehsal Fərqi)
                score = cand["priority"]
                if tgt[1] != self.player_id:
                    score += tgt[6] * 5 # İstehsalı almaq vacibdir
                
                # Əgər bu hədəf "tələ"dirsə (rəqibin donanması yaxındadırsa), xalı azalt
                # (Burada mürəkkəb simulyasiya əvəzinə sadə təhdid analizi)
                
                if score > best_score:
                    best_score = score
                    best_move = [fl[0], angle, int(required)]

            if best_move:
                moves.append(best_move)

        return moves

agent_instance = OrbitTitan()
def agent(obs):
    return agent_instance.agent(obs)