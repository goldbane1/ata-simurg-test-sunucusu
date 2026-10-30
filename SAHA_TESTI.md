# Saha testi: switch kurulumu ve YKİ yazılımıyla bağlantı

Bu rehber, test sunucusunu (Raspberry Pi) takım switch'ine bağlayıp **mevcut YKİ
yazılımımızı** ona karşı çalıştırmak için yazıldı. Amaç, yarışmadaki bağlantının
aynısını kurup YKİ'nin hakem sunucusuyla doğru konuştuğunu görmek.

## Hedef düzen

```
YKİ bilgisayarı (192.168.50.10) ──kablo──┐
                                         ├── Takım switch'i
Raspberry Pi    (192.168.50.25) ──kablo──┘
                 sunucu: 5000 portu
```

| Cihaz | IP | Görevi |
| --- | --- | --- |
| Raspberry Pi | `192.168.50.25/24` | Sahte hakem sunucusu |
| YKİ bilgisayarı | `192.168.50.10/24` | Mevcut YKİ yazılımı |
| Ağ geçidi | Yok | Test ağı internete çıkmıyor |

## Yanınızda olsun

- [ ] Raspberry Pi, resmi güç adaptörü
- [ ] Switch ve güç adaptörü
- [ ] En az 2 ethernet kablosu
- [ ] YKİ bilgisayarı (YKİ yazılımı kurulu)
- [ ] Bu repo YKİ bilgisayarında da olsun (`istemci_test.py` için)

## 1. Pi'yi hazırlayın (evde, Wi-Fi varken)

```bash
ssh simurg@<pi-wifi-ip>
cd ~/teknofest_test_sunucusu
git pull
chmod +x ag_ayarla.sh
./ag_ayarla.sh --ip 192.168.50.25/24 --deneme   # ne yapacağını görün
sudo ./ag_ayarla.sh --ip 192.168.50.25/24       # uygulayın
./ag_ayarla.sh --durum
```

`--durum` çıktısında şunlar olmalı:

- `nmcli profili : test-agi (manual)`
- `Sunucu portu : 5000`
- `Servis : active`

Ayar kalıcıdır; Pi kapanıp açılınca da geçerli olur. Kablo takılı değilken ethernet
`IPv4 adresi yok` görünebilir, kablo takılınca adres gelir.

## 2. YKİ bilgisayarına sabit IP verin (Windows)

1. **Ayarlar → Ağ ve İnternet → Ethernet → IP ataması → Düzenle → El ile → IPv4: Açık**
2. IP: `192.168.50.10`, alt ağ maskesi: `255.255.255.0`
3. Ağ geçidi ve DNS: **boş**
4. Kaydedin

PowerShell'de `ipconfig` yazınca Ethernet bölümünde `192.168.50.10` görünmeli.

## 3. Switch'i kurun

1. Switch'e güç verin.
2. Pi'yi ve YKİ bilgisayarını switch'e takın (port sırası önemli değil).
3. Bağlantı ışıklarının yandığını kontrol edin.

Yönetilebilir bir switch kullanıyorsanız ilk testte VLAN, port güvenliği gibi ayarları
kapalı tutun; önce düz bağlantının çalıştığını görün.

## 4. Bağlantıyı doğrulayın (YKİ bilgisayarından)

Sırayla yapın. Bir adım geçmezse sonrakine geçmeyin.

| # | Kontrol | Komut / işlem | Beklenen |
| --- | --- | --- | --- |
| 1 | Pi'ye ulaşım | `ping 192.168.50.25` | Cevap geliyor, süre ~1 ms |
| 2 | Panel | Tarayıcıda `http://192.168.50.25:5000/panel` | Sunucu saati ilerliyor |
| 3 | API testi | `python istemci_test.py --sunucu http://192.168.50.25:5000 kontrol` | `19/19 kontrol başarılı` |
| 4 | Sürekli gönderim | `python istemci_test.py --sunucu http://192.168.50.25:5000 ucus` | Panelde ~1,4 Hz, boşluk 0 |

Bu 4 adım geçtiyse ağ ve sunucu sağlam. Bundan sonra çıkacak sorunlar YKİ yazılımıyla ilgilidir.

## 5. YKİ yazılımını bağlayın

### 5.1 Ayarlar

YKİ yazılımında hakem sunucusu ayarlarını şöyle girin:

| Ayar | Değer |
| --- | --- |
| Sunucu adresi | `http://192.168.50.25:5000` |
| Kullanıcı adı | `atasimurg` |
| Şifre | `simurg2026` |
| Takım numarası | `1` |

### 5.2 Test sırası

1. Hakem panelini tarayıcıda açık tutun.
2. YKİ'yi başlatıp sunucuya bağlanın.
3. Paneldeki **Takımlar** tablosunda `atasimurg` satırını izleyin.

### 5.3 Panelde neye bakılacak

