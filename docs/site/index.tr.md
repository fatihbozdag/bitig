---
hide:
  - navigation
---

# bitig

<p align="center">
  <img src="assets/bitig-banner.svg" alt="bitig — hesaplamalı stilometri" style="max-width: 100%;">
</p>

`bitig`, **yazar tespiti**, **yazar grupları arasında üslup karşılaştırması** ve **adli
yazarlık analizi** için geliştirilmiş bir Python paketi ve komut satırı aracıdır. R'ın
`Stylo` paketinin temel yöntemlerini (Delta, Zeta, PCA/MDS, kümeleme, bootstrap konsensüs
ağaçları, sınıflandırma) kapsar; bunlara bir spaCy işlem hattı, transformer gömmeleri, bir
Bayes katmanı (PyMC), olabilirlik oranı kalibrasyonlu yazar doğrulama ve delil zinciri
özetleri ile mühürlü raporlar içeren bir vaka iş akışı ekler.

Ad, Eski Türkçede *yazı* ya da *yazıt* anlamına gelen ve 8. yüzyıl Orhon yazıtlarına
kazınan türden metni karşılayan sözcükten gelir.

## Mimari

<p align="center">
  <img src="assets/bitig-architecture.svg" alt="derlem → öznitelikler → yöntemler → adli → çıktı" style="max-width: 100%;">
</p>

Öznitelik çıkarıcılar, Delta sınıflandırıcıları ve Bayes yazar tespit modeli birer
scikit-learn kestiricisidir. Her `Result` köken bilgisini taşır (derlem özeti, öznitelik
özeti, tohum, kütüphane sürümleri, zaman damgası, çözümlenmiş yapılandırma); böylece
`study.yaml` olarak yazılan bir çalışma, aynı tohum ve kütüphane sürümleriyle aynı
değerlere yeniden üretilebilir (bkz. [Sonuçlar ve köken bilgisi](concepts/results.md)).

## Hızlı gezinti

<div class="grid cards" markdown>

-   :fontawesome-solid-rocket:{ .lg .middle } **Başlarken**

    ---

    bitig'yı kurun, ilk derlemizi oluşturun ve CLI'dan bir Burrows Delta çalışması çalıştırın.

    [:octicons-arrow-right-24: Kurulum ve hızlı başlangıç](getting-started.md)

-   :material-book-open-page-variant:{ .lg .middle } **Kavramlar**

    ---

    Derlem → Öznitelikler → Yöntemler → Sonuçlar. İşlem hattının dört katmanı, açıklamalı.

    [:octicons-arrow-right-24: Kavramlar](concepts/index.md)

-   :material-shield-search:{ .lg .middle } **Adli dilbilim araç takımı**

    ---

    General Impostors ve Unmasking ile doğrulama, olabilirlik oranı kalibrasyonu, PAN değerlendirmesi ve Adli Laboratuvar vaka iş akışı.

    [:octicons-arrow-right-24: Adli dilbilim araç takımı](forensic/index.md)

-   :material-school:{ .lg .middle } **Öğreticiler**

    ---

    Federalist Papers üzerinde Mosteller & Wallace'ı izleyin, uçtan uca PAN tarzı doğrulama yapın ve Türkçe düzyazıyı çözümleyin.

    [:octicons-arrow-right-24: Öğreticiler](tutorials/index.md)

</div>

## Neler var?

| Katman | İçerik |
|---|---|
| **Derlem** | `.txt` + TSV meta veri, filtreleme ve gruplama, her metni kimliğine ve meta verisine bağlayan bir derlem özeti |
| **Öznitelikler** | en sık sözcükler, karakter / sözcük / POS n-gramları, bağımlılık bigramları, işlev sözcükleri, noktalama, cümle uzunluğu, okunabilirlik (6 İngilizce gösterge ile Türkçe, Almanca, İspanyolca ve Fransızca için yerel formüller), 8 sözcüksel çeşitlilik göstergesi, cümle ve bağlamsal gömmeler |
| **Yöntemler** | Burrows, Eder, Eder Simple, Argamon, Cosine ve Quadratic Delta; Zeta (klasik, Eder); PCA, MDS, t-SNE, UMAP; Ward, k-means, HDBSCAN; bootstrap konsensüs ağaçları; stilometriye uygun çapraz doğrulamalı sklearn sınıflandırıcıları (tabakalı, bir yazarı dışarıda bırak, bir metni dışarıda bırak); Bayesçi Wallace–Mosteller ve hiyerarşik grup karşılaştırması |
| **Adli dilbilim** | General Impostors ve Unmasking ile doğrulama; konu sağlamlığı için Sapkota karakter n-gram kategorileri ve Stamatatos metin çarpıtması; Platt / izotonik kalibrasyonla log-LR; C_llr, AUC, c@1, F0.5u (PAN tanımları), ECE, Brier, Tippett verileri; Nordgaard vd. (2012) tarafından önerilen ve ENFSI (2015) tarafından benimsenen iki yönlü sözel ölçekle LR çerçeveli HTML raporu; delil zinciri özetleri ve mühürlü raporlar içeren vaka iş akışı ([Adli Laboratuvar](forensic/case-workflow.md)) |
| **Diller** | İngilizce, Türkçe, Almanca, İspanyolca, Fransızca: dile özgü işlev sözcükleri, okunabilirlik ve gömme varsayılanları; Türkçe çözümleme Stanza (BOUN treebank'ı) ile |
| **Çıktı** | her yöntem için `result.json` + Parquet tabloları + şekiller; HTML / Markdown raporları; vaka raporlarının PDF dışa aktarımı (`bitig[reports]`) |

Dokümantasyon İngilizce ve Türkçedir (`/tr/`).

## Durum

PyPI'daki son sürüm **0.3.1**'dir (`pip install bitig`). `main` dalı henüz yayımlanmamış
değişiklikler içerir; bunların bir kısmı sonuçları ya da davranışı değiştirir (vaka
mühürleri, General Impostors varsayılanları, kalibrasyon, PAN ölçütleri, öznitelik
ölçekleme). [`CHANGELOG.md`](https://github.com/fatihbozdag/bitig/blob/main/CHANGELOG.md)
bunları **[results]** ve **[breaking]** etiketleriyle listeler.

## Lisans ve atıf

BSD-3-Clause. Bkz. [`LICENSE`](https://github.com/fatihbozdag/bitig/blob/main/LICENSE).

bitig'yı yayımlanmış bir çalışmada kullanıyorsanız lütfen
[`CITATION.cff`](https://github.com/fatihbozdag/bitig/blob/main/CITATION.cff) aracılığıyla atıf yapın.
