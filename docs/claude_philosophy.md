# Claude Agent Fəlsəfəsi (claude.py)

Bu agent (Claude) ehtiyatlı, çox-qatlı analitik və yüksək riyazi dəqiqliyə malik bir fəlsəfə ilə işləyir. Claude risk almayan, lakin qarantiyalı qələbəni hədəfləyən bir sistemdir.

## Əsas Strateji Sütunlar

### 1. İterativ Orbital Kəsişmə (Orbital Intercept Solver)
Claude digər agentlərdən fərqli olaraq, hədəfin sadəcə indikator orbiti üzərinə hesablanmış bucağına qane olmur. O, "Fixed-Point Iteration" (Daimi Nöqtə İterasiyası) adlı bir riyazi model tətbiq edir.
- Birinci təxmin (planetin indiki yeri).
- Ora çatmaq üçün vaxt hesablanır.
- Həmin vaxtda planetin yeni yeri tapılır.
- Damping factor (0.55/0.45 nisbəti) ilə köhnə və yeni təxminlər birləşdirilir.
- Bu iterasiya 64 dəfəyə qədər təkrarlanır ki, raket (donanma) hədəf planetlə milimetrik kəsişsin və səhv etmə ehtimalı 0-a düşsün.

### 2. Donanma Axınının Analizi (Fleet-flow Analysis)
Claude kosmosda uçan HƏR BİR rəqib və dost donanmasını (fleet) izləyir və onların hara getdiyini (Ray Projection) təxmin edir.
- Hər planet üçün "Gözlənilən Kömək" (`my_in`) və "Gözlənilən Təhlükə" (`opp_in`) hesablanır.
- Buna əsasən gələcəkdə planetin üzərindəki qarnizonun miqdarı qabaqcadan proqnozlaşdırılır.

### 3. Fövqəladə Müdafiə Sistemi (Emergency Defence Pass)
Hücumdan da öncə, Claude bütün planetlərini skan edir və yolda olan düşmən gəmiləri səbəbilə "düşmək üzrə olan" (deficit) planetlərini tapır. Dərhal ən yaxın müttəfiq planetdən bura milimetrik şəkildə qoruma gəmiləri göndərir.

### 4. İqtisadi ROI Skorinqi (Economic Scoring)
Hər hücum qərarı bu düsturla verilir:
`base_score = prod / (needed * (1 + dist/60))`
- **Bəhanələr (Modifiers):** 
  - Əgər hədəfin içi demək olar ki, boşdursa (çox zəif qorunursa), o hədəfin cazibədarlığını `2.5x` artırır.
  - Hədəf düşmənə aiddirsə `2.2x` qat dəyər qatır (Çünki rəqibin gəlirini kəsmək ikiqat qazancdır).
  - Əgər iqtisadi baxımdan rəqibdən geri qalırsa (Trailing state), təcili şəkildə düşmən planetlərinə hücum həvəsini `1.4x` artırır ki, fərqi bağlasın.

### 5. Günəşdən Tam Qorunma (Sun Avoidance)
Hər bir buraxılış bucağı (launch angle) "Line-to-Point Distance" (Xətt və Nöqtə Məsafəsi) düsturu ilə günəşə olan məsafədən yoxlanılır. Əgər ən ufak bir ehtimal varsa ki, donanma günəşin qırmızı zonasına toxunacaq, o əmr dərhal ləğv edilir.
