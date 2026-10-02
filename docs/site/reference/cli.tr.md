# CLI başvurusu

`bitig` olarak kurulan her bitig CLI komutu. Kesin seçenek listesi için `bitig --help` ya da
`bitig <komut> --help` çalıştırın; `bitig --version` sürümü yazdırır.

Çoğu çözümleme komutu ilk argüman olarak `.txt` dosyalarından oluşan bir derlem dizini,
`--metadata/-m` aracılığıyla da bir üst veri TSV dosyası alır (bir `filename` sütunu ve
istenen alanlar, örn. `author`). Seçenekler komuttan komuta değişir — aşağıda listelenmiştir.

## Proje iskeleti

### `bitig init <name>`

Yeni bir proje dizini oluşturur.

```bash
bitig init my-study [--target DIR] [--language en|tr|de|es|fr] [--force]
```

Oluşturulanlar:

```
my-study/
├── corpus/          # .txt dosyalarını (ve isteğe bağlı metadata.tsv'yi) buraya bırakın
├── results/         # bitig run her çalıştırma için buraya bir klasör yazar
├── reports/         # bitig report ile oluşturduğunuz raporlar için
├── .bitig/cache/    # spaCy DocBin önbelleği
├── .gitignore
├── README.md        # kısa bir yönlendirme
└── study.yaml       # bildirimsel çalışma yapılandırması (1000 MFW üzerinde Burrows Delta)
```

- `--target, -t` — oluşturulacak dizin (varsayılan `./<name>`)
- `--language, -l` — `study.yaml` dosyasına yazılan proje dili (varsayılan `en`)
- `--force` — dizin boş olmasa bile eksik dosyaları tamamlar

`metadata.tsv` oluşturulmaz; siz bir dosya sağlayana kadar `study.yaml` içindeki `metadata:`
satırı yorum satırı olarak kalır.

## İçe aktarma

### `bitig ingest <path>`

Bir derlem dizinini spaCy ile ayrıştırır ve ayrıştırmaları DocBin olarak önbelleğe alır.

```bash
bitig ingest corpus/ --metadata corpus/metadata.tsv [--no-strict] [--spacy-model en_core_web_sm]
```

- `--metadata, -m` — dosya adlarını üst veri alanlarına eşleyen TSV
- `--strict` (varsayılan) / `--no-strict` — her dosya için bir üst veri satırı gerektirir / gerektirmez
- `--cache-dir` — önbellek konumu (varsayılan `.bitig/cache`)
- `--spacy-model` — yüklenecek spaCy modeli (varsayılan: `en_core_web_trf`)
- `--exclude` — atlanacak spaCy işlem hattı bileşeni (tekrarlanabilir)
- `--language, -l` — derlem dil kodu (varsayılan `en`)

`bitig run` bir içe aktarma adımı gerektirmez: desteklediği öznitelik türleri ham metin
üzerinde çalışır.

### `bitig info`

Ortam bilgisini yazdırır: bitig, Python, platform ve spaCy sürümleri. Geçerli dizinde bir
`study.yaml` varsa yapılandırılmış dili de gösterir. Bir derlemi incelemez.

## Öznitelikler

### `bitig features <path>`

Bir öznitelik matrisi oluşturur ve parquet olarak kaydeder.

```bash
bitig features corpus/ --metadata corpus/metadata.tsv --type mfw --n 500 [--output features.parquet]
```

- `--type` — `mfw` (varsayılan), `word_ngram`, `char_ngram`, `function_word`, `punctuation`
- `--n` — `mfw` için ilk N, ya da n-gram derecesi (varsayılan 1000)
- `--min-df` (yalnızca mfw), `--scale` (`none`, `zscore`, `l1`, `l2`), `--lowercase` (yalnızca mfw)
- `--output, -o` — parquet yolu (varsayılan `features.parquet`)

Diğer çıkarıcılar (`lexical_diversity`, `readability`, sözcük türü ve bağımlılık
öznitelikleri, gömmeler) bu komuttan değil, `study.yaml` ya da Python API'si üzerinden
kullanılabilir.

## Yöntemler

