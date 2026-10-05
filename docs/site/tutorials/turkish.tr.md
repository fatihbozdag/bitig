# Türkçe stilometri öğreticisi

Çalıştırılabilir bir Türkçe örnek: bir Türkçe proje kurun, ardından Türkçe Wikisource'dan alınan,
telif hakkı süresi dolmuş Ömer Seyfettin kısa hikayelerinden oluşan bir derlemi MFW, PCA ve Ward
kümeleme ile inceleyin.

## Kurulum

```bash
uv pip install 'bitig[turkish]'
python -c "import stanza; stanza.download('tr')"
bitig init seyfettin --language tr
cd seyfettin
```

Bu komut, Türkçe için önceden yapılandırılmış (`preprocess.language: tr`) `study.yaml` içeren bir
proje dizini oluşturur. Şununla doğrulayın:

```bash
bitig info
```

`language` satırı `tr` gösterir.

Stanza (`spacy-stanza` aracılığıyla) yalnızca `bitig ingest` ve Python API'deki spaCy tabanlı
öznitelikler için gereklidir. `bitig run` komutunun oluşturduğu öznitelikler (MFW, n-gramlar,
işlev sözcükleri, noktalama, sözcüksel çeşitlilik, okunabilirlik) ham metin üzerinde çalışır ve
Stanza'yı hiç yüklemez.

## Derlem

