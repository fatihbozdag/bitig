# Öğretici: Federalist Papers

Mosteller & Wallace'ın (1964) 85 Federalist Papers üzerindeki klasik yazar tespiti
çalışmasının yeniden üretimi.

## Arka plan

Federalist Papers (1787–1788), ABD Anayasası'nın onaylanması için *Publius* takma adıyla
yayımlandı. 73 makalenin yazarlığı bilinmektedir (Hamilton, Madison, Jay); 12 makale Hamilton
ile Madison arasında tartışmalıdır. Mosteller & Wallace (1964), sözcük sıklığı Bayesian çıkarımını
kullanarak tartışmalı 12 makaleyi Madison'a atadı — bu sonuç sonraki tüm stilometrik analizlerle
doğrulandı.

Bu öğretici, bitig'yı kullanarak çalışmanın özünü yeniden üretir: bilinen Hamilton / Madison
makaleleri üzerinde Burrows Delta eğitimi, tartışmalı makalelerin öğrenilen uzaya yansıtılması
ve PCA ile Ward dendrogramı aracılığıyla ayrışımın görselleştirilmesi.

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

`metadata.tsv`'de her makale için şu sütunlar bulunur: `filename`, `author`, `number`, `role`
(bilinen-yazarlı makaleler için `train`, tartışmalı olanlar için `test`).

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

`filter: role: [train]` satırı, eğitim sırasında tartışmalı makaleleri gizler; böylece Delta
temiz bir Hamilton / Madison merkezi elde eder. Tartışmalı kümeyi analiz adımında geri yansıtırız.

## 4. Çalışmayı çalıştırın

```bash
bitig run study.yaml --name demo
```

`results/demo/` altında yöntem başına dizinler beklenir:

```
results/demo/
├── resolved_config.json
├── burrows/
│   └── result.json
├── pca/
│   └── result.json
├── ward/
│   └── result.json
└── zeta_hamilton_madison/
    ├── result.json
    ├── table_0.parquet     # Hamilton'ın tercih ettiği sözcük dağarcığı
    └── table_1.parquet     # Madison'ın tercih ettiği sözcük dağarcığı
```

## 5. Şekilleri oluşturun

Matplotlib oluşturma, ince bir son işlem adımıdır (tam entegrasyon sonraki bir aşamada gelir).
Örnek, çağırabileceğiniz bir `render_figures.py` içerir:

```bash
python examples/federalist/render_figures.py results/demo metadata.tsv
```

Bu komut her yöntem dizinine `pca.png`, `ward.png` ve `zeta.png` üretir.

## 6. Rapor

```bash
bitig report results/demo --output results/demo/report.html
```

HTML'yi tarayıcıda açın — yöntem bölümleri, gömülü şekiller ve tam köken bilgisi JSON'u içeren
tek sayfalık bir rapor elde edersiniz.

## Beklenen sonuç

PCA'da Hamilton ve Madison makaleleri ilk iki bileşen boyunca iki sıkı küme oluşturur
(birlikte ~%35 varyans); Jay'in beş denemesi kenarda yer alır. MFW=200'de Burrows Delta,
tartışmalı her makaleyi Madison'a atfeder — Mosteller & Wallace'ın 1964 sonucuyla örtüşür.

Bu öğreticinin hızlı başlangıç mini sürümü önce yalnızca 9 makale üzerinde işlem hattını
çalıştırmak isteyenler için
[`examples/quickstart/`](https://github.com/fatihbozdag/bitig/tree/main/examples/quickstart)
adresindedir.
