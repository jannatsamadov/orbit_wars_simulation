# v5 Swarm Intelligence Philosophy

## Qısa Təsvir
v5 tək fərdlərin eqoist qərarlarından imtina edib, mərkəzləşdirilmiş və koordinasiya edilmiş "Sürü" (Swarm) məntiqi ilə işləyir. Mean Field Control (Ortalama Sahə Nəzarəti) elementlərinə əsaslanır.

## Əsas Strategiya
1. **Ortaq Hovuz (Global Pool):** Bütün planetlərdəki istifadə edilə bilən (`ships - MIN_GARRISON`) gəmilər vahid bir hovuzda cəmlənir. 
2. **Ağırlıq Mərkəzi (Swarm Center):** Bütün planetlərin çəkili mərkəzi (`X, Y`) hesablanır. Planetdə nə qədər çox gəmi varsa, mərkəz o qədər ona yaxın olur.
3. **Riyazi Hədəfləmə:** 
   - Hədəf planetin gələcəkdəki pozisiyası (future_pos) Swarm Mərkəzinə nəzərən tapılır.
   - Əgər planetin gələcək pozisiyası bizə cari pozisiyasından daha yaxındırsa, deməli planet **"bizə doğru fırlanır"**. Bu planetlərin xalı 2 dəfə artırılır (çünki gəmilər ona daha tez çatacaq).
   - Score = `Production² * (Approach_Bonus) / Distance`.
4. **Sinxron Atəş (Coordinated Strike):** Bir planet üçün məsələn, 30 gəmi lazımdırsa, bunu 1 planet deyil, Swarm hovuzundan ən yaxın olan bir neçə planet (15, 10, 5) paylaşdırıb eyni anda atəş açır.

## Niyə İşləmədi? (v5.1 ehtiyacı)
Orbit Wars oyununda gəmi sayı donanmanın (fleet) sürətinə təsir edir (loqarifmik olaraq böyük filolar daha sürətlidir). v5 bir neçə planetdən kiçik hissələr çıxardığı üçün, hər kiçik filo yavaş uçur və hədəfə fərqli vaxtlarda çatır.
Nəticədə ilk çatan filo hədəfi zəiflədir (ölür) və opportunist agentlər (Sniper, v2) kənardan gəlib boşalmış planeti zəbt edirlər. Buna görə "Macro Swarm" (v5.1) yaradılmasına qərar verildi.
