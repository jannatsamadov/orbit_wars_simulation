# Orbit Wars — "Adaptive Pressure" Strategy

## Core Philosophy

> **Daim təzyiq altında saxla, heç vaxt müdafiəsiz qalma.**

Oyunun əsas mexanikası **istehsalat kompozisiyası**dır: hər tur planet gəmi istehsal edir,
bu gəmilər başqa planetlərə göndərilir, yeni planetlər fəth edilir, daha çox istehsalat əldə
olunur. Eksponensial böyümə yarışıdır. Kim daha tez daha çox planet ələ keçirsə, qalib gəlir.

Amma sadəcə hücum etmək yetmir — müdafiəsiz qalan planetlər itirilir, göndərilən gəmilər
əslində "dondurulmuş kapital"dır (tranzit zamanı heç nə istehsal etmirlər). Bu tarazlığı
riyazi şəkildə optimallaşdırmaq lazımdır.

---

## Decision Architecture

Hər turda agent bu addımları icra edir:

```
1. WORLD STATE     → Bütün planetlər, fleetlər, kometlər parse edilir
2. RAY TRACING     → Uçuşda olan fleetlərin hədəfləri müəyyən edilir
3. THREAT MAP      → Hər bizim planetə gələn təhlükə hesablanır
4. RESERVE CALC    → Hər planetdə nə qədər gəmi saxlamaq lazımdır
5. TARGET SCORING  → Bütün hədəflər qiymətləndirilir (attack/defend/logistics)
6. GREEDY ASSIGN   → Ən yaxşı (src→tgt) cütləri seçilir, budget deducted
7. EXECUTE         → Kinematik interception ilə atəş bucaqları hesablanır
```

---

## Weight Vector (RL-Ready)

Bütün çəkilər bir dict-də saxlanılır ki gələcəkdə RL ilə tune edilsin:

| Simvol | Ad | Default | Təsvir |
|--------|-----|---------|--------|
| `w_time` | Time Decay | 0.6 | Uzaq hədəflərin dəyərini azaldan eksponent |
| `w_disrupt` | Disruption | 0.8 | Düşmən planeti almağın əlavə dəyəri (double-swing) |
| `w_leader` | Leader Focus | 1.5 | Lideri hədəf almağın əlavə çarpanı |
| `w_reserve` | Reserve Mult | 3.0 | Planetdə saxlanacaq gəmi = production × w_reserve |
| `w_threat` | Threat Response | 1.2 | Gələn təhlükəyə qarşı ehtiyat çarpanı |
| `w_defend` | Defense Priority | 5.0 | Müdafiə planlarının prioritet çarpanı |
| `w_logistics` | Logistics | 0.3 | Arxa cəbhədən ön cəbhəyə transfer dəyəri |
| `w_comet` | Comet Discount | 0.7 | Kometin qalan ömrünə görə dəyər azaltması |
| `w_neutral` | Neutral Bonus | 1.3 | Neytral planetlərin erkən oyun prioriteti |
| `w_fortify` | Fortification | 0.15 | Artıq gəmi göndərərək qarnizonu gücləndirmə |
| `w_opp_cost` | Opportunity Cost | 0.1 | Tranzitdə olan gəminin itirdiyi istehsalat dəyəri |
| `w_min_attack` | Min Attack Ships | 8 | Hücum üçün minimum gəmi sayı |
| `w_min_logi` | Min Logistics Ships | 10 | Logistik transfer üçün minimum surplus |

---

## Formulas

### 1. Target Value Score

Hər (source_i → target_j) cütü üçün:

```
V(i→j) = value_j / (cost_ij × time_penalty)
```

**value_j** — hədəfin strateji dəyəri:
```
turns_left = max(0, TOTAL_TURNS - current_step - travel_time)

if target is NEUTRAL:
    value_j = prod_j × turns_left × w_neutral

if target is ENEMY:
    value_j = prod_j × turns_left × (1 + w_disrupt)
    if target.owner == leader_id:
        value_j *= w_leader

if target is OWN (defense):
    value_j = prod_j × turns_left × w_defend

if target is COMET:
    comet_remaining = path_length - path_index - travel_time
    effective_turns = min(turns_left, comet_remaining)
    value_j = prod_j × max(0, effective_turns) × w_comet
```

**cost_ij** — fəth xərci (iterativ həll):
```
cost = iterative_ship_solver(src, tgt, player, arrivals_map)
     = garrison_at_arrival + 1
     
garrison_at_arrival = current_garrison
                    + production × travel_time    (if owned)
                    + Σ incoming_enemy_ships       (if same owner)
                    - Σ incoming_friendly_ships    (if different owner)
```

**time_penalty** — uzaq hədəfləri cəzalandırma:
```
time_penalty = travel_time ^ w_time
```
`w_time = 0.6` → məsafə mühümdür amma dominant deyil.

---

### 2. Reserve Calculation

