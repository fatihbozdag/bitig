# study.yaml şeması

`bitig run` tarafından tüketilen bildirimsel çalışma yapılandırması. Minimal bir örnek:

```yaml
name: my-study
seed: 42

corpus:
  path: corpus
  metadata: corpus/metadata.tsv

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
```

Dosya iki aşamada doğrulanır. Yükleme aşaması biçimi denetler: her bölüm tanımadığı
anahtarları reddeder, bu nedenle yanlış yazılmış bir üst düzey ya da bölüm anahtarı hata
verir. Ardından `bitig run`, her öznitelik ve yöntem parametresini aktarıldığı kurucuya göre
denetler ve bilinmeyen bir parametre varsa çalışmayı reddeder; böylece bir yazım hatası ya
da eskimiş bir anahtar sessizce yok sayılmak yerine yükleme sırasında hata verir.

!!! note "Kabul edilir ama şu anda kullanılmaz"
    Bazı bölümler şemanın parçasıdır (dolayısıyla bunları içeren bir `study.yaml` yüklenir),
    ancak `bitig run` henüz bunları okumaz: **`viz`**, **`report`**, **`cache`**,
    **`preprocess.spacy`** (`model`, `backend`, `device`, `exclude`) ve
    **`preprocess.normalize`**. Aşağıda işaretlenmişlerdir. Bunları ayarlamanın bir
    çalıştırmaya etkisi yoktur.

## Üst düzey anahtarlar

| Anahtar | Tür | Zorunlu | Açıklama |
|---|---|---|---|
| `name` | str | hayır | Çalışma adı (varsayılan `unnamed-study`); `resolved_config.json` dosyasına kaydedilir |
| `seed` | int | hayır | Varsayılan seed değeri (42). Kendi değerini belirtmeyen her stokastik yönteme iletilir (bkz. [yeniden üretilebilirlik](../concepts/results.md)). |
| `corpus` | object | evet | Derlem yapılandırması (aşağıya bakınız) |
| `preprocess` | object | hayır | Derlem dili; spaCy ve normalleştirme ayarları (aşağıda) |
| `features` | list | hayır | Yöntemlerin başvurduğu öznitelik çıkarıcılar (varsayılan: yok) |
| `methods` | list | hayır | Çalıştırılacak yöntemler (varsayılan: yok) |
| `output` | object | hayır | Çıktı dizini / zaman damgalama |
| `viz` | object | hayır | *Kabul edilir ama şu anda kullanılmaz* |
| `report` | object | hayır | *Kabul edilir ama şu anda kullanılmaz* |
| `cache` | object | hayır | *Kabul edilir ama şu anda kullanılmaz* |

## corpus

```yaml
corpus:
  path: corpus                    # .txt dosyalarının bulunduğu dizin
  metadata: corpus/metadata.tsv   # isteğe bağlı: dosya adı + rastgele alanları içeren TSV
  filter:                         # isteğe bağlı: çalıştırmadan önce derlemi filtrele
    role: [train]
```

| Anahtar | Açıklama |
|---|---|
| `path` | `.txt` dosyalarının bulunduğu dizin (zorunlu). |
| `metadata` | `filename` sütunu ve istenen alanları içeren isteğe bağlı TSV. Verildiğinde her metin dosyasının bir satırı olmalıdır — `study.yaml` içinde bir `strict` anahtarı yoktur. |
| `filter` | Yalnızca üst verisi her anahtarla eşleşen belgeleri tutar: tekil bir değer birebir eşleşme, bir liste ise üyelik anlamına gelir. |

## preprocess

```yaml
preprocess:
  language: en              # en, tr, de, es, fr
```

| Anahtar | Açıklama |
|---|---|
| `language` | Derlem dil kodu (varsayılan `en`; büyük/küçük harf duyarsız). İşlev sözcüğü listelerini, okunabilirlik formüllerini ve benzeri dile özgü kaynakları seçer. |
| `spacy.model`, `spacy.backend` (`spacy` \| `spacy_stanza`), `spacy.device` (`auto` \| `cpu` \| `mps` \| `cuda`), `spacy.exclude` | *Kabul edilir ama şu anda kullanılmaz.* `bitig run` spaCy ayrıştırması yapmaz; desteklediği çıkarıcılar ham metin üzerinde çalışır. `bitig ingest` için bir spaCy modeli seçmek üzere `--spacy-model` seçeneğini kullanın. |
| `normalize.lowercase`, `normalize.strip_punct`, `normalize.collapse_numerals`, `normalize.expand_contractions` | *Kabul edilir ama şu anda kullanılmaz.* Küçük harfe çevirme öznitelik başına ayarlanır (`lowercase:`). |

## features

Her öznitelik çıkarıcı, bir `id` (yöntemler tarafından başvurulan), bir `type` ve
doğrudan ya da bir `params:` anahtarı altında yazılan türe özgü parametreler içeren bir
sözlüktür.

### Desteklenen türler

| type | parametreler |
|---|---|
| `mfw` | `n`, `min_df`, `max_df`, `scale` ({none, zscore, l1, l2}), `lowercase` |
| `word_ngram` | `n` (int veya [min, max]), `lowercase`, `scale`, `max_features` |
| `char_ngram` | `n` (int veya [min, max]), `include_boundaries`, `scale`, `max_features` |
| `function_word` | `wordlist` (isteğe bağlı liste), `language`, `scale` |
| `punctuation` | (yok) |
| `lexical_diversity` | `indices` (varsayılan `[ttr, yules_k]`) |
| `readability` | `indices`, `language` |