Her yöntem komutu derlemden kendi MFW matrisini oluşturur. Seçenekler komuta özgüdür;
yalnızca `cluster`, `consensus` ve `classify` `--seed` alır (varsayılan 42).

| Komut | İşlev | Başlıca seçenekler |
|---|---|---|
| `bitig delta <path>` | Delta'yı uygular, belge başına yazar tespitlerini yazdırır | `-m` (zorunlu), `--method {burrows,argamon,eder,eder_simple,cosine,quadratic}`, `--mfw 1000`, `--mfw-min 2`, `--group-by author`, `--test-filter role=test` |
| `bitig zeta <path>` | İki grup arasında Craig's Zeta karşılaştırması | `-m` (zorunlu), `--group-by author`, `--variant {classic,eder}`, `--top-k 20`, `--group-a X --group-b Y` (varsayılan: en büyük iki grup) |
| `bitig reduce <path>` | Boyut indirgeme → parquet | `--method {pca,mds,tsne,umap}`, `--n-components 2`, `--mfw 500`, `-o reduce.parquet` |
| `bitig cluster <path>` | Kümeleme → parquet + özet | `--method {hierarchical,kmeans,hdbscan}`, `--n-clusters 2`, `--linkage ward`, `--mfw 500`, `--seed`, `-o cluster.parquet` |
| `bitig consensus <path>` | Önyükleme fikir birliği ağacı → Newick | `--bands 100,200,300,400,500`, `--replicates 100`, `--subsample 0.8`, `--support-threshold 0.5`, `--seed`, `-o consensus.nwk` |
| `bitig classify <path>` | sklearn sınıflandırıcısı + stilometri uyumlu çapraz doğrulama, yazar başına ölçütler | `-m` (zorunlu), `--estimator {logreg,svm_linear,svm_rbf,rf,hgbm}`, `--cv-kind {stratified,loao,leave_one_text_out}`, `--groups-by COL` (`loao` için), `--folds 5`, `--group-by author`, `--mfw 500`, `--seed` |
| `bitig embed <path>` | Sentence-transformer gömmeleri → parquet (ek: `bitig[embeddings]`) | `--model`, `--pool {mean,cls,max}`, `-o embeddings.parquet` |
| `bitig bayesian <path>` | Wallace–Mosteller yazar tespiti (ek: `bitig[bayesian]`) | `-m` (zorunlu), `--group-by author`, `--test-filter role=test`, `--mfw 500`, `--prior-alpha 1.0` |

`umap` ve `hdbscan`, `bitig[cluster]` ekini gerektirir.

## Düzenleme

### `bitig run <study.yaml>`

Bildirimsel bir çalışmayı uçtan uca yürütür (bkz. [study.yaml şeması](config.md)).

```bash
bitig run study.yaml --name demo [--output results/] [--overwrite]
```

Her yöntemin `Result` nesnesini kendi alt dizinine ve bir `resolved_config.json` dosyasına yazar.
Önceki bir çalıştırmayı içeren dizin reddedilir; `--overwrite` o çalıştırmanın çıktılarını (ve
yalnızca onları) değiştirir. Herhangi bir yöntem başarısız olursa çıkış kodu 1'dir — başarısız
her yöntemin klasöründe hata izini içeren bir `error.txt` bulunur.

- `--output, -o` — temel dizin (varsayılan: `study.yaml` içindeki `output.dir`)
- `--name` — çalıştırma dizininin adı (varsayılan: bir zaman damgası; `output.timestamp` false ise yok)

### `bitig report <run-dir>`

Bir çalıştırma dizininden Jinja2 HTML veya Markdown raporu oluşturur.

```bash
bitig report results/demo --output results/demo/report.html [--format html|md] [--title "Çalışmam"]
```

### `bitig plot <result-dir>`

Tek bir yöntemin sonuç dizinini (`result.json` dosyasını içeren klasör) alır. Henüz
uygulanmamıştır: bir bildirim yazdırır ve hiçbir şekil oluşturmaz. `bitig run` her yöntem
klasörüne zaten varsayılan bir şekil yazar; özel şekiller için Python'dan `bitig.viz`
işlevlerini kullanın.

