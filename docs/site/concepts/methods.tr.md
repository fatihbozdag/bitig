# Yöntemler

Yöntemler, bir `FeatureMatrix`'i `Result`'a dönüştürür. Her yöntem, anlamlı olduğu yerde `sklearn` uyumludur (`fit`, `predict`, `fit_transform`).

## Yazar tespiti — Delta varyantları

Tüm Delta varyantları `_DeltaBase`'i paylaşır, z-puanlı öznitelikler üzerinde çalışır ve en yakın-merkez sınıflandırıcı üretir.

| Sınıf | Uzaklık | Referans |
|---|---|---|
| `BurrowsDelta` | ortalama mutlak L1 | Burrows 2002 |
| `ArgamonLinearDelta` | L2 (Öklid) | Argamon 2008 |
| `QuadraticDelta` | karesel L2 | — |
| `CosineDelta` | 1 − kosinüs benzerliği | Smith & Aldridge 2011 |
| `EderDelta` / `EderSimpleDelta` | ağırlıklı Delta varyantları | Eder 2015 |

```python
from bitig import MFWExtractor, BurrowsDelta
fm = MFWExtractor(n=200, scale="zscore", lowercase=True).fit_transform(corpus)
y = np.array(corpus.metadata_column("author"))
clf = BurrowsDelta().fit(fm, y)
predictions = clf.predict(fm)       # en yakın-merkez etiketleri
probs = clf.predict_proba(fm)       # negatif uzaklıklar üzerinde softmax
```

### BurrowsDelta
`BurrowsDelta()`

*Şu durumda kullanın:* 2 veya daha fazla aday yazar varsa ve her birinden ~2000+ sözcüklük bilinen yazı mevcutsa; hangi yazarın sorgulandığı metni büyük olasılıkla yazdığını sıralamak istiyorsanız.
*Şu durumda kullanmayın:* yalnızca tek aday yazarınız varsa (`GeneralImpostors` doğrulamasını kullanın) ya da metinler ~500 sözcükten kısa olduğunda (sinyal gürültülü hale gelir).
*Beklenen sonuç:* aday başına bir uzaklık skoru; en düşük uzaklık tahmin edilen yazardır.

Klasik Burrows (2002) yöntemi: öznitelikleri z-puanlama, her adayın merkezine ortalama mutlak fark (L1) uzaklığı. Edebi İngilizce için iyi bir varsayılan seçim.

### CosineDelta
`CosineDelta()`

*Şu durumda kullanın:* Delta ailesine dayalı yazar tespiti için modern bir varsayılan istiyorsanız — kosinüs, belge uzunluğu farklılıklarına karşı dayanıklıdır ve L1'e kıyasla aykırı sözcüklere daha az duyarlıdır.
*Şu durumda kullanmayın:* derlem farklı türleri dikkat gözetilmeksizin harmanlıyorsa; konu, biçemi baskıladığında kosinüs daha az tanımlayıcı olur.
*Beklenen sonuç:* aday başına `[0, 2]` aralığında bir uzaklık skoru; en düşük uzaklık kazanır.

Smith & Aldridge (2011). Modern stilometride standart seçim; ayar yapmadan önce genellikle en iyi tek yöntem temelidir.

### EderDelta / EderSimpleDelta
`EderDelta()`, `EderSimpleDelta()`

*Şu durumda kullanın:* en sık sözcükler (MFW) kuyruğundaki gürültülü düşük frekanslı sözcükleri bastırmak istiyorsanız — Eder'in ağırlıklandırması, daha az sık geçen özniteliklerin katkısını cezalandırır.
*Şu durumda kullanmayın:* MFW listeniz zaten kısaysa (n < 100); aşağı ağırlıklandırılacak kuyruk bulunmaz.
*Beklenen sonuç:* Burrows Delta ile aynı biçim; kuyruk MFW katkıları aksi takdirde baskın olacağında farklı sıralama.

Eder (2015). İki varyant: `EderDelta` açık öznitelik başına ağırlıklarla, `EderSimpleDelta` basitleştirilmiş bir şemayla.

### ArgamonLinearDelta
`ArgamonLinearDelta()`

*Şu durumda kullanın:* L1 yerine özellikle Öklid (L2) uzaklığı istiyorsanız — z-puanlamasından sonra öznitelikler yaklaşık Gaussian dağılımlı olduğunda uygundur.
*Şu durumda kullanmayın:* MFW dağılımı aykırı değer üretecek kadar çarpıksa; L2, aykırı değerleri ikinci dereceden cezalandırır. `CosineDelta` veya `BurrowsDelta` tercih edin.
*Beklenen sonuç:* aday başına bir uzaklık skoru; diğer Delta varyantlarıyla aynı sıralama biçimi, büyük öznitelik sapmalarına farklı duyarlılık.

