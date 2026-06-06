# v2 Sniper Plus Philosophy

## Qısa Təsvir
v2, v1-in sadə yaxınlıq məntiqini iqtisadi bir məntiqə çevirir. Yaxınlıqla yanaşı planetin dəyərini (istehsalını) da hesablayaraq daha dəyərli hədəflərə "Sniper" (Snayper) kimi fürsətçi zərbələr endirir.

## Əsas Strategiya
1. **Production-Weighted Priority:** Hədəf seçərkən məsafəyə deyil, dəyərə baxır. 
   Düstrur: `Score = (target.production ** 2) / max(distance, 0.1)`. Bu o deməkdir ki, böyük planetlər kiçiklərdən dəfələrlə daha cəlbedicidir.
2. **Qorunma Zolağı (MIN_GARRISON):** Fərqli olaraq, hər planetində daimi 10 gəmi saxlayır. Bu onu düşmənin opportunist zərbələrindən qoruyur.
3. **Snayper Effekti:** 4-oyunçulu matçlarda başqalarının zəiflətdiyi statik (hərəkətsiz xarici) planetləri və ya birbaşa yaxınlaşan planetləri dəqiq iqtisadi hədəfləyib zəbt edir.

## Üstünlükləri
- Çox güclü İqtisadi Baza: Neytral planetlər içində yalnız ən çox gəmi verənləri tutur deyə oyunda istehsal lideri olur.
- Sürətli atəşlər: İterasiyalı hesablamalar olmadığı üçün tərəddüd etmir.

## Zəif Cəhətləri
- **Orbit Proqnozu Hələ Də Yoxdur:** Yenə də hərəkət edən planetlərə qarşı kor-koranə atəş açır. Lakin dəyərli (xarici dairədəki statik) planetlərə üstünlük verdiyi üçün bu qüsur çox hiss olunmur.
