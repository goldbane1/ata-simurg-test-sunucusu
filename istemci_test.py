#!/usr/bin/env python3
"""
Test sunucusunu (veya API'si aynı olan herhangi bir sunucuyu) deneyen istemci.

İki mod var:
  kontrol : Her uç noktayı ve hata durumunu tek tek dener, sonuçları tablo halinde yazar.
  ucus    : Gerçek bir yer istasyonu gibi davranır: giriş, saat senkronu, 0,7 sn'de bir
            telemetri, ortada bir kilitlenme ve kamikaze bildirimi, HSS sorgusu.

Örnekler:
  python3 istemci_test.py --sunucu http://192.168.1.25:5000 kontrol
  python3 istemci_test.py --sunucu http://192.168.1.25:5000 ucus --sure 60
"""
import argparse
import datetime
import math
import time

import requests

GUN_MS = 24 * 60 * 60 * 1000


# ---------------------------------------------------------------------------
# Saat yardımcıları
# ---------------------------------------------------------------------------

def saat_ms(z):
    return ((z["saat"] * 60 + z["dakika"]) * 60 + z["saniye"]) * 1000 + z["milisaniye"]


def yerel_gun_ms():
    an = datetime.datetime.now()
    return ((an.hour * 60 + an.minute) * 60 + an.second) * 1000 + an.microsecond // 1000