`corpus/` dizinine Türkçe metinlerinizi UTF-8 `.txt` dosyası olarak ekleyin. İyi bir
telif hakkı süresi dolmuş kaynak, [Türkçe Vikikaynak'taki Ömer Seyfettin](https://tr.wikisource.org/wiki/Yazar:%C3%96mer_Seyfettin)
sayfasıdır — 20. yüzyıl başına ait düzinelerce kısa hikaye orada zaten yazıya geçirilmiş durumdadır.

`corpus/metadata.tsv` dosyasını ekleyin ve `study.yaml` içindeki `metadata:` satırının yorumunu
kaldırın:

```tsv
filename	author	year
bomba.txt	Omer_Seyfettin	1910
kesik_biyik.txt	Omer_Seyfettin	1911
forsa.txt	Omer_Seyfettin	1913
pembe_incili_kaftan.txt	Omer_Seyfettin	1917
```

İskele çalışması `author` sütununa göre gruplanmış Burrows Delta çalıştırır; bu yöntem **en az iki**
farklı `author` değerine ait belge gerektirir. Tek yazarla Delta yöntemi başarısız olur ve
`bitig run` 1 durum koduyla çıkar. Ya ikinci bir yazarın metinlerini ekleyin ya da aşağıdaki
çalışan örnekte olduğu gibi Delta yöntemini `reduce` / `cluster` yöntemleriyle değiştirin.

## Çalışmayı çalıştırın

```bash
bitig ingest corpus/ --language tr --metadata corpus/metadata.tsv   # isteğe bağlı
bitig run study.yaml --name first-run
```

`bitig ingest`, Stanza'yı `spacy-stanza` aracılığıyla çalıştırır ve ayrıştırmaları DocBin olarak
önbelleğe alır. `bitig run` bu önbelleği okumaz; dolayısıyla bu çalışma için ingest adımı isteğe
bağlıdır.

## Çıktılar

İskele Türkçe çalışması **MFW** (ilk 1 000 sözcük, z-skorlu) oluşturur ve **Burrows Delta**
çalıştırır. `bitig run`, yöntem başına bir klasör ve çalıştırma yapılandırmasını yazar:

```
results/first-run/
├── resolved_config.json      # tam çözümlenmiş çalışma yapılandırması
└── burrows/
    ├── result.json           # tahminler, yeniden ikame doğruluğu, köken bilgisi
    └── confusion_matrix.png
```

- `result.json`, yöntemin değerlerini ve bir köken bilgisi bloğunu (bitig sürümü, derlem özeti,
  öznitelik özeti, seed, çözümlenmiş yapılandırma) içerir. Ayrı bir `provenance.json` yoktur.
- Delta değerleri örneklem içidir: `resubstitution_accuracy` bir ayrışabilirlik denetimidir;
  `attributions` ise `author` değeri olmayan belgeleri listeler.
- Diğer yöntemler kendi varsayılan şekillerini yazar: `reduce` için `scatter.png` ve
  `pca_biplot.png`, `cluster` için `dendrogram.png`, `zeta` için `zeta.png`. Yalnızca tablo
  döndüren yöntemler (Zeta, kayan Delta, doğrulama) ayrıca `table_N.parquet` dosyaları yazar.
- Başarısız bir yöntem, klasöründe `result.json` yerine bir `error.txt` bırakır ve çalıştırma
  1 durum koduyla çıkar.

## Çalışan örnek: Ömer Seyfettin'in 28 kısa hikayesi

Depodaki `examples/turkish_seyfettin/` dizini, Ömer Seyfettin'in
(1884-1920; Türkiye'de telif hakkı süresi 1991'de dolmuştur)
[tr.wikisource.org](https://tr.wikisource.org) üzerinden `fetch_corpus.py`
betiği ile çekilmiş 28 kısa hikayesi üzerinde uçtan uca bir çalıştırma sunar. Derlem
çalışmayla birlikte depoya işlenmiştir; yeniden çekmeniz gerekmez:

```bash
bitig run examples/turkish_seyfettin/study.yaml --name seyfettin
# isteğe bağlı: hikayeleri yeniden indirin (~30s; Wikisource'a saygılı)
python examples/turkish_seyfettin/fetch_corpus.py --n 30
```

**Derlem.** 200 belirteçlik alt sınırı geçen 28 hikaye var; uzunluklar 326 ile
4 455 belirteç arasında (medyan ≈ 1 560). Wikisource transkripsiyonları CC BY-SA 4.0
lisanslıdır; atıf bilgileri ve kaynak URL'ler
`examples/turkish_seyfettin/manifest.json` dosyasındadır.

**Çalışma.** En sık 500 sözcük (z-skorlu, `min_df = 2`) → PCA + Ward hiyerarşik kümeleme.
Çalışma ayrıca varsayılan olarak hiçbir yöntemin kullanmadığı bir Türkçe işlev sözcüğü
özniteliği (`tr_fwords`) oluşturur; denemek için bir yöntemin `features:` alanını ona
yönlendirin. Tek yazarlı bir derlem yazarlar arası yazar tespitine ya da doğrulamaya (Delta,
Imposters, classify) izin vermez; bu nedenle bu *yazar içi keşifsel stilometri*dir, yazar
tespiti değildir.

Çalıştırma şunları yazar:

```
examples/turkish_seyfettin/results/seyfettin/
├── resolved_config.json
├── pca/
│   ├── result.json        # koordinatlar, yüklemeler, açıklanan varyans
│   ├── scatter.png
│   └── pca_biplot.png
└── ward/
    ├── result.json        # küme etiketleri ve bağlantı matrisi
    └── dendrogram.png
```

### MFW-500 sözcüksel uzayı üzerinde PCA

PC1 varyansın **%8,0**'ini, PC2 ise **%6,9**'unu açıklar. Tek bir bileşen baskın değildir:
tek bir yazarın iç sözcüksel varyansı pek çok küçük eksene yayılır.

**En büyük yüklemeler — PC1**: `o`, `akşam`, `gül`, `bana`, `karşı`, `bakıyordu`, `nihayet`, `ki`.

**En büyük yüklemeler — PC2**: `durdu`, `idi`, `başını`, `hafif`, `değildi`, `üzerine`, `şeyler`, `tarafa`.

`pca/pca_biplot.png`, en büyük 15 yükleme vektörünü aynı 2-B izdüşüm üzerine bindirir.

### Ward hiyerarşik kümeleme (k = 4)

Dendrogramı (`ward/dendrogram.png`) dört düz kümede kesmek şunu verir:

| Küme | n  | Üyeler | Hikaye uzunluğu (belirteç) |
|-----:|---:|---|---|
| 0    | 17 | `and`, `antiseptik`, `elma`, `kasag`, … | medyan 1 152 (326–3 115) |
| 1    |  9 | `aleko`, `bomba`, `ferman`, `forsa`, … | medyan 2 418 (1 096–4 455) |
| 2    |  1 | `keramet` | 508 |
| 3    |  1 | `hediye` | 454 |

Hikaye uzunluğu kümelerle örtüşür: iki tekil küme, derlemin en kısa ikinci ve üçüncü
hikayeleridir; 1. küme ise uzun hikayeleri toplar. Kısa metinlerde z-skorlu MFW sayımları
gürültülenir, dolayısıyla kısa hikayeler konudan bağımsız olarak ana buluttan uzaklaşır. Bu
yöntem hatası değil — küçük *N* için MFW kestirim varyansının doğal sonucudur:

> Türkçe kısa düzyazıda stilometri yapıyorsanız, alt küme yapısından
> tema/dönem sonuçları çıkarmadan önce belge başına belirteç tabanını en az
> 1 000'e yükseltin — ya da uzunluğa karşı çok daha hoşgörülü olan karakter
> n-gramlarına geçin.

### Bunun *yapmadığı* — sınırlamalar

Gerçek bir **yazar tespiti** gösterimi, Wikisource'taki erken-cumhuriyet
döneminde benzer kapsama sahip en az bir başka telif hakkı süresi dolmuş Türkçe
düzyazı yazarına ihtiyaç duyar; Wikisource:tr şu anda bunu sunmuyor (Refik
Halit Karay'ın transkripsiyonları orada bulunsa da altta yatan metinler ancak
2036'da Türkiye'de kamuya geçecektir). Atfetme çalışmaları için Seyfettin'i
çağdaş bir edebî yazar yerine farklı bir tür/kayıt dengelemesi sağlayan bir
denetim derlemi (örn. meclis konuşmaları, konuya göre Türkçe Wikipedia
seçilmiş makaleleri ya da kendi kurumsal derleminiz) ile eşleştirmenizi
öneririz.

## Özelleştirme

Öznitelikleri veya yöntemleri değiştirmek için `study.yaml` dosyasını düzenleyin. `bitig run`,
`mfw`, `word_ngram`, `char_ngram`, `function_word`, `punctuation`, `lexical_diversity` ve
`readability` öznitelik türlerini oluşturur; başka bir türü çalışmayı yüklerken reddeder. Örneğin
karakter n-gramları kısa metinlerde daha dayanıklıdır:

```yaml
features:
  - id: char3
    type: char_ngram
    n: 3
    scale: zscore
```

Bağlamsal gömmeler bir `bitig run` öznitelik türü değildir. Bunları Python'dan
`bitig.features.ContextualEmbeddingExtractor` ile kullanın; `language="tr"` ile model
`dbmdz/bert-base-turkish-cased` olarak çözümlenir ve `model=` herhangi bir HuggingFace denetim
noktasını kabul eder (örn. `stefan-it/bert5urk`). Bu, `bitig[embeddings]` ekini gerektirir.

## Türkçe'ye özgü notlar

- **Morfoloji.** Türkçe eklemeli bir dildir; `evlerinizden` gibi bir belirteç `ev+ler+iniz+den`
  biçimlerini tek formda bir araya getirir. Stanza'nın BOUN modeli bu biçimleri doğru şekilde
  lemmatize eder ve etiketler; bu durum POS n-gram ve bağımlılık tabanlı öznitelikler için
  önemlidir. Stilometrik çözümleme açısından bu morfolojik zenginlik, sözcük düzeyi MFW listelerini
  doğrudan Türkçe'ye uygulamak yerine lemma tabanlı ya da kök tabanlı öznitelikleri
  tercih etmeyi gerektirebilir.
- **Hece sayımı.** Hem Ateşman hem de Bezirci-Yılmaz, Türkçe yazıma özel bir sesli harf sayacı
  kullanır (`ı`, `ğ`, `ş`, `ç`, `ü`, `ö` dahil).
- **İşlev sözcükleri.** Paketlenmiş liste, Türkçe'nin kapalı sınıf ilgeçlerine, bağlaçlarına ve
  söylem parçacıklarına dayanır (örn. `ile`, `ancak`, `fakat`, `çünkü`, `ki`, `ise`).

## Sorun giderme

- **`ModuleNotFoundError: No module named 'spacy_stanza'`** — şunu çalıştırın:
  `uv pip install 'bitig[turkish]'`.
- **`FileNotFoundError: ... stanza_resources/tr/default.zip`** — şunu çalıştırın:
  `python -c "import stanza; stanza.download('tr')"`. Model yaklaşık 600 MB'tır.
- **MPS'de çok yavaş ilk aktarım.** Stanza'nın Türkçe modeli henüz Apple Silicon MPS'i
  desteklememektedir. İlk çalıştırmada CPU ayrıştırma hızları beklenir; sonraki çalıştırmalar
  önbellek isabetleridir.
