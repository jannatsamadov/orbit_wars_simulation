# ChatGPT v3 Strategy & Philosophy

Bu sənəd `chatgptv3.py` (ChatGPT tərəfindən yaradılmış üçüncü versiya) agentinin döyüş fəlsəfəsini izah edir. 

## Əsas Strategiya
ChatGPT v3 **"Mərkəzləşdirilmiş Güc (Hub) və Dəqiq Hesablama"** strategiyasına əsaslanır. O, planetləri iki kateqoriyaya bölür: Hücumçu cəbhə planetləri və arxada qalan "Təchizat" (Hub) planetləri.

### 1. Dəqiq Gələcək Təxmini (Fixed-Point Interception)
- Bir planetə (xüsusilə fırlanan) çatmaq üçün sadəcə təxmini xətt çəkmir. İterativ riyazi funksiya ilə (`choose_intercept`) donanmanın gedəcəyi vaxtı hesablayıb, o vaxta planetin gələcəyi yeri tapır. Sonra həmin yerə çatmaq üçün vaxtı bir daha hesablayır və bu prosesi 5 dəfə təkrarlayır. Nəticədə 100% dəqiq kəsişmə nöqtəsini əldə edir.

### 2. Gələcək Gücün (Future Strength) Hesablanması
- `estimate_future_strength` funksiyası ilə hədəfə çatana qədər hədəfin neçə tur ərzində neçə yeni gəmi istehsal edəcəyini hesablayır.
- Göndərdiyi gəmi sayını məhz bu "gələcək gücə" uyğun hesablayır (`future_strength + 3`), beləliklə israfın qarşısını alır.

### 3. Dinamik Hədəf Qiymətləndirməsi (Strategic Valuation)
- `owner_bonus` sistemi ilə rəqib planetlərə daha yüksək üstünlük verir (`1.5x`), neytrallara isə normal (`1.15x`).
- İstehsalata güclü əhəmiyyət verir (`(production + 1.0) ** 2`). Lakin hədəfin "gələcək gücü"nə və məsafəyə (arrival_turns) bölərək ideal balı (score) çıxarır.

### 4. İki Mərhələli Oyun: Genişlənmə və Dəstək
- **Genişlənmə (Expansion/Attack):** Güclü (15+ gəmi) olan planetlər ən yaxşı rəqib/neytral hədəflərə qüvvə göndərir. 35% qüvvəni həmişə müdafiə (reserve) üçün saxlayır.
- **Dəstək (Reinforcement):** Əgər o tur çox az hücum qərarı alınıbsa (oyun sakitləşibsə), agent avtomatik olaraq **"Reinforcement phase"**-ə (Dəstək mərhələsi) keçir. Bütün kiçik planetlərdəki boş gəmiləri ən çox istehsalı olan "Hub" (Mərkəzi baza) planetinə göndərir ki, orada kütləvi, yenilməz bir donanma (Swarm) toplanıb böyük zərbələr endirə bilsin.
