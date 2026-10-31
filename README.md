# TEKNOFEST Savaşan İHA – Test Yarışma Sunucusu (Raspberry Pi)

Bu klasör, Raspberry Pi'yi **TEKNOFEST hakem sunucusunun bir kopyası** gibi çalıştırır.
API, "Savaşan İHA Yarışması Haberleşme Dokümanı 2026"daki adresleri, alan adlarını ve
durum kodlarını taklit eder. Böylece yer istasyonu yazılımınızı yarışmadan önce gerçekçi
bir sunucuya karşı deneyebilirsiniz.

> Bu resmi sunucu değildir. Dokümanda yazmayan davranışlar en alttaki
> "Varsayımlar" bölümünde ayrıca belirtilmiştir.

## Ne yapar?

- Dokümandaki 7 uç noktanın hepsi: giriş, sunucu saati, telemetri, kilitlenme, kamikaze, QR, HSS
- Gerçekçi hatalar: oturumsuz istek 401, hatalı paket 204, aralık dışı değer 400,
  **2 Hz üstü telemetri 400 + "3"**
- Telemetri cevabında etrafınızda dönen **3 sahte rakip uçak**
- Tarayıcıdan açılan **hakem paneli**: takımların telemetri hızı, 1 saniyeyi aşan boşluklar
  (ceza adayları), son hata nedeni, kilitlenme ve kamikaze bildirimleri, HSS duyurusu
- Gelen her paketin zaman damgalı kaydı (`kayitlar/` klasörü)

## Dosyalar

| Dosya | Görevi |
| --- | --- |
| `sunucu.py` | Test sunucusu |
| `ayarlar.yaml` | Takımlar, şifreler, sahte rakipler, QR, HSS, test ayarları |
| `istemci_test.py` | Sunucuyu deneyen istemci; aynı zamanda yer istasyonu için örnek kod |
| `requirements.txt` | Gerekli Python paketleri |
| `teknofest-sunucu.service` | Pi açılınca sunucuyu otomatik başlatma dosyası |
| `ag_ayarla.sh` | Pi'nin IP'sini ve sunucu portunu tek komutla ayarlar |
| `SAHA_TESTI.md` | Switch kurulumu ve YKİ yazılımını test sunucusuna bağlama rehberi |

---

## 1. Gerekenler

- Raspberry Pi 4 veya 5 (3B+ da yeterli), en az 16 GB microSD kart
- Takım switch'i ve ethernet kabloları
- Yer bilgisayarı (yer istasyonu yazılımının çalıştığı bilgisayar)

## 2. Ağ düzeni

Yarışmada yer bilgisayarınız organizasyonun verdiği kabloyla hakem sunucusuna bağlanacak.
Testte bu sunucunun yerini Raspberry Pi alır:

```
Yer bilgisayarı (192.168.50.10) ──┐
                                 ├── Takım switch'i ── Raspberry Pi (192.168.50.25:5000)
Doodle Labs yer radyosu ─────────┘                      "hakem sunucusu" rolünde
```

> **Not:** Dokümandaki `http://127.0.0.25:5000` sadece adres **biçimine** örnektir.
> `127.x.x.x` adresleri bilgisayarın kendisini gösterir ve başka bir cihazdan erişilemez.
> Testte Pi'nin gerçek ağ adresini (ör. `192.168.50.25`) kullanın.

## 3. Kurulum

### 3.1 Pi'ye işletim sistemi yükleyin

1. Bilgisayarınıza **Raspberry Pi Imager**'ı kurun.
2. İşletim sistemi olarak **Raspberry Pi OS Lite (64-bit)** seçin.
3. Ayarlar (dişli simgesi) bölümünde:
   - Ana bilgisayar adı: `yarismasunucu`
   - Kullanıcı adı ve şifre (örnekte kullanıcı adı `simurg`)
   - **SSH'yi etkinleştir**
   - Zaman dilimi: `Europe/Istanbul`
4. Kartı yazın, Pi'ye takın.

### 3.2 Dosyaları kopyalayıp kurun (internet gerekir)

Pi internete bağlıyken (Wi-Fi veya ethernet) Pi'nin terminalinde:

