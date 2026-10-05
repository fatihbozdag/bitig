# Yöntem seçimi

Hangi bitig yönteminin sorunuza uyacağından emin değil misiniz? Bu sayfa en yaygın
durumlar için *"X'i yapmak istiyorum — hangisini kullanmalıyım?"* sorusunu yanıtlar.
Yöntem adları tam ayrıntı için [Yöntemler](methods.md) ve
[Adli araç seti](../forensic/index.md) sayfalarındaki birincil girdilere bağlanır.

## Yazar tespiti, karşılaştırma, keşif

| Amaç | Gerekli veri | Yöntem | Öne çıkan ölçüt | Öğretici |
|---|---|---|---|---|
| 1 sorgulanan belgeyi N aday yazar arasından tespit etmek | Her aday için ~2k+ sözcük bilinen metin; 1 sorgulanan belge | [`CosineDelta`](methods.md#cosinedelta) (sağlam varsayılan) veya [`BurrowsDelta`](methods.md#burrowsdelta) (klasik) | en yakın yazar sıralaması | [Federalist](../tutorials/federalist.md) |
| Bilinmeyen bir derlemi biçemsel benzerlikle kümelemek | 20+ belge, etiketler isteğe bağlı | [`PCAReducer`](methods.md#pcareducer) + [`KMeansCluster`](methods.md#kmeanscluster) veya [`HDBSCANCluster`](methods.md#hdbscancluster) | silhouette, görsel inceleme | — |
| Önceden tanımlı iki yazar grubunu karşılaştırmak | Her grup için 10+ belge | [`ZetaClassic`](methods.md#zetaclassic) veya [`ZetaEder`](methods.md#zetaeder) | sözcük başına ayırt edicilik skoru | — |
| Belgeleri makine öğrenmesiyle sınıflandırmak | Her sınıf için 20+ belge | [`build_classifier`](methods.md#snflandrma-capraz-dogrulama) + [`cross_validate_bitig`](methods.md#snflandrma-capraz-dogrulama) | CV doğruluğu / F1 | — |
| Görselleştirme için öznitelikleri boyut indirgemek | herhangi bir `FeatureMatrix` | [`PCAReducer`](methods.md#pcareducer) / [`UMAPReducer`](methods.md#umapreducer) / [`TSNEReducer`](methods.md#tsnereducer) / [`MDSReducer`](methods.md#mdsreducer) | görsel inceleme | — |
| Bayes yaklaşımıyla N aday arasında yazar tespiti | ham sayımlar olarak N aday × ≥1k sözcük (`MFWExtractor(scale="none")`); 1 sorgulanan belge | [`BayesianAuthorshipAttributor`](methods.md#bayesianauthorshipattributor) | aday başına sonsal olasılık | — |
| MFW bantları üzerinde bootstrap konsensüs ağacı | 10+ belge, birden fazla MFW bandı | [`BootstrapConsensus`](methods.md#bootstrapconsensus) | klad desteği ile Newick ağacı | — |

## Adli — tek-olgu doğrulama

| Amaç | Gerekli veri | Yöntem | Öne çıkan ölçüt | Öğretici |
|---|---|---|---|---|
| 1 sorgulanan belge ile 1 aday arasında "aynı yazar mı?" sorusunu doğrulamak | 1 adayın bilinen yazıları + bir sahte-aday havuzu (~100 belge) | [`GeneralImpostors`](../forensic/verification.md#general-impostors) | doğrulama puanı (yalnızca [`CalibratedScorer`](../forensic/calibration.md#calibratedscorer) sonrasında bir log-LR) | [PAN-CLEF](../tutorials/pan-clef.md) |
| Konudan bağımsız aynı-yazar doğrulaması | uzun düzyazı Q + K + sahte-aday havuzu | [`Unmasking`](../forensic/verification.md#unmasking) | doğruluk düşüş eğrisi | [PAN-CLEF](../tutorials/pan-clef.md) |
| Doğrulamada konu yanlılığını azaltmak | herhangi bir derlem | [`CategorizedCharNgramExtractor`](features.md#categorizedcharngramextractor), `categories=("prefix","suffix","punct")`; veya [`distort_corpus(mode="dv_ma")`](features.md#distort_corpus) | yukarı akışlı doğrulayıcıyla aynı | [PAN-CLEF](../tutorials/pan-clef.md) |
| Ham doğrulayıcı skorlarını kanıtsal olabilirlik oranına dönüştürmek | etiketli geliştirme denemelerinde doğrulayıcı çıktıları | [`CalibratedScorer`](../forensic/calibration.md#calibratedscorer) + [`compute_pan_report`](../forensic/evaluation.md#compute_pan_report) | log-LR, `C_llr`, `ECE` | [PAN-CLEF](../tutorials/pan-clef.md) |
| LR çerçeveli adli rapor üretmek | delil zinciri alanlarıyla birlikte `Result` | [`build_forensic_report`](../forensic/reporting.md) | iki yönlü ENFSI sözel ölçeği | — |

## Bu sayfa nasıl okunur

- **"Gerekli veri"** bir asgaridir — daha fazlası her zaman daha iyidir.
- **"Öne çıkan ölçüt"** yazımda alıntılamanız gereken çıktıdır, yöntemin ürettiği tek
  çıktı değildir.
- Aynı görev için iki yöntem listelendiğinde ilki önerilen varsayılandır; ikincisi
  değerlendirmeye değer yayımlanmış bir alternatiftir.

## Sonraki

- [Yöntemler](methods.md) — yöntem başına gloss + ayrıntı içeren tam katalog.
- [Öznitelikler](features.md) — öznitelik çıkarıcı başına gloss + ayrıntı içeren katalog.
- [Adli araç seti](../forensic/index.md) — kalibrasyon, değerlendirme, raporlama.
