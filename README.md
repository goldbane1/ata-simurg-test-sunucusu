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

## 5. Test senaryoları

İki tür test var:

- **Altyapı kontrolü:** Pi, switch, kablo, sabit IP ve servisin sahada çalıştığını gösterir.
  Bir kez yapılır, yaklaşık 10 dakika sürer.
- **Senaryolar:** Asıl amaç YKİ'nin bu durumlara doğru tepki vermesidir. Tablodaki
  `istemci_test.py` komutları doğru davranışın panelde nasıl göründüğünü gösterir; aynı
  durumları sonra YKİ ile deneyin.

### 5.1 Altyapı kontrolü

Komutları YKİ bilgisayarında, repo klasöründe çalıştırın.

| Kontrol | Komut | Beklenen |
| --- | --- | --- |
| Ağ ve API | `python istemci_test.py --sunucu http://192.168.50.25:5000 kontrol` | `19/19 kontrol başarılı` |
| Kesintisiz akış | `python istemci_test.py --sunucu http://192.168.50.25:5000 ucus --sure 120` | Panelde ~1,4 Hz, **>1 sn boşluk** 0 |
| Açılışta başlama | Pi'de `sudo reboot`, 1–2 dk bekleyin | Panel kendiliğinden açılır, IP yine `192.168.50.25` |

Üçü de geçerse sunucu ve ağ hazırdır; sonrasında çıkan sorunlar YKİ ile ilgilidir.

### 5.2 Önerilen test senaryoları

| Ne denenecek | Nasıl | Beklenen |
| --- | --- | --- |
| Normal akış | `ucus --sure 120` | Panelde 1,4 Hz, hiç boşluk ve ihlal yok |
| 2 Hz sınırı | `ucus --periyot 0.3` | Panelde "2 Hz ihlali" artar, istemci 400 / "3" görür |
| Yavaş sunucu | `ayarlar.yaml` → `yapay_gecikme_ms: [100, 800]` | İstemci zaman aşımını atlatır, boşluk sayısı izlenir |
| Sunucu yeniden başlar | Uçuş sırasında `sudo systemctl restart teknofest-sunucu` | İstemci 401 alıp yeniden giriş yapar |
| Kablo kopması | Uçuş sırasında yer bilgisayarının kablosunu 3 sn çekip takın | Panelde ">1 sn boşluk" 1 artar, istemci kendiliğinden devam eder |
| Tek IP kuralı | `ip_kontrolu: true`, takımın `ip` alanını yazın | Başka IP'den giriş 403 alır |
| HSS | Panelden duyur | Yer istasyonu haritada daireleri gösterir |
| Yanlış QR | `ucus --qr-metni yanlis` | Panelde kamikaze "Yanlış" görünür |
| Hatalı paketler | `kontrol` modu | 204 ve 400 durumlarının hepsi denenir |
| İki takım | Pi'de ayrı pencerede `venv/bin/python istemci_test.py --sunucu http://localhost:5000 --kadi deneme2 --sifre deneme2 ucus --sure 1800` | Her takım diğerini `konumBilgileri`nde görür |

Notlar:

- `ayarlar.yaml`'da bir şey değiştirdikten sonra servisi yeniden başlatın:
  `sudo systemctl restart teknofest-sunucu`. Testten sonra `yapay_gecikme_ms: [0, 0]` ve
  `ip_kontrolu: false` yapmayı unutmayın.
- Sunucu, `konumBilgileri` listesine takımın **kendisini de** ekler (dokümandaki örnekte de
  böyle). YKİ bu listeden kendi takım numarasını ayıklamalı; yoksa kendini rakip olarak görür.
- Bir rakip veri göndermeyi bırakırsa sunucu son konumunu göndermeye devam eder ama
  `zaman_farki` büyür. YKİ eski konuma göre hedef seçmemeli.

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