```bash
# Kodu GitHub'dan indir (private repo olduğu için GitHub girişi ister, aşağıdaki nota bakın)
git clone https://github.com/goldbane1/ata-simurg-test-sunucusu.git ~/teknofest_test_sunucusu

cd ~/teknofest_test_sunucusu
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Denemek için çalıştır (Ctrl+C ile durur)
venv/bin/python sunucu.py --ayarlar ayarlar.yaml
```

**Private repo girişi:** `git clone` kullanıcı adı ve şifre ister. Şifre yerine GitHub'da
oluşturulan bir **Personal Access Token** girilir (GitHub → Settings → Developer settings →
Personal access tokens → Fine-grained tokens; yalnızca bu repo için "Contents: Read" izni yeterli).

**Kod güncellendiğinde** Pi'de:

```bash
cd ~/teknofest_test_sunucusu
git pull
sudo systemctl restart teknofest-sunucu
```

### 3.3 Pi'ye sabit IP verin

Sahada modem olmayacağı için Pi'nin ethernet adresi sabit olmalı. Bunu `ag_ayarla.sh`
script'i yapar (ayrıntılar: **3.7 Ağ ayarı script'i**). Pi'nin içinde:

```bash
cd ~/teknofest_test_sunucusu
chmod +x ag_ayarla.sh                       # ilk seferde: çalıştırılabilir yap
sudo ./ag_ayarla.sh --ip 192.168.50.25/24
```

Test ağı için bilerek `192.168.50.x` seçildi: ev modemleri genelde `192.168.1.x` veya
`192.168.0.x` kullanır; Pi'nin Wi-Fi'si ve ethernet'i aynı aralıkta olursa paketler karışır.
Ağ geçidi verilmediği için Pi internete Wi-Fi'den çıkmaya devam eder ve Wi-Fi üzerinden
kurduğunuz SSH bağlantısı kopmaz.

### 3.4 Yer bilgisayarına sabit IP verin

Yer bilgisayarının ethernetine elle adres verin:

- IP: `192.168.50.10`
- Alt ağ maskesi: `255.255.255.0`
- Ağ geçidi ve DNS: boş

(Windows: Ayarlar → Ağ → Ethernet → IP ataması → Düzenle → Elle → IPv4.)

Dokümana göre sunucuya bağlanan bilgisayarın **güvenlik duvarı kapalı** olmalı;
testte de aynı şekilde deneyin.

### 3.5 Bağlantıyı test edin

Yer bilgisayarından:

```bash
ping 192.168.50.25
```

Tarayıcıda hakem panelini açın: `http://192.168.50.25:5000/panel`

Sonra tüm uç noktaları otomatik deneyin:

```bash
pip install requests
python istemci_test.py --sunucu http://192.168.50.25:5000 kontrol
```

Beklenen sonuç: `Sonuç: 19/19 kontrol başarılı`

### 3.6 Pi açılınca otomatik başlasın

`teknofest-sunucu.service` dosyasındaki `simurg` yazan yerleri kendi kullanıcı adınızla
değiştirin. Sonra Pi'nin içinde:

```bash
cd ~/teknofest_test_sunucusu
sudo cp teknofest-sunucu.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now teknofest-sunucu

# Durum ve canlı kayıtlar:
systemctl status teknofest-sunucu
journalctl -u teknofest-sunucu -f
```

Artık Pi'yi switch'e takıp açmanız yeterli; sunucu kendiliğinden başlar.

### 3.7 Ağ ayarı script'i (`ag_ayarla.sh`)

Pi'nin ethernet IP'sini ve sunucunun portunu tek komutla değiştirir, servisi yeniden başlatır
ve sunucunun yeni ayarla cevap verdiğini kontrol eder. Arayüz ekibi sunucuya farklı bir
adres veya porttan bağlanacaksa ya da yarışma günü verilen IP'yi denemek istiyorsanız bunu
kullanın.

