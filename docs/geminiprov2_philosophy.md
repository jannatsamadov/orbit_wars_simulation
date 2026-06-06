# Gemini Pro v2 Strategy & Philosophy

Bu sənəd `geminiprov2.py` agentinin döyüş fəlsəfəsini izah edir. 

## Əsas Strategiya
Gemini Pro v2 **"Dinamik Faydalılıq və Proqnozlaşdırma"** (Dynamic Utility Scoring) strategiyasından istifadə edir. Bütün planetləri eyni vaxtda qiymətləndirir və əlindəki boş (deployable) gəmiləri ən dəyərli (yüksək ROI gətirən) cəbhələrə yatırır.

### 1. Fiziki Model (CCW CCW Təqibi)
- Qabaqcıl Kinematika mühərriki yazaraq `predict_interception` funksiyası ilə düşmən planetinə "təxmini" bir xətt atmır. Planet fırlanırsa (CCW), onun qabağına çıxacaq şəkildə **10 iterativ tsikl** (loop) həyata keçirir.
- Hər iterasiyada məsafəni və planetin orbital bucağını tapır. Cəmi 0.05 saniyəlik fərq qalana qədər bucaqları tənzimləyir.
- Göndərdiyi qüvvələrin Günəş tərəfindən yanaraq yox olmamasını təmin etmək üçün `check_sun_collision` ilə riyazi limitləri cızır.

### 2. Müdafiə Minimumu
- Hər hansı planetdən hücuma başlamazdan öncə həmin planetin **istehsalat gücünün 2 misli** qədərini qoruma olaraq (`production * 2`) bazada saxlayır. Bu isə onu digər aqressiv botlardan daha dözümlü edir.

### 3. Dinamik Faydalılıq Hesablanması (Dynamic Utility Scoring)
- Sırf böyük donanma axtarmır. Yüksək fayda-məsrəf (cost-benefit) yanaşması ilə tətbiq edir:
  `Utility = production / (time_of_flight + 1.0)`
  `Score = Utility / required_ships`
- Yəni bir planetin istehsalatı nə qədər çoxdursa, ona çatmaq nə qədər az vaxt alacaqsa və bunun üçün bizdən nə qədər AZ gəmi tələb olunacaqsa, balı (Score) o qədər yüksək olur.
- Neytralları ələ keçirməkdənsə, rəqibləri əzməyə üstünlük verir (Rəqiblərə 1.2x xal çarpanı tətbiq edilir).

### 4. Dəqiq Qüvvə Göndərişi
- Hücum hədəfi tapıldıqdan sonra hədəf planetin ora çatana qədər (actual_t) neçə yeni gəmi tikəcəyini dəqiq hesablayır: `actual_future_garrison = target["ships"] + target["production"] * actual_t`
- Cəmi `+5` gəmi ehtiyat (margin) saxlayaraq dəqiq şəkildə həmin miqdarı göndərir. Əgər bəs etmirsə, planetdə qalan bütün boş qüvvəni həmin tərəfə yollayır.
