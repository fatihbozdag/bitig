# Adli Laboratuvar: vaka iş akışı

*Şu durumda kullanın:* bir soruşturmanın tüm parçalarını bir arada tutmanız gerekiyorsa:
özet değerleriyle delil dosyaları, analiz ayarları, her çalıştırma ve sonunda dondurulup
mühürlenen bir rapor.
*Şu durumda kullanmayın:* bir derlemi keşfediyor ya da yöntemleri karşılaştırıyorsanız.
Bunun için bir `study.yaml` ile `bitig run` kullanın ([Kavramlar](../concepts/index.md))
veya aşağıda bağlantısı verilen adli API sayfalarına bakın.
*Beklenen sonuç:* her vaka için bir dizin. Delil değişmiş, eksik ya da kayıt dışıysa bitig
çalıştırmayı ve imzalamayı reddeder; `bitig case verify` mühürlü vakayı daha sonra
yeniden denetler.

**Vaka** (Case), Adli Laboratuvar'ın temel birimidir. Grafik arayüz (`bitig gui`, ardından
*Forensic Lab →*) sizi beş adımda yönlendirir: Evidence (delil), Method (yöntem), Run
(çalıştırma), Findings (bulgular) ve Report (rapor). `bitig case` komutları aynı dizinler
üzerinde çalışır, Python'daki `bitig.cases.Case` sınıfı da öyle.

