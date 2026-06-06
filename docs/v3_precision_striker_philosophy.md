# v3 Precision Striker Philosophy

## Qısa Təsvir
v3 modelinin əsas məqsədi kosmosun fizikasını anlamaq və düşmən hədəflərini "gələcəkdə" olduqları yerdə vurmaqdır. O həmçinin düşmənin ETA ərzində istehsal edəcəyi gəmiləri də hesablayır.

## Əsas Strategiya
1. **İterativ Orbit Hesablaması (Predict Pos):** Planetin hərəkət sürətini (`angular_velocity`) və gəmilərimizin sürətini bilir. Gəmilərimizin hədəfə nə vaxt çatacağını (ETA) təxmin edir və planetin o vaxt harada olacağını (future_pos) iterativ olaraq (4 dəfə) hesablayır ki, dəqiq kəsişmə (intercept) nöqtəsini tapsın.
2. **Düşmən İstehsalını Ön görmək:** Əgər hədəf düşmənə aiddirsə, o, biz gəlib çatana qədər yeni gəmilər çıxaracaq.
   Düstur: `Extra_ships = target.production * ETA`. Beləcə ora sürpriz bir məğlubiyyətlə çatmırıq, böyük bir filo (buffer + 5 ilə) göndəririk.
3. **Günəşdən Qorunma:** Atəş xəttinin Günəşə (SUN) dəyib-dəymədiyini yoxlayır, əgər dəyəcəksə, atəşdən vaz keçir.
4. **Müdafiə Rejimi:** Bizə doğru gələn düşmən filolarının (enemy_fleets) hansı planetimizi hədəflədiyini trayektoriya kəsişməsi ilə tapıb, yaxındakı planetlərimizdən kömək (reinforcements) yollayır.

## Üstünlükləri
- Boşa gedən atəş (demək olar) sıfıra enir.
- Birəbir (1v1) döyüşlərdə məğlubedilməz bir riyazi üstünlük yaradır.

## Zəif Cəhətləri
- Ehtiyatlı olduğu və çox gəmi gözlədiyi üçün (buffer + istehsal + min garrison) oyunun əvvəlində Neytral planetlərə yayılmaqda (Expansion) ləngiyir.