Hər bizim planet üçün minimum saxlanılacaq gəmi sayı:

```
incoming_threat = Σ (enemy fleet ships heading to planet i)  [ray tracing]

reserve_i = max(1, ceil(
    prod_i × w_reserve                    # base reserve
    + incoming_threat × w_threat          # threat response
))
```

**Intuisiya**: Yüksək istehsalatlı planetlər daha çox qorunmalıdır.
Gələn təhlükə ray tracing ilə müəyyən edilir. `w_threat = 1.2` yəni
gələn fleetdən 20% artıq gəmi saxlayırıq (safety margin).

---

### 3. Phase-Adaptive Aggression

```
if step < 80:          phase = "EXPANSION"
elif step < 300:       phase = "CONSOLIDATION"  
else:                  phase = "DOMINATION"
```

| Faza | Neytral Bonus | Düşmən Bonus | Reserve Mult | Min Attack |
|------|---------------|--------------|--------------|------------|
| EXPANSION | ×1.5 | ×0.8 | ×2.0 | 5 |
| CONSOLIDATION | ×1.0 | ×1.2 | ×3.0 | 8 |
| DOMINATION | ×0.6 | ×1.8 | ×2.0 | 5 |

Erkən oyunda neytral planetlər prioritetdir (genişlənmə).
Gec oyunda düşmən planetlər prioritetdir (hücum).
Reserve mid-game-də ən yüksəkdir (konsolidasiya).

---

### 4. Logistics Transfer

Arxa cəbhədəki (safe) planetlərdən ön cəbhəyə (threatened) gəmi transferi:

```
exposure(planet) = Σ enemy_military_nearby / (Σ friendly_military_nearby + ε)

if exposure(src) < 0.3 AND exposure(tgt) > 0.5:
    surplus = src.ships - reserve_src
    if surplus >= w_min_logi:
        logi_value = w_logistics × surplus × (exposure_tgt - exposure_src) / distance
```

---

### 5. Greedy Assignment with Budget Tracking

```python
candidates = []
for src in my_planets:
    for tgt in all_targets:
        score = compute_score(src, tgt, ...)
        candidates.append((score, src, tgt, ships_needed, angle))

candidates.sort(reverse=True)   # ən yüksək dəyərdən başla

committed = {}   # src_id → committed ships
for score, src, tgt, ships, angle in candidates:
    available = src.ships - reserve[src.id] - committed[src.id]
    if available >= ships:
        execute_move(src, tgt, angle, ships)
        committed[src.id] += ships
```

Bu "greedy" yanaşma optimal deyil amma:
- O(n²) performans verir (500 turda hər turda ~0.01s)
- Ən dəyərli planları əvvəl təmin edir
- Budget izləmə ilə over-commit-i önləyir

---

### 6. Anti-Scatter Mechanism

Əvvəlki agentlərin əsas problemi: çoxlu kiçik fleetlər göndərmək ("scatter").
Bunu önləmək üçün:

1. **Minimum attack threshold**: `w_min_attack = 8` — 8 gəmidən az hücum yoxdur
2. **One-fleet-per-target**: Eyni hədəfə 2 fleet göndərilmir (deduplicate)
3. **Score threshold**: `score < 0` olan planlar icra edilmir

---

## Future RL Integration

Weight vector `W` sabit dict kimi saxlanılır:

```python
W = {
    "w_time": 0.6,
    "w_disrupt": 0.8,
    ...
}
```

RL agenti bu dict-i episod başında set edə bilər:
```python
def rl_agent(obs):
    W = policy_network(obs)   # NN outputs weight vector
    return strategy(obs, W)
```

Alternativ olaraq, evolutionary strategy (CMA-ES) ilə weight-ləri 
populyasiya üzərində optimallaşdırmaq mümkündür.

---

## Comparison with Other Approaches

| Xüsusiyyət | Bu Agent | Claude Lagrangian | v7 Timeline | main.py Sniper |
|-----------|----------|-------------------|-------------|----------------|
| Kinematika | ✅ Sıfırdan | ✅ Köhnə engine | ✅ Köhnə engine | ✅ Köhnə engine |
| Comet lifecycle | ✅ Path-based | ❌ Sonsuz zənn edir | ❌ Fərqsiz | ❌ İgnore edir |
| Phase adaptation | ✅ 3-fazalı | ❌ Statik | ❌ Statik | ❌ Statik |
| Anti-scatter | ✅ Min threshold | ❌ Scatter problemi | ⚠️ Partial | ⚠️ Partial |
| Iterative solver | ✅ ships↔speed↔time | ❌ Yoxdur | ⚠️ Partial | ❌ Yoxdur |
| RL-ready weights | ✅ Dict-based | ⚠️ Hardcoded | ❌ Yoxdur | ❌ Yoxdur |
| Defense | ✅ Ray-trace based | ⚠️ Proximity | ⚠️ Timeline | ⚠️ Simple |
