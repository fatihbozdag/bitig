# Değerlendirme (PAN paketi)

Adli yayınlar ve mahkemeler ham doğruluktan fazlasını bekler. bitig, standart PAN doğrulama görevi metrik menüsünü tek bir çağrının arkasında sunar.

## Tek çağrı değerlendirme

```python
from bitig.forensic import compute_pan_report

report = compute_pan_report(
    probs=calibrated_probs,     # CalibratedScorer'dan
    y=ground_truth_labels,
    log_lrs=log_lr_values,      # isteğe bağlı; cllr_bits'i etkinleştirir
)
report.to_dict()
# {
#   "auc": 0.94, "c_at_1": 0.88, "f05u": 0.87,
#   "brier": 0.11, "ece": 0.042, "cllr_bits": 0.31,
#   "n_target": 80, "n_nontarget": 120,
# }
```

## Metrikler

| Ölçüt | Ölçtüğü | Ne için | Aralık | Kaynak |
|---|---|---|---|---|
| `auc` | Sıralama kalitesi | **Sistemler arasında seçim yaparken.** Daha yüksek AUC → sistem, aynı-yazar çiftlerini farklı-yazar çiftlerinin üzerinde daha güvenilir biçimde sıralar. | 0 (tamamen ters) – 1 (mükemmel); 0.5 rastgeledir | — |
| `c_at_1` | Çekimser kalma kredisiyle doğruluk | **"Bilmiyorum" cevabının yanlış cevaptan daha güvenli olduğu operasyonel kararlar** için. | 0 – 1 | Peñas & Rodrigo 2011 |
| `f05u` | Yanıtsızlık cezalı hassasiyet ağırlıklı F | **PAN-tipi değerlendirme.** Aşırı güvenli yanlış cevapları cezalandırır. | 0 – 1 | Bevendorff et al. 2019/2020 |
| `brier` | Posterior kalibrasyonu | **Olasılıksal çıktı kalitesi.** Düşük = daha iyi kalibre edilmiş olasılıklar. | 0 (mükemmel) – 1 (en kötü) | Brier 1950 |
| `ece` | Beklenen kalibrasyon hatası | **`predict_proba` dürüst mü?** Tahminleri güvene göre gruplar; iddia edilen ile gerçek doğruluğu karşılaştırır. | 0 (mükemmel) – 1 | — |
| `cllr` | Log-olabilirlik-oranı maliyeti | **Adli LR kalitesi.** Kanıtsal çıktı için katı uygun puanlama kuralı. | 0 (mükemmel) – ∞ | Brümmer & du Preez 2006 |
| `tippett` | LR dağılım grafiği | **Kalibrasyonu görsel olarak denetleme.** Kümülatif hedef ve hedef olmayan LR eğrileri ayrışmalıdır. | — | — |

### c@1

$$
\text{c@1} = \frac{1}{n}\!\left( n_\text{correct} + n_\text{unanswered} \cdot \frac{n_\text{correct}}{n} \right)
$$

*yanıtsız* denemeler `|p − 0.5| ≤ margin` olan denemelerdir. Varsayılan margin = 0 ile, PAN değerlendiricisinde olduğu gibi tam olarak `p = 0.5` yanıtsızdır; böyle çıktılar yoksa c@1 doğruluğa eşittir. Pozitif bir margin çekimser bandı genişletir ancak PAN ile karşılaştırılamaz.

PAN doğrulama paylaşımlı görevi, çekinmesini bilen sistemleri ödüllendirdiği için — doğrudan "yetersiz kanıt" adli kavramıyla örtüşür — 2013'ten bu yana c@1'i birincil metrik olarak kullanmaktadır.

### C_llr

$$
C_\text{llr} = \frac{1}{2}\!\left[
  \frac{1}{|T|}\!\sum_{i \in T} \log_2\!\left(1 + \tfrac{1}{\text{LR}_i}\right)
  +
  \frac{1}{|N|}\!\sum_{i \in N} \log_2\!\left(1 + \text{LR}_i\right)
\right]
$$

$T$ = hedef denemeler (target trials), $N$ = hedef olmayan denemeler (non-target trials). En iyi kalibre edilmiş referans sisteme göre deneme başına ortalama bilgi kaybı (bit cinsinden) olarak yorumlanır.

- **Yalnızca önsel olasılık sistemi** (her log-LR = 0) → C_llr = **1.0** tam.
- **Mükemmel, güvenilir sistem** → C_llr ≈ 0.
- **Yanıltıcı sistem** (yanlış işaret) → C_llr > 1.

C_llr < 1 olan bir sistem yalnızca önsel olasılık sistemini geride bırakır. Adli yayınlar, C_llr'nin ayrım *ve* kalibrasyonu tek bir skalerde yakalaması nedeniyle AUC'nin yanında C_llr'yi düzenli olarak raporlar.

## Tippett grafikleri

`tippett(log_lrs, y)`, doğrudan çizebileceğiniz sınıf başına kümülatif dağılımları döndürür:

```python
import matplotlib.pyplot as plt
from bitig.forensic import tippett

data = tippett(log_lrs, y)
plt.step(data["thresholds"], data["target_cdf"], label="aynı-yazar")
plt.step(data["thresholds"], data["nontarget_cdf"], label="farklı-yazar")
plt.xlabel("log₁₀(LR) eşiği")
plt.ylabel("P(log-LR ≥ eşik | sınıf)")
plt.legend()
```