!!! warning "Mührün kanıtladıkları ve kanıtlamadıkları"
    Varsayılan olarak imzalı bir vaka **yalnızca özet değerleriyle** (*Null* eklentisi)
    mühürlenir. Vaka dizinine yazma erişimi olan herkes vakayı değiştirip tüm özet
    değerlerini yeniden hesaplayabilir. Bu yüzden Null mührü bir bütünlük kaydıdır,
    kurcalamaya karşı bir kanıt **değildir**. Kurcalamayı ortaya koyan bir mühür için HMAC
    eklentisi, gizli bir anahtar ve bu anahtara sahip bir doğrulayıcı gerekir (bkz.
    [Null ve HMAC](#null-ve-hmac)).

## Vaka yapısı

Vakalar varsayılan olarak `~/.bitig/cases/` altında tutulur. Her CLI komutu başka bir kök
dizin için `--cases-dir` alır. Grafik arayüz her zaman varsayılan kökü kullanır.

```text
<cases-dir>/<vaka-kimliği>/
├── case.json              # vaka kaydı (elle düzenlemeyin)
├── study.yaml             # reçeteden üretilen çözümlenmiş analiz yapılandırması
├── evidence/
│   ├── questioned/        # sorgulanan belgeler
│   ├── known/             # yazarı bilinen belgeler
│   └── control/           # boş oluşturulur; analizde kullanılmaz
├── runs/
│   ├── <run-id>/          # her çalıştırma için bir dizin (UTC zaman damgası)
│   └── latest -> <run-id> # dosya sistemi destekliyorsa sembolik bağ
└── report/
    ├── draft.html         # imzasız vakanın çalışma raporu
    ├── signed.html        # imzalama anında dondurulan rapor
    └── signed.json        # mühür
```

Vaka kimliği tek bir yol bileşeni olmalıdır (`[A-Za-z0-9._-]+`). `case.json` şunları
içerir:

- kimlik: `id`, `title`, `examiner`, `created_at`
- ayarlar: `recipe`, `mode`, `overrides`
- kayıtlı delil (yol, `sha256`, boşluğa göre token sayısı, rol, yazar)
- `study_hash`, `corpus_hash`, `runs`, `latest_run` ve `latest_run_state_hash`
- imza alanları
- yalnızca ekleme yapılabilen `custody_log`
- `forked_from`

bitig `case.json` dosyasını güvenilmeyen girdi olarak yükler. Vaka dizininin dışını
gösteren delil yolları ve çalıştırma kimlikleri reddedilir. Bir vaka nesnesi, yüklendikten
sonra değişmiş bir `case.json` dosyasının üzerine kaydetmeyi reddeder; böyle bir durumda
vakayı yeniden yükleyin.

## Reçeteler ve kip

Bir vaka bir **reçete** (recipe) ile oluşturulur. Reçete, varsayılan öznitelikleri ve
yöntemleri olan adlandırılmış bir sorudur. `--recipe` verilmezse `bitig case new`
`imposters_lr` kullanır.

| Reçete kimliği | Soru | Kip |
|---|---|---|
| `imposters_lr` | Bu metni bu kişi mi yazdı? (General Impostors ile yazar doğrulama) | forensic |
| `delta_attribution` | N yazardan hangisi? | research |
| `exploration` | Bu derlemin yapısı nasıl? (PCA + hiyerarşik kümeleme) | research |
| `zeta_contrast` | A grubunu B grubundan ne ayırıyor? | research |
| `bayesian` | N aday üzerinde Bayesçi yazar sonsal dağılımı | research |
| `custom` | Elle düzenlenmiş çalışma (arayüzdeki *Custom* kutucuğu) | türetilir |

Kip (mode) seçilmez, türetilir. Herhangi bir `verify` yöntemi içeren çalışma **forensic**,
diğer her çalışma **research** kipindedir. Kip, rapor şablonunu belirler.

Parametreleri (ör. *Candidate author* yani aday yazar, MFW boyutu, yineleme sayısı,
tohum) arayüzün Method adımında ya da Python'da `Case.set_param` ile değiştirirsiniz.
Bunlar için bir CLI komutu yoktur. İki yol da `study.yaml` dosyasını yeniden üretir ve
özet değerini kaydeder. bitig dışında düzenlenmiş bir `study.yaml` fark edilir;
çalıştırma ve imzalama onu reddeder.

## Adım adım örnek (CLI + Python)

Bu komutlar bitig'in geliştirme sürümünde gösterildiği gibi çalıştırıldı. Her komut
`--cases-dir cases` aldığı için `~/.bitig` altına hiçbir şey yazılmaz.

**1. Küçük bir yapay derlem oluşturun.** İki bilinen yazarı ve bir sorgulanan mektubu
vardır.

```python title="make_texts.py"
import pathlib, random

random.seed(1)
common = "the of and to a in that it is was he for on as with his at by but not".split()
styles = {
    "alice": "garden morning light quiet window letter river softly perhaps indeed".split(),
    "bob": "engine market figures report quarterly deadline budget meeting numbers".split(),
}
out = pathlib.Path("texts")
out.mkdir(exist_ok=True)
for name, style in [("alice_1", "alice"), ("alice_2", "alice"),
                    ("bob_1", "bob"), ("bob_2", "bob"), ("letter", "alice")]:
    words = random.choices(common * 2 + styles[style], k=400)
    (out / f"{name}.txt").write_text(" ".join(words) + ".\n", encoding="utf-8")
```

**2. Vakayı oluşturun ve delili kaydedin.**

```bash
python make_texts.py
bitig case new letter-2026 --title "Anonymous letter" --examiner "J. Doe" --cases-dir cases
bitig case add-evidence letter-2026 texts/letter.txt --role questioned --cases-dir cases
bitig case add-evidence letter-2026 texts/alice_1.txt texts/alice_2.txt \
    --role known --author Alice --cases-dir cases
bitig case add-evidence letter-2026 texts/bob_1.txt texts/bob_2.txt \
    --role known --author Bob --cases-dir cases
bitig case status letter-2026 --cases-dir cases
```

```text
registered evidence/questioned/letter.txt  sha256=5d57c5c6828e…
...
  evidence:  questioned=1, known=4, control=none
  runs:      0
  custody: OK
```

**3. Parametreleri ayarlayın ve analizi çalıştırın.** `imposters_lr` bir *Candidate
author* (aday yazar) ister. Parametreler için CLI komutu olmadığından onları Python'dan
(ya da arayüzün Method adımında) ayarlayın:

```python title="set_params.py"
from bitig.cases import Case

case = Case.load("cases/letter-2026")
case.set_param("methods[verify].candidate", "Alice")  # şüphelinin yazar etiketi
case.set_param("methods[verify].mfw_n", 50)           # küçük örnek metinler
```

Ardından vakayı `bitig case run` ile çalıştırın:

```bash
python set_params.py
bitig case run letter-2026 --cases-dir cases
```

```text
  ✓ verify
  run: cases/letter-2026/runs/2026-10-02T10-28-12Z
succeeded — All 1 method(s) succeeded.
```

Çalıştırıcının ilerleme günlüğü stderr'e gider ve yukarıda gösterilmemiştir. Aday yazar
parametresi olmadan aynı komut `blocked — Set the 'Candidate author' parameter …`
yazdırır ve 2 koduyla çıkar. Arayüzün Run adımı da, Python'dan
`bitig.case_run.perform_run(case)` de aynı işi yapar (bkz.
[Analizi çalıştırma](#analizi-calstrma)).

**4. İmzalayın ve doğrulayın.**

```bash
bitig case sign letter-2026 --cases-dir cases
bitig case verify letter-2026 --cases-dir cases
```

```text
  ✓ case_state_hash: matches sealed value
  ✓ report_html_hash: report matches sealed value
  ✓ run_outputs: 4 run file(s) match sealed hashes
  ✓ unregistered_files: no unregistered files under evidence/
  ✓ evidence_custody: all evidence files match registered hashes
  ✓ signer: signed by 'J. Doe'
  ✓ signature: UNSIGNED (Null plugin): hashes only — anyone with write access can
recompute them, so this seal is not tamper-evident
UNSIGNED — hashes consistent, but letter-2026 has a Null seal: this is not evidence
against tampering by anyone with write access. Sign with --signature-plugin hmac for a
tamper-evident seal.
```

Komut **3** koduyla çıkar: özet değerleri sağlamdır, ancak Null mührü kurcalamayı ortaya
koymaz (bkz. [Mührü doğrulama](#muhru-dogrulama)).

**5. Bir çatalda devam edin.** İmzalı vaka artık salt okunurdur.

```bash
bitig case fork letter-2026 letter-2026-b --cases-dir cases
bitig case list --cases-dir cases
```

## Delil ve delil zinciri

### Roller

| Rol | Nasıl eklenir | Notlar |
|---|---|---|
| `questioned` | `bitig case add-evidence <id> <dosyalar…> --role questioned` | Yazarlığı tartışmalı belgeler. Varsayılan olarak doğrulama her sorgulanan belgeyi hedefler. |
| `known` | `bitig case add-evidence <id> <dosyalar…> --role known --author <etiket>` | CLI ve arayüz bir yazar etiketi ister. Doğrulama bilinen metinleri yazara göre gruplar. |
| `control` | Arayüzün Evidence adımı, yalnızca forensic vakalar (`Case.set_control_corpus`) | Yalnızca bir referanstır (`corpus_id`, `n_docs`). **Hiçbir çalıştırıcı onu kullanmaz.** Raporlar onu "not used by the analysis" (analizde kullanılmadı) olarak listeler. |

`add-evidence` her dosyayı `evidence/<rol>/` altına kopyalar, SHA-256 özet değerini
hesaplar ve `case.json` dosyasına kaydeder. Şunları reddeder:

- zaten var olan bir hedef dosyayı;
- diğer rol altında zaten kayıtlı bir dosya kökünü. Dosya kökü çalıştırmadaki belge
  kimliğidir, bu yüzden `questioned/alice.txt` ile `known/alice.txt` birlikte var olamaz;
- imzalı bir vakada yapılan her değişikliği.

**Yalnızca kayıtlı dosyalar analiz edilir ve mühürlenir.** Bir çalıştırma derlemini
kayıtlı girdilerden kurar ve her dosyayı okurken özet değerini yeniden hesaplar.
`evidence/` dizinini asla taramaz. `evidence/` altına elle kopyalanan bir dosya yok
sayılır. `bitig case status` böyle dosyaları kayıt dışı olarak listeler ve
`bitig case verify` bunun için `unregistered_files` denetiminde başarısız olur.

### Delil zinciri denetimi ve uyuşmazlıklar

bitig her kayıtlı dosyanın özet değerini yeniden hesaplar ve kayıtlı `sha256` ile
karşılaştırır. Eksik bir dosya da uyuşmazlık sayılır. Uyuşmazlık olduğu sürece:

- `bitig case status` dosyaları listeler ve **2** koduyla çıkar;
- çalıştırma **engellenir**;
- imzalama reddedilir;
- uyuşmazlığı kabul etmediğiniz sürece çatallama reddedilir (bkz.
  [Çatallama](#catallama)).

Bundan sonra ne yapacağınız nedene bağlıdır.

**Dosya meşru bir nedenle değişti** (ör. farklı satır sonlarıyla yeniden dışa aktarıldı).
Dosyayı gerekçesiyle birlikte yeniden onaylayın:

```bash
bitig case reacknowledge letter-2026-b evidence/known/bob_1.txt \
    --reason "Re-exported by the client" --cases-dir cases
```

```text
re-acknowledged evidence/known/bob_1.txt: 5d9655fb4ba4… → f4b35d03c52f… by J. Doe
  Re-run the analysis before signing: bitig case run letter-2026-b
```

Bu işlem `custody_log` kaydına `at`, `by` (varsayılan: inceleyen kişi ya da `--by`),
`path`, `old_sha256`, `new_sha256` ve `reason` alanlarını içeren bir girdi ekler ve yeni
özet değerini kaydeder. Delil zinciri günlüğü mühürlü vaka durumunun bir parçasıdır ve
raporda *Re-acknowledged evidence changes* başlığı altında görünür. Vaka durumunu da
değiştirdiği için imzalamadan önce analizi yeniden çalıştırmanız gerekir. bitig şunları
yeniden onaylamayı reddeder:

- gerekçe verilmediğinde;
- kayıtlı olmayan bir yolu veya değişmemiş bir dosyayı;
- imzalı bir vakayı;
- **eksik** bir dosyayı. Bunun yerine vakayı çatallayın.

Arayüzün Evidence adımında uyuşmayan her kartta bir *Re-acknowledge* düğmesi bulunur.

**Dosya eksik ya da hiç değişmemesi gerekiyordu.** Vakayı çatallayın ve gerekçenizi
kaydedin (bkz. [Çatallama](#catallama)).

## Analizi çalıştırma

```bash
bitig case run <id> --cases-dir cases
```

`bitig case run`, arayüzün Run adımı ve Python'daki `bitig.case_run.perform_run(case)`
aynı işi yapar. Şu ön koşulları sırayla denetler ve ilk başarısız olanda bir mesajla
birlikte `blocked` döndürürler:

1. vaka imzalı;
2. bir delil zinciri uyuşmazlığı var;
3. `study.yaml` bitig dışında değiştirilmiş;
4. çalışma yapılandırması geçersiz;
5. `verify` yöntemleri için:
    - en az bir sorgulanan belge kayıtlı;
    - her bilinen belgenin bir yazar etiketi var;
    - *Candidate author* parametresi ayarlı ve bilinen bir yazarla eşleşiyor;
    - sahte yazar (impostor) görevi gören en az bir başka yazar var;
    - açıkça verilmiş bir `target_ids` listesi tam olarak kayıtlı sorgulanan belgeleri
      adlandırıyor.

Ön koşullar geçildikten sonra bitig `study.yaml` dosyasını yeniden üretir, derlemi kayıtlı
delilden kurar ve çalıştırmanın üzerinde hesaplandığı vaka durumu özet değerini kaydeder.
Çalıştırma `runs/<UTC zaman damgası>/` altına yazar. Sonucun `status` değeri şunlardan
biridir:

| Durum | Anlamı |
|---|---|
| `succeeded` | Her yöntem bir sonuç üretti; çalıştırma `latest_run` olur. |
| `partial` | Bazı yöntemler `error.txt` yazdı; çalıştırma yine de kaydedilir. |
| `failed` | Hiçbir yöntem başarılı olmadı; çalıştırma dizini diskte kalır ama **kaydedilmez**. |
| `blocked` | Bir ön koşul çalıştırmayı reddetti; hiçbir şey yürütülmedi. |

`bitig case run` her yöntem için `✓` ya da (hatasıyla birlikte) `✗` yazdırır, ardından
çalıştırma dizinini ve durumu gösterir. Çıkış kodu, her yöntem başarılıysa **0**,
`partial` ya da `failed` için **1**, `blocked` için **2**'dir.

!!! note "Sorgulanan belgeler ve `target_ids`"
    `target_ids` boş ya da ayarlanmamışsa `verify` yöntemi, parametreleri ayarladıktan
    sonra kaydedilenler dahil, her kayıtlı sorgulanan belgeyi hedefler. `Case.set_param`
    ve arayüzdeki çekmece otomatik doldurulan hedef listesini kaydetmez.

    `overrides` içinde açıkça verilmiş bir `target_ids` listesi tam olarak kayıtlı
    sorgulanan belgeleri adlandırmalıdır. Böyle bir liste ya siz ayarladığınız için ya da
    daha eski bir bitig sürümü `set_param` çağrısında onu dondurduğu için oradadır. Liste
    bir sorgulanan belgeyi dışarıda bırakıyorsa ya da kayıtlı bir sorgulanan belge
    olmayan bir kimlik içeriyorsa, çalıştırma hiçbir şey yürütülmeden engellenir:

    ```text
    blocked — The verify method's target list does not match the questioned evidence:
    questioned document(s) ['alice_2'] are not targeted. Clear or update 'target_ids'
    (an empty list targets every questioned document).
    ```

    Her sorgulanan belgeyi hedeflemek için `case.set_param("methods[verify].target_ids",
    [])` ile düzeltin ya da listenin tamamını verin.

## Raporlar

`bitig.report.case_report.build_case_report(case)` imzasız bir vaka için
`report/draft.html` dosyasını oluşturur. Arayüzün Report adımı bu raporu gösterir.
Forensic ya da research şablonu vakanın kipine göre seçilir.

- **Forensic rapor**:
    - soru, öne çıkan değerler, yöntem paragrafı ve şekiller;
    - delil zinciri (rol, dosya, token sayısı, özet değeri), yeniden onaylanan
      değişiklikler ve çatal notu;
    - köken bilgisi alt bilgisi (derlem, öznitelik ve çalışma özet değerleri, tohum,
      bitig sürümü) ve vaka özet değeri.

  `imposters_lr` için rapor, şans düzeyinin yanında **her sorgulanan belge için bir
  General Impostors puanı** verir. Puanı kalibre edilmemiş, **olabilirlik oranı
  olmayan** ve ENFSI sözel ölçeği uygulanmayan bir değer olarak etiketler. Olabilirlik
  oranı, Hp/Hd hipotezleri ve sözel ölçek yalnızca sonuç gerçekten kalibre edilmiş bir
  `lr` ya da `log_lr` içerdiğinde görünür. Bunu nasıl elde edeceğiniz için bkz.
  [Kalibrasyon](calibration.md).
- **Research rapor**: araştırma sorusu (reçete), öne çıkan sonuç, yöntemler, şekiller,
  kayıtlı delil ve delil zinciri günlüğü.

`build_case_report(case, format="pdf")` WeasyPrint ile `report/final.pdf` dosyasını
yazar. Bunun için `pip install "bitig[reports]"` gerekir; arayüzde bunun için bir *Export
PDF* düğmesi vardır. İmzalı bir vakada iki işlev de dondurulmuş `signed.html` dosyasını
sunar ve onu asla yeniden oluşturmaz. Mühür artık yeniden üretilemiyorsa dışa aktarmayı
**reddeder**. Dışa aktarma sırasında HMAC imzasının kendisi denetlenmez.

## İmzalama ve mühürleme

```bash
bitig case sign <id> [--signed-by AD] [--signature-plugin null|hmac] --cases-dir cases
```

Aşağıdakilerin hepsi sağlanmadıkça imzalama reddedilir (`Cannot sign: …`):

- delil kayıtlı;
- delil zinciri sağlam;
- `study.yaml` düzenlenmemiş;
- başarılı bir çalıştırma var;
- bu çalıştırma **güncel** vaka durumu üzerinde hesaplanmış. Çalıştırmadan sonra delili
  yeniden onaylarsanız ya da ayarları değiştirirseniz önce yeniden çalıştırmanız gerekir.

İmzalama, raporu SIGNED başlığıyla oluşturur ve `report/signed.html` olarak dondurur.
Ayrıca `report/signed.json` dosyasını yazar:

| Alan | Neyi bağlar |
|---|---|
| `case_state_hash` | kimlik, inceleyen kişi, reçete, overrides, `study.yaml` özet değeri, her delil girdisi (rol, yol, özet değeri, token sayısı, yazar), control referansı, delil zinciri günlüğü ve `forked_from` üzerinden SHA-256 |
| `report_html_hash` | dondurulmuş `signed.html` |
| `latest_run`, `run_manifest` | **en son** çalıştırma dizinindeki her dosyanın özet değeri (sonuçlar, tablolar, şekiller, çözümlenmiş yapılandırma) |
| `signed_at`, `signed_by`, `signature_plugin_id`, `bitig_version` | kimin, ne zaman ve nasıl imzaladığı |

İmzalama atomiktir. Mühür dosyaları önce geçici adlarla yazılıp yerlerine taşınır,
`case.json` dosyasına `signed: true` en son yazılır. Herhangi bir adım başarısız olursa
vaka imzasız kalır. İmzalamadan sonra vaka **salt okunurdur**: delil eklemek, parametre
değiştirmek, çalıştırmak ve yeniden onaylamak "Fork it for further work" mesajıyla
reddedilir. Önceki çalıştırmalar, `draft.html` ve dışa aktarılan `final.pdf` mühürün
kapsamında değildir.

### Null ve HMAC

| | Null (varsayılan) | HMAC (`--signature-plugin hmac`) |
|---|---|---|
| Eklediği | hiçbir şey: yalnızca özet değerleri | imzalayan dahil tüm `signed.json` yükü üzerinde bir HMAC-SHA256 `signature` bloğu (`scheme: 2`) ve bir anahtar parmak izi |
| Anahtar | yok | `BITIG_SIGNATURE_KEY` ortam değişkeninden paylaşılan bir gizli anahtar (anahtar yoksa imzalama başarısız olur) |
| Kurcalamayı ortaya koyar mı? | **Hayır.** Yazma erişimi olan herkes vakayı düzenleyip tüm özet değerlerini yeniden hesaplayabilir. | Evet, anahtara sahip olmayan herkese karşı. Bu, paylaşılan gizli anahtara dayalı bir şemadır; açık anahtarlı ya da donanım destekli bir imza değildir. |
| Sağlam olduğunda `verify` kararı | `UNSIGNED — hashes consistent, but … has a Null seal` (çıkış 3) | anahtarla `seal verified — … is intact` (çıkış 0); anahtar olmadan `CANNOT VERIFY` (çıkış 4) |

```bash
export BITIG_SIGNATURE_KEY="change-me"      # gerçek anahtarı kabuk geçmişinin dışında tutun
bitig case sign letter-2026-b --signature-plugin hmac --cases-dir cases
```

Arayüzdeki *Sign & lock* düğmesi her zaman **Null** eklentisini kullanır. HMAC mührü için
CLI'ı kullanın.

### Mührü doğrulama

```bash
bitig case verify <id> [--key ANAHTAR] --cases-dir cases
```

`verify` mühürlenmiş her değeri diskten yeniden hesaplar. Her denetim için `✓` (geçti),
`✗` (başarısız) ya da `?` (denetlenemedi) yazdırır:

| Denetim | Ne zaman başarısız olur |
|---|---|
| `case_state_hash` | kanonik vaka durumunda herhangi bir şey değiştiğinde |
| `report_html_hash` | `signed.html` değiştiğinde ya da eksik olduğunda |
| `run_outputs` | mühürlü çalıştırmadaki bir dosya değiştirildiğinde, silindiğinde ya da eklendiğinde; `latest_run` değiştiğinde; ya da mühür `run_manifest` öncesine aitse ("legacy seal", bitig 0.3.1 ve öncesi) |
| `unregistered_files` | `evidence/` altında hiç kaydedilmemiş bir dosya olduğunda (bu dosya mühürün kapsamında **değildir**) |
| `evidence_custody` | bir delil dosyası kayıtlı özet değeriyle artık eşleşmediğinde ya da eksik olduğunda |
| `signer` | `case.json` içindeki `signed_by` / `signed_at`, `signed.json` ile farklı olduğunda |
| `signature` | `case.json` ve `signed.json` içindeki eklenti kimlikleri uyuşmadığında; HMAC imzası eksik ya da geçersizse; ya da `--key` verildiği halde mühürde imza yoksa. Anahtar olmadan denetlenen bir HMAC imzası `✗` değil `?` ile işaretlenir. |

Çıkış kodları:

| Çıkış | Karar | Anlamı |
|---|---|---|
| **0** | `seal verified` | her denetim geçti ve HMAC imzası geçerli |
| **1** | `… is not signed` | vaka imzasız; doğrulanacak bir şey yok |
| **2** | `SEAL BROKEN` | en az bir denetim başarısız oldu (kurcalama ya da uyuşmazlık) |
| **3** | `UNSIGNED` | özet değerleri sağlam, ancak mühür bir Null mührü ve kurcalamayı ortaya koymaz |
| **4** | `CANNOT VERIFY` | özet değerleri sağlam, ancak HMAC imzası anahtar olmadan denetlenemez |

Yalnızca 0 çıkış kodu, kurcalamayı ortaya koyan bir mührün denetlendiği anlamına gelir.
HMAC mührü için `--key` verin ya da `BITIG_SIGNATURE_KEY` ayarlayın. Anahtar olmadan imza
denetimi `?` ile işaretlenir:

```text
  ✓ signer: signed by 'J. Doe'
  ? signature: CANNOT VERIFY: HMAC signature present but no key provided (pass
signature_key= or set BITIG_SIGNATURE_KEY)
CANNOT VERIFY — hashes consistent, but letter-2026-b carries an HMAC signature and no key
was given (--key or $BITIG_SIGNATURE_KEY).
```

Doğru anahtarla denetim `✓ signature: HMAC signature valid` olur ve karar
`seal verified — letter-2026-b is intact` olur. Yanlış anahtarla
`✗ signature: HMAC signature INVALID (wrong key or tampered payload)` hatası ve 2 çıkış
koduyla başarısız olur.

Açıkça verilen bir `--key` her zaman geçerli bir HMAC **gerektirir**, bu yüzden
kaldırılmış ya da düşürülmüş bir imza geçemez: `--key` ile doğrulanan bir Null mührü
`a signature key was supplied but the seal carries no signature` hatasıyla başarısız olur
(çıkış 2). Yalnızca `BITIG_SIGNATURE_KEY` içinde bulunan bir anahtar HMAC mühürlerini
denetler, ancak bir Null mührünü 3 çıkış kodunda bırakır. İmza satırına bu durumda
`$BITIG_SIGNATURE_KEY is set: if this case was signed with HMAC, its signature has been
removed` notu eklenir. Vakanın HMAC ile imzalandığını biliyorsanız `--key` verin.

Python'da `Case.verify_seal(signature_key=…)` bir `SealVerification` döndürür. Onun
`status` değeri `not_signed`, `broken`, `unverifiable`, `unsigned` ya da `verified`
olur; bunlar sırasıyla 1, 2, 4, 3 ve 0 çıkış kodlarına karşılık gelir.

İmzalı bir vakada `bitig case status` da mühür artık yeniden üretilemiyorsa uyarır. Bu
uyarı imza denetimini atlar. Arayüzün Report adımında, HMAC mühürleri için isteğe bağlı
bir anahtar alan bir *Verify seal* penceresi vardır; bu pencere anahtarsız denetlenen bir
HMAC mührü için *CANNOT VERIFY* gösterir.

## Çatallama

```bash
bitig case fork <id> <yeni-id> [--title T] [--examiner E] \
    [--acknowledge-mismatch "gerekçe"] --cases-dir cases
```

Çatal (fork) yeni ve imzasız bir vakadır. Şunları kopyalar:

- reçete ve overrides;
- control referansı;
- yeniden kaydedilen her kayıtlı delil dosyası.

Çalıştırmalar, raporlar ve imza durumu kopyalanmaz. Her çatal `forked_from` kaydını
tutar:

- üst vakanın kimliği, zaman ve üst vakanın `case_state_hash` değeri;
- üst vakanın kayıtlı delil özet değerleri;
- varsa delil zinciri uyuşmazlıkları.

`forked_from` çatalın mühürlü durumunun bir parçasıdır ve rapor bununla ilgili bir not
yazdırır.

Kaynak vaka delil zinciri denetiminden geçemezse çatallama **reddedilir**: kopyalama,
değiştirilmiş dosyalara temiz bir vakada yeni özet değerleri verirdi.
`--acknowledge-mismatch "<gerekçe>"` çatallamaya izin verir ve gerekçeyi
`acknowledged_reason` olarak saklar. Kaynakta eksik olan dosyalar kopyalanamaz ve
`omitted_missing` altında listelenir.

```text
$ bitig case fork demo demo-2 --cases-dir cases
error: Source case 'demo' has a chain-of-custody mismatch on evidence/known/bob_2.txt.
Forking would register the altered files under fresh hashes; pass an acknowledgement
reason to fork anyway (it is recorded in the fork).
```

Arayüzde çatallama düğmesi yoktur. Arayüzün mesajları `bitig case fork` komutunu önerir.

## Vakaları listeleme ve inceleme

| Komut | Gösterdikleri |
|---|---|
| `bitig case list` | `--cases-dir` altındaki her vakanın tablosu (kimlik, kip, reçete, delil sayısı, çalıştırmalar, imza, başlık). Okunamayan vakalar bildirilir ve atlanır. |
| `bitig case open <id>` | yol, kip, reçete, inceleyen kişi, imza durumu, en son çalıştırma |
| `bitig case status <id>` | tüm kayıt alanları, özet değerleri, delil envanteri, delil zinciri denetimi (`--no-verify` atlar; uyuşmazlıkta çıkış 2) ve kayıt dışı dosyalar; imzalı vakalar için mühür uyarısı |

## Grafik arayüzde

`bitig gui` için `pip install "bitig[gui]"` gerekir. Vaka listesine (`/case`) ve *New
case* düğmesine ulaşmak için *Forensic Lab →* bağlantısını açın. Beş adım şunlardır:

- **Evidence**: sorgulanan ve bilinen dosyaları kaydedin (bilinen dosyalar bir yazar
  etiketi ister), control referansını ayarlayın, delil zinciri durumunu görün ve
  değişmiş dosyaları yeniden onaylayın. *Add file* yerel dosya seçiciyi kullanır, bu
  yüzden `--no-native` altında devre dışıdır.
- **Method**: bir reçete kutucuğu seçin, parametrelerini çekmecede düzenleyin ya da
  `study.yaml` için *Custom* düzenleyicisini açın.
- **Run**: `perform_run` çalıştırır ve başarılı ya da başarısız olan yöntemleri listeler.
- **Findings**: en son çalıştırmanın sonuçlarını gösterir.
- **Report**: taslak raporu gösterir; *Export PDF*, *Sign & lock* (yalnızca Null
  eklentisi) ve *Verify seal* (isteğe bağlı HMAC anahtarı) düğmeleri vardır.

## Sırada ne var

- [Doğrulama](verification.md): `imposters_lr` reçetesinin arkasındaki General Impostors
  yöntemi
- [Kalibrasyon ve LR çıktısı](calibration.md): puanları olabilirlik oranlarına
  dönüştürmek
- [Raporlama](reporting.md): Case iş akışı dışındaki bağımsız adli rapor
