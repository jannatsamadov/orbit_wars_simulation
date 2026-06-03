# HTML / Flask Bug Logs

Bu sənəd sistemdəki lokal Flask serveri və HTML arasında baş verən spesifik problemlərin texniki səbəblərini və həllərini loglamaq üçün yaradılmışdır.

---

## Bug #1: "Network error: TypeError: Cannot read properties of undefined (reading 'forEach')"

- **Nə baş verdi:** `Run Simulation` düyməsinə basdıqda oyun açılmırdı və ekranda bu error görünürdü. HTML kodu `data.scores.forEach` oxumağa çalışırdı, lakin `data.scores` tapılmırdı.
- **Səbəb:** Flask serverinin fərqli versiyaları (zombi proseslər) arxa planda Port 5000-də asılı qalmışdı. Python faylına (`app.py`) `scores` əlavə edib yenidən başlatmağa çalışsaq da, Port əvvəldən məşğul olduğu üçün yeni server portu ala bilməmişdi. Sənin brauzerin arxa planda hələ də **köhnə kodla işləyən** (və JSON daxilində `scores` göndərməyən) zombi serverlə əlaqə qururdu.
- **Həll:** `taskkill /F /PID <pid>` əmri ilə Port 5000-də olan BÜTÜN Python prosesləri məhv edildi. Daha sonra təmizlənmiş portda server yenidən, yalnız 1 nüsxədə işə salındı.

---

## Bug #2: Qovluğa yeni model əlavə etdikdə (məs: kimi.py) HTML dropdown-da görünmürdü

- **Nə baş verdi:** Sən qovluğa yeni `.py` agentləri əlavə etdikdən sonra brauzeri yeniləsən də, modellər siyahıya düşmədi.
- **Səbəb:** Əvvəlki kodda `glob` vasitəsilə qovluğun taranıb yeni modellərin siyahıya (`MODELS`) əlavə edilməsi yalnız **Server ilk dəfə işə düşəndə (Global səviyyədə)** baş verirdi. Yeni bir `.py` faylı əlavə etmək Flask serverini avtomatik restart etmədiyinə görə, serverin xatirəsində (RAM) siyahı köhnə vəziyyətində qalırdı.
- **Həll:** `glob` ilə faylları tarama kodunu Qlobal hissədən çıxarıb, birbaşa `index()` (ana səhifəni yükləyən) route daxilinə köçürdüm.
- **Nəticə:** Artıq HTML səhifəsini hər dəfə yeniləyəndə (Refresh / F5), server birbaşa qovluğa baxır, yeni gələn hər hansı agenti tapıb anında HTML dropdown-a əlavə edir. Serveri bağlayıb açmağa ehtiyac yoxdur.

---

## Bug #3: "The connection was closed unexpectedly" (Lokal Serverin cavab verməməsi)

- **Nə baş verdi:** `Run Simulation` düyməsinə basdıqda və ya brauzerdə səhifəni yüklədikdə server qəfildən bağlanırdı və ya timeout verirdi. Eyni zamanda CLI-da `curl` etdikdə "connection closed unexpectedly" xətası alınırdı.
- **Səbəb:** Əvvəlki "Bug #1"-də olan port 5000-dəki donmuş (zombi) Python proseslərini Windows-da `taskkill` ilə məhv etmək istədikdə, proseslər o qədər dərin bloklanmışdı (deadlock) ki, `taskkill` əmrləri belə timeout verib uğursuz olurdu. Port 5000 faktiki olaraq əməliyyat sistemi tərəfindən girov götürülmüşdü. Nə qədər ki server eyni porta (5000) qoşulmağa çalışır, qüsurlu yüklənmələr və əlaqənin qopması davam edəcəkdi.
- **Həll (Niyə 5000 yox, 5005?):** Əməliyyat sisteminin bloklanmış resursu (Port 5000) ilə "mübarizə aparmaq" əvəzinə, ən təmiz, təhlükəsiz və qəti həll serverin portunu dəyişməkdir. `app.py`-da `app.run(port=5005)` təyin edərək serveri tamamilə təmiz, heç bir prosesin mane olmadığı yeni porta keçirdim. 
- **Nəticə:** Server artıq port 5005 üzərində heç bir əngəl olmadan problemsiz işləyir. Eyni problemi başqa istifadəçilər (və ya başqa bir AI) yaşayarsa, ən effektiv AI alqoritmi / həlli budur: "Əgər portda zombi proses varsa və `kill` əmri işləmirsə, dərhal portu dəyiş!" 

---