| Komut | Ne yapar |
| --- | --- |
| `./ag_ayarla.sh --durum` | Mevcut IP, port, servis durumu ve panel adresini gösterir. `sudo` gerekmez |
| `sudo ./ag_ayarla.sh` | Soru sorarak ayarlar; boş bıraktığınız değer değişmez |
| `sudo ./ag_ayarla.sh --ip 192.168.50.25/24` | Sadece ethernet IP'sini değiştirir |
| `sudo ./ag_ayarla.sh --port 8080` | Sadece portu değiştirir |
| `sudo ./ag_ayarla.sh --ip 10.0.0.25/24 --port 5000` | İkisini birlikte değiştirir |
| `sudo ./ag_ayarla.sh --ip 10.0.0.25/24 --gateway 10.0.0.1` | Ağ geçidiyle birlikte (çoğu test ağında gerekmez) |
| `sudo ./ag_ayarla.sh --dhcp` | Ethernet'i tekrar otomatik IP'ye döndürür |
| `./ag_ayarla.sh --ip 10.0.0.25/24 --deneme` | Hiçbir şeyi değiştirmeden ne yapılacağını gösterir |

Bilmeniz gerekenler:

- **IP biçimi:** Sonunda `/24` gibi ağ maskesiyle yazılır. `127.x.x.x` kabul edilmez; o adres
  başka cihazdan erişilemez.
- **Port:** 1024–65535 arası olmalı. 1024 altı portlar yönetici yetkisi ister.
- **Yedek:** Port değişmeden önce `ayarlar.yaml.yedek_TARİH` adıyla yedek alınır. Bir şey
  ters giderse yedeği `ayarlar.yaml` adıyla geri kopyalayıp servisi yeniden başlatın.
- **`git pull` ile çakışma:** Script `ayarlar.yaml`'ı değiştirdiği için kod güncellenirken Git
  "yerel değişiklik var" diyebilir. Bu durumda `git stash`, `git pull`, `git stash pop`
  sırasıyla çalıştırın.
- **Script ne yapar:** `test-agi` adında bir NetworkManager profili oluşturur veya günceller.
  Profil açılışta otomatik devreye girer, Pi'deki hazır DHCP profilinin önüne geçer. Ağ geçidi
  verilmezse internet yolu olarak kullanılmaz, yani Wi-Fi interneti bozulmaz.

---

## 4. Kullanım

### Giriş bilgileri (`ayarlar.yaml`)

| Hesap | Kullanıcı adı | Şifre | Takım no |
| --- | --- | --- | --- |
| Takımımız | `atasimurg` | `simurg2026` | 1 |
| İkinci deneme takımı | `deneme2` | `deneme2` | 2 |
| Hakem (panel için) | `hakem` | `hakem123` | – |

### Hakem paneli

`http://192.168.50.25:5000/panel` adresi her saniye yenilenir.

| Sütun | Ne anlama gelir |
| --- | --- |
| Son paket | Son kabul edilen telemetriden bu yana geçen süre. 1 sn'yi aşarsa kırmızı |
| Hız | Son 5 saniyedeki ortalama gönderim hızı. 1–2 Hz arası yeşil |
| 2 Hz ihlali | 400 / "3" ile reddedilen paket sayısı |
| >1 sn boşluk | İki telemetri arasında 1 saniyeyi aşan boşluk sayısı (**ceza adayı**) |
| Son hata | Son reddedilen paketin nedeni, ör. `Aralık: iha_yatis=120 aralık dışında` |

**HSS duyurusu:** Panelde hakem adı ve şifresiyle giriş yapıp **Duyur (aç)** butonuna basın.
Bundan sonra `/api/hss_koordinatlari` dolu liste döner.

### Kayıtlar

Her açılışta `kayitlar/oturum_TARİH_SAAT.jsonl` dosyası oluşur. Gelen her paket, durum kodu
ve red nedeni satır satır yazılır. Uçuş sonrası "neden reddedildi?" sorusunun cevabı buradadır.

### Uçuş modu (örnek yer istasyonu)

```bash
python istemci_test.py --sunucu http://192.168.50.25:5000 ucus --sure 60
```

Bu mod gerçek yer istasyonu gibi davranır ve sizin yazılımınız için **örnek kod** olarak
kullanılabilir:

- Giriş yapar, 401 alırsa otomatik yeniden giriş yapar
- Sunucu saatini RTT/2 yöntemiyle senkronlar, 2 dakikada bir yeniler
- 0,7 saniyede bir telemetri gönderir (yaklaşık 1,4 Hz)
- İsteklerde 0,4 sn zaman aşımı kullanır; cevap gelmezse beklemeden sonraki tura geçer
- 15. saniyede kilitlenme, 25. saniyede kamikaze bildirimi yapar (her biri tek paket)
- 2 saniyede bir HSS sorgular

---

## 5. Sunucu tarafı test planı

Bu bölüm, sunucunun ve ağın yarışma koşullarında doğru davrandığını adım adım doğrulamak
içindir. Testler `istemci_test.py` ile yapılır, YKİ yazılımı gerekmez. YKİ'yi bağlama
adımları için `SAHA_TESTI.md` dosyasına bakın.

### 5.1 Hazırlık

1. Pi'de kodu güncelleyin ve servisin çalıştığını görün:
   ```bash
   cd ~/teknofest_test_sunucusu
   git pull
   ./ag_ayarla.sh --durum        # Servis: active, IP: 192.168.50.25
   ```
2. YKİ bilgisayarı switch'te, ethernet'i `192.168.50.10` olmalı.
3. Hakem panelini tarayıcıda açık tutun: `http://192.168.50.25:5000/panel`
4. Komutlar YKİ bilgisayarında, repo klasöründe çalıştırılır. Yazmayı kısaltmak için:
   - **Windows PowerShell:** `$S = "http://192.168.50.25:5000"` sonra komutlarda `$S` kullanın.
   - **Linux / Pi:** `S=http://192.168.50.25:5000` sonra komutlarda `$S` kullanın.
   - Pi'nin içinden çalıştırırken adres `http://localhost:5000` olur.
5. **Her testten önce** panelin temiz olması için servisi yeniden başlatabilirsiniz (sayaçlar
   bellekte tutulur, yeniden başlatınca sıfırlanır):
   ```bash
   sudo systemctl restart teknofest-sunucu
   ```

> Testlerde istemcinin uçuş modu (`ucus`) 15. saniyede bir kilitlenme, 25. saniyede bir
> kamikaze bildirimi gönderir ve 0,7 saniyede bir telemetri yollar. Panelde bunları
> görmeniz normaldir.

---

### A. Temel çalışma

#### T1 — API kontrolü

- **Amaç:** Bütün uç noktaların ve hata kodlarının dokümana uygun cevap verdiğini görmek.
- **Komut:** `python istemci_test.py --sunucu $S kontrol`
- **Beklenen:** `Sonuç: 19/19 kontrol başarılı`. Bu test 401, 400, 204, 403 ve 404
  durumlarının hepsini dener.

#### T2 — Uzun süreli kararlılık (30 dakika)

- **Amaç:** Sunucunun ve ağın uzun süre kesintisiz çalıştığını görmek. Bir yarışma oturumundan
  uzun tutulmalı.
- **Komut:** `python istemci_test.py --sunucu $S ucus --sure 1800`
- **Beklenen:**
  - İstemci sonunda `0 hata, 0 zaman aşımı` yazar.
  - Panelde **Hız** ~1,4 Hz, **Red**, **2 Hz ihlali** ve **>1 sn boşluk** sıfır kalır.
  - Test bitince Pi'de `vcgencmd measure_temp` 70°C altında, `vcgencmd get_throttled` sonucu `0x0`.

---

### B. Kural ihlalleri

#### T3 — 2 Hz sınırı

- **Amaç:** Çok sık gönderilen telemetrinin reddedildiğini görmek.
- **Komut:** `python istemci_test.py --sunucu $S ucus --sure 10 --periyot 0.3`
- **Beklenen:** İstemci ekranında `400 '3'` satırları çıkar, panelde **2 Hz ihlali** artar.
  Kabul edilen paketler saniyede en çok 2 olur.

#### T4 — Yanlış QR metni

- **Amaç:** Kamikaze bildiriminde QR metninin kontrol edildiğini görmek.
- **Komut:** `python istemci_test.py --sunucu $S ucus --sure 30 --qr-metni yanlis`
- **Beklenen:** Panelin **Kamikaze bildirimleri** tablosunda sonuç **Yanlış** görünür.
  Doğru metinle (`teknofest2026`) yapılan önceki testlerde **Doğru** görünmüştü.