Şema ayrıca `pos_ngram`, `dependency_bigram`, `sentence_length`, `sentence_embedding` ve
`contextual_embedding` türlerini de tanır, ancak `bitig run` bunları uygulamaz ve bunları
kullanan bir çalışmayı reddeder. Bu türler Python API'si üzerinden kullanılabilir.

## methods

Her yöntem, bir `id`, bir `kind`, isteğe bağlı bir `features` (öznitelik id'si), isteğe
bağlı bir `group_by` (üst veri sütunu), isteğe bağlı bir `cv` bloğu (yalnızca classify) ve
doğrudan ya da bir `params:` anahtarı altında yazılan parametreler içeren bir sözlüktür.
`features` bir liste olduğunda yalnızca ilk öğesi kullanılır. `zeta`, `consensus`,
`rolling_delta` ve `verify` doğrudan derlem üzerinde çalışır ve `features` kullanmaz.

### Desteklenen türler

| kind | Açıklama |
|---|---|
| `delta` | En yakın-centroid yazar tespiti; `features` ve `group_by` gerektirir. `variant:` şunlardan biridir: `burrows` (varsayılan), `cosine`, `eder`, `eder_simple`, `argamon_linear`, `quadratic`. `method:`, `variant:` için kullanımdan kaldırılmış bir takma addır. |
| `zeta` | Craig's Zeta; `group_by` gerektirir. Parametreler: `variant` (varsayılan `classic`, `eder`), `top_k` (varsayılan 20), `min_df`, `group_a`, `group_b` (varsayılan: en büyük iki grup). |
| `reduce` | Boyut indirgeme; `features` gerektirir. `variant`: `pca` (varsayılan), `mds`, `tsne`, `umap` (ek: `bitig[cluster]`); `n_components` (varsayılan 2) ve alttaki kestiricinin kendi anahtar sözcük argümanları. |
| `cluster` | Kümeleme; `features` gerektirir. `variant`: `hierarchical` (varsayılan; `n_clusters`, `linkage`, `metric`), `kmeans` (`n_clusters`, `random_state`, `n_init`), `hdbscan` (`min_cluster_size`, `min_samples`, `metric`; ek: `bitig[cluster]`). |
| `consensus` | Önyükleme fikir birliği ağacı. Parametreler: `mfw_bands` (varsayılan `[100, 200, 300]`), `replicates` (varsayılan 20), `subsample`, `support_threshold`, `seed`. |
| `classify` | sklearn sınıflandırıcısı; `features` ve `group_by` gerektirir. `estimator`: `logreg` (varsayılan), `svm_linear`, `svm_rbf`, `rf`, `hgbm`. Çapraz doğrulama bir `cv:` bloğunda belirtilir (aşağıda). |
| `bayesian` | Wallace–Mosteller yazar tespiti; `features` ve `group_by` gerektirir. Parametre: `prior_alpha` (varsayılan 1.0). Ek: `bitig[bayesian]`. |
| `rolling_delta` | Uzun metinler üzerinde kayan Delta; `group_by` ve `target_ids` gerektirir. Parametreler: `window_size`, `step`, `base_delta`, `mfw_n`, `lowercase`. |
| `verify` | General Impostors ile yazar doğrulama; `group_by`, `target_ids` ve `candidate` gerektirir. Parametreler: `n_iter`, `feature_frac`, `impostor_n`, `base_delta`, `mfw_n`, `lowercase`, `threshold`, `seed`. |

### cv (classify)

```yaml
cv:
  kind: stratified          # stratified | loao | leave_one_text_out
  folds: 5                  # katman sayısı (varsayılan 5)
  groups_from: work         # yalnızca loao: katmanları gruplayan üst veri sütunu
```

`loao`, `groups_from` gerektirir ve bu sütun `group_by` sütununun birebir yeniden
etiketlenmiş hâli olmamalıdır.

## output

```yaml
output:
  dir: results/         # varsayılan
  timestamp: true       # çalıştırmaları zaman damgalı alt dizinlere sarar
```

`bitig run --output` ve `--name` bu ayarları geçersiz kılar.

## viz, report, cache

*Kabul edilir ama şu anda kullanılmaz.* `bitig run` her yöntemin varsayılan şeklini her
zaman PNG olarak yazar; raporları [`bitig report`](cli.md#bitig-report-run-dir) ile oluşturun,
spaCy önbelleğini [`bitig cache`](cli.md#onbellek) ile yönetin.

```yaml
viz:
  format: [pdf, png]    # pdf | png | svg | eps | tiff
  dpi: 300
  style: default
  palette: colorblind

report:
  format: none          # html | md | none
  offline: false
  include: [corpus, config, provenance, results]
  title: null

cache:
  dir: .bitig/cache
  reuse: true
```

## Gerçekçi çok yöntemli bir örnek

```yaml
name: federalist
seed: 42
output: { dir: results, timestamp: false }

corpus:
  path: corpus
  metadata: corpus/metadata.tsv
  filter:
    role: [train]

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

  - id: zeta_h_m
    kind: zeta
    group_by: author
    params:
      top_k: 50
      group_a: Hamilton
      group_b: Madison

  - id: logreg
    kind: classify
    features: mfw200
    group_by: author
    estimator: logreg
    cv: { kind: stratified, folds: 3 }
```
