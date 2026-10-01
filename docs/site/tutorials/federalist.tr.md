# Öğretici: Federalist Papers

Mosteller & Wallace'ın (1964) 85 Federalist Papers üzerindeki klasik yazar tespiti
çalışmasının yeniden üretimi.

## Arka plan

Federalist Papers (1787–1788), ABD Anayasası'nın onaylanması için *Publius* takma adıyla
yayımlandı. 73 makalenin yazarlığı bilinmektedir (Hamilton, Madison, Jay); geri kalanlar ya ortak
çalışmadır ya da Hamilton ile Madison arasında tartışmalıdır. Mosteller & Wallace (1964), sözcük
sıklığı Bayesian çıkarımını kullanarak tartışmalı makaleleri Madison'a atadı — sonraki stilometrik
çalışmalar bu sonucu genel olarak desteklemiştir.

Literatür genellikle 12 tartışmalı makale sayar (49–58, 62, 63). bitig ile gelen derlem 58 numaralı
makaleyi Madison olarak etiketler; bu nedenle derlemde **11 tartışmalı makale** (49–57, 62, 63) ve
3 ortak Hamilton–Madison makalesi (18–20) bulunur.

Bu öğretici, bitig'yı kullanarak çalışmanın özünü iki adımda yeniden üretir:

1. 71 tek yazarlı makaleyi Burrows Delta, PCA, Ward dendrogramı ve Craig's Zeta ile inceleyen
   bildirimsel bir `study.yaml`. Tartışmalı makaleler bu adımın dışında tutulur: PCA'ya
   yansıtılmazlar ve şekillerinde görünmezler.
2. Bilinen makaleler üzerinde eğitip her tartışmalı makaleyi bir adaya atayan ayrı bir yazar
   tespiti adımı (`--test-filter` ile `bitig delta` / `bitig bayesian`).

## Ne oluşturacaksınız

Sonunda şunlara sahip olacaksınız:

- 85 Federalist Paper aktarılmış bir proje iskeleti.
- Dört analiz tanımlayan bir `study.yaml`: Burrows Delta, PCA, Ward kümeleme, Hamilton ile
  Madison arasında Craig's Zeta karşıtlığı.
- Yöntem başına `Result` JSON'ları ve oluşturulmuş şekilleri içeren bir `results/demo/` dizini.
- Her şeyi bir araya getiren tek bir HTML raporu.

## 1. Projeyi başlatın

```bash
bitig init federalist
cd federalist
```

Bu komut, boş bir `corpus/` ve başlangıç `study.yaml` içeren bir proje dizini oluşturur.

## 2. Makaleleri ekleyin

