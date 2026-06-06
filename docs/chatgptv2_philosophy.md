# ChatGPT v2 Strategy & Philosophy

Bu sənəd `chatgptv2.py` (ChatGPT tərəfindən yaradılmış ikinci versiya) agentinin döyüş fəlsəfəsi və riyazi yanaşmasını izah edir.

## Əsas Strategiya
ChatGPT v2 əsasən "Təzyiq (Pressure) və Təhlükəsizlik" mərkəzli oynayır. Rəqibin donanmalarını öncədən analiz edərək planetlərin gələcək müdafiə qabiliyyətini (ROI) hesablayır.

### 1. Düşmən Təzyiqinin (Pressure) Hesablanması
- Bütün uçan donanmaları analiz edir və onların qət edəcəyi trayektoriya əsasında hansı planetə hücum etdiklərini "təxmin" (target_guess) edir.
- Hər planet üçün bu təxminlərə əsasən `incoming_strength` hesablayır. Beləliklə, bir planetin sadəcə hazırkı gəmilərini yox, həm də üzərinə gələn təhlükəni nəzərə alaraq qərar verir.

### 2. Müdafiə Rezervi (Garrison)
- Öz planetlərindən hücuma keçməzdən əvvəl həmin planetə gələn düşmən təzyiqini hesablayır və `enemy_pressure * 1.15` (15% ehtiyatla) qədər gəmini planetdə saxlayır (ən az 10 gəmi olmaq şərtilə). Beləliklə, ev planetləri müdafiəsiz qalıb ələ keçirilmir.

### 3. Hədəf Seçimi (Target Scoring)
Hədəfləri bu meyarlarla sıralayır:
- **İstehsalat:** Yüksək istehsalata önəm verir (`8.0 * production`).
- **Gələcək Müdafiə:** Hədəfin mövcud gəmiləri və üzərinə gedən digər rəqib donanmaları cəmləyib `0.08` qatsayısı ilə dəyərdən çıxır. Yəni çox güclü qorunan və artıq cəbhəyə çevrilmiş planetlərdən uzaq durur.
- **Neytral Üstünlüyü:** Neytral planetlər üçün əlavə `+3.0` bal verir.

### 4. Dəqiq Kəsişmə və Hücum (Interception)
- Hədəfin hərəkətdə (orbitdə) olub-olmadığını hesablayır.
- Lazım olan qüvvəni `target["ships"] + target["production"] * 3 + 5` düsturu ilə tapır. (Hədəfə çatana qədər 3 turluq bir istehsal ehtimalı edir).
- Minimum gəmi göndərir ki, ehtiyat qüvvələr israf olmasın, amma kifayət qədər böyük donanma olsun ki, sürət də yüksək olsun (ən azı əldəki qüvvənin 55%-i).
- Günəşlə toqquşma ehtimalını tam dəqiqliklə oxşar üçbucaqlar/vektor proyeksiya düsturu ilə (point to line distance) hesablayaraq təhlükəli zonalardan uzaq durur.