İyi ayrım yapan bir sistemde hedef CDF sağda (yüksek log-LR'ler ağırlıklı olarak hedef), hedef olmayan CDF solda birikirler.

## Referans

### compute_pan_report

*Şu durumda kullanın:* etiketlenmiş bir doğrulama denemesi grubunuz var ve tek bir çağrıda her standart metriği — AUC, c@1, F0.5u, Brier, ECE, (isteğe bağlı) C_llr — istiyorsunuz.
*Şu durumda kullanmayın:* yalnızca tek bir metriğe ihtiyacınız var; her metrik fonksiyonu doğrudan çağrılabilir.
*Beklenen sonuç:* her alanı doldurulmuş bir `PANReport` veri sınıfı.

::: bitig.forensic.metrics.compute_pan_report

::: bitig.forensic.metrics.PANReport

### AUC

*Şu durumda kullanın:* aynı kıyaslama üzerinde iki doğrulama sistemini karşılaştırırken — AUC eşik bağımsızdır.
*Şu durumda kullanmayın:* operasyonel bir karar almanız gerekiyor — AUC, eşiğin nereye ayarlanacağı konusunda hiçbir şey söylemez.
*Beklenen sonuç:* `[0, 1]` aralığında tek bir sayı; 0.5 rastgele bir sıralamayı, 0.5'in altındaki değerler ise ters bir sıralamayı gösterir. Tahmin edilen olasılıkların kalibre edilmiş olmasına bağlı değildir.

::: bitig.forensic.metrics.auc

### c@1

*Şu durumda kullanın:* sisteminiz çekimser kalabiliyorsa ("bilmiyorum") ve bunu dürüstçe kredilendirmek istiyorsanız — doğruluk artı çekimser kalma için kısmi kredi bonusu.
*Şu durumda kullanmayın:* sisteminiz hiçbir zaman tam 0.5 (çekimser sinyali) üretmiyorsa; `c@1` o zaman doğruluğa eşittir.
*Beklenen sonuç:* `[0, 1]` aralığında tek bir sayı. Yalnızca çekimser kalma oranı > 0 olduğunda doğruluğu geçer.

::: bitig.forensic.metrics.c_at_1

### F0.5u

*Şu durumda kullanın:* bir PAN-CLEF doğrulama izini puanlıyorsanız — PAN'ın hassasiyet ağırlıklı F ölçüsü, `1.25·TP / (1.25·TP + 0.25·(FN + N_u) + FP)`; burada `N_u`, etiketinden bağımsız olarak her yanıtsız denemeyi (`p = 0.5`) sayar (Bevendorff vd. 2019/2020).
*Şu durumda kullanmayın:* PAN dışı bir kitleye raporluyorsanız; uzman bir metriktir.
*Beklenen sonuç:* `[0, 1]` aralığında tek bir sayı.

::: bitig.forensic.metrics.f05u

### C_llr

*Şu durumda kullanın:* adli açıdan **LR çıktınızın ne kadar iyi olduğunu** ölçmeniz gerekiyorsa — bu, konuşmacı tanıma topluluğunun benimsediği katı uygun puanlama kuralıdır.
*Şu durumda kullanmayın:* puanlayıcınız doğruluk-tipi olasılıklar üretiyorsa; `C_llr` log-olabilirlik oranları bekler.
*Beklenen sonuç:* negatif olmayan tek bir sayı; 0 mükemmeldir; 1 bilgisizdir (yazı-tura ile eşleşir).

::: bitig.forensic.metrics.cllr

### ECE

*Şu durumda kullanın:* olasılıksal dürüstlüğü denetlemek istiyorsanız — ECE, tahminleri iddia edilen güvene göre gruplandırır ve gerçek doğruluğun eşleşip eşleşmediğini kontrol eder.
*Şu durumda kullanmayın:* geliştirme kümeniz küçükse (<200 deneme); ECE'nin grup tahminleri gürültülü hale gelir.
*Beklenen sonuç:* `[0, 1]` aralığında tek bir sayı; 0 mükemmel kalibrasyon demektir.

::: bitig.forensic.metrics.ece

### Brier

*Şu durumda kullanın:* olasılıksal sınıflandırıcılar için uygun bir puanlama kuralı istiyorsanız (LR çıktıları değil) — tahmin edilen olasılık ile gerçek değer arasındaki klasik karesel hata.
*Şu durumda kullanmayın:* adli LR'ye özgü bir metriğe ihtiyaç duyuyorsanız — `C_llr` kullanın.
*Beklenen sonuç:* `[0, 1]` aralığında tek bir sayı; 0 mükemmeldir.

::: bitig.forensic.metrics.brier

### Tippett

*Şu durumda kullanın:* görsel bir kalibrasyon denetimi istiyorsanız — hedef deneme ve hedef olmayan log-LR'leri kümülatif dağılımlar olarak çizin.
*Şu durumda kullanmayın:* tek sayılı bir özete ihtiyacınız varsa (`C_llr` kullanın).
*Beklenen sonuç:* `thresholds` (sıralı benzersiz log-LR değerleri) ile `target_cdf` / `nontarget_cdf` (her sınıfta her eşiğin üzerinde veya eşiğinde kalan denemelerin oranı) anahtarlarını içeren, matplotlib grafiği için hazır bir sözlük.

::: bitig.forensic.metrics.tippett
