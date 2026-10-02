# Öznitelikler

Her öznitelik çıkarıcı, yöntemlerin tükettiği ortak sayısal zarf olan bir `FeatureMatrix` döndürür.

## FeatureMatrix

```python
@dataclass
class FeatureMatrix:
    X: np.ndarray            # (n_docs, n_features)
    document_ids: list[str]
    feature_names: list[str]
    feature_type: str
    extractor_config: dict[str, Any]
    provenance_hash: str
```

Temel özellikler:

- `fm.n_features`, `n_docs` için `len(fm)`
- `fm.as_dataframe()` — `document_ids` ile indekslenmiş pandas `DataFrame`
- `fm.concat(other)` — aynı satır kimliklerine sahip iki matrisi sütun bazında birleştirir

## Mevcut çıkarıcılar

`bitig`'dan içe aktarın:

| Çıkarıcı | Girdi | Çıktı |
|---|---|---|
| `MFWExtractor(n=..., scale=..., lowercase=...)` | Corpus | en sık n sözcük: z-puanlı göreli frekanslar (varsayılan), L1 / L2 satır normalize sayımlar ya da ham sayımlar |
| `CharNgramExtractor(n=..., include_boundaries=..., scale=...)` | Corpus | karakter n-gramı sayımları (sklearn CountVectorizer'a devredilir) |
| `WordNgramExtractor(n=..., lowercase=..., scale=...)` | Corpus | sözcük n-gramı sayımları |
| `PosNgramExtractor(n=..., tagset=..., spacy_model=...)` | Corpus | spaCy sözcük türü (POS) n-gramı sayımları |
| `DependencyBigramExtractor(spacy_model=..., lowercase=...)` | Corpus | (head_lemma, dep, child_lemma) üçlüsü sayımları |
| `FunctionWordExtractor(wordlist=..., language=..., scale=...)` | Corpus | paketlenmiş dile özgü işlev sözcüklerinin sayımları |
| `PunctuationExtractor()` | Corpus | 32 ASCII noktalama karakterinin sayımları |
| `ReadabilityExtractor(indices=..., language=...)` | Corpus | dile özgü okunabilirlik indeksleri (İngilizce varsayılan: Flesch, FK-grade, Gunning Fog) |
| `SentenceLengthExtractor(spacy_model=...)` | Corpus | cümle başına belirteç sayısının ortalama, standart sapma ve çarpıklığı |
| `LexicalDiversityExtractor(indices=...)` | Corpus | TTR, MATTR, MTLD, HD-D, Yule's K/I, Herdan's C, Simpson's D |
| `SentenceEmbeddingExtractor(model=...)` | Corpus | sentence-transformers havuzlanmış gömmesi (ek: `bitig[embeddings]`) |
| `ContextualEmbeddingExtractor(model=..., layer=..., pool=...)` | Corpus | HF dönüştürücü gizli durum vektörleri (ek: `bitig[embeddings]`) |

### Öznitelik çıkarıcı ayrıntısı

Yukarıdaki her çıkarıcı sklearn tarzı bir nesnedir; `fit_transform(corpus)` bir
`FeatureMatrix` döndürür.

#### MFWExtractor
`MFWExtractor(n=200, scale="zscore", lowercase=True)`

*Şu durumda kullanın:* kanonik stilometrik özniteliği — en sık sözcüklerin (MFW) göreli
frekanslarını — istediğinizde. Delta-ailesi atıf çalışmaları için varsayılan seçimdir.
*Şu durumda kullanmayın:* derleminiz çok küçükse (<200 benzersiz belirteç) ya da soru
konudan bağımsızsa (MFW konuya duyarlıdır; bkz. `CategorizedCharNgramExtractor`).
*Beklenen sonuç:* `(n_docs, n)` boyutlu kayan noktalı matris. Varsayılanlar `n=1000`,
`scale="zscore"`, `lowercase=False`'tur (ayrıca `min_df=1`, `max_df=1.0`). `scale="zscore"`
altında her değer `sayım / belgedeki toplam sözcük sayısı` göreli frekansının, uydurulmuş
sütun ortalamaları ve standart sapmalarıyla z-puanlanmış halidir; `"l1"` altında satırlar
tutulan sözcükler üzerinden 1'e toplanır; `"none"` ham sayımlardır.

#### CharNgramExtractor
`CharNgramExtractor(n=3, include_boundaries=False, scale="none", max_features=None)`

*Şu durumda kullanın:* alt sözcük stilini (ön ekler, son ekler, noktalama bitişikliği)
yakalayan ve OOV sözcükler ya da yazım hatalarıyla başa çıkabilen öznitelikler
istediğinizde.
*Şu durumda kullanmayın:* dillerin yazı sistemleri karışıyorsa (yazı sistemleri
arasındaki n-gramlar gürültü üretir) ya da sözcük düzeyinde anlamsal duyarlılık
gerekiyorsa.
*Beklenen sonuç:* sklearn'ın `CountVectorizer` bileşeniyle (büyük/küçük harf
dönüştürmeden) oluşturulmuş yoğun sayım matrisi. `include_boundaries=True` onun `char_wb`
çözümleyicisini kullanır (sözcük sınırları içindeki n-gramlar). `n` bir tamsayı ya da
`(min_n, max_n)` demeti olabilir.

