# Deepseek v2 Strategy & Philosophy

Bu sənəd `deepseekv2.py` agentinin döyüş fəlsəfəsini izah edir.

## Əsas Strategiya
Deepseek v2 fəlsəfəsi **"Mükəmməl Riyaziyyat və Tam Optimal Qərarlar"** (Perfect Math & Optimal Decisions) prinsipinə əsaslanır. Heç bir təxmini, yaxud "heuristic" (kobud kəsrli) hesablamaya güvənmir; tamamilə həndəsi və cəbri tənliklərdən istifadə edir.

### 1. Bisection Metodu ilə Kusursuz Kəsişmə
- Fırlanan planetlərə çatmaq üçün gəminin sürəti və planetin orbital sürəti arasında qalan "kəsişmə zamanını" (intercept time) riyazi olaraq `Bisection (Yarıya bölmə)` metodu ilə tapır. Qeyri-xətti funksiyada (`f(t) = v*t - dist`) aralığı 40 dəfə yarıya bölərək inanılmaz dərəcədə dəqiq nəticə alır.

### 2. Dəqiq Toqquşma Deteksiyası (Ray-Circle & Segment-Circle Intersects)
- Rəqib donanmaların uçuş xətlərini "Ray" (şüa) olaraq qəbul edir və Planetlərin / Günəşin koordinatlarını Dairə kimi götürür. Diskriminant hesablama (Kvadrat tənlik `b^2 - 4ac`) ilə donanmanın hədəf planetə (və ya günəşə) tam olaraq DƏQİQ MİLLİSANİYƏSİNDƏ (turn olaraq) nə vaxt çırpılacağını tapır.
- Bu hesablama həmçinin planetlərin öz orbitlərində hərəkətini (CCW CCW fırlanmasını) nəzərə alır!

### 3. Təhlükə Təhlili (Threat Assessment)
- Əvvəlcə rəqibin bütün donanmalarının məhz *kəsişmə kvadrat tənlikləri* vasitəsilə hara və nə vaxt dəyəcəyini hesablayır.
- Təhlükədə olan planetlərdə **"ships left at impact must be > enemy_ships"** (Vuruş anında qalan gəmilərin sayı düşmən gəmilərindən çox olmalıdır) qanunu qoyur və yalnız artıq gəmiləri hücuma buraxır.

### 4. Aktiv Hücum və Qurtarma Əməliyyatları
- Bütün planetlər iki əməliyyat üzrə qiymətləndirilir:
  - **Hücum (Attack):** Hədəf planetə məsafə, lazım olan qüvvə və hədəfin istehsalat dəyəri (score = prod * 50 - ships - t_arr * 0.5) əsasında hücum.
  - **Müdafiə (Defend):** Öz planetlərindən biri ağır təhlükə altındadırsa və özünü qoruya bilmirsə, digər planetlər mütləq oraya "reinforcement" (kömək) göndərir. Köməyə gedən gəmilərin sayı dəqiq olaraq ehtiyaca uyğun (`needed + 5`) hesablanır və eyni "Bisection" tənliyi ilə fırlanan planeti düzgün bucaq altında izləyir.
