# Qwen v2 Strategy & Philosophy

Bu sənəd `qwenv2.py` agentinin döyüş fəlsəfəsini izah edir. 

## Əsas Strategiya
Qwen v2 öz oyununu **"Tam Qarnizon Simulyasiyası və Göndərilən Qüvvələrin Optimallaşdırılması"** üzərində qurur. Əsas üstünlüyü Binary Search istifadə edərək eyni anda həm ideal uçuş vaxtını, həm də göndərilməli olan ideal gəmi sayını dəqiq tapmasıdır.

### 1. Keçmiş İzləyərək Fırlanmanın Aşkarlanması
- Kimi v2 agentinə bənzər olaraq Qwen də planetlərin əvvəlki yerlərini `agent.prev_positions` içində saxlayır və əgər planet yerindən tərpənibsə (`dist > 0.001`), onu orbital (fırlanan) planet olaraq qeyd edir. Tur 0 üçün isə CCW bucaq sürəti varsa və radius `35.0`-dən kiçikdirsə, onu birbaşa fırlanan planet kimi götürür.

### 2. Gələcək Simulyasiyası (Garrison Simulation)
- Uçuşda olan bütün donanmaların (özünün və ya rəqibin) son çatma məntəqələrini (`predict_fleet_dest`) tapır və xəritədəki hər bir planet üçün uçuş qeydlərini (`incoming`) hazırlayır.
- `get_enemy_ships_at` funksiyası ilə zamanın istənilən `t` anı üçün hədəf planetin üzərində kimin neçə gəmisi olacağını *tarixi simulyasiya edərək* (həmin ana qədər dəyəcək digər donanmaları bir-bir hesablayaraq) dəqiq tapır. Beləliklə, düşmənin istehsalını və ona gələn köməyi eyni anda görür.

### 3. Binary Search ilə "Ən Yaxşı Sərmayə (ROI)" Hesablaması
- Hədəfə hücum etmək üçün təxmini gəmi göndərmir. Minimum 1-dən maksimum mövcud gəmi sayına qədər Binary Search (`low`, `high`) edərək həmin planetə göndəriləcək **minimal, amma qələbə üçün yetərli gəmi sayını (min_S)** axtarır.
- Hər sınaq sayında (mid), planetə çatma zamanını hesablayır, daha sonra simulyasiyaya girib baxır ki, "Bu qədər gəmi göndərsəm, o vaxt çatanda oradakı cəmi qüvvəni üstələyə biləcəmmi?". Əgər bəli isə, daha da AZ göndərməyə çalışır.
- Nəticədə ən yüksək ROI (`score = production / min_S`) verən planetə tam yetərli qüvvə ilə hücum edir. Beləliklə heç bir resursu boşuna xərcləmir.

### 4. Güclərin Birləşdirilməsi (Fallback: Consolidate Forces)
- Əgər bir planetdən hücum etmək üçün sərfəli hədəf tapa bilmirsə (məsələn, göndərə biləcəyi bütün gəmilər belə yetərsizdirsə), həmin planetdəki qüvvələri passiv saxlamır. Onları ən yaxındakı, Təhlükəsiz olan digər öz (dost) planetinə yollayır. Beləliklə, xırda ordular toplanıb böyük bir güc formalaşdırır (Macro Swarm taktikasına bənzər Mərkəzləşmə).