---

### C. Dayanıklılık

Bu testlerde istemci uçarken bir şeyi bilerek bozarız ve istemcinin **kendiliğinden
toparlanıp toparlanmadığına** bakarız.

#### T5 — Yavaş sunucu

- **Amaç:** Sunucu geç cevap verdiğinde istemcinin donmadan devam ettiğini görmek.
- **Adımlar:**
  1. Pi'de `ayarlar.yaml` içinde `yapay_gecikme_ms: [100, 800]` yapın ve servisi yeniden başlatın.
  2. `python istemci_test.py --sunucu $S ucus --sure 60`
- **Beklenen:** İstemci zaman zaman `zaman aşımı (beklemeden sonraki tura geçiliyor)` yazar
  ama donmaz, gönderime devam eder.
- **Bitince:** `yapay_gecikme_ms: [0, 0]` yapıp servisi yeniden başlatın.

#### T6 — Sunucu yeniden başlıyor

- **Amaç:** Sunucu yeniden başladığında istemcinin oturumu yeniden açtığını görmek.
- **Adımlar:**
  1. `python istemci_test.py --sunucu $S ucus --sure 120`
  2. 20. saniye civarında Pi'de: `sudo systemctl restart teknofest-sunucu`
- **Beklenen:** İstemci 1–2 kez `bağlantı hatası`, ardından `401 -> yeniden giriş` yazar
  ve 200 almaya devam eder. Paneldeki sayaçlar sıfırlanır; bu normaldir.

#### T7 — Kablo kopması

- **Amaç:** Ağ kısa süre koptuğunda istemcinin kendiliğinden devam ettiğini görmek.
- **Adımlar:**
  1. `python istemci_test.py --sunucu $S ucus --sure 120`
  2. YKİ bilgisayarının ethernet kablosunu 3 saniye çekip geri takın.
- **Beklenen:** İstemci birkaç `bağlantı hatası` ya da `zaman aşımı` yazar, sonra 200
  almaya devam eder. Panelde **>1 sn boşluk** 1 artar. Bu sayı, yarışmada ceza alacağınız
  saniyelerin göstergesidir.

#### T8 — Pi'nin elektriği kesiliyor

- **Amaç:** Pi elektrik kesintisinden sonra kendiliğinden ayağa kalkıyor mu?
- **Adımlar:**
  1. `python istemci_test.py --sunucu $S ucus --sure 300`
  2. Önce güvenli yol: Pi'de `sudo reboot`.
  3. İsterseniz **bir kez** gerçek kesintiyi de deneyin: Pi'nin fişini 10 saniye çekip takın.
- **Beklenen:** Pi açılırken istemci bağlantı hataları yazar. Pi açıldıktan sonra
  (yaklaşık 1 dakika) istemci `401 -> yeniden giriş` ile devam eder. Pi'nin IP'si yine
  `192.168.50.25`'tir.
- **Uyarı:** Fişten çekmek SD kartı bozabilir. Bu testi sık yapmayın; normalde
  `sudo shutdown -h now` ile kapatın.

---

### D. Çoklu takım

Yarışmada sahada başka takımlar da uçacak. Bu testlerde ikinci bir takım (`deneme2`)
çalıştırıp sunucunun rakip verisini doğru dağıttığını görürüz.

**Takım 2'yi çalıştırmanın en kolay yolu Pi'nin kendisi** (ek bilgisayar gerekmez). Pi'ye
ayrı bir SSH penceresinde:

```bash
cd ~/teknofest_test_sunucusu
venv/bin/python istemci_test.py --sunucu http://localhost:5000 --kadi deneme2 --sifre deneme2 ucus --sure 1800
```

Bu pencere kapanırsa Takım 2 de durur. Alternatif olarak aynı YKİ bilgisayarında ikinci bir
terminalden ya da `192.168.50.11` adresli ikinci bir bilgisayardan da çalıştırabilirsiniz.

#### T9 — İki takım birlikte

