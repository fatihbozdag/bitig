# Sorun giderme

Sık karşılaşılan kurulum ve çalışma sorunları ile çözümleri.

## Python sürümü

bitig **Python 3.11+** gerektirir. Daha eski bir yorumlayıcıda `pip install bitig` kurulumu
reddeder (paket `requires-python >=3.11` bildirir). 3.11+ bir yorumlayıcı edinmek için
[uv](https://docs.astral.sh/uv/) ya da `pyenv` kullanın:

```bash
uv venv --python 3.11
```

## spaCy modeli bulunamadı

```
OSError: [E050] Can't find model 'en_core_web_trf'.
```

bitig metni spaCy ile çözümler, ancak bir model **içermez**; bu nedenle kurulumdan sonra bir
model indirin:

```bash
python -m spacy download en_core_web_trf      # transformer işlem hattı (en yüksek doğruluk)
python -m spacy download en_core_web_sm        # küçük işlem hattı (çok daha hızlı, daha düşük doğruluk)
```

Ardından çalışmanızda `preprocess.spacy.model` ile bu modeli belirtin ya da `bitig ingest`
komutuna `--spacy-model` geçirin. İngilizce dışındaki diller için uygun işlem hattını indirin
(`de_dep_news_trf`, `es_dep_news_trf`, `fr_dep_news_trf`); Türkçe farklı biçimde ele alınır
(aşağıya bakın).

## `ImportError: requires the optional ... extra`

Temel kurulumu hafif tutmak için bazı yetenekler isteğe bağlı eklentilerin (extra) arkasındadır.
Bir içe aktarma hatasıyla karşılaşırsanız ilgili eklentiyi kurun:

| Eklenti | Sağladığı | Kurulum |
|---|---|---|
| `cluster` | UMAP indirgeme, HDBSCAN kümeleme | `uv pip install "bitig[cluster]"` |
| `bayesian` | PyMC ile hiyerarşik grup karşılaştırması (NumPy tabanlı Wallace–Mosteller yazar tespit modeli eklenti **gerektirmez**) | `uv pip install "bitig[bayesian]"` |
| `embeddings` | sentence-transformers ve bağlamsal BERT çıkarıcıları | `uv pip install "bitig[embeddings]"` |
| `viz` | Plotly / kaleido / ete3 etkileşimli ve ağaç şekilleri | `uv pip install "bitig[viz]"` |
| `interactive` | Yalnızca Plotly, etkileşimli şekiller için | `uv pip install "bitig[interactive]"` |
| `reports` | WeasyPrint ile PDF dışa aktarımı | `uv pip install "bitig[reports]"` |
| `gui` | NiceGUI + pywebview masaüstü arayüzü | `uv pip install "bitig[gui]"` |
| `turkish` | Stanza ile Türkçe çözümleme (`multilang` bir takma addır) | `uv pip install "bitig[turkish]"` |
| `docs` | Bu siteyi derlemek için MkDocs Material | `uv pip install "bitig[docs]"` |

## Türkçe kurulumu ve sürüm sabitlemeleri

Türkçe çözümleme, `spacy-stanza` ile sarmalanan Stanford Stanza (BOUN treebank'ı) üzerinden
yapılır. Üst akıştaki yığın yalnızca dar bir sürüm aralığında çalıştığı için `bitig[turkish]`
eklentisi bağımlılıklarını bilinçli olarak **sabitler**:

- `spacy-stanza` 1.0.4 (son sürümü) `stanza`'yı `<1.7` ile sınırlar; bu nedenle Stanza `1.6.x`
  aralığında kalmalıdır.
- Stanza 1.6.x, `torch.load`'u `weights_only=False` olmadan çağırır; bu da `weights_only`
  varsayılanının `True` olduğu `torch>=2.6` sürümlerinde bozulur. Bu nedenle `torch` `<2.6` ile
  sınırlanmıştır.
- torch 2.6'nın altında tutulduğu için `transformers` da `<5.19` ile sınırlanmıştır: 5.19 bir
  model kurmak için torch 2.6 gerektirir, 5.20 ise içe aktarma sırasında hata verir. Bu durum
  `turkish` eklentisi `embeddings` ile birlikte kurulduğunda önem taşır.

Eklentiyi kurduktan sonra Stanza Türkçe modelini bir kez indirin:

```bash
uv pip install "bitig[turkish]"
python -c "import stanza; stanza.download('tr')"
```

Notlar:

- Türkçe model kümesi ilk indirmeden sonra diskte yaklaşık 700 MB yer kaplar.
- Türkçe için `preprocess.spacy.backend` ayarlamanız **gerekmez**; bitig `spacy_stanza`
  arka ucunu derlemin dilinden kendiliğinden belirler.

## PDF dışa aktarımı başarısız (WeasyPrint)

`bitig[reports]`, sistem kitaplıklarına (Pango, HarfBuzz) gereksinim duyan WeasyPrint'i kurar.
Debian/Ubuntu üzerinde:

```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
```

macOS'ta bunları Homebrew ile kurun (`brew install pango`). HTML ve Markdown raporlarının böyle
bir sistem bağımlılığı yoktur; yalnızca PDF dışa aktarımı bu kitaplıkları gerektirir.

## `bitig plot` bir taslak iletisi yazdırıyor

`bitig plot` henüz bir çiziciye bağlanmamıştır. Şimdilik şekil üretmek için:

- çalışmayı `bitig run` ile çalıştırın; bu komut her yöntemin varsayılan şeklini yazar
  (`study.yaml` içindeki `viz` bloğu kabul edilir ancak henüz okunmaz), ya da
- `bitig.viz.plot_*` işlevlerini doğrudan Python'dan çağırın.

## Hâlâ çözemediniz mi?

Tam hata izini (traceback), Python sürümünüzü (`bitig info`) ve çalıştırdığınız komutu
içeren bir kayıt açın: <https://github.com/fatihbozdag/bitig/issues>.
