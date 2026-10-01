# Doğrulama

Yazar doğrulama (authorship verification) tek sınıflı bir karardır: **belirli bir aday, bu sorgulanan belgeyi üretmiş midir?** Gerçek dava çalışmaları nadiren kapalı bir aday kümesi sunar; bu nedenle doğrulama — yazar tespitinin aksine — adli açıdan standart görevdir.

bitig iki tamamlayıcı doğrulayıcı sunar.

## General Impostors

*Şu durumda kullanın:* bir sorgulanan belgeniz, bir adayın bilinen belgelerinin ve diğer yazarlardan oluşan ~100+ sahte yazar havuzunun olduğu, adli açıdan standart aynı-yazar-mı-değil-mi sorusunu yanıtlamanız gereken durumlarda.
*Şu durumda kullanmayın:* sahte yazar havuzunuz yoksa veya adayın bilinen metinleri toplamda ~1000 sözcüğün altındaysa (test örneklem boyutuna bağımlı hale gelir).
*Beklenen sonuç:* `[0, 1]` aralığında bir puan; olabilirlik oranı olarak raporlamadan önce `CalibratedScorer` ile kalibrasyon yapın.

Koppel & Winter (2014). Sorgulanan belge Q, adayın bilinen belgeleri K ve diğer yazarlardan oluşan sahte yazar havuzu I verildiğinde, yinelemeli olarak:

1. Rastgele bir öznitelik alt uzayı örneklenir.
2. Havuzdan m sahte yazar örneklenir.
3. Q'nun, örneklenen herhangi bir sahte yazardan çok K'ya daha yakın olup olmadığı kontrol edilir.

Kazanan yinemelerin oranı, [0, 1] aralığındaki doğrulama puanıdır.

```python
from bitig.features import MFWExtractor
from bitig.forensic import GeneralImpostors

# Q, K ve sahte yazarların ortak bir sözcük dağarcığı paylaşması için
# birleştirilmiş derlem üzerinde öznitelikler oluşturulur.
fm = MFWExtractor(n=200, scale="zscore", lowercase=True).fit_transform(pooled_corpus)
q_fm      = slice_by_ids(fm, ["questioned"])
known_fm  = slice_by_ids(fm, known_doc_ids)
impostors = slice_by_ids(fm, impostor_doc_ids)

gi = GeneralImpostors(n_iterations=100, feature_subsample_rate=0.5, seed=42)
result = gi.verify(questioned=q_fm, known=known_fm, impostors=impostors)
result.values["score"]       # [0, 1] aralığında
result.values["wins"]        # ham kazanma sayısı
```

### Parametreler

