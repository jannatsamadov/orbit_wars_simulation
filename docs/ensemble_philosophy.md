# Ensemble Super Bot Fəlsəfəsi (ensemble.py)

Bu agent mövcud ən yaxşı AI modellərinin (Kimi, Deepseek, Qwen, ChatGPT və Claude) güclü tərəflərinin birləşdirildiyi "Super Model"dir. Onun qərar vermə alqoritmi həm həndəsi dəqiqliyə, həm də makro-strateji gedişlərə əsaslanır.

## Əsas Strateji Fərqliliklər

### 1. Oyunçu Sayına Görə Dinamik Adaptasiya (4v4 vs 1v1)
Ən böyük innovasiya modelin neçə nəfərlik oyuna düşdüyünü başa düşməsidir:
- İlk turda xəritədəki unikal sahibləri (owners) sayaraq oyunun növünü təyin edir.
- **1v1 Rejimi:** Düşmənə qarşı birbaşa aqressiv və təzyiq əsaslı (All-in) hücumlara keçir.
- **4-Nəfərlik Rejim (FFA):** Ortadakı qırğına (Inner planets) heç vaxt birinci girmir. O bilir ki, mərkəz "Diqqət Mərkəzi"dir və ora girən hamının hədəfinə çevriləcək. Buna görə də "Kənar Genişlənmə" (Outer Edge Expansion) edir: mərkəzdən uzaq, lakin istehsalatı böyük olan xarici planetləri alır və səssizcə böyüyür.

### 2. İstehsalat (Production) Fokuslu İqtisadiyyat
Rəqiblərin kiçik planetlərlə vaxt itirdiyi bir vaxtda, bu model hədəfləri seçərkən *İstehsalatın 1.5-ci qüvvəti* (`prod ** 1.5`) düsturu ilə xal hesablayır. Yəni radiusu/istehsalı böyük olan planetlər onun üçün 1 nömrəli şikardır.

### 3. Böyük Donanma Yığılması (Fleet Accumulation)
Bəzi modellər 1-2 gəmi yığılan kimi hücuma göndərib gəmiləri yollarda zibil edir. 
- Ensemble isə planetdəki gəmi sayı onun tutumunun (radiusunun) ən azı 50%-nə və ya minimum 15 gəmiyə çatana qədər dözür və yığır.
- Göndərəndə isə ehtiyac olan minimum sayı yox, ehtiyacın 1.3 qatını göndərir. Niyə? Çünki gəmi sayı artdıqca uçuş sürəti (Fleet Speed) logarifmik olaraq kəskin artır və düşmənə hazırlaşmağa vaxt qalmır!

### 4. Claude tipli Fövqəladə Müdafiə və Kəsişmə
Claude modelindən öyrəndiyi `intercept_pos` (İterativ orbital kəsişmə) və Fövqəladə müdafiə skanlama sistemini də arxa planda işlədir ki, kənardan gələn qəfil zərbələrə qarşı həmişə qorunma qarnizonu saxlasın.