| Sütun | İyi | Sorun varsa anlamı |
| --- | --- | --- |
| Son paket | 1 sn'nin altında, yeşil | Kırmızıysa YKİ telemetri göndermiyor ya da gönderemiyor |
| Hız | 1–2 Hz, yeşil | 1 Hz altı: ceza riski. 2 Hz üstü: paketler reddediliyor |
| Red | Artmıyor | Artıyorsa **Son hata** sütununa bakın |
| 2 Hz ihlali | 0 | YKİ çok sık gönderiyor; gönderim aralığını 0,6–0,8 sn yapın |
| >1 sn boşluk | 0 | Gönderim zamanlaması düzensiz; ağ ya da YKİ döngüsü takılıyor |
| Konum, irtifa, batarya | Gerçek değerler | Boşsa veya saçmaysa alan eşleştirmesi yanlış |
| GPS saati | UTC saat, ilerliyor | Türkiye saatiyse UTC'ye çevrilmemiş (3 saat fark) |

### 5.4 "Son hata" sütunundaki mesajlar

| Mesaj | Nedeni | YKİ'de yapılacak |
| --- | --- | --- |
| `Format: iha_xxx eksik (204)` | Pakette bir alan yok veya adı yanlış | Alan adlarını haberleşme dokümanıyla karşılaştırın |
| `Format: iha_xxx sayı olmalı (204)` | Sayı metin olarak gönderilmiş (`"50"`) | JSON'a sayı olarak yazın |
| `Aralık: iha_yatis=... (400 / 2)` | Açı aralık dışında | Yatış/dikilme ±90, yönelme 0–360 arasına sınırlayın |
| `iha_kilitlenme=1 iken hedef_... sıfır olamaz` | Kilitlenme var ama hedef kutusu boş | Kilitlenme 1 iken hedef alanlarını doldurun |
| `2 Hz üstü gönderim (400 / 3)` | Saniyede 2'den fazla paket | Gönderim aralığını artırın |
| `Takım no uyuşmuyor (400 / 4)` | Paketteki takım no oturumla aynı değil | Giriş cevabındaki takım numarasını kullanın |

Daha ayrıntılı bilgi için Pi'deki kayıt dosyası (gelen paketin tamamı dahil):

```bash
tail -n 5 ~/teknofest_test_sunucusu/kayitlar/oturum_*.jsonl
```

### 5.5 Kilitlenme, kamikaze ve HSS

- **Kilitlenme / kamikaze:** YKİ bildirim gönderince panelin alt tablolarında bir satır
  belirmeli. Kamikazede QR metni `teknofest2026` ise sonuç "Doğru" görünür.
- **HSS:** Panelde hakem girişi yapın (`hakem` / `hakem123`) ve **Duyur (aç)** butonuna basın.
  YKİ haritasında 3 daire görünmeli.

## 6. Dayanıklılık testleri (zaman kalırsa)

| Test | Nasıl | YKİ'den beklenen |
| --- | --- | --- |
| Kablo kopması | YKİ kablosunu 3 sn çekip takın | Kendiliğinden devam etmeli |
| Sunucu yeniden başlaması | Pi'de `sudo systemctl restart teknofest-sunucu` | 401 alıp yeniden giriş yapmalı |
| Yavaş sunucu | `ayarlar.yaml` → `yapay_gecikme_ms: [100, 800]`, servisi yeniden başlatın | Donmamalı, gönderime devam etmeli |
| Pi'nin elektriği kesilir | Fişi çekip takın | Pi açılınca (~1 dk) YKİ yeniden bağlanmalı |

Testlerden sonra `yapay_gecikme_ms` değerini `[0, 0]` yapmayı unutmayın.

## 7. Test sonunda

- Paneldeki **Kabul / Red / 2 Hz ihlali / >1 sn boşluk** değerlerini not alın veya ekran
  görüntüsünü kaydedin.
- Pi'deki kayıt dosyasını saklamak isterseniz YKİ bilgisayarına kopyalayın:
  ```bash
  scp simurg@192.168.50.25:~/teknofest_test_sunucusu/kayitlar/*.jsonl .
  ```
- Pi'yi kapatırken: `sudo shutdown -h now`, yeşil ışık sönünce fişi çekin.

## Sorun giderme

| Belirti | Kontrol |
| --- | --- |
| Ping gitmiyor | Pi'de `./ag_ayarla.sh --durum` ile IP'yi, YKİ'de `ipconfig` ile adresi kontrol edin; kablo ışıkları yanıyor mu? |
| Ping gidiyor, panel açılmıyor | Pi'de `systemctl status teknofest-sunucu` ve `journalctl -u teknofest-sunucu -n 30` |
| Panel açılıyor, YKİ bağlanamıyor | YKİ'deki adres `http://` ile başlıyor ve `:5000` içeriyor mu? YKİ bilgisayarının güvenlik duvarı kapalı mı? |
| YKİ bağlanıyor ama hep 401 | YKİ giriş yapmıyor ya da oturum çerezini saklamıyor (her istekte aynı HTTP oturumu kullanılmalı) |
| Pi'ye SSH ile ulaşamıyorum | Aynı switch'teyseniz `ssh simurg@192.168.50.25` ile bağlanın |