- **Amaç:** Takımların birbirini `konumBilgileri` içinde gördüğünü doğrulamak.
- **Adımlar:**
  1. Takım 2'yi yukarıdaki komutla Pi'de başlatın.
  2. YKİ bilgisayarında Takım 1: `python istemci_test.py --sunucu $S ucus --sure 120`
- **Beklenen:**
  - Panelde iki takımın satırı da yeşil, ikisi de ~1,4 Hz.
  - Takım 1'in ekranında `rakipler=[1, 2, 101, 102, 103]` görünür.
- **Not:** Listede takımın **kendisi (1)** de vardır. Dokümandaki örnekte de böyle. YKİ
  yazılımı bu listeden kendi takım numarasını ayıklamalıdır; yoksa kendini rakip olarak
  görür.

#### T10 — Rakibin sinyali kesiliyor

- **Amaç:** Veri göndermeyi bırakan bir rakibin nasıl göründüğünü anlamak.
- **Adımlar:** T9 devam ederken Pi'deki Takım 2 penceresinde `Ctrl+C` yapın.
- **Beklenen:** Panelde Takım 2'nin **Son paket** süresi büyür ve kırmızıya döner. Sunucu
  Takım 2'nin son konumunu diğer takımlara göndermeye devam eder; `zaman_farki` değeri
  paneldeki **Son paket** süresiyle aynı şekilde büyür.
- **YKİ için anlamı:** `zaman_farki` büyüyen bir rakip eski konumdadır. YKİ bunu "kayıp"
  olarak göstermeli, otonomi bu konuma göre hedef seçmemeli.

#### T11 — Tek IP kuralı

- **Amaç:** Yarışmadaki "her takım yalnızca kendine verilen IP'den bağlanabilir" kuralını
  denemek. Tek bilgisayarla yapılabilir.
- **Adımlar:**
  1. Pi'de `ayarlar.yaml` içinde `ip_kontrolu: true` yapın ve servisi yeniden başlatın.
  2. YKİ bilgisayarından (`192.168.50.10`) Takım 1: `python istemci_test.py --sunucu $S kontrol`
  3. Aynı bilgisayardan Takım 2: `python istemci_test.py --sunucu $S --kadi deneme2 --sifre deneme2 kontrol`
- **Beklenen:**
  - 2. adım: `19/19`. Takım 1'in IP'si `192.168.50.10` ve izinli.
  - 3. adım: **Doğru giriş** satırı `403 'Bu IP adresinden bağlantıya izin verilmiyor.'`
    ile başarısız olur ve test durur. Takım 2'ye
    `192.168.50.11` tanımlı, bu bilgisayardan giremez.
- **Bitince:** `ip_kontrolu: false` yapıp servisi yeniden başlatın. Aksi halde Pi'nin
  içinden yapılan testler (`localhost`) de 403 alır.

#### T12 — Takım eklemek

- **Amaç:** Daha kalabalık bir sahayı taklit etmek.
- **Adımlar:** `ayarlar.yaml`'daki `takimlar` listesine ekleyin ve servisi yeniden başlatın:
  ```yaml
    - takim_numarasi: 3
      kadi: deneme3
      sifre: deneme3
      ip: 192.168.50.12
  ```
  Sonra Takım 2 komutunu `--kadi deneme3 --sifre deneme3` ile çalıştırın.
- **Beklenen:** Panelde üç takım satırı. Takım 1'in `rakipler` listesinde 3 de görünür.

---

### E. Görev akışları

#### T13 — HSS duyurusu

- **Amaç:** HSS bölgelerinin sadece hakem duyurusundan sonra verildiğini görmek.
- **Adımlar:**
  1. `python istemci_test.py --sunucu $S ucus --sure 60`
  2. Panelde hakem girişi yapın (`hakem` / `hakem123`) ve **Duyur (aç)** deyin.
  3. 20 saniye sonra **Kapat** deyin.
- **Beklenen:** Duyurudan önce istemci HSS ile ilgili bir şey yazmaz. Duyurudan sonra
  2 saniyede bir `HSS aktif: 3 bölge` yazar. Kapatınca durur.

#### T14 — Kilitlenme ve kamikaze bildirimi