#### WordNgramExtractor
`WordNgramExtractor(n=1, lowercase=False, scale="none", max_features=None)`

*Şu durumda kullanın:* unigramlar (MFW eşdeğeri) ya da kısa bigram ifadeler
istediğinizde ve z-puanlama istemediğinizde. Bigramlar sabit ifadeleri saptamak için
kullanışlıdır.
*Şu durumda kullanmayın:* küçük derlemlerde n ≥ 3 — seyreklik baskın gelir. Unigramlar
için ham sayımlar gerekmiyorsa `MFWExtractor` kullanın.
*Beklenen sonuç:* yoğun sayım matrisi; sözcük dağarcığı n ile hızla büyür.

#### PosNgramExtractor
`PosNgramExtractor(n=2, tagset="coarse", spacy_model="en_core_web_trf")`

*Şu durumda kullanın:* sözdizimsel stil öznitelikleri — sözcük türü (POS) etiketi
dizileri — istediğinizde; içerik sözcüklerine duyarsız, kayıt ve sözdizimsel kayda
duyarlıdır.
*Şu durumda kullanmayın:* spaCy ardışık düzeniniz bir etiketleyici içermiyorsa (çoğu
`_trf` modeli içerir) ya da belgeler çok kısaysa.
*Beklenen sonuç:* POS n-gramları üzerinde yoğun sayım matrisi. `tagset="coarse"`
(varsayılan) Universal POS etiketlerini kullanır (`token.pos_`; daha az boyut);
`tagset="fine"` modelin ince taneli etiketlerini kullanır (`token.tag_`).

#### DependencyBigramExtractor
`DependencyBigramExtractor(spacy_model="en_core_web_trf", lowercase=True)`

*Şu durumda kullanın:* sözdizimsel stil öznitelikleri — özellikle spaCy tarafından
çözümlenen (head-lemma, bağımlılık-ilişkisi, child-lemma) üçlüleri — istediğinizde.
*Şu durumda kullanmayın:* ayrıştırıcı bir darboğazsa; bağımlılık çözümlemesi spaCy
ardışık düzeninin en yavaş adımıdır ve POS n-gramlarıyla ikame edilebilir.
*Beklenen sonuç:* `head|dep|child` lemma üçlüleri üzerinde yoğun sayım matrisi.

#### FunctionWordExtractor
`FunctionWordExtractor(wordlist=None, language=None, scale="none")`

*Şu durumda kullanın:* belgenin dili için kısa, konudan bağımsız işlev sözcüğü
listesini — stilometrinin klasik konu karşıtı sinyali — istediğinizde.
*Şu durumda kullanmayın:* derleminiz belge başına dil etiketi olmaksızın dilleri
karıştırıyorsa — dile özgü sözcük listesi uygulanmaz.
*Beklenen sonuç:* varsayılan olarak ham sayımlardan oluşan `(n_docs, |wordlist|)` matris;
`scale="zscore"` göreli frekansları (`sayım / belgedeki toplam sözcük sayısı`) z-puanlar,
`"l1"` / `"l2"` satırları normalize eder. `wordlist` verilmezse sözcük listesi `language`
(ya da derlem dili) için paketlenmiş listeden gelir (bkz. [Languages](languages.md)).

#### PunctuationExtractor
`PunctuationExtractor()`

*Şu durumda kullanın:* neredeyse konudan bağımsız saf stil öznitelikleri istediğinizde
— noktalama kullanımı dikkat çekici biçimde yazara özgü ve derlem açısından sağlamdır.
*Şu durumda kullanmayın:* kaynak metin normalleştirilmişse veya noktalama işaretleri
çıkarılmışsa (örn. düzeltme yapılmamış OCR çıktısı).
*Beklenen sonuç:* Python'un `string.punctuation` dizisindeki her karakter için bir sütun
içeren, ham sayımlardan oluşan `(n_docs, 32)` matris. `scale` argümanı almaz; belgelerin
uzunlukları farklıysa sonradan normalize edin.

#### ReadabilityExtractor
`ReadabilityExtractor(indices=None, language=None)`

