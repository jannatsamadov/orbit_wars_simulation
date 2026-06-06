# v5.1 Macro Swarm Philosophy

## Qısa Təsvir
v5.1 (Macro Swarm), v5-in (Swarm Intelligence) üzləşdiyi "parçalanmış filoların sürət və zamanlama asinxronluğu" problemini həll edən versiyadır.

## Əsas Strategiya
Oyunda `fleet_speed` gəmi sayından loqarifmik asılıdır. Məsələn, 30 gəmilik tək bir filo, 10 gəmilik 3 fərqli filodan daha sürətlə mənzilə çatır.

Bunu həll etmək üçün **"Minimum Fleet Size Threshold"** (Donanma alt limiti) və ya "İri Həcmli Sinxronizasiya" təyin edilir:
1. Swarm hovuzu eyni qalır. Hədəfləmə məntiqi (Ağırlıq mərkəzinə görə və bizə doğru fırlanan planetlərə öncəlik) eyni qalır.
2. Ancaq **Sinxron Atəş** mərhələsində planeti xırda-xırda vuran kiçik filolar (məsələn, 5-10 gəmi) göndərilmir. 
3. Swarm yalnız o vaxt həmlə edir ki, hovuzdakı planetlərdən **ən azı biri və ya maksimum ikisi** güclü (threshold-u keçən) bir ordu göndərə bilsin. Beləcə filolar həm çox yüksək sürətlə uçur, həm də Sniper-lərin araya girməsinə vaxt qoymadan planeti darmadağın edir.

## Gələcək İdeyalar (Future Ideas)
- **Time-on-Target (ToT) Riyaziyyatı:** Reallıqda hərbi koordinasiya belədir ki, hədəfə uzaq olan topçu birinci atəş açır, yaxındakı topçu isə mərmilərin eyni saniyədə hədəfə dəyməsi üçün (delay) bir neçə saniyə gözləyib sonra atır. Növbəti versiyalarda, hər planetdən filonun çatacağı turn (ETA) hesablanıb, filoların yola çıxma (dispatch) turn-ləri elə gecikdirilə bilər ki, fərqli nöqtələrdən atılan bütün filolar planetə **Eyni Turn-də** çatsın. Bu, Orbit Wars üçün inqilabi bir yanaşma olacaq.