- **Amaç:** Bildirimlerin sunucu saatiyle ve her olay için tek paket olarak geldiğini görmek.
- **Komut:** `python istemci_test.py --sunucu $S ucus --sure 30`
- **Beklenen:**
  - 15. saniyede **Kilitlenme bildirimleri** tablosuna bir satır düşer. **Kilitlenme bitişi**
    saati, **Alındı** saatinden en fazla birkaç yüz milisaniye öncedir.
  - 25. saniyede **Kamikaze bildirimleri** tablosuna bir satır düşer, sonuç **Doğru**.
  - Her olay için **tek** satır vardır.

---

### 5.2 Test sonrası

1. Değiştirdiğiniz ayarları geri alın: `yapay_gecikme_ms: [0, 0]`, `ip_kontrolu: false`,
   eklediğiniz deneme takımları. Servisi yeniden başlatın.
2. Pi'nin sağlığına bakın: `vcgencmd measure_temp`, `vcgencmd get_throttled`.
3. Kayıtları saklamak isterseniz YKİ bilgisayarına kopyalayın:
   ```bash
   scp simurg@192.168.50.25:~/teknofest_test_sunucusu/kayitlar/*.jsonl .
   ```

### 5.3 Sonuç çizelgesi

Testleri yaparken işaretleyin. Kalan bir test varsa **Not** sütununa paneldeki
**Son hata** mesajını ya da istemcinin çıktısını yazın.

| Test | Geçti | Not |
| --- | --- | --- |
| T1 API kontrolü (19/19) | ☐ | |
| T2 Uzun süreli kararlılık (30 dk) | ☐ | |
| T3 2 Hz sınırı | ☐ | |
| T4 Yanlış QR metni | ☐ | |
| T5 Yavaş sunucu | ☐ | |
| T6 Sunucu yeniden başlıyor | ☐ | |
| T7 Kablo kopması | ☐ | |
| T8 Pi'nin elektriği kesiliyor | ☐ | |
| T9 İki takım birlikte | ☐ | |
| T10 Rakibin sinyali kesiliyor | ☐ | |
| T11 Tek IP kuralı | ☐ | |
| T12 Takım eklemek | ☐ | |
| T13 HSS duyurusu | ☐ | |
| T14 Kilitlenme ve kamikaze | ☐ | |

---

## 6. Varsayımlar (dokümanda yazmayan davranışlar)

Dokümanda açıkça yazanlar birebir uygulandı: uç noktalar, JSON alan adları, durum kodları
(200, 204, 400, 401, 403, 404, 500), değer aralıkları, 2 Hz üstüne 400 + "3", HSS duyurusu
yokken boş liste. Aşağıdakiler ise dokümanda belirtilmediği için bizim seçimimizdir.
Yer istasyonu yazılımınızı bunlara **sıkı sıkıya bağlamayın**:

| Konu | Bu sunucuda | Not |
| --- | --- | --- |
| 400 içerik kodları | `1` hatalı giriş, `2` aralık dışı, `4` takım no uyuşmuyor | Dokümanda yalnızca `3` (2 Hz üstü) tanımlı |
| Aralık dışı değer | 400 + "2" | Doküman sadece "paket hatalı sayılır" diyor |
| Oturum | Çerez (cookie) ile tutulur | İstemcide `requests.Session()` kullanın |
| Giriş cevabı | Takım numarası düz sayı olarak (`1`) | |
| Hız sınırı | Son 1 saniyede 2 paket kabul edildiyse 3.'sü reddedilir | |
| Telemetri cevabı | Takımın kendisi de `konumBilgileri`nde yer alır | Dokümandaki örnekte de takım 1 listede |
| HSS kapalıyken | `{"sunucusaati": {...}, "hss_koordinat_bilgileri": []}` | Doküman "boş liste döner" diyor; istemciniz düz `[]` gelirse de çalışmalı |
| Kamikaze QR alanı | `qrMetni` ve `qrMetni ` (sonunda boşluk) ikisi de kabul | Dokümandaki örnekte anahtar sonunda boşluk var, muhtemelen yazım hatası |
| Sunucu saati | Pi'nin yerel saati | Pi'de pilli saat yok; internetsiz açılınca saat yanlış olabilir. Bu sorun değil: istemcinin sunucu saatine göre senkron olmasını zaten bu test eder |
