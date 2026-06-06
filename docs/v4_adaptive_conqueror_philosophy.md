# v4 Adaptive Conqueror Philosophy

## Qısa Təsvir
v4, əvvəlki modellərin ən güclü xüsusiyyətlərini vəziyyətə uyğunlaşdıraraq hibridləşdirdiyimiz modeldir: v1-in (sürət) və v3-ün (dəqiqlik) mükəmməl birləşməsi.

## Əsas Strategiya
Düşmənin növünə (State) görə adaptiv (Adaptive) davranır:

**1. Neytral Planetlərə Qarşı (Expansion Phase):**
   - Neytral planetlər (owner == -1) gəmi istehsal etmirlər (və ya bizə qarşı çıxarmırlar). 
   - Ona görə də onlara qarşı v3 kimi mürəkkəb riyaziyyat və ya ehtiyat etmir. 
   - Sadəcə `target.ships + 1` qədər gəmi göndərir. 
   - Öz bazasında saxladığı minimum gəmini (`MIN_GARRISON`) 10-dan 2-yə salır ki, sürətlə bütün xəritəyə yayıla bilsin.

**2. Düşmən Planetlərə Qarşı (Combat Phase):**
   - Düşmən planetinə hücum edəndə isə yenidən `v3_precision_striker` rejiminə keçir.
   - Gələcək orbit koordinatını hesablayır, düşmənin ETA ərzindəki istehsalını üstünə gəlir və qorunmanı gücləndirir (MIN_GARRISON = 10).

## Üstünlükləri
- FFA (Free-for-all) oyunlarda v1 kimi aqressiv böyüyür, amma sonradan v1 kimi axmaqlaşmır, düşmənə qarşı v3 dəqiqliyi ilə ağır zərbələr vurur.
