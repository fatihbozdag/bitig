# CLI başvurusu

Her bitig CLI komutu. `bitig` giriş noktası aracılığıyla `bitig` olarak kurulur.

## Proje iskeleti

### `bitig init <name>`

Yeni bir proje dizini oluşturur.

```bash
bitig init my-study
```

Oluşturulanlar:

```
my-study/
├── corpus/             # .txt dosyalarını buraya bırakın
│   └── metadata.tsv    # dosya başına bir satır
├── study.yaml          # bildirimsel çalışma yapılandırması
└── README.md           # kısa bir yönlendirme
```

## İçe aktarma

### `bitig ingest <path>`

İsteğe bağlı üst veriyle bir derlem dizinini ayrıştırır.

```bash
bitig ingest corpus/ --metadata corpus/metadata.tsv [--strict|--no-strict]
```

- `--strict` (varsayılan) — herhangi bir belge üst veri satırından yoksunsa hata verir
- `--no-strict` — kısmi kapsamı kabul eder

Çıktı, sonraki komutlar için bir spaCy DocBin olarak önbelleğe alınır.

### `bitig info`

İçe aktarılmış bir derlemi özetler: belge sayısı, üst veri alanları ve değer dağılımları,
toplam simge sayısı.

## Öznitelikler

### `bitig features <path>`

Bir öznitelik matrisi oluşturur ve özeti yazdırır.

```bash
bitig features corpus/ --metadata corpus/metadata.tsv --type mfw --n 500
```

Türler: `mfw`, `word_ngram`, `char_ngram`, `function_word`, `punctuation`,
`lexical_diversity`, `readability`.

## Yöntemler

Tüm yöntem komutları `--metadata`, `--group-by <field>`, `--seed <int>` seçeneklerini kabul eder.

| Komut | İşlev |
|---|---|
| `bitig delta <path> --method {burrows,argamon,eder,cosine,quadratic}` | Delta'yı uygular, yazar başına tahminleri yazdırır |
| `bitig zeta <path> --group-a X --group-b Y` | İki yazar grubu arasında Craig's Zeta karşılaştırması yapar |
| `bitig reduce <path> --method {pca,mds,tsne,umap} --n-components 2` | Boyut indirgeme → parquet |
| `bitig cluster <path> --method {hierarchical,kmeans,hdbscan} --n-clusters N --seed S` | k-means için `--seed` ile kümeleme |
| `bitig consensus <path>` | MFW bantları üzerinde önyükleme fikir birliği ağacı |
| `bitig classify <path> --estimator {logreg,svm_linear,svm_rbf,rf,hgbm} --cv-kind {stratified,loao,leave_one_text_out}` | sklearn sınıflandırıcısı + stilometri uyumlu çapraz doğrulama |
| `bitig embed <path>` | Cümle veya bağlamsal gömme (ek: `bitig[embeddings]`) |
| `bitig bayesian <path>` | Wallace–Mosteller yazar tespiti + hiyerarşik grup karşılaştırması (ek: `bitig[bayesian]`) |

## Düzenleme

### `bitig run <study.yaml>`

Bildirimsel bir çalışmayı uçtan uca yürütür.

```bash
bitig run study.yaml --name demo [--output results/] [--overwrite]
```

Her yöntemin `Result` nesnesini kendi alt dizinine ve bir `resolved_config.json` dosyasına yazar.
Önceki bir çalıştırmayı içeren dizin reddedilir; `--overwrite` o çalıştırmanın çıktılarını (ve
yalnızca onları) değiştirir. Herhangi bir yöntem başarısız olursa çıkış kodu 1'dir — başarısız
her yöntemin klasöründe hata izini içeren bir `error.txt` bulunur.

### `bitig report <run-dir>`

Bir çalıştırma dizininden Jinja2 HTML veya Markdown raporu oluşturur.

```bash
bitig report results/demo --output results/demo/report.html [--format html|md]
```

### `bitig plot <run-dir>`

Kaydedilmiş Result nesnelerinden yönteme özgü şekiller (PCA dağılım grafiği, Ward dendrogramı, Zeta tercih grafiği, …) oluşturur.

### `bitig shell`

Bir çalışma kurulumunda size eşlik eden etkileşimli Rich tabanlı sihirbaz.

## Önbellek

### `bitig cache <cmd>`

`bitig ingest` tarafından üretilen spaCy DocBin önbelleğini yönetir:

- `bitig cache info` — özetler
- `bitig cache clear` — kaldırır

## Yardım alma

Her komut `--help` seçeneğini destekler:

```bash
bitig --help
bitig run --help
```