Argamon (2008). Gaussian üretici model altında Delta'nın olasılıksal yorumu.

### QuadraticDelta
`QuadraticDelta()`

*Şu durumda kullanın:* karesel L2 uzaklığı kullanan deneyleri yeniden üretmek istiyorsanız — karekök olmaksızın Argamon Delta'ya eşdeğerdir.
*Şu durumda kullanmayın:* aşağı akış birleştirme için kalibre edilmiş bir uzaklığa ihtiyaç duyuyorsanız; karesel uzaklıklar gerçek bir metrik değildir.
*Beklenen sonuç:* aday başına bir uzaklık skoru; Argamon Linear Delta ile monoton, dolayısıyla sıralama aynıdır.

## Karşıtlık — Zeta

Craig'in Zeta'sı (`ZetaClassic`) ve Eder'in yumuşatılmış varyantı (`ZetaEder`), bir yazar grubunun diğerine kıyasla en çok tercih ettiği sözcük dağarcığını çıkarır.

```python
from bitig.methods.zeta import ZetaClassic
result = ZetaClassic(group_by="author", top_k=50, group_a="Hamilton", group_b="Madison").fit_transform(corpus)
df_a, df_b = result.tables   # oranlarla birlikte en yüksek k A-tercihli / B-tercihli sözcükler
```

### ZetaClassic
`ZetaClassic(group_by=..., top_k=..., group_a=..., group_b=...)`

*Şu durumda kullanın:* iki önceden tanımlanmış yazar grubunuz (veya yazarınız) varsa ve her grubun diğerine kıyasla hangi sözcükleri tercih ettiğini öğrenmek istiyorsanız — Craig'in klasik Zeta'sı.
*Şu durumda kullanmayın:* yalnızca bilinmeyen bir belgeyi adaylara karşı sıralamak istiyorsanız (bunun yerine Delta kullanın) ya da gruplarınız çok küçükse (her grupta <10 belge).
*Beklenen sonuç:* en yüksek k sözcüklük iki tablo; her sözcüğün A'daki ve B'deki oranı; büyük farklar belirleyici sözcük dağarcığıdır.

### ZetaEder
`ZetaEder(group_by=..., top_k=..., group_a=..., group_b=...)`

*Şu durumda kullanın:* Eder (2017) yumuşatması ile Zeta istiyorsanız — çok nadir veya çok yaygın sözcükleri klasik versiyona kıyasla daha zarif biçimde ele alır.
*Şu durumda kullanmayın:* Burrows/Craig dönemi sonuçlarını karşılaştırma amacıyla yeniden üretiyorsanız; tarihsel eşlik için `ZetaClassic` kullanın.
*Beklenen sonuç:* `ZetaClassic` ile aynı çıktı biçimi; kuyruklara yakın daha düzgün sıralama.

## Boyut indirgeme

Tüm indirgeyiciler bir `FeatureMatrix` kabul eder ve 2 boyutlu / n boyutlu koordinatları içeren bir `Result` döndürür.

### PCAReducer
`PCAReducer(n_components=2)`

*Şu durumda kullanın:* eksenlerin dik varyans yönleri olduğu hızlı, yorumlanabilir bir 2 veya 3 boyutlu projeksiyon istiyorsanız. "Dermemi görselleştir" soruları için varsayılan seçim.
*Şu durumda kullanmayın:* yazar farklılıkları son derece doğrusal değilse; PCA'nın doğrusal eksenleri kavisli manifoldları kaçırır.
*Beklenen sonuç:* `coords` (n_docs × n_components) + bileşen başına `explained_variance_ratio_`.

### UMAPReducer
`UMAPReducer(n_components=2, n_neighbors=15, min_dist=0.1)`

*Şu durumda kullanın:* hem yerel *hem de* küresel yapıyı koruyan doğrusal olmayan bir projeksiyon istiyorsanız — genellikle stilometrik özniteliklerin en iyi görünen 2 boyutlu görselleştirmesi.
*Şu durumda kullanmayın:* bir tohum sabitlemeden yeniden üretilebilirliğe ihtiyaç duyuyorsanız — UMAP stokastiktir. Her zaman `random_state` ayarlayın.
*Beklenen sonuç:* `coords` (n_docs × n_components). `bitig[viz]` gerektirir.

### TSNEReducer
`TSNEReducer(n_components=2, perplexity=30)`

