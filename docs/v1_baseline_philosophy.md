# v1 Baseline Philosophy

## Qısa Təsvir
v1 (Nearest Sniper) Kaggle tərəfindən verilən baza (baseline) agentinin bir az daha təkmilləşdirilmiş və ya eyni məntiqdə işləyən versiyasıdır. Onun fəlsəfəsi sürət, sadəlik və aqressiyadır.

## Əsas Strategiya
1. **Yalnız Düşmənə Hücum (Targets):** Sadəcə oyunçunun sahib olmadığı (Neytral və ya Düşmən) planetləri hədəf alır.
2. **Ən Yaxın Hədəf (Greedy Proximity):** Öz planetlərindən hər biri üçün, riyazi olaraq ən yaxın planeti seçir (`math.hypot(mine.x - target.x, mine.y - target.y)`).
3. **Minimum Gəmi (Minimalist Strike):** Hədəfi zəbt etmək üçün lazım olan *dəqiq* gəmi sayını (`hədəf.ships + 1`) göndərir.

## Üstünlükləri
- Çox sürətlidir. Oyunun əvvəlində heç bir gözləmə olmadan bütün yaxındakı Neytral planetləri tutur.
- Resurs israf etmir (`ships + 1` qədər atır).

## Zəif Cəhətləri
- **Orbit Proqnozlaşdırması Yoxdur:** Hərəkət edən planetlərə atəş edərkən onların mövcud yerinə atəş açır. Gəmilər çatana qədər planet yerini dəyişir deyə gəmilər çox vaxt boşluğa uçur.
- **Müdafiə Yoxdur:** Öz planetini boşaldır, düşmən hücumlarına qarşı aciz qalır.
