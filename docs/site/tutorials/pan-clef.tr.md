# Öğretici: PAN-CLEF yazar doğrulama

PAN-CLEF tarzı bir yapı üzerinde uçtan uca adli yazar doğrulama işlem hattı. Sonunda şunlara
sahip olacaksınız: **kalibre edilmiş bir General Impostors puanlayıcı**, tam **PAN metrik seti**,
bir **Tippett grafiği** ve LR çerçeveli ve zincir-of-custody meta verisi içeren bir
**adli HTML raporu**.

!!! info "PAN-CLEF hakkında"
    [PAN @ CLEF](https://pan.webis.de) paylaşımlı görevi, 2013'ten bu yana her yıl yazar
    doğrulama değerlendirmeleri düzenlemektedir. Her yılın derleminde her biri
    `(known_docs, questioned_doc)` çifti olan ve ikili gerçek etiketle etiketlenmiş
    `same-author` / `different-author` *denemelerden* oluşan bir koleksiyon bulunur.
    Standart metrik menüsü AUC + c@1 + F0.5u + Brier + cllr'dir.

    Bu öğretici, gerçek PAN derlemi indirmesi gerektirmeden uçtan uca çalışması için
    **yapay** bir PAN tarzı veri kümesi kullanır. Gerçek veriler için yapay yükleyiciyi
    `load_pan_trials("path/to/pan22/pairs.jsonl")` ile değiştirin.

## Görev

Girdi:

- Çok sayıda yazarın belgelerinden oluşan bir **referans popülasyon** (*sahte yazar havuzu*).
- Her biri şunları içeren bir **doğrulama denemeleri kümesi**:
    - `questioned_id` — tek bir sorgulanan belge
    - `known_ids` — bir veya daha fazla bilinen-yazarlı belge
    - `is_target` — ikili gerçek etiket (1 = Q ve K'yı aynı yazar yazdı; 0 = farklı)

Her deneme için üretin:

- **Kalibre edilmiş posterior** p(aynı-yazar | kanıt)
- **log₁₀ olabilirlik oranı**
- AUC, c@1, F0.5u, Brier, ECE, C_llr içeren genel **PANReport**

## 1. Yapay derlem oluşturun

```python
import numpy as np
from bitig.corpus import Corpus, Document

rng = np.random.default_rng(42)
VOCAB = [
    # Letter-only tokens so MFW's regex picks them up
    *[f"{a}{b}" for a in "abcdefgh" for b in "abcdefgh"]
]

def _author_profile():
    """Each author has an idiosyncratic Dirichlet profile over the shared vocabulary."""
    return rng.dirichlet(np.ones(len(VOCAB)) * 0.4)

def _sample_doc(profile, n_words=800):
    return " ".join(rng.choice(VOCAB, size=n_words, p=profile).tolist())

N_AUTHORS = 40
authors = {f"A{i:02d}": _author_profile() for i in range(N_AUTHORS)}

# Two docs per author: one goes to the known set, one is the candidate for questioning.
documents = []
for author, profile in authors.items():
    for sample_idx in range(2):
        doc_id = f"{author}_s{sample_idx}"
        documents.append(
            Document(
                id=doc_id,
                text=_sample_doc(profile),
                metadata={"author": author, "sample": sample_idx},
            )
        )
corpus = Corpus(documents=documents)
print(f"Corpus: {len(corpus)} documents from {N_AUTHORS} authors")
```

## 2. Denemeleri tanımlayın

PAN denemesinin bilinen K kümesi, sorgulanan Q belgesi ve bir etiketi vardır. Aynı-yazar
ve farklı-yazar çiftleri arasında dengeli olan denemeler oluştururuz.

```python
from dataclasses import dataclass

@dataclass
class Trial:
    trial_id: str
    known_ids: list[str]
    questioned_id: str
    is_target: int          # 1 = same author; 0 = different

trials: list[Trial] = []
author_list = sorted({d.metadata["author"] for d in documents})

for candidate in author_list:
    # Known set: the candidate's sample 0.
    k_id = f"{candidate}_s0"

    # Same-author trial: questioned = the candidate's sample 1.
    trials.append(Trial(
        trial_id=f"T_{candidate}_same",
        known_ids=[k_id],
        questioned_id=f"{candidate}_s1",
        is_target=1,
    ))

    # Different-author trial: questioned = sample 1 from a random OTHER author.
    other = rng.choice([a for a in author_list if a != candidate])
    trials.append(Trial(
        trial_id=f"T_{candidate}_diff_{other}",
        known_ids=[k_id],
        questioned_id=f"{other}_s1",
        is_target=0,
    ))

print(f"{len(trials)} trials ({sum(t.is_target for t in trials)} target / "
      f"{sum(1 - t.is_target for t in trials)} non-target)")
```

## 3. Paylaşımlı bir öznitelik uzayı çıkarın

Q, K ve sahte yazarların aynı sözcük dağarcığında bulunması için öznitelik matrisini bir kez
birleştirilmiş derlem üzerinde oluşturun.

```python
from bitig import MFWExtractor

fm = MFWExtractor(n=500, scale="zscore", lowercase=True).fit_transform(corpus)

# Index by document id for easy slicing below.
id_to_row = {doc_id: i for i, doc_id in enumerate(fm.document_ids)}
```

## 4. Her deneme için General Impostors çalıştırın

Her deneme için şunları bir araya getiririz:

- Sorgulanan belge satırı
- Bilinen belge satırları
- Sahte yazar havuzu = aday yazar hariç herkes

```python
from bitig.features import FeatureMatrix
from bitig.forensic import GeneralImpostors

def slice_fm(rows: list[int]) -> FeatureMatrix:
    return FeatureMatrix(
        X=fm.X[rows],
        document_ids=[fm.document_ids[i] for i in rows],
        feature_names=fm.feature_names,
        feature_type=fm.feature_type,
    )

gi = GeneralImpostors(n_iterations=100, feature_subsample_rate=0.5, seed=42)

scores, labels = [], []
for trial in trials:
    q_rows = [id_to_row[trial.questioned_id]]
    k_rows = [id_to_row[kid] for kid in trial.known_ids]
    candidate_author = corpus.documents[k_rows[0]].metadata["author"]

    # Impostor pool: all docs from OTHER authors except the questioned one itself.
    impostor_rows = [
        id_to_row[d.id]
        for d in corpus.documents
        if d.metadata["author"] != candidate_author and d.id != trial.questioned_id
    ]

    result = gi.verify(
        questioned=slice_fm(q_rows),
        known=slice_fm(k_rows),
        impostors=slice_fm(impostor_rows),
    )
    scores.append(result.values["score"])
    labels.append(trial.is_target)

scores = np.array(scores)
labels = np.array(labels)
print(f"mean score (target trials): {scores[labels == 1].mean():.3f}")
print(f"mean score (non-target):    {scores[labels == 0].mean():.3f}")
```

Bu yapay kurulumda iki ortalama açıkça ayrılmış olmalıdır (≈ 0,8 / ≈ 0,2).

## 5. Kalibre edin

Ham GI puanları ayrım biçimlidir ancak olasılık değildir. Çıktının savunulabilir bir posterior
olması için ayrılmış bir bölümde kalibre edin.

```python
from bitig.forensic import CalibratedScorer, log_lr_from_probs

# 60/40 split — calibrate on the first 60%, evaluate on the rest.
n = len(scores)
cut = int(0.6 * n)
perm = rng.permutation(n)
cal_idx, test_idx = perm[:cut], perm[cut:]

scorer = CalibratedScorer(method="platt").fit(scores[cal_idx], labels[cal_idx])
test_probs = scorer.predict_proba(scores[test_idx])
test_log_lrs = scorer.predict_log_lr(scores[test_idx])
test_labels = labels[test_idx]

print(f"calibrated posterior range: [{test_probs.min():.2f}, {test_probs.max():.2f}]")
print(f"log-LR range:               [{test_log_lrs.min():.2f}, {test_log_lrs.max():.2f}]")
```

## 6. PAN değerlendirmesi

```python
from bitig.forensic import compute_pan_report

report = compute_pan_report(
    probs=test_probs,
    y=test_labels,
    log_lrs=test_log_lrs,
    c_at_1_margin=0.05,   # 5 % abstention band around 0.5
)
for k, v in report.to_dict().items():
    if isinstance(v, float):
        print(f"  {k:12s} {v:.3f}")
    else:
        print(f"  {k:12s} {v}")
```

Yapay kurulumda beklenen çıktı (yaklaşık):

```
  auc          0.97
  c_at_1       0.92
  f05u         0.91
  brier        0.10
  ece          0.04
  cllr_bits    0.24
  n_target     20
  n_nontarget  20
```

## 7. Tippett grafiği

```python
import matplotlib.pyplot as plt
from bitig.forensic import tippett

data = tippett(test_log_lrs, test_labels)

fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
ax.step(data["thresholds"], data["target_cdf"],
        where="post", label="same author", linewidth=2)
ax.step(data["thresholds"], data["nontarget_cdf"],
        where="post", label="different author", linewidth=2, linestyle="--")
ax.set_xlabel(r"log$_{10}$(LR) threshold")
ax.set_ylabel(r"P(log$_{10}$-LR ≥ threshold | class)")
ax.set_title("Tippett plot — GI + Platt calibration")
ax.legend()
fig.tight_layout()
fig.savefig("tippett.png", dpi=300, bbox_inches="tight")
```

İyi ayrım yapan bir sistem, pozitif log-LR'ler boyunca hedef CDF'nin 1,0'a yakın kalmasını
ve hedef-dışı CDF'nin hızla düşmesini gösterir.

## 8. Adli HTML raporu

Test kümesi sonuçlarını bitig `Result` olarak kaydedin, `Provenance` üzerine delil zinciri
meta verisi damgalayın ve LR çerçeveli adli raporu oluşturun.

```python
import json
import spacy
from pathlib import Path
from bitig.provenance import Provenance
from bitig.result import Result
from bitig.report import build_forensic_report

run_dir = Path("pan_demo")
(run_dir / "gi").mkdir(parents=True, exist_ok=True)

result = Result(
    method_name="general_impostors",
    params={"n_iterations": 100, "feature_subsample_rate": 0.5, "seed": 42},
    values={
        "score_mean_target":    float(test_probs[test_labels == 1].mean()),
        "score_mean_nontarget": float(test_probs[test_labels == 0].mean()),
        "n_trials": int(len(test_labels)),
    },
    provenance=Provenance.current(
        spacy_model="n/a",
        spacy_version=spacy.__version__,
        corpus_hash=corpus.hash(),
        feature_hash=fm.provenance_hash,
        seed=42,
        resolved_config={"method": "pan_tutorial"},
        questioned_description="PAN-style verification trials (synthetic corpus)",
        known_description="one known sample per candidate, 40 authors",
        hypothesis_pair="H1: candidate wrote Q; H0: different author wrote Q",
        acquisition_notes="synthetic Dirichlet-multinomial profiles, seed 42",
        custody_notes="reproducible from tutorial code above",
    ),
)
result.save(run_dir / "gi")

build_forensic_report(
    run_dir,
    output=run_dir / "report.html",
    title="PAN-style verification — demo",
    lr_summaries={"general_impostors": {
        "log_lr": f"{test_log_lrs.mean():.2f}",
        "lr":     f"{10 ** test_log_lrs.mean():.1f}",
    }},
)
print(f"report: {run_dir / 'report.html'}")
```

HTML'yi tarayıcıda açın: hipotez bloğu, delil zinciri bloğu, ENFSI sözel ölçeği yorumuyla
yöntem düzeyinde LR özeti ve yeniden üretilebilirlik köken bilgisini içeren tek sayfalık adli
bir rapor elde edersiniz.

## Gerçek PAN verilerine geçiş

Gerçek PAN derlemleri için:

```python
import json

def load_pan_trials(jsonl_path):
    """PAN-style format: one JSON object per line with known-texts + unknown-text + truth."""
    trials = []
    with open(jsonl_path) as f:
        for line in f:
            obj = json.loads(line)
            trials.append(Trial(
                trial_id=obj["id"],
                known_ids=obj["known_ids"],
                questioned_id=obj["questioned_id"],
                is_target=int(obj["same_author"]),
            ))
    return trials
```

İndirme talimatları ve derlem lisans koşulları
[pan.webis.de](https://pan.webis.de) adresindedir. PAN 2020 ve 2022 yazar doğrulama
derlemleri en büyük kamuya açık aynı-yazar kıyaslama veri kümeleri arasındadır.

## Yeniden üretilebilirlik notları

- Bu öğreticideki her rastgele seçim tohumlanmıştır (`rng = np.random.default_rng(42)` +
  `GeneralImpostors(seed=42)` + deterministik olan `scorer.method="platt"`).
- Aynı Python + numpy + scikit-learn sürümleriyle yeniden çalıştırma, özdeş `Result.values`
  üretir (kayan nokta yuvarlaması dışında).
- `Provenance` kaydı tüm sürümleri yakalar; herhangi bir sapma tespit edilebilir.

Her bileşenin daha ayrıntılı belgeleri için bkz. [Adli araç seti](../forensic/index.tr.md).
