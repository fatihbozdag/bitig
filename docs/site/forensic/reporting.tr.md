# Raporlama

*Şu durumda kullanın:* kalibre edilmiş bir doğrulama `Result` nesneniz varsa ve adli biçimde bir rapora ihtiyacınız varsa: delil zinciri meta verisi, iki yönlü Nordgaard et al. (2012) / ENFSI (2015) sözel ölçeğine dayalı olabilirlik oranı (LR) ifadesi ve denetlenebilir bir HTML artefaktı.
*Şu durumda kullanmayın:* keşifsel bir araştırma şekli istiyorsanız — `concepts/results.md` içindeki standart raporlama yolunu kullanın.
*Beklenen sonuç:* sabit bölümlere sahip oluşturulmuş bir HTML raporu: test edilen hipotezler, delil zinciri, yöntem başına kalibre edilmiş LR ve sözel ifadesi, şekiller ve parametreler, kanıtsal sorumluluk reddi ve köken bilgisi.

Adli raporlar bir puandan fazlasını gerektirir: test edilen **hipotez çifti (hypothesis pair)**, tanımlanan **bilinen ve sorgulanan** materyal, kaynak dosyalara uzanan **delil zinciri (chain of custody)** izi ve metriklerin analiz koşullarına bağlı olduğunu belirten **kanıtsal sorumluluk reddi**.

## build_forensic_report

*Şu durumda kullanın:* `Result` nesnesinden HTML'e tek çağrıyla ulaşmak istiyorsanız. Delil zinciri alanlarını, kalibre edilmiş LR'leri ve sözel ölçek ifadelerini bir Jinja2 şablonuna aktarır.
*Şu durumda kullanmayın:* araştırma makalesi şekli üretiyorsanız — standart `bitig report` CLI'yı veya `concepts/methods.md` içindeki çizim yardımcılarını kullanın.
*Beklenen sonuç:* oluşturulan HTML dosyasının yolu (yalnızca HTML; Tippett grafiği için PAN-CLEF eğitimindeki gibi `bitig.forensic.tippett` ile kendi çiziminizi kullanın).

```python
from bitig.report import build_forensic_report

build_forensic_report(
    "results/case_001",
    output="results/case_001/forensic_report.html",
    title="R v Smith — yazar analizi",
    lr_summaries={
        "general_impostors": {"log_lr": "1.34", "lr": "21.9"},
        "unmasking":          {"log_lr": "1.10", "lr": "12.6"},
    },
)
```

`lr_summaries` içindeki değerler kalibre edilmiş olabilirlik oranları olmalıdır; örneğin vakanın kendi denemesi için `CalibratedScorer.predict_log_lr` çıktısı. Ham bir General Impostors puanı bir kazanma oranı, bir Unmasking puanı ise bir doğruluk düşüşü ölçüsüdür; hiçbiri LR değildir, bu nedenle önce [kalibrasyondan](calibration.md) geçirilmelidir. Sözel ifade, sayısal `lr` (veya `10 ** log_lr`) değerinden `bitig.forensic.verbal_scale.lr_verbal_statement` ile hesaplanır ve hiçbir zaman elle yazılmaz.

Şablon bölümleri:

1. **Test edilen hipotezler** — yalnızca `Provenance` üzerinde `hypothesis_pair`, `questioned_description` veya `known_description` doldurulmuşsa oluşturulur.
2. **Delil zinciri** — yalnızca `acquisition_notes`, `custody_notes` veya `source_hashes` doldurulmuşsa oluşturulur.
3. **Yöntem başına LR bloğu** — yalnızca `lr_summaries` sözlüğü geçirilmişse oluşturulur. log₁₀(LR), LR, iki yönlü sözel ifade (destek gücü ve desteklenen önerme) ve ölçeğin güç bantları gösterilir.
4. **Yöntem başına şekiller + parametreler** (kaydedilmiş `Result` dizininden).
5. **Kanıtsal sorumluluk reddi** — her zaman oluşturulur.
6. **Yeniden üretilebilirlik köken bilgisi** — her zaman oluşturulur (`Provenance` kaydının tam JSON'u).

## Delil zincirinin doldurulması

Provenance oluştururken adli alanları geçirin:

```python
from bitig.provenance import Provenance

provenance = Provenance.current(
    spacy_model="en_core_web_trf",
    spacy_version=spacy.__version__,
    corpus_hash=corpus.hash(),
    feature_hash=fm.provenance_hash,
    seed=42,
    resolved_config=cfg.model_dump(),
    questioned_description="W-2026-0815 numaralı arama kararıyla 2026-03-15 tarihinde el konulan e-posta zinciri",
    known_description="Şüphelinin Gmail hesabından 2024-2026 dönemine ait 15 kişisel e-posta",
    hypothesis_pair="H1: şüpheli tarafından yazılmıştır; H0: şüpheli dışında biri tarafından yazılmıştır",
    acquisition_notes="Tam sürücü görüntüsü; delil zinciri el koymadan analize kadar bütündür",
    custody_notes="Elde etme sonrasında değişiklik yapılmamıştır. Aşağıdaki SHA-256 değerleri orijinal dosyalarla eşleşmektedir.",
    source_hashes={
        "questioned_1": "a1b2c3...",
        "known_1":       "d4e5f6...",
        "known_2":       "...",
    },
)
```

## HTML güvenliği

Adli rapor şablonu, Jinja2 otomatik kaçış (autoescape) etkin olarak oluşturulur — kullanıcı tarafından sağlanan her dize (delil zinciri notları, hipotez metni, kaynak özetler) HTML karakter referanslarıyla kaçırılır. `custody_notes` içindeki bir `<script>` etiketi, tarayıcıda HTML açıldığında çalıştırılmak yerine `&lt;script&gt;` olarak oluşturulur.

## Kanıtsal sorumluluk reddi

Şablon, ENFSI (2015) değerlendirmeli raporlama kılavuzundan uyarlanmış standart bir sorumluluk reddi içerir:

> Çıktı, uzman adli dilbilim kararını bilgilendirmeye yöneliktir; yerini almaz.
> Burada bildirilen olabilirlik oranları, belirli bilinen ve sorgulanan materyal,
> seçilen öznitelik uzayı ve kullanılan kalibrasyon kümesine koşulludur. Kalibrasyon
> koşulları dışındaki popülasyonlara genelleme yapılması uygun değildir. Raporlama,
> Avrupa Adli Bilimler Enstitüleri Ağı'nın (ENFSI 2015) önerdiği çerçeveyi izler.

Özel bir şablon sağlayarak sorumluluk reddini geçersiz kılabilirsiniz; referans uygulama için yerleşik `src/bitig/report/templates/forensic_lr.html.j2` dosyasına bakın.

## Sözel ölçek

*Şu durumda kullanın:* bir log-LR değerini adli raporda beklenen sade dil tanımlayıcısına çevirmeniz gerekiyorsa (ENFSI 2015 / Nordgaard ve diğerleri 2012).
*Şu durumda kullanmayın:* istatistiksel bir kitleye rapor sunuyorsanız — log-LR değerini `C_llr` ile birlikte doğrudan aktarın.
*Beklenen sonuç:* log-LR değerinin büyüklüğüne ve desteklenen önermeyi belirleyen işaretine karşılık gelen tek satırlık sözel ifade.

Sözel ölçek, pratisyenlerin İngilizce ankor terimini koruyabilmesi için her iki dilde sunulmaktadır:

| \|log₁₀(LR)\| aralığı | English | Turkish |
|---|---|---|
| 0 – 1 | weak support | *zayıf destek* |
| 1 – 2 | moderate support | *ılımlı destek* |
| 2 – 3 | moderately strong support | *ılımlı güçlü destek* |
| 3 – 4 | strong support | *güçlü destek* |
| 4 – 6 | very strong support | *çok güçlü destek* |
| ≥ 6 | extremely strong support | *son derece güçlü destek* |

Ölçek iki yönlüdür: LR > 1 aynı yazar önermesini (Hp), LR < 1 farklı yazar önermesini (Hd) destekler; bir LR ile tersi için destek gücü aynıdır. Ölçek tek bir yerde, `bitig.forensic.verbal_scale.LR_LADDER` içinde tanımlanır; raporlar onu buradan okur.

## Referans

::: bitig.report.render.build_forensic_report

::: bitig.provenance.Provenance
    options:
      members:
        - current
        - from_dict
        - to_dict
        - has_forensic_metadata