### `bitig shell [<corpus>]`

Asgari etkileşimli menü: bir derlem yükler (isteğe bağlı olarak `--metadata` ile), belge
sayısını ve üst veri alanlarını listeleyebilir ve her yöntem için ilgili CLI komutunu
gösterir.

### `bitig gui`

Masaüstü arayüzünü başlatır (ek: `bitig[gui]`).

```bash
bitig gui [--no-native] [--host 127.0.0.1] [--port 8080] [--width 1200] [--height 800]
```

- `--no-native` — yerel pencere yerine varsayılan tarayıcıda açar
- `--dev` — arayüz geliştirme için anında yeniden yükleme

## Önbellek

### `bitig cache <cmd>`

`bitig ingest` tarafından üretilen spaCy DocBin önbelleğini yönetir. Her alt komut
`--cache-dir` alır (varsayılan `.bitig/cache`).

- `bitig cache size` — toplam bayt ve kayıt sayısı
- `bitig cache list` — önbellek anahtarlarını listeler
- `bitig cache clear` — tüm kayıtları siler

## Forensic Lab vakaları

### `bitig case <cmd>`

Forensic Lab vakalarını yönetir: delil zinciri kayıtlı deliller, bir tarif (recipe),
çalıştırmalar ve imzalı bir rapor. Her alt komut `--cases-dir` alır (varsayılan
`~/.bitig/cases/`). Tam yordam için [vaka iş akışına](../forensic/case-workflow.md) bakın.

| Komut | İşlev |
|---|---|
| `bitig case new <id> --title T --examiner E [--recipe R]` | Bir vaka oluşturur; tarifler: `imposters_lr` (varsayılan), `delta_attribution`, `bayesian`, `zeta_contrast`, `exploration` ya da `custom` |
| `bitig case add-evidence <id> <files…> --role questioned` / `--role known --author A` | Dosyaları vakaya kopyalar, karma değerlerini hesaplar ve kaydeder (yalnızca kayıtlı deliller çözümlenir ve mühürlenir) |
| `bitig case list` | Tüm vakaların tablosu |
| `bitig case open <id>` | Yol ve kısa bir özet |
| `bitig case status <id> [--no-verify]` | Delil zinciri denetimiyle tam durum; delil uyuşmazlığında çıkış kodu 2 |
| `bitig case reacknowledge <id> <evidence-path> --reason R [--by NAME]` | Değişmiş bir delil dosyasının yeni karma değerini kabul eder (kayda geçer); imzalamadan önce vaka yeniden çalıştırılmalıdır |
| `bitig case run <id>` | Vakanın çözümlemesini kayıtlı deliller üzerinde, arayüzün Run adımıyla aynı ön koşullarla çalıştırır; her yöntem için ✓/✗ ve çalıştırma dizinini yazdırır. Çıkış 0 = tüm yöntemler başarılı, 1 = kısmi ya da başarısız, 2 = engellendi |
| `bitig case fork <id> <new-id> [--title] [--examiner] [--acknowledge-mismatch REASON]` | İmzasız bir alt vaka olarak kopyalar |
| `bitig case sign <id> [--signed-by NAME] [--signature-plugin hmac\|null]` | Vakayı imzalar ve kilitler; başarılı bir çalıştırma gerektirir |
| `bitig case verify <id> [--key KEY]` | Mührü yeniden hesaplar; çıkış 0 = doğrulandı (geçerli HMAC), 1 = imzalı değil, 2 = bozuk, 3 = karma değerleri sağlam ama Null mührü (UNSIGNED), 4 = karma değerleri sağlam ama HMAC anahtarsız denetlenemiyor (CANNOT VERIFY). HMAC anahtarı verilmezse `$BITIG_SIGNATURE_KEY` kullanılır |

Vaka parametreleri için bir CLI komutu yoktur; onları arayüzün Method adımında ya da
Python'da `Case.set_param` ile ayarlayın.

## Yardım alma

Her komut `--help` seçeneğini destekler:

```bash
bitig --help
bitig run --help
bitig case --help
```
