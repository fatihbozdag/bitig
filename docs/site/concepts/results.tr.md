# Sonuçlar ve köken bilgisi

Her yöntem, bitig genelinde ortak dönüş türü olan bir `Result` döndürür.

## Result

```python
@dataclass
class Result:
    method_name: str
    params: dict[str, Any]
    values: dict[str, Any]          # JSON-safe (ndarray {"__ndarray__": ...} olarak kodlanır)
    tables: list[pd.DataFrame]      # parquet olarak dışa aktarılır
    figures: list[Any]              # matplotlib figürleri veya ham baytlar
    provenance: Provenance | None
```

### Kalıcılık

```python
result.save("results/demo/pca")   # result.json + table_*.parquet yazar
```

`result.save(directory)` şunları yazar:

- `result.json` — `method_name`, `params`, `values` (numpy kodlanmış), `provenance`
- `table_0.parquet`, `table_1.parquet`, … — `tables` içindeki her DataFrame için birer dosya
- Figür yazılmaz: `Result.save` bunları görselleştirme katmanına bırakır. `bitig run`,
  uygun olduğu yerde her yöntem için varsayılan bir figür üretir (örneğin indirgeyiciler için
  `scatter.png`, hiyerarşik kümeleme için `dendrogram.png`, Zeta için `zeta.png`)

`Result.from_json("results/demo/pca/result.json")` ile gidiş-dönüş sağlanır.

## Köken bilgisi

Her Result'ın `.provenance` alanı tam yeniden üretilebilirlik zarfını taşır:

```python
@dataclass
class Provenance:
    bitig_version: str
    python_version: str
    spacy_model: str
    spacy_version: str
    corpus_hash: str
    feature_hash: str | None
    seed: int
    timestamp: datetime
    resolved_config: dict[str, Any]
    # Adli dilbilim (tümü isteğe bağlı):
    questioned_description: str | None
    known_description: str | None
    hypothesis_pair: str | None
    acquisition_notes: str | None
    custody_notes: str | None
    source_hashes: dict[str, str]
    corpus_hash_scheme: int         # güncel derlem özetleri için 2
    library_versions: dict[str, str]
```

`Provenance.current(...)` çalışma zamanı ve girdilerinizden bir kayıt oluşturur.
`Provenance.from_dict(...)` kaydedilmiş bir `result.json`'dan gidiş-dönüş sağlar.

### Yeniden üretilebilirlik sözleşmesi

Aynı seed değeriyle, aynı ortamda (`library_versions` alanının kaydettiği Python, numpy, scikit-learn sürümleri) aynı corpus üzerinde aynı `study.yaml`'ın iki ayrı çalıştırılması **özdeş sonuç değerleri** üretir; tek istisna, çok iş parçacıklı BLAS'ın değiştirebildiği son basamaklardaki kayan nokta yuvarlamasıdır. `result.json` bayt düzeyinde özdeş değildir: `provenance.timestamp` her çalıştırmanın zamanını kaydeder. Çalıştırıcı, bir yöntem kendi değerini belirtmedikçe `cfg.seed` değerini şunlara iletir:

- her indirgeyicinin (PCA, MDS, t-SNE, UMAP) ve k-means'in `random_state` parametresi
- her `classify` tahmincisinin `random_state` parametresi ve Stratified K-Fold karıştırması
- `consensus` ve `verify` (General Impostors) yöntemlerinin `seed` parametresi

Hiyerarşik kümeleme, HDBSCAN ve Delta deterministiktir. Kayan nokta yuvarlamasının ötesindeki belirleyici olmayan bir durum hata sayılır — lütfen bildirin.

## Çok yöntemli çalıştırmaları yükleme

`bitig run study.yaml`, şu dizin yapısını üretir:

```
results/demo/
├── resolved_config.json
├── burrows/
│   └── result.json
├── pca/
│   ├── result.json
│   ├── scatter.png         # varsayılan figür
│   └── pca_biplot.png
└── zeta/
    ├── result.json
    ├── table_0.parquet
    ├── table_1.parquet
    └── zeta.png
```

Başarısız olan bir yöntem, kendi dizinine hata izini içeren bir `error.txt` bırakır ve
`bitig run` bu durumda 1 koduyla çıkar. Önceki bir çalıştırmayı barındıran dizin,
`--overwrite` verilmedikçe reddedilir.

`build_report(results/demo, output="report.html")`, dizin altındaki her `result.json`'ı yükler ve tek bir HTML raporu oluşturur.

## Sonraki adım

- [Adli dilbilim araç takımı](../forensic/index.md) — Provenance'ın adli dilbilim alanlarının devreye girdiği yer.
