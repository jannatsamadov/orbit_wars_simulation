# Kimi v2 Strategy & Philosophy

Bu sənəd `kimiv2.py` agentinin döyüş fəlsəfəsini izah edir. 

## Əsas Strategiya
Kimi v2 digər bütün modellərdən bir addım irəli gedərək **"Vizual Keçmişin İzlənməsi (State Tracking)" və "Optimal Donanma Formalaşdırması"** strategiyasını işlədir. Kimi eyni zamanda qısa yol seçmək əvəzinə, böyük və sürətli donanmalar yaradaraq logarifmik sürət üstünlüyünü maksimum istifadə etməyə çalışır.

### 1. Keçmiş İzləyərək Orbiti Anlamaq (State Tracking)
- Oyun tərəfindən "hansı planetin orbitdə olub-olmaması" birbaşa verilmədiyi üçün, Kimi hər turn planetlərin X və Y koordinatlarını `agent.state` içərisində yadda saxlayır.
- Son 5 tur üzrə planetlərin koordinat tarixçəsini götürür və bucaqları analiz edərək planetin Saat Əqrəbinin Əksinə (CCW) hərəkət edib-etmədiyini aşkar edir. Əgər belədirsə, onun birbaşa daxili planet olduğunu kəşf edir.

### 2. Düşmən və Dost Donanmalarının Deteksiyası (Ray-casting)
- Səmada uçan bütün donanmaların uçuş bucağı (angle) üzrə riyazi şüa ataraq (Ray-casting) onların DƏQİQ olaraq hansı planetlərə doğru hərəkət etdiyini aşkarlayır.
- `incoming_friendly` və `incoming_enemy` lüğətlərini yaradaraq hər bir planetin təhlükəsizlik səviyyəsini (eff_defense) müəyyən edir. Rəqib planetini ələ keçirmək üçün bizim digər bir planetdən göndərdiyimiz donanma yoldadırsa, onu təkrar hədəf almır (qüvvə israfından qaçır).

### 3. Kobud və Dəqiq Kəsişmə Axtarışı (Coarse & Fine Search)
- `solve_interception` funksiyasında əvvəlcə zaman (time_of_flight) üzrə kobud axtarış (`0.5` addımlarla), sonra isə tapılan ən yaxşı zaman ətrafında incə axtarış (`0.05` addımlarla) edir. Bu, tam dəqiq kəsişməni tapmasını zəmanət altına alır.

### 4. Sürət və Böyüklük Əsaslı Hücumlar (Speed-Optimized Fleets)
- Kimi bilir ki, donanma nə qədər böyükdürsə o qədər sürətli uçur (`math.log(ships)` düsturuna əsasən).
- Əgər hədəf 20 vahiddən uzaqdadırsa, qələbə qazanmaq üçün tələb olunan minimum gəmidən DAHA ÇOX (məs: ehtiyac yoxdursa belə 40-80 gəmi) göndərir. Nəticədə donanma çox sürətli uçur, rəqibin planeti istehsalını artırmadan dərhal işğal edilir. "Overkill" zərəri ilə "Speed" faydasını bir yerdə hesablayır (`speed_bonus`).

### 5. Dəstək və Xilasetmə (Defensive Reinforcements)
- Təhlükə altında olan (üzərinə çoxlu düşmən gələn) öz planetlərinə, təhlükəsiz zonada qalan digər planetlərindən avtomatik böyük dəstək göndərir.