*Şu durumda kullanın:* yerel komşuluk yapısını vurgulayan doğrusal olmayan bir projeksiyon istiyorsanız — yazarlar sıkı kümelenir.
*Şu durumda kullanmayın:* kümeler arası uzaklıkların anlamlı olması gerekiyorsa (t-SNE bunları bozar) ya da koordinatları aşağı akış yöntemi için öznitelik olarak kullanmayı planlıyorsanız.
*Beklenen sonuç:* `coords` (n_docs × n_components). Tohum olmadan belirleyici değildir.

### MDSReducer
`MDSReducer(n_components=2, metric=True)`

*Şu durumda kullanın:* çiftler arası Delta uzaklıklarını olabildiğince gerçeğe yakın korumaya çalışan bir projeksiyon istiyorsanız — dendrogram + dağılım grafiğini birlikte yorumlamak için uygundur.
*Şu durumda kullanmayın:* büyük bir derlem (>500 belge) varsa; MDS kötü ölçeklenir.
*Beklenen sonuç:* `coords` (n_docs × n_components) + `stress` (düşükse daha iyi uyum).

## Kümeleme

Kümeleyiciler bir `FeatureMatrix` kabul eder ve küme etiketleri üretir; hiyerarşik kümeleme ayrıca dendrogramlar için bağlantı matrisini döndürür.

### HierarchicalCluster
`HierarchicalCluster(linkage="ward")`

*Şu durumda kullanın:* yaprakların belgeler, dal yüksekliklerinin uzaklıklar olduğu bir dendrogram — stilometrinin kanonik görselleştirmesi — istiyorsanız.
*Şu durumda kullanmayın:* derlem dendrogram incelemesinin artık pratik olmayacağı kadar büyükse (>2000 belge).
*Beklenen sonuç:* `labels` (n_docs,) + `scipy.cluster.hierarchy.dendrogram` ile kullanılabilir `linkage_matrix`.

Desteklenen bağlantılar: `"ward"` (varsayılan, varyansı en aza indiren), `"average"`, `"complete"`, `"single"`.

### KMeansCluster
`KMeansCluster(n_clusters=3, seed=42)`

*Şu durumda kullanın:* tahmini bir küme sayınız varsa ve benzer boyutlu küresel kümeler istiyorsanız — en hızlı kümeleme seçeneği.
*Şu durumda kullanmayın:* küme boyutları çok eşitsizse, küme şekilleri uzunsa veya `n_clusters`'ı önceden bilmiyorsanız (`HDBSCANCluster` kullanın).
*Beklenen sonuç:* `labels` (n_docs,) + küme merkezleri.

### HDBSCANCluster
`HDBSCANCluster(min_cluster_size=5)`

*Şu durumda kullanın:* küme sayısını önceden bilmiyorsanız, değişken küme yoğunluğu bekliyorsanız veya "gürültü" noktalarının aykırı değer (-1) olarak etiketlenmesini istiyorsanız.
*Şu durumda kullanmayın:* derlem küçükse (<30 belge); HDBSCAN'ın yoğunluk tahminleri kararsız hale gelir.
*Beklenen sonuç:* gürültü için -1 içeren `labels` (n_docs,); `probabilities` (küme üyelik güveni).

## Konsensüs ağaçları

### BootstrapConsensus
`BootstrapConsensus(mfw_bands=[100, 200, 300], replicates=20)`

*Şu durumda kullanın:* dendrogram için sağlamlık kanıtı istiyorsanız — MFW öznitelik kümesini tekrar tekrar yeniden örnekleyin ve hangi kladların hayatta kaldığını görün.
*Şu durumda kullanmayın:* hızlı tek bir görselleştirmeye ihtiyaç duyuyorsanız; bootstrap birçok Delta + kümeleme döngüsü çalıştırır ve yavaştır.
*Beklenen sonuç:* klade destek değerleriyle Newick formatında konsensüs ağacı. Her tekrar belgeleri de alt örnekler (`subsample`, varsayılan 0.8); bu nedenle bir kladın desteği, **tüm üyelerini içeren** ağaçlar arasında o kladın klade olarak göründüğü ağaçların oranıdır. Desteği `support_threshold` değerinden (varsayılan 0.5, çoğunluk kuralı) kesinlikle büyük olan kladlar ağacı oluşturur.

Eder (2017) MFW bantları üzerinde önyükleme yapar; bitig ayrıca belgeleri de alt örnekler, Eder'in yöntemi bunu yapmaz.

## Sınıflandırma + çapraz doğrulama