Deponun [`examples/federalist/`](https://github.com/fatihbozdag/bitig/tree/main/examples/federalist)
dizininde 85 makalenin tamamı ayrı `.txt` dosyaları olarak ve hazır bir `metadata.tsv` ile
mevcuttur. `corpus/` ile `metadata.tsv` dosyalarını kopyalayın ya da örnekteki kendi
`README.md` dosyasını takip ederek Project Gutenberg'den oluşturun.

`metadata.tsv`'de her makale için şu sütunlar bulunur: `filename`, `author`, `role`, `notes`.
`role`, 71 tek yazarlı makale için `train`, 11 tartışmalı makale için `test` (`author` =
`Disputed`) ve 3 ortak makale için `excluded` (`author` = `Joint_HM`) değerini alır. Aşağıdaki
çalışma dosyayı `corpus/metadata.tsv` konumundan okur; bu yüzden onu `corpus/` içine kopyalayın.

## 3. study.yaml dosyasını düzenleyin

```yaml
name: federalist
seed: 42
output:
  dir: results
  timestamp: false

corpus:
  path: corpus
  metadata: corpus/metadata.tsv
  filter:
    role: [train]            # tartışmalı makaleleri eğitimden dışla

features:
  - id: mfw200
    type: mfw
    n: 200
    scale: zscore
    lowercase: true

methods:
  - id: burrows
    kind: delta
    variant: burrows
    features: mfw200
    group_by: author

  - id: pca
    kind: reduce
    features: mfw200
    params: { n_components: 2 }

  - id: ward
    kind: cluster
    features: mfw200
    params: { n_clusters: 3, linkage: ward }

  - id: zeta_hamilton_madison
    kind: zeta
    group_by: author
    params:
      top_k: 50
      group_a: Hamilton
      group_b: Madison
```

`filter: role: [train]` satırı, çalışmadaki **her** yöntem için yalnızca 71 tek yazarlı makaleyi
(Hamilton, Madison, Jay) tutar. Tartışmalı ve ortak makaleler hiç yüklenmez; dolayısıyla hiçbir şey
geri yansıtılmaz: Delta burada yalnızca örneklem içi (yeniden ikame) doğruluğunu raporlar, PCA ve
dendrogram da yalnızca yazarı bilinen makaleleri gösterir. Tartışmalı makalelerin yazar tespiti
5. adımdadır.

## 4. Çalışmayı çalıştırın

```bash
bitig run study.yaml --name demo
```

`results/demo/` altında yöntem başına dizinler beklenir:

```
results/demo/
├── resolved_config.json
├── burrows/
│   ├── result.json
│   └── confusion_matrix.png
├── pca/
│   ├── result.json
│   ├── scatter.png
│   └── pca_biplot.png
├── ward/
│   ├── result.json
│   └── dendrogram.png
└── zeta_hamilton_madison/
    ├── result.json
    ├── table_0.parquet     # Hamilton'ın tercih ettiği sözcük dağarcığı
    ├── table_1.parquet     # Madison'ın tercih ettiği sözcük dağarcığı
    └── zeta.png
```

Her `result.json` kendi köken bilgisi bloğunu (derlem özeti, seed, çözümlenmiş yapılandırma)
taşır. Bir yöntem başarısız olursa dizininde bunun yerine bir `error.txt` bulunur ve `bitig run`
1 durum koduyla çıkar.

## 5. Tartışmalı makaleleri atayın

Bildirimsel çalışma henüz bir alt küme üzerinde eğitip başka birini puanlayamaz; bu yüzden yazar
tespiti, `--test-filter` ile `bitig delta` ve `bitig bayesian` komutlarını kullanır:

```bash
bitig delta corpus --method burrows --mfw 200 \
    --metadata corpus/metadata.tsv --group-by author --test-filter role=test

bitig bayesian corpus --mfw 200 \
    --metadata corpus/metadata.tsv --group-by author --test-filter role=test
```

Her iki komut da **`--test-filter` ile seçilmeyen her makale** üzerinde eğitilir: 71 tek yazarlı
makale *ve* Hamilton, Madison ve Jay'in yanında dördüncü bir `Joint_HM` sınıfı oluşturan 3 ortak
makale. Hiçbir komut ortak makaleleri dışarıda bırakamaz; bunun için onları verdiğiniz derlem
dizininden çıkarın.

`bitig bayesian` bir `max p(author)` sütunu yazdırır. Bunlar her sözcük geçişini bağımsız sayan
Naive Bayes sonsal değerleridir; bu nedenle 0'a ya da 1'e itilirler ve **kalibre edilmiş
olasılıklar değildir**. Bunları bir kesinlik ölçüsü olarak değil, adayların sıralaması olarak
okuyun.

## 6. Şekilleri oluşturun

`bitig run` yukarıda listelenen varsayılan şekilleri zaten yazar, ancak PCA dağılım grafiği yazara
göre renklendirilmez. Örnek, PCA dağılım grafiğini yazara göre renklendirerek yeniden çizen, ayrıca
dendrogramı ve Zeta grafiğini üreten bir `render_figures.py` içerir:

```bash
python examples/federalist/render_figures.py results/demo corpus/metadata.tsv
```

Bu komut ilgili yöntem dizinlerine `pca.png`, `ward.png` ve `zeta.png` üretir. Betik örneğin kendi
`study.yaml` dosyası için yazıldığından şekil başlıklarında "MFW=500" yazar.

## 7. Rapor

```bash
bitig report results/demo --output results/demo/report.html
```

HTML'yi tarayıcıda açın — yöntem bölümleri, gömülü şekiller ve bir köken bilgisi bölümü içeren
tek sayfalık bir rapor elde edersiniz.

## Beklenen sonuç

Yukarıdaki adımlar, gelen derlem üzerinde çalıştırıldığında şu sayıları verir:

- **PCA** (71 makale, MFW 200): ilk iki bileşen varyansın %7,5'ini ve %5,9'unu açıklar (toplam
  %13,5). PC1 esas olarak Jay'in beş denemesini diğer tüm makalelerden ayırır. Hamilton ve
  Madison büyük ölçüde örtüşür: Madison makaleleri PC2'de ortalamada daha yukarıda yer alır,
  ancak temiz bir ayrım yoktur. Örneğin kendi MFW 500 çalışmasında iki bileşen %5,6 ve %4,6
  açıklar.
- **Ward** (3 küme): 15 Madison makalesinin tamamı, 11 Hamilton makalesiyle birlikte tek bir
  kümeye düşer. Diğer 40 Hamilton makalesi ikinci bir küme oluşturur; Jay'in makaleleri 3 / 2
  bölünür.
- **Çalışmadaki Burrows Delta**: yeniden ikame doğruluğu 1,0. Bu bir yazar tespiti sonucu değil,
  örneklem içi bir ayrışabilirlik denetimidir.
- **Yazar tespiti (5. adım)**: `bitig delta` (MFW 200) 11 tartışmalı makalenin tamamını
  Madison'a atar. `bitig bayesian` da 11 makalenin hepsi için Madison'ı seçer ve her biri için
  `max p(author)` = 1.000 yazdırır. Yukarıda açıklandığı gibi bu 1.000 kalibre edilmiş bir
  olasılık değildir.

Madison ataması Mosteller & Wallace'ın 1964 sonucuyla örtüşür.

!!! warning "Yazar imzaları metinlerde duruyor"
    Her derlem dosyası Project Gutenberg imza satırını (`HAMILTON`, `MADISON`, `JAY`) korur ve
    tartışmalı makalelerde `MADISON` yazar. Zeta listelerinin başında `hamilton` ve `madison`
    sözcüklerinin yer almasının nedeni budur. MFW 200'de iki ad da öznitelikler arasında
    değildir ve imzaları silmek yazar tespitini değiştirmez. MFW 500'de `hamilton` bir
    özniteliktir. Bu derlem üzerinde kendi deneylerinizi yapmadan önce imzaları çıkarın.

Bu öğreticinin hızlı başlangıç mini sürümü önce yalnızca 9 makale üzerinde işlem hattını
çalıştırmak isteyenler için
[`examples/quickstart/`](https://github.com/fatihbozdag/bitig/tree/main/examples/quickstart)
adresindedir.