*Şu durumda kullanın:* okunabilirliği bir stil özniteliği olarak — Flesch, FK-grade,
Gunning Fog vb. — MFW ile birleştirmek istediğinizde.
*Şu durumda kullanmayın:* okunabilirlik bizzat sorunun kendisiyse (bu durumda metriği
doğrudan okuyun; Delta'ya dahil etmeyin). İngilizce dışı diller için dile özgü yerel formül
varyantını kullanın — bkz. `concepts/languages.md`.
*Beklenen sonuç:* her indeks için bir sütun içeren `(n_docs, k)` matris. `indices=None`
ile dilin varsayılanı kullanılır — İngilizce için `flesch`, `flesch_kincaid`,
`gunning_fog`; `coleman_liau`, `ari` ve `smog` da `indices=` ile kullanılabilir.

#### SentenceLengthExtractor
`SentenceLengthExtractor(spacy_model="en_core_web_trf")`

*Şu durumda kullanın:* cümle ritmi imzasını — cümle başına belirteç sayısının ortalama,
standart sapma ve çarpıklığını — istediğinizde. Küçük ama güçlü bir stilistik sinyal.
*Şu durumda kullanmayın:* metinde yoğun cümle sınırı hataları varsa (örn. BÜYÜK HARFLE
yazılmış hukuki metin çoğu cümle bölücüyü bozar).
*Beklenen sonuç:* `mean`, `sd`, `skew` sütunlarından oluşan `(n_docs, 3)` matris.

#### LexicalDiversityExtractor
`LexicalDiversityExtractor(indices=("ttr", "yules_k"))`

*Şu durumda kullanın:* sözcüksel çeşitlilik öznitelikleri — TTR, MATTR, MTLD, HD-D,
Yule'ün K/I'sı, Herdan'ın C'si, Simpson'ın D'si — istediğinizde. Sekiz indeks
duyarlılıkları karşılaştırmanıza olanak tanır.
*Şu durumda kullanmayın:* belgeler çok kısaysa (<200 belirteç); çoğu indeks kararsız
hale gelir.
*Beklenen sonuç:* istenen her indeks için bir sütun içeren `(n_docs, k)` matris (varsayılan
`indices=("ttr", "yules_k")`; örneğin `["ttr", "mattr", "mtld", "hdd"]` verin). Bir ölçünün
tanımsız olduğu yerde değer NaN olur ve uyarı verilir: 42 belirteçten kısa metinlerde HD-D,
hiçbir tam faktör tamamlanmadığında MTLD, her belirteç tekil olduğunda Yule'ün I'sı
(`V²/(M2 − V)`). `bitig run` NaN öznitelikleri bir yönteme aktarmak yerine reddeder. Her
kısa metin NaN vermez: MATTR 100 belirteçlik penceresinin altında düz TTR'ye geri döner ve
boş bir belge TTR, MATTR, MTLD, Yule'ün K'sı, Herdan'ın C'si ve Simpson'ın D'si için 0.0
alır.

#### SentenceEmbeddingExtractor
`SentenceEmbeddingExtractor(model=None, language=None, pool="mean", device=None)`

*Şu durumda kullanın:* modern sinirsel gömme öznitelik kümesi — belge başına havuzlanmış
sentence-transformer çıktısı — istediğinizde. Sınıflandırma ve kümelemede güçlü; orta
büyüklükteki derlemler için yeterince hızlı.
*Şu durumda kullanmayın:* donanımınızda GPU / MPS yoksa ve derleminiz büyükse (CPU
çıkarımı yavaştır) ya da yorumlanabilirlik önemliyse (bu vektörler opaktır).
*Beklenen sonuç:* `(n_docs, embedding_dim)` yoğun matris. `model=None` ile model,
uydurma sırasında dile göre seçilir (İngilizce: `sentence-transformers/all-mpnet-base-v2`).
`bitig[embeddings]` gerektirir.

#### ContextualEmbeddingExtractor
`ContextualEmbeddingExtractor(model=None, language=None, layer=-1, pool="mean", device=None, max_length=512)`

*Şu durumda kullanın:* belge başına toplanmış HuggingFace model gizli durumları —
yapılandırılabilir havuzlama (`pool="mean"`, `"cls"` veya `"max"`) ile dile özgü gömmeler (örn. Türkçe için
`dbmdz/bert-base-turkish-cased`) — istediğinizde.
*Şu durumda kullanmayın:* belirli bir modelin temsilini gerektirmiyorsanız —
daha hafif ve hızlı bir varsayılan için `SentenceEmbeddingExtractor` kullanın.
*Beklenen sonuç:* `(n_docs, hidden_dim)` yoğun matris. `model=None` ile model dile göre
seçilir (İngilizce: `bert-base-uncased`; Türkçe: `dbmdz/bert-base-turkish-cased`).
`bitig[embeddings]` gerektirir.

## Öznitelikleri birleştirme

Çok öznitelikli matris oluşturmanın iki yolu:

### Python

```python
from bitig import MFWExtractor, PunctuationExtractor

mfw = MFWExtractor(n=200, scale="zscore").fit_transform(corpus)
punct = PunctuationExtractor().fit_transform(corpus)
combined = mfw.concat(punct)  # (n_docs, n_mfw + n_punct)
```

### study.yaml

```yaml
features:
  - id: mfw
    type: mfw
    n: 200
    scale: zscore
  - id: punct
    type: punctuation
```

Yöntemler öznitelik kimliklerine başvurabilir; çalıştırıcı her matrisi bir kez oluşturur ve yeniden kullanır.

## Adli dilbilim öznitelik çıkarıcıları

Konu-değişmez iki çıkarıcı `bitig.forensic` altında yer alır:

#### CategorizedCharNgramExtractor
`CategorizedCharNgramExtractor(n=3, categories=None, scale="none", lowercase=False)`

*Şu durumda kullanın:* adli doğrulama için konudan bağımsız karakter düzeyinde öznitelikler
istediğinizde — n-gramlar sözcükteki konuma göre sınıflandırılır; böylece yalnızca stili
taşıyan kategorileri (ekler, noktalama) tutup konuya duyarlı tam sözcük kategorisini
düşürebilirsiniz.
*Şu durumda kullanmayın:* konu sağlamlığı hedef değilse — düz bir `CharNgramExtractor`
daha hızlı ve boyut başına daha fazla sinyal taşır.
*Beklenen sonuç:* seçilen n-gram kategorileriyle kısıtlanmış yoğun sayım matrisi.
Varsayılan `categories=None` yedi kategorinin tümünü tutar, yani filtreleme yapmaz.

Sapkota ve ark. 2015, konular arasında en iyi sonucu ek + noktalama n-gramlarının
verdiğini bulmuştur; bu alt küme için `categories=("prefix", "suffix", "punct")` değerini
açıkça verin.

#### distort_corpus
`distort_corpus(corpus, mode="dv_ma")`

*Şu durumda kullanın:* Stamatatos (2017) konu maskeleme istediğinizde — içerik sözcüklerini
yer tutucularla değiştirirken işlev sözcüklerini ve noktalamayı korur. Konudan bağımsız
bir ardışık düzen için herhangi bir çıkarıcıyla eşleştirin.
*Şu durumda kullanmayın:* analiziniz içerik sözcüğü sinyaline ihtiyaç duyuyorsa (örn.
ayırt edici sözcük dağarcığını arayan Zeta).
*Beklenen sonuç:* mevcut herhangi bir çıkarıcıya beslediğiniz yeni bir Corpus nesnesi.
Her iki mod da işlev-sözcük listesinde olmayan her sözcüğü maskeler: `"dv_ma"`
(varsayılan) maskelenen sözcüğün uzunluğunu korur, `"dv_sa"` onu tek bir `*`'a indirger.

Bkz. [Konu-değişmez öznitelikler](../forensic/topic-invariance.md).

## Ölçekleme

`MFWExtractor`, `CharNgramExtractor`, `WordNgramExtractor`, `FunctionWordExtractor` ve
`CategorizedCharNgramExtractor` `scale ∈ {"none", "zscore", "l1", "l2"}` parametresini kabul eder:

- `none` — ham sayımlar. Bayesian Wallace–Mosteller için kullanın.
- `l1` — satırlar, tutulan öznitelikler üzerinde toplamı 1 olacak şekilde normalize edilir. Zeta-benzeri karşıtlık yöntemleri için kullanın.
- `l2` — birim normlu satırlar. Kosinüs tabanlı uzaklıklar için kullanın.
- `zscore` — eğitim ortalamaları / standart sapmalarına göre sütun bazında z-puanı (Stylo kuralı). MFW için z-puanlanan değerler göreli frekanslardır: `sayım / belgedeki toplam sözcük sayısı` (`FunctionWordExtractor` için de aynı); karakter ve sözcük n-gramlarında payda belgedeki toplam n-gram sayısıdır. `CategorizedCharNgramExtractor` ham sayımları z-puanlar. **Burrows Delta için zorunludur.**

Z-puanı ortalaması / standart sapması `fit` aşamasında öğrenilir ve `transform` sırasında uygulanır; dolayısıyla görülmemiş belgeler üzerindeki puanlar eğitim dağılımını kullanır. `cross_validate_bitig(..., extractor=..., corpus=...)` çıkarıcıyı her eğitim katında yeniden uydurur; böylece dışarıda tutulan belgeler sözcük dağarcığını ya da bu istatistikleri etkilemez (bkz. [Methods](methods.md)).

## Sonraki adım

- [Methods](methods.md) — FeatureMatrix'i alıp Result üretmek.