Herhangi bir sklearn sınıflandırıcı (Lojistik Regresyon, lineer / RBF SVM, Random Forest, HistGBM) `build_classifier(name)` ile, ayrıca üç stilometri odaklı çapraz doğrulama stratejisiyle `cross_validate_bitig(fm, y, cv_kind=...)`:

*Şu durumda kullanın:* etiketli belgeleriniz (yazar veya grup) varsa ve yazar kimliğini katlara sızdırmayan stilometri odaklı çapraz doğrulama ile standart makine öğrenmesi performans ölçütleri — doğruluk, F1, karışıklık matrisleri — istiyorsanız.
*Şu durumda kullanmayın:* sınıf başına ~20'den az belgeniz varsa; çapraz doğrulama istatistiksel olarak anlamsız hale gelir. Ayrıca tek vaka doğrulaması için kullanmayın (`GeneralImpostors` kullanın).
*Beklenen sonuç:* kat başına tahminler, ortalama doğruluk / makro F1 ve aşağı akış grafikleri için kat düzeyinde `Result` nesneleri.

- `stratified` — StratifiedKFold; `seed` karıştırmayı denetler
- `loao` — hedef olmayan bir sütun (ör. konu ya da kaynak) olan `groups_from` üzerinde LeaveOneGroupOut. Hedefin kendisine (ya da onun bire bir yeniden etiketlenmesine) göre gruplamak, görülmemiş sınıfları dışarıda bırakır ve reddedilir. `cross_validate_bitig(clf, None, y, extractor=..., corpus=...)`, öznitelik çıkarıcıyı her eğitim katmanında yeniden uydurur; böylece dışarıda tutulan belgeler sözcük dağarcığını ya da z-puanlarını etkilemez.
- `leave_one_text_out` — LeaveOneOut

## Bayesian

### BayesianAuthorshipAttributor
`BayesianAuthorshipAttributor()`

*Şu durumda kullanın:* N aday yazar üzerinde ilkeli Dirichlet düzleştirmesiyle posteriyor olasılıkları istiyorsanız — Wallace–Mosteller Federalist yaklaşımı.
*Şu durumda kullanmayın:* öznitelikleriniz z-puanlıysa (ham sayımlar bekler; `MFWExtractor(scale="none")` kullanın).
*Beklenen sonuç:* `predict_proba`, belge başına adaylar üzerinde posteriyor olasılık vektörleri döndürür. `bitig[bayesian]` gerekmez — bu varyant saf NumPy'dır.

### HierarchicalGroupComparison
`HierarchicalGroupComparison(group_a=..., group_b=..., feature_name=...)`

*Şu durumda kullanın:* iki yazar popülasyonunun stilistik bir öznitelik açısından sistematik biçimde farklılaşıp farklılaşmadığını tam yazar başına belirsizlikle sınamak istiyorsanız — PyMC değişken-kesişim modeli.
*Şu durumda kullanmayın:* grup başına yalnızca bir yazarınız varsa (havuzlama sinyali yok) ya da hızlı bir tarama yöntemine ihtiyaç duyuyorsanız (MCMC örneklemesi yavaştır; önce frekansçı Zeta kullanın).
*Beklenen sonuç:* grup farkı parametresi için posteriyor çekimleri içeren arviz `InferenceData`. `bitig[bayesian]` gerektirir.

## Adli dilbilim yöntemleri

`bitig.forensic` altında:

*Şu durumda kullanın:* bitig'nın tek vaka doğrulamasını veya kalibrasyon katmanını kullanmak istiyorsanız — yöntem başına ayrıntılı açıklamalar için özel [Adli dilbilim araç takımı](../forensic/index.md) sayfalarına bakın.
*Şu durumda kullanmayın:* kapalı bir aday kümeniz varsa ve yalnızca yazar tespiti istiyorsanız — yukarıdaki Delta varyantlarını kullanın.
*Beklenen sonuç:* sınıflandırıcı doğruluğu değil, kalibre edilmiş log-OO + kanıt meta verisi döndüren puanlayıcılar.

| Yöntem | Görev | Referans |
|---|---|---|
| `GeneralImpostors` | tek sınıflı yazar doğrulama | Koppel & Winter 2014 |
| `Unmasking` | uzun metin doğrulama (doğruluk-bozunma eğrisi) | Koppel & Schler 2004 |
| `CalibratedScorer` | herhangi bir puanlayıcının Platt / izotonik kalibrasyonu | Platt 1999; Niculescu-Mizil & Caruana 2005 |

Bkz. [Adli dilbilim araç takımı](../forensic/index.md).

## Sonraki adım

- [Sonuçlar ve köken bilgisi](results.md) — her yöntemin döndürdüğü değer.
