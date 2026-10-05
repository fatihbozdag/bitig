# Diller

bitig beş dil için birinci sınıf destek sunar: **İngilizce**, **Türkçe**, **Almanca**, **İspanyolca** ve **Fransızca**. Her dilin paketlenmiş işlev sözcüğü listeleri, yerel okunabilirlik formülleri ve uçtan uca test edilmiş işlem hatları bulunur.

## Desteklenen diller

| Kod | Dil | Arka uç | Varsayılan model | Okunabilirlik |
|------|---------|-----------------|--------------------------|------------------------------------------|
| en | İngilizce | yerel spaCy | `en_core_web_trf` | Flesch, Flesch-Kincaid, Gunning Fog, Coleman-Liau, ARI, SMOG |
| tr | Türkçe | `spacy-stanza` | Stanza `tr` (BOUN) | Ateşman, Bezirci-Yılmaz |
| de | Almanca | yerel spaCy | `de_dep_news_trf` | Flesch-Amstad, Wiener Sachtextformel |
| es | İspanyolca | yerel spaCy | `es_dep_news_trf` | Fernández-Huerta, Szigriszt-Pazos |
| fr | Fransızca | yerel spaCy | `fr_dep_news_trf` | Kandel-Moles, LIX |

## Kayıt defteri nasıl çalışır

bitig'daki her dil bağımlı nokta (ön işleme işlem hattı, işlev sözcüğü yükleme, okunabilirlik indeksi seçimi, gömme modeli varsayılanları) merkezi `LANGUAGES` kayıt defterinden okur. Bilinmeyen kodlar, desteklenen kümeyi listeleyen açıklayıcı bir hata mesajıyla anında başarısız olur.

```python
from bitig import LANGUAGES, get_language

spec = get_language("tr")
print(spec.backend)                       # 'spacy_stanza'
print(spec.default_model)                 # 'tr'
print(spec.readability_indices)           # ('atesman', 'bezirci_yilmaz')
print(spec.contextual_embedding_default)  # 'dbmdz/bert-base-turkish-cased'
```

`LanguageSpec` dondurulmuş bir veri sınıfıdır; bu nedenle özellikler iş parçacıkları ve süreçler arasında güvenle paylaşılabilir.

## Bir çalışmada dil bildirme

Bir çalışma, dilini `study.yaml` içinde yalnızca bir kez bildirir. Bu değer, kayıt defterine karşı yapılandırma yüklendiği anda doğrulanır; yazım hataları herhangi bir ayrıştırma başlamadan önce yakalanır.

```yaml
# study.yaml
preprocess:
  language: tr
  spacy:
    # model ve arka uç, `language` değerinden otomatik çözümlenir.
    # Yalnızca ne yaptığınızdan eminseniz geçersiz kılın:
    # model: my-custom-model
    # backend: spacy
```

Komut satırından, `bitig init` veya `bitig ingest` komutuna `--language` bayrağını ekleyin:

```bash
bitig init mystudy --language tr
bitig ingest corpus/ --language tr --metadata corpus/metadata.tsv
```

Geçerli dizinde bir `study.yaml` bulunduğunda `bitig info`, yapılandırılmış dili yazdırır; böylece etkin işlem hattını tek bakışta doğrulayabilirsiniz.

## Türkçe ön koşulları

Türkçe, şu anda yerel bir spaCy işlem hattı olarak gönderilmeyen tek dildir. bitig, Türkçeyi [Stanza](https://stanfordnlp.github.io/stanza/) aracılığıyla [`spacy-stanza`](https://github.com/explosion/spacy-stanza) üzerinden yönlendirir; bu yöntem yine de yerel spaCy `Doc` nesnelerini döndürür ve aşağı yöndeki her şey özdeş biçimde çalışır.

```bash
uv pip install 'bitig[turkish]'
python -c "import stanza; stanza.download('tr')"
```

Stanza Türkçe modeli (yaklaşık 600 MB) ilk kullanımda indirilir. Bundan sonra `bitig ingest --language tr`, İngilizce yoluyla özdeş biçimde çalışır.

## İşlev sözcükleri

Dil başına işlev sözcüğü listeleri `src/bitig/resources/languages/<code>/function_words.txt` konumunda yer alır. İngilizce dışındaki listeler, Universal Dependencies kapalı sınıf belirteçlerinden (ADP / CCONJ / DET / PRON / SCONJ / PART / AUX) türetilmiş ve en sık görülen biçimlere indirgenerek elde edilmiştir. Yeniden oluşturmak için:

```bash
python scripts/regenerate_function_words.py
```

## Okunabilirlik formülleri

İngilizce dışındaki her dil, `bitig.languages.readability_<code>` içinde uygulanan en az iki yerel okunabilirlik indeksiyle birlikte gelir:

- **Türkçe (tr):** Ateşman (1997), Bezirci-Yılmaz (2010)
- **Almanca (de):** Flesch-Amstad (1978), Wiener Sachtextformel (Bamberger & Vanecek, 1984)
- **İspanyolca (es):** Fernández-Huerta (1959), Szigriszt-Pazos (1993)
- **Fransızca (fr):** Kandel-Moles (1958), LIX (Björnsson, 1968)

Almanca ve Fransızca heceler, *Abend* ya da *école* gibi sözcükleri eksik sayan heceleme
noktalarına göre değil, ünlü çekirdeklerine göre sayılır (`bitig.languages._syllables`).
İngilizce indeksler `textstat` kütüphanesinden gelir ve bitig'in kendiliğinden hiçbir zaman
indirmediği NLTK cmudict sözlüğünü gerektirir (`python -m nltk.downloader cmudict`).

Bir çalışma `type: readability` bildirdiğinde, çıkarıcı `indices` bağımsız değişkeni başka
indeksler belirtmedikçe dilin varsayılan indekslerini (`LanguageSpec.readability_indices`)
kullanır. İngilizce için varsayılanlar Flesch, Flesch-Kincaid ve Gunning Fog'dur.

## Altıncı bir dil ekleme

1. `bitig.languages.registry.REGISTRY` içine bir `LanguageSpec` girişi ekleyin.
2. `src/bitig/resources/languages/<code>/function_words.txt` dosyasını oluşturun (UD derlem listesini genişlettikten sonra `scripts/regenerate_function_words.py` çalıştırın).
3. Dil için yerel okunabilirlik formülleri mevcutsa, bunları `bitig.languages.readability_<code>` içinde yazın ve `bitig.features.readability._INDEX_REGISTRY` içinde kaydedin.
4. `tests/languages/` altına birim testleri ve en az bir entegrasyon testi ekleyin.
5. `docs/site/tutorials/` altına bir öğretici sayfa ekleyin.

Tam tasarım gerekçesi için `docs/superpowers/specs/` altındaki çok dilli destek belirtimini inceleyin.
