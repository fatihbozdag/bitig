# Corpus

`Corpus`, bir `Document` listesi ve (örtük olarak) bu belgelerin üst verisidir. Her ikisi de `bitig.corpus` içinde tanımlanmış veri sınıflarıdır.

## Derlem oluşturma

### Dosya sisteminden

```bash
bitig ingest corpus/ --metadata corpus/metadata.tsv
```

`metadata.tsv`, ilk sütunu `filename` olan (değerler `corpus/` dizinindeki dosya adlarıyla eşleştirilir) ve diğer her sütunun `Document.metadata` alanına dönüştüğü sekmeyle ayrılmış bir dosyadır:

```tsv
filename	author	year	genre
fed_01.txt	Hamilton	1787	political essay
fed_10.txt	Madison	1787	political essay
fed_50.txt	Unknown	1788	political essay
```

### Python ile

```python
from bitig.io import load_corpus
corpus = load_corpus("corpus/", metadata="corpus/metadata.tsv", strict=True)
```

- `strict=True` (varsayılan): Üst veri satırı eksik olan her belge için hata fırlatır.
- `strict=False`: Kısmi kapsama izin verir — yeni etiketlenmemiş bir belge geldiğinde kullanışlıdır.

### Programatik olarak

```python
from bitig.corpus import Corpus, Document

corpus = Corpus(documents=[
    Document(id="q", text=q_text, metadata={"role": "questioned"}),
    Document(id="k1", text=k1_text, metadata={"author": "Alice"}),
    Document(id="k2", text=k2_text, metadata={"author": "Alice"}),
])
```

## Filtreleme ve gruplama

`Corpus.filter(**query)`, belirtilen her anahtar-değer çiftini karşılayan belgelerden oluşan yeni bir Corpus döndürür:

```python
hamiltonian = corpus.filter(author="Hamilton")
train_only = corpus.filter(role="train")
```

Birden fazla değerle eşleştirmek için bir liste kullanılabilir:

```python
two_authors = corpus.filter(author=["Hamilton", "Madison"])
```

`Corpus.groupby(field)`, alt derlemlerin bulunduğu bir sözlük döndürür:

```python
grouped = corpus.groupby("author")
# {"Hamilton": Corpus(...), "Madison": Corpus(...), "Jay": Corpus(...)}
```

## Özetleme

`Corpus.hash()`, sıralanmış `(belge kimliği, metin özeti, üst veri özeti)` üçlülerinden ve dilden türetilen kararlı bir SHA-256 özeti üretir; böylece her metin kendi kimliğine ve etiketlerine bağlanır: iki belgenin metinlerini yer değiştirmek özeti değiştirir. Bu özet, her `Provenance` kaydına eklenir; böylece aynı derlemle çalışan iki çalışma, dosya sistemi yolundan, çalışma zamanından veya giriş dizinindeki belge sıralamasından bağımsız olarak aynı özeti paylaşır.

`Provenance.corpus_hash_scheme`, değeri hangi özetleme şemasının ürettiğini kaydeder. Şema 2 (bitig 0.3.2+), metinleri ve kimlikleri birbirinden bağımsız iki liste olarak özetleyen ve onları birbirine bağlamayan şema 1'in yerini almıştır; farklı şemalardan gelen özetler karşılaştırılamaz.

!!! note "Sıra duyarlılığı"
    `Corpus.hash()` tasarım gereği sıra-değişmezdir (aynı metinler + üst veri = aynı özet). Öznitelik matrisi düzenini etkileyen satır yeniden sıralamalarını tespit etmek gibi sıra-duyarlı bir özete ihtiyaç duyarsanız, `[d.id for d in corpus.documents]` listesini ayrıca özetleyin.

## Sonraki adım

- [Features](features.md) — derlemin sayısal matrise dönüştürülmesi.