def ms_to_saat(ms):
    ms %= GUN_MS
    return {"saat": ms // 3600000, "dakika": ms // 60000 % 60,
            "saniye": ms // 1000 % 60, "milisaniye": ms % 1000}


class SaatSenkronu:
    """Sunucu saati ile yerel saat arasındaki farkı RTT/2 yöntemiyle bulur."""

    def __init__(self):
        self.fark_ms = 0

    def olc(self, oturum, url, deneme=5):
        en_iyi = None
        for _ in range(deneme):
            y0 = yerel_gun_ms()
            t0 = time.monotonic()
            r = oturum.get(url + "/api/sunucusaati", timeout=1.0)
            rtt = (time.monotonic() - t0) * 1000
            if r.status_code != 200:
                continue
            # Cevap geldiğinde yerel saat ~ y0 + rtt, sunucu saati ~ gelen + rtt/2
            fark = (saat_ms(r.json()) + rtt / 2) - (y0 + rtt)
            fark = (fark + GUN_MS / 2) % GUN_MS - GUN_MS / 2
            if en_iyi is None or rtt < en_iyi[0]:
                en_iyi = (rtt, fark)
            time.sleep(0.05)
        if en_iyi:
            self.fark_ms = round(en_iyi[1])
        return en_iyi

    def simdi(self):
        return ms_to_saat(yerel_gun_ms() + self.fark_ms)


def gps_saati_utc():
    """Gerçek sistemde bu değer doğrudan Cube'un SYSTEM_TIME mesajından gelmeli."""
    an = datetime.datetime.now(datetime.timezone.utc)
    return {"saat": an.hour, "dakika": an.minute, "saniye": an.second,
            "milisaniye": an.microsecond // 1000}


# ---------------------------------------------------------------------------
# Sahte uçuş verisi
# ---------------------------------------------------------------------------

def sahte_telemetri(takim_no, t, kilitlenme=False):
    merkez_enlem, merkez_boylam, r, v = 41.5100, 36.1190, 150.0, 20.0
    aci = v / r * t
    enlem = merkez_enlem + r * math.sin(aci) / 111320
    boylam = merkez_boylam + r * math.cos(aci) / (111320 * math.cos(math.radians(merkez_enlem)))
    yonelme = (math.degrees(math.atan2(-math.sin(aci), math.cos(aci))) + 360) % 360
    return {
        "takim_numarasi": takim_no,
        "iha_enlem": round(enlem, 7),
        "iha_boylam": round(boylam, 7),
        "iha_irtifa": round(50 + 2 * math.sin(t / 3), 1),
        "iha_dikilme": round(3 * math.sin(t), 1),
        "iha_yonelme": round(yonelme, 1),
        "iha_yatis": round(-math.degrees(math.atan(v * v / (9.81 * r))), 1),
        "iha_hiz": v,
        "iha_batarya": max(0, round(95 - t / 20)),
        "iha_otonom": 1,
        "iha_kilitlenme": 1 if kilitlenme else 0,
        "hedef_merkez_X": 320 if kilitlenme else 0,
        "hedef_merkez_Y": 240 if kilitlenme else 0,
        "hedef_genislik": 40 if kilitlenme else 0,
        "hedef_yukseklik": 30 if kilitlenme else 0,
        "gps_saati": gps_saati_utc(),
    }


# ---------------------------------------------------------------------------
# Kontrol modu
# ---------------------------------------------------------------------------

def kontrol(args):
    url = args.sunucu.rstrip("/")
    sonuclar = []

    def dene(ad, beklenen_kod, cagri, beklenen_icerik=None, ek=None):
        try:
            r = cagri()
            durum_ok = r.status_code == beklenen_kod
            icerik_ok = beklenen_icerik is None or r.text.strip() == beklenen_icerik
            ek_ok = ek is None or ek(r)
            basarili = durum_ok and icerik_ok and ek_ok
            detay = f"{r.status_code} {r.text.strip()[:60]!r}"
        except Exception as e:  # noqa: BLE001
            basarili, detay = False, f"istisna: {e}"
        sonuclar.append((basarili, ad, detay))
        print(("  ✓ " if basarili else "  ✗ ") + f"{ad:<52} {detay}")
        return basarili

    s = requests.Session()
    print(f"\nSunucu: {url}\n")

    dene("Oturum açmadan istek -> 401", 401, lambda: s.get(url + "/api/sunucusaati", timeout=2))
    dene("Hatalı şifre -> 400", 400,
         lambda: s.post(url + "/api/giris", json={"kadi": args.kadi, "sifre": "yanlis"}, timeout=2))
    ok = dene("Doğru giriş -> 200 + takım no", 200,
              lambda: s.post(url + "/api/giris", json={"kadi": args.kadi, "sifre": args.sifre}, timeout=2))
    if not ok:
        print("\nGiriş yapılamadı, kullanıcı adı/şifreyi kontrol edin.")
        return
    takim_no = int(s.post(url + "/api/giris", json={"kadi": args.kadi, "sifre": args.sifre},
                          timeout=2).text)

    dene("Sunucu saati -> 200", 200, lambda: s.get(url + "/api/sunucusaati", timeout=2),
         ek=lambda r: set(r.json()) == {"gun", "saat", "dakika", "saniye", "milisaniye"})

    time.sleep(1.1)
    dene("Geçerli telemetri -> 200 + konumBilgileri", 200,
         lambda: s.post(url + "/api/telemetri_gonder", json=sahte_telemetri(takim_no, 0), timeout=2),
         ek=lambda r: "konumBilgileri" in r.json() and "sunucusaati" in r.json())
    s.post(url + "/api/telemetri_gonder", json=sahte_telemetri(takim_no, 0.1), timeout=2)
    dene("Aynı saniyede 3. paket (2 Hz üstü) -> 400 / 3", 400,
         lambda: s.post(url + "/api/telemetri_gonder", json=sahte_telemetri(takim_no, 0.2), timeout=2),
         beklenen_icerik="3")

    time.sleep(1.1)
    p = sahte_telemetri(takim_no, 1)
    p["iha_yatis"] = 120
    dene("Yatış 120° (aralık dışı) -> 400 / 2", 400,
         lambda: s.post(url + "/api/telemetri_gonder", json=p, timeout=2), beklenen_icerik="2")

    p = sahte_telemetri(takim_no, 1)
    p["iha_yonelme"] = -10
    dene("Yönelme -10° (aralık dışı) -> 400 / 2", 400,
         lambda: s.post(url + "/api/telemetri_gonder", json=p, timeout=2), beklenen_icerik="2")

    p = sahte_telemetri(takim_no, 1)
    del p["iha_batarya"]
    dene("Eksik alan (iha_batarya) -> 204", 204,
         lambda: s.post(url + "/api/telemetri_gonder", json=p, timeout=2))

    p = sahte_telemetri(takim_no, 1)
    p["iha_irtifa"] = "50"
    dene("Metin olarak sayı (\"50\") -> 204", 204,
         lambda: s.post(url + "/api/telemetri_gonder", json=p, timeout=2))

    p = sahte_telemetri(takim_no, 1)
    p["iha_kilitlenme"] = 1
    dene("Kilitlenme=1 ama hedef alanları 0 -> 400 / 2", 400,
         lambda: s.post(url + "/api/telemetri_gonder", json=p, timeout=2), beklenen_icerik="2")

    p = sahte_telemetri(takim_no + 50, 1)
    dene("Başka takımın numarası -> 400 / 4", 400,
         lambda: s.post(url + "/api/telemetri_gonder", json=p, timeout=2), beklenen_icerik="4")

    senkron = SaatSenkronu()
    senkron.olc(s, url)
    dene("Kilitlenme bilgisi -> 200", 200,
         lambda: s.post(url + "/api/kilitlenme_bilgisi",
                        json={"kilitlenmeBitisZamani": senkron.simdi(), "otonom_kilitlenme": 1},
                        timeout=2))
    dene("Kamikaze bilgisi -> 200", 200,
         lambda: s.post(url + "/api/kamikaze_bilgisi",
                        json={"kamikazeBaslangicZamani": senkron.simdi(),
                              "kamikazeBitisZamani": senkron.simdi(),
                              "qrMetni": "teknofest2026"}, timeout=2))
    dene("QR koordinatı -> 200", 200, lambda: s.get(url + "/api/qr_koordinati", timeout=2),
         ek=lambda r: {"qrEnlem", "qrBoylam"} <= set(r.json()))
    dene("HSS (duyuru yokken) -> 200 + boş liste", 200,
         lambda: s.get(url + "/api/hss_koordinatlari", timeout=2),
         ek=lambda r: r.json().get("hss_koordinat_bilgileri") == [])
    dene("Olmayan adres -> 404", 404, lambda: s.get(url + "/api/olmayan", timeout=2))
    dene("Takım hesabıyla hakem işlemi -> 403", 403,
         lambda: s.post(url + "/api/hakem/hss", json={"aktif": True}, timeout=2))

    h = requests.Session()
    if h.post(url + "/api/giris", json={"kadi": args.hakem_kadi, "sifre": args.hakem_sifre},
              timeout=2).status_code == 200:
        h.post(url + "/api/hakem/hss", json={"aktif": True}, timeout=2)
        dene("HSS (duyurudan sonra) -> 200 + dolu liste", 200,
             lambda: s.get(url + "/api/hss_koordinatlari", timeout=2),
             ek=lambda r: len(r.json().get("hss_koordinat_bilgileri", [])) > 0)
        h.post(url + "/api/hakem/hss", json={"aktif": False}, timeout=2)

    basarili = sum(1 for b, *_ in sonuclar if b)
    print(f"\nSonuç: {basarili}/{len(sonuclar)} kontrol başarılı\n")


# ---------------------------------------------------------------------------
# Uçuş modu
# ---------------------------------------------------------------------------

def ucus(args):
    url = args.sunucu.rstrip("/")
    s = requests.Session()

    def giris_yap():
        r = s.post(url + "/api/giris", json={"kadi": args.kadi, "sifre": args.sifre}, timeout=2)
        r.raise_for_status()
        return int(r.text)

    takim_no = giris_yap()
    print(f"Giriş tamam, takım no: {takim_no}")

    senkron = SaatSenkronu()
    olcum = senkron.olc(s, url)
    print(f"Saat farkı: {senkron.fark_ms} ms (en iyi RTT {olcum[0]:.1f} ms)")

    qr = s.get(url + "/api/qr_koordinati", timeout=2).json()
    print(f"QR konumu: {qr}")

    periyot = args.periyot
    baslangic = time.monotonic()
    sonraki = baslangic
    sayac = {"200": 0, "hata": 0, "zaman_asimi": 0}
    kilit_gonderildi = kamikaze_gonderildi = False
    son_hss = 0.0
    son_senkron = time.monotonic()

    while time.monotonic() - baslangic < args.sure:
        simdi = time.monotonic()
        t = simdi - baslangic
        kilitleniyor = 10 <= t < 15

        try:
            r = s.post(url + "/api/telemetri_gonder",
                       json=sahte_telemetri(takim_no, t, kilitleniyor), timeout=args.zaman_asimi)
            if r.status_code == 200:
                sayac["200"] += 1
                rakipler = [k["takim_numarasi"] for k in r.json()["konumBilgileri"]]
                print(f"{t:6.1f} sn  200  rakipler={rakipler}", end="\r")
            elif r.status_code == 401:
                print(f"\n{t:6.1f} sn  401 -> yeniden giriş")
                giris_yap()
            else:
                sayac["hata"] += 1
                print(f"\n{t:6.1f} sn  {r.status_code} {r.text.strip()!r}")
        except requests.exceptions.Timeout:
            sayac["zaman_asimi"] += 1
            print(f"\n{t:6.1f} sn  zaman aşımı (beklemeden sonraki tura geçiliyor)")
        except requests.exceptions.ConnectionError as e:
            sayac["hata"] += 1
            print(f"\n{t:6.1f} sn  bağlantı hatası: {e.__class__.__name__}")

        # Kilitlenme ve kamikaze: her olay için TEK paket. Yalnızca 200 alınca
        # "gönderildi" sayılır; ağ hatasında bir sonraki turda yeniden denenir.
        # Gerçek sistemde zaman, olay bittiği anda kaydedilmeli (burada 15. sn).
        try:
            if t >= 15 and not kilit_gonderildi:
                r = s.post(url + "/api/kilitlenme_bilgisi",
                           json={"kilitlenmeBitisZamani": senkron.simdi(), "otonom_kilitlenme": 1},
                           timeout=1.0)
                print(f"\n{t:6.1f} sn  kilitlenme bildirildi -> {r.status_code}")
                kilit_gonderildi = r.status_code == 200

            if t >= 25 and not kamikaze_gonderildi:
                bas = senkron.simdi()
                r = s.post(url + "/api/kamikaze_bilgisi",
                           json={"kamikazeBaslangicZamani": bas,
                                 "kamikazeBitisZamani": senkron.simdi(),
                                 "qrMetni": args.qr_metni}, timeout=1.0)
                print(f"\n{t:6.1f} sn  kamikaze bildirildi -> {r.status_code}")
                kamikaze_gonderildi = r.status_code == 200

            if simdi - son_hss > 2.0:
                son_hss = simdi
                hss = s.get(url + "/api/hss_koordinatlari", timeout=1.0).json()
                # Doküman "boş liste döner" diyor; düz liste ihtimaline karşı ikisini de oku
                liste = hss if isinstance(hss, list) else hss.get("hss_koordinat_bilgileri", [])
                if liste:
                    print(f"\n{t:6.1f} sn  HSS aktif: {len(liste)} bölge")

            if simdi - son_senkron > 120:
                son_senkron = simdi
                senkron.olc(s, url)
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"\n{t:6.1f} sn  yan istek başarısız ({e.__class__.__name__}), sonra denenecek")

        # Sabit periyot: bir sonraki gönderim zamanını bir öncekine göre hesapla
        sonraki += periyot
        bekle = sonraki - time.monotonic()
        if bekle > 0:
            time.sleep(bekle)
        else:
            sonraki = time.monotonic()

    print(f"\n\nBitti: {sayac['200']} başarılı, {sayac['hata']} hata, "
          f"{sayac['zaman_asimi']} zaman aşımı")


def main():
    ap = argparse.ArgumentParser(description="Test sunucusu istemcisi")
    ap.add_argument("--sunucu", default="http://127.0.0.1:5000")
    ap.add_argument("--kadi", default="atasimurg")
    ap.add_argument("--sifre", default="simurg2026")
    ap.add_argument("--hakem-kadi", default="hakem")
    ap.add_argument("--hakem-sifre", default="hakem123")
    alt = ap.add_subparsers(dest="mod", required=True)
    alt.add_parser("kontrol", help="Tüm uç noktaları ve hata durumlarını dene")
    u = alt.add_parser("ucus", help="Yer istasyonu gibi sürekli telemetri gönder")
    u.add_argument("--sure", type=float, default=40, help="saniye")
    u.add_argument("--periyot", type=float, default=0.7, help="telemetri aralığı (sn)")
    u.add_argument("--zaman-asimi", type=float, default=0.4, help="istek zaman aşımı (sn)")
    u.add_argument("--qr-metni", default="teknofest2026")
    args = ap.parse_args()
    kontrol(args) if args.mod == "kontrol" else ucus(args)


if __name__ == "__main__":
    main()
