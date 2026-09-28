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
    method: burrows
    features: mfw200
    group_by: author
```

## Üst düzey anahtarlar

| Anahtar | Tür | Zorunlu | Açıklama |
|---|---|---|---|
| `name` | str | evet | Çalışma adı; raporlarda gösterilir |
| `seed` | int | hayır | Varsayılan seed değeri (42). Kendi değerini belirtmeyen her stokastik yönteme iletilir (bkz. [yeniden üretilebilirlik](../concepts/results.md)). |
| `corpus` | object | evet | Derlem yapılandırması (aşağıya bakınız) |
| `features` | list | evet | Bir veya daha fazla öznitelik çıkarıcı |
| `methods` | list | evet | Çalıştırılacak bir veya daha fazla yöntem |
| `output` | object | hayır | Çıktı dizini / zaman damgalama |
| `cache` | object | hayır | DocBin önbellek dizini |
| `preprocess` | object | hayır | spaCy model seçimi |

## corpus

```yaml
corpus:
  path: corpus                    # .txt dosyalarının bulunduğu dizin
  metadata: corpus/metadata.tsv   # isteğe bağlı: dosya adı + rastgele alanları içeren TSV
  strict: true                    # varsayılan: üst verisi olmayan dosya varsa hata ver
  filter:                         # isteğe bağlı: çalıştırmadan önce derlemi filtrele
    role: [train]
```

## features

Her öznitelik çıkarıcı, bir `id` (yöntemler tarafından başvurulan), bir `type` ve
türe özgü parametreler içeren bir sözlüktür.

### Desteklenen türler

| type | parametreler |
|---|---|
| `mfw` | `n`, `min_df`, `max_df`, `scale` ({none, zscore, l1, l2}), `lowercase` |
| `word_ngram` | `n` (int veya [min, max]), `lowercase`, `scale` |
| `char_ngram` | `n`, `include_boundaries`, `scale` |
| `function_word` | `wordlist` (isteğe bağlı liste veya yol), `scale` |
| `punctuation` | (yok) |
| `lexical_diversity` | (yok) |
| `readability` | (yok) |

## methods

Her yöntem, bir `id`, bir `kind`, isteğe bağlı bir `features` (öznitelik id'si) ve
`params` içeren bir sözlüktür.

### Desteklenen türler

| kind | Açıklama |
|---|---|
| `delta` | En yakın-centroid yazar tespiti (varsayılan olarak `method: burrows`) |
| `zeta` | Craig's Zeta; `group_by` ve çıkarılan ya da belirtilen `params.group_a` / `group_b` gerektirir |
| `reduce` | Boyut indirgeme (varsayılan PCA); `params.n_components` |
| `cluster` | Hiyerarşik kümeleme (varsayılan Ward); `params.n_clusters`, `params.linkage` |
| `consensus` | Önyükleme fikir birliği ağacı; `params.mfw_bands`, `params.replicates` |
| `classify` | sklearn sınıflandırıcısı; `params.estimator`, `cv.kind`, `cv.folds` |

## output

```yaml
output:
  dir: results          # varsayılan
  timestamp: true       # çalıştırmaları zaman damgalı alt dizinlere sarar
```

## cache

```yaml
cache:
  dir: .bitig/cache     # spaCy DocBin önbellek konumu
```

## preprocess

```yaml
preprocess:
  spacy:
    model: en_core_web_trf    # varsayılan; hız için sm/md ile değiştirilebilir
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
    method: burrows
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
```
