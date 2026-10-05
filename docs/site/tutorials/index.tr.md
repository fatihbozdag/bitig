# Öğreticiler

bitig ile birlikte üç çalıştırılabilir öğretici gelir.

## [Federalist Papers](federalist.tr.md)

Mosteller & Wallace'ın (1964) klasik yazar tespiti çalışmasını 85 Federalist Papers üzerinde
yeniden ele alın. Örnek derlem yalnızca makale gövdelerini içerir (başlıklar ve yazar imzaları
çıkarılmıştır) ve No. 58'i Madison olarak etiketler; bu nedenle 11 tartışmalı makale vardır
(No. 49–57, 62, 63). Bildirimsel bir çalışma tek yazarlı makaleleri inceler; tartışmalı
makaleler ardından bilinen makaleler üzerinde eğitilen `bitig delta` ve `bitig bayesian` ile
atanır.

Gösterilen konular: derlem aktarımı, MFW öznitelik çıkarımı, Burrows Delta, PCA
görselleştirmesi, Ward dendrogramı, Hamilton ile Madison arasında Craig Zeta karşıtlığı ve
`--test-filter` ile yazar atama.

## [PAN-CLEF doğrulama](pan-clef.tr.md)

PAN-CLEF tarzı bir yapı üzerinde uçtan uca adli yazar doğrulama işlem hattı: sorgulanan
belgeyi aday yazarın bilinen örnekleriyle ve bir sahte yazar havuzuyla eşleştirin, General
Impostors ile puanlayın, Platt ölçeklendirme ile kalibre edin ve delil zinciri bilgisiyle
LR çerçeveli adli HTML raporu dahil tam PAN metrik setini raporlayın —
AUC, c@1, F0.5u, Brier, ECE, C_llr.

Gösterilen konular: uçtan uca `bitig.forensic` iş akışı.

## [Türkçe stilometri](turkish.tr.md)

Bir Türkçe proje kurun (`bitig init --language tr`) ve Türkçe Wikisource'dan alınan, kamu
malı Ömer Seyfettin öykülerinden oluşan bir derlemi MFW, PCA ve Ward kümeleme ile inceleyin.

Gösterilen konular: Türkçe dil profili, `bitig[turkish]` eki ve Stanza, `bitig run`
komutunun ayrıştırma yapmadan oluşturduğu öznitelikler.