| Parametre | Varsayılan | Açıklama |
|---|---|---|
| `n_iterations` | 100 | Rastgele alt uzay + sahte yazar örnekleme yineleme sayısı |
| `feature_subsample_rate` | 0.5 | Her yinelemede örneklenen öznitelik oranı |
| `impostor_sample_size` | `ceil(sqrt(pool_size))` | Yineleme başına sahte yazar sayısı — büyük havuzların testi önemsizleştirmemesi için alt-doğrusal ölçeklenir |
| `similarity` | `"cosine"` | `"cosine"` (gerçek değerli) veya `"minmax"` (yalnızca negatif olmayan öznitelikler) |
| `aggregate` | `"centroid"` | `"centroid"` (K'nın ortalaması) veya `"nearest"` (en benzer bilinen belge; adaya her yinelemede k şanstan en iyisini verir, bu yüzden puanları aynı yazar yönünde yanlı kılar — aynı ayarda kalibre edin) |
| `seed` | 42 | RNG seed değeri (öznitelik + sahte yazar örnekleme) |

### Berabere durumlar

Berabere durumlar **sahte yazarlar lehine** bozulur (katı `>`). Q, K'ya ve bir sahte yazara eşit derecede yakınsa, yineleme kayıp olarak sayılır — adli açıdan tutucu seçim.

### İki uygulama

`bitig.forensic.GeneralImpostors` (bu sayfa), Q'yu sizin oluşturduğunuz öznitelik matrislerindeki tek tek sahte yazar **belgeleriyle** karşılaştırır. `bitig run` (`kind: verify`) ve Adli Laboratuvar Vakaları tarafından kullanılan `bitig.methods.imposters.GeneralImposters` ise kendi MFW uzayını kurar ve Q'yu yazar **merkezleriyle** karşılaştırır. İkisi de varsayılan olarak her yinelemede `ceil(sqrt(havuz))` sahte yazar örnekler ve [0, 1] aralığında kalibre edilmemiş bir kazanma oranı döndürür — bunu şans düzeyine göre okuyun, asla olabilirlik oranı olarak değil. Puanları farklıdır; bir eşleşme testi, belirsiz olmayan durumlarda aynı sonuca vardıklarını denetler.

## Unmasking

*Şu durumda kullanın:* uzun düz yazı adaylarınız (roman bölümleri, uzun denemeler, blog arşivleri) varsa ve dağılım varsayımına dayanmayan bir doğrulama istiyorsanız — doğruluk düşüş eğrisi bizzat yorumlanabilir bir delil zinciri oluşturur.
*Şu durumda kullanmayın:* belgeleriniz kısa ise (her taraf için <~1500 sözcük) — Unmasking, çapraz doğrulamayı anlamlı biçimde çalıştırmak için yeterli parçaya ihtiyaç duyar.
*Beklenen sonuç:* eleme turları boyunca bir doğruluk eğrisi; aynı yazara ait çiftler dik düşüş gösterir, farklı yazara ait çiftler rastgele düzeyde veya üzerinde kalır.

Koppel & Schler (2004). Dağılım varsayımına dayanmayan, uzun metin doğrulama yöntemi. Q ve K, sözcük pencereleri halinde parçalanır; ardından yinelemeli olarak:

1. Q parçalarını K parçalarından ayırt etmek için ikili sınıflandırıcı eğitilir.
2. CV doğruluğu ölçülür.
3. **Q için en ayrıştırıcı** ve **K için en ayrıştırıcı** üst-N öznitelik kaldırılır (Koppel & Schler'e göre tur başına 2 × N).
4. Tekrarlanır.

Aynı yazara ait belgeler stilistik olarak benzerdir: birkaç yüzeysel fark kaldırıldığında sınıflandırıcı hızla çöker (büyük düşüş). Farklı yazara ait belgeler ayrıştırıcı öznitelik vermeyi sürdürür, bu nedenle doğruluk yüksek kalır (küçük düşüş).

```python
from bitig.features import MFWExtractor
from bitig.forensic import Unmasking

unmasking = Unmasking(chunk_size=500, n_rounds=10, n_eliminate=3, seed=42)
result = unmasking.verify(
    questioned=questioned_text,            # str, Document veya Corpus
    known=known_text,
    extractor=MFWExtractor(n=200, scale="zscore", lowercase=True),
)
result.values["accuracy_curve"]    # list[float], uzunluk n_rounds
result.values["accuracy_drop"]     # skaler özet (curve[0] - curve[-1])
result.values["eliminated_per_round"]   # denetlenebilir tur başına öznitelik kaldırma
```

### Hangisi seçilmeli

| Durum | Seçim |
|---|---|
| Kısa CMC / tehdit metinleri (toplam < ~2000 sözcük) | `GeneralImpostors`. Unmasking, CV'yi anlamlı biçimde çalıştırmak için her tarafta daha fazla metne ihtiyaç duyar. |
| Uzun düz yazı (roman, deneme, blog arşivi) | `Unmasking` — doğruluk düşüş eğrisi doğrudan yorumlanabilir. İkinci görüş olarak GI ile birleştirin. |
| Kanıtsal rapor oluşturma | Her ikisini çalıştırın ve her ikisini `CalibratedScorer` ile kalibre edin. İki yöntem arasındaki uyum, başlı başına kanıtsal sinyaldir (Juola tarzı çok yöntemli karar). |

## Referans

::: bitig.forensic.verify.GeneralImpostors
    options:
      show_root_full_path: false

::: bitig.forensic.unmasking.Unmasking
    options:
      show_root_full_path: false
