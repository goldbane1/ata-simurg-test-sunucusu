#!/usr/bin/env python3
"""
TEKNOFEST 2026 Savaşan İHA - TEST yarışma sunucusu (ATA Simurg)

"Savaşan İHA Yarışması Haberleşme Dokümanı 2026"daki API'yi taklit eder.
Amaç: yer istasyonu yazılımını yarışmadan önce gerçekçi bir sunucuya karşı denemek.
Resmi sunucu DEĞİLDİR; dokümanda yazmayan davranışlar README'de "varsayım" olarak işaretlidir.

Çalıştırma:
    python3 sunucu.py --ayarlar ayarlar.yaml
Hakem paneli:
    http://<sunucu-ip>:5000/panel
"""
import argparse
import datetime
import json
import math
import os
import random
import threading
import time
from collections import deque
from functools import wraps
from pathlib import Path

import yaml
from flask import Flask, Response, jsonify, redirect, request, session

# ---------------------------------------------------------------------------
# Ayarlar ve durum
# ---------------------------------------------------------------------------

AYAR = {}
KILIT = threading.Lock()        # takım durumu, kilitlenme/kamikaze listeleri
LOG_KILIT = threading.Lock()    # yalnızca kayıt dosyası
BASLANGIC = time.time()

# takim_numarasi -> takım durumu
TAKIMLAR = {}
KILITLENMELER = []
KAMIKAZELER = []
HSS_AKTIF = False
LOG_DOSYASI = None

# Dokümandan: 2 Hz üstü -> 400 + "3".
# Aşağıdaki diğer içerik kodları bu test sunucusuna aittir (dokümanda yok).
HATA_GIRIS = "1"        # kullanıcı adı / şifre hatalı
HATA_ARALIK = "2"       # bir değer izin verilen aralık dışında
HATA_HIZ = "3"          # 2 Hz üstü telemetri (DOKÜMANDA TANIMLI)
HATA_TAKIM_NO = "4"     # paketteki takım numarası oturumla uyuşmuyor


def yeni_takim_durumu(no, kadi):
    return {
        "takim_numarasi": no,
        "kadi": kadi,
        "son_telemetri": None,
        "son_telemetri_zamani": None,
        "kabul_zamanlari": deque(),   # son 1 sn içindeki kabul edilen paketler (hız sınırı)
        "son_5sn": deque(),           # Hz göstergesi için
        "toplam": 0,
        "reddedilen": 0,
        "hiz_ihlali": 0,
        "bosluk_sayisi": 0,           # 1 sn'yi aşan boşluk sayısı
        "en_uzun_bosluk": 0.0,
        "son_hata": "",
        "son_hata_zamani": None,
    }


def ayarlari_yukle(yol):
    global AYAR
    with open(yol, encoding="utf-8") as f:
        AYAR = yaml.safe_load(f)
    for t in AYAR["takimlar"]:
        TAKIMLAR[t["takim_numarasi"]] = yeni_takim_durumu(t["takim_numarasi"], t["kadi"])


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def sunucu_saati(t=None):
    an = datetime.datetime.fromtimestamp(time.time() if t is None else t)
    return {
        "gun": an.day,
        "saat": an.hour,
        "dakika": an.minute,
        "saniye": an.second,
        "milisaniye": an.microsecond // 1000,
    }


def saat_metni(z):
    if not isinstance(z, dict):
        return str(z)
    return "{:02}:{:02}:{:02}.{:03}".format(
        int(z.get("saat", 0)), int(z.get("dakika", 0)),
        int(z.get("saniye", 0)), int(z.get("milisaniye", 0)))


def sayi_mi(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


def tamsayi_mi(v):
    return sayi_mi(v) and float(v).is_integer()


def kaydet(olay, **veri):
    """Her isteği ve olayı JSONL dosyasına yazar."""
    satir = {"zaman": datetime.datetime.now().isoformat(timespec="milliseconds"),
             "olay": olay, **veri}
    with LOG_KILIT:
        if LOG_DOSYASI:
            LOG_DOSYASI.write(json.dumps(satir, ensure_ascii=False) + "\n")
            LOG_DOSYASI.flush()


def konsol(mesaj):
    print(datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3], mesaj, flush=True)


def yapay_gecikme():
    araligi = AYAR.get("yapay_gecikme_ms") or [0, 0]
    alt, ust = araligi
    if ust > 0:
        time.sleep(random.uniform(alt, ust) / 1000.0)


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------

ARALIKLAR = {
    "iha_enlem": (-90, 90),
    "iha_boylam": (-180, 180),
    "iha_irtifa": (None, None),
    "iha_dikilme": (-90, 90),
    "iha_yonelme": (0, 360),
    "iha_yatis": (-90, 90),
    "iha_hiz": (0, None),
    "iha_batarya": (0, 100),
    "hedef_merkez_X": (0, None),
    "hedef_merkez_Y": (0, None),
    "hedef_genislik": (0, None),
    "hedef_yukseklik": (0, None),
}
BAYRAKLAR = ("iha_otonom", "iha_kilitlenme")
HEDEF_ALANLARI = ("hedef_merkez_X", "hedef_merkez_Y", "hedef_genislik", "hedef_yukseklik")


def saat_dogrula(z, ad):
    """(tur, mesaj) döner. tur: None | 'format' | 'aralik'"""
    if not isinstance(z, dict):
        return "format", f"{ad} bir nesne olmalı"
    for alan, ust in (("saat", 23), ("dakika", 59), ("saniye", 59), ("milisaniye", 999)):
        if alan not in z:
            return "format", f"{ad}.{alan} eksik"
        if not tamsayi_mi(z[alan]):
            return "format", f"{ad}.{alan} tam sayı olmalı"
        if not 0 <= z[alan] <= ust:
            return "aralik", f"{ad}.{alan}={z[alan]} (0-{ust} olmalı)"
    return None, ""


def telemetri_dogrula(p):
    if not isinstance(p, dict):
        return "format", "gövde JSON nesnesi değil"
    gerekli = ["takim_numarasi", *ARALIKLAR.keys(), *BAYRAKLAR, "gps_saati"]
    for alan in gerekli:
        if alan not in p:
            return "format", f"{alan} eksik"
    if not tamsayi_mi(p["takim_numarasi"]):
        return "format", "takim_numarasi tam sayı olmalı"
    for alan, (alt, ust) in ARALIKLAR.items():
        v = p[alan]
        if not sayi_mi(v):
            return "format", f"{alan} sayı olmalı (gelen: {v!r})"
        if (alt is not None and v < alt) or (ust is not None and v > ust):
            return "aralik", f"{alan}={v} aralık dışında ({alt}..{ust})"
    for alan in BAYRAKLAR:
        if p[alan] not in (0, 1) or isinstance(p[alan], bool):
            return "aralik", f"{alan} 0 veya 1 olmalı (gelen: {p[alan]!r})"
    if p["iha_kilitlenme"] == 1:
        for alan in HEDEF_ALANLARI:
            if p[alan] == 0:
                return "aralik", f"iha_kilitlenme=1 iken {alan} sıfır olamaz"
    return saat_dogrula(p["gps_saati"], "gps_saati")


# ---------------------------------------------------------------------------
# Sahte rakipler
# ---------------------------------------------------------------------------

def sahte_rakip_konumu(r, simdi):
    """Rakip, saha merkezi etrafında daire çizer."""
    merkez_enlem, merkez_boylam = AYAR["saha_merkezi"]
    yaricap = r["yaricap_m"]
    hiz = r["hiz_ms"]
    yon = 1 if r.get("saat_yonunde", True) else -1
    aci = r.get("faz_derece", 0) * math.pi / 180 + yon * (hiz / yaricap) * (simdi - BASLANGIC)
    dx = yaricap * math.cos(aci)          # doğu (m)
    dy = yaricap * math.sin(aci)          # kuzey (m)
    enlem = merkez_enlem + dy / 111320.0
    boylam = merkez_boylam + dx / (111320.0 * math.cos(math.radians(merkez_enlem)))
    # Hareket yönü: dairenin teğeti
    vx, vy = -math.sin(aci) * yon, math.cos(aci) * yon
    yonelme = (math.degrees(math.atan2(vx, vy)) + 360) % 360
    yatis = math.degrees(math.atan(hiz * hiz / (9.81 * yaricap))) * (-yon)
    irtifa = r["irtifa_m"] + 3 * math.sin((simdi - BASLANGIC) / 4)
    return {
        "takim_numarasi": r["takim_numarasi"],
        "iha_enlem": round(enlem, 7),
        "iha_boylam": round(boylam, 7),
        "iha_irtifa": round(irtifa, 1),
        "iha_dikilme": round(random.uniform(-4, 4), 1),
        "iha_yonelme": round(yonelme, 1),
        "iha_yatis": round(max(-90, min(90, yatis)), 1),
        "iha_hizi": round(hiz + random.uniform(-1, 1), 1),
        "zaman_farki": random.randint(20, 500),
    }


def konum_bilgileri(simdi):
    liste = []
    for t in TAKIMLAR.values():
        p = t["son_telemetri"]
        if p is None:
            continue
        liste.append({
            "takim_numarasi": t["takim_numarasi"],
            "iha_enlem": p["iha_enlem"],
            "iha_boylam": p["iha_boylam"],
            "iha_irtifa": p["iha_irtifa"],
            "iha_dikilme": p["iha_dikilme"],
            "iha_yonelme": p["iha_yonelme"],
            "iha_yatis": p["iha_yatis"],
            "iha_hizi": p["iha_hiz"],     # dokümanda cevaptaki ad "iha_hizi"
            "zaman_farki": int((simdi - t["son_telemetri_zamani"]) * 1000),
        })
    for r in AYAR.get("sahte_rakipler", []):
        liste.append(sahte_rakip_konumu(r, simdi))
    return liste


# ---------------------------------------------------------------------------
# Flask uygulaması
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False


def hata_kaydi(takim, mesaj):
    if takim in TAKIMLAR:
        TAKIMLAR[takim]["son_hata"] = mesaj
        TAKIMLAR[takim]["son_hata_zamani"] = time.time()


def ip_izinli_mi(kadi):
    if not AYAR.get("ip_kontrolu", False):
        return True
    for t in AYAR["takimlar"]:
        if t["kadi"] == kadi and t.get("ip"):
            return request.remote_addr == t["ip"]
    return True


def oturum_gerekli(f):
    @wraps(f)
    def sarmal(*a, **k):
        if "kadi" not in session:
            kaydet("istek", ip=request.remote_addr, yol=request.path, durum=401)
            return Response("Kimliksiz erişim denemesi. Oturum açmanız gerekmektedir.", 401)
        if not ip_izinli_mi(session["kadi"]):
            kaydet("istek", ip=request.remote_addr, yol=request.path, durum=403,
                   neden="izinsiz IP")
            return Response("Bu IP adresinden bağlantıya izin verilmiyor.", 403)
        yapay_gecikme()
        return f(*a, **k)
    return sarmal


def hakem_gerekli(f):
    @wraps(f)
    def sarmal(*a, **k):
        if "kadi" not in session:
            return Response("Kimliksiz erişim denemesi.", 401)
        if session.get("rol") != "hakem":
            return Response("Yetkisiz erişim denemesi.", 403)
        return f(*a, **k)
    return sarmal


@app.post("/api/giris")
def giris():
    veri = request.get_json(silent=True)
    if not isinstance(veri, dict) or not isinstance(veri.get("kadi"), str) \
            or not isinstance(veri.get("sifre"), str):
        kaydet("giris", ip=request.remote_addr, durum=204)
        return Response(status=204)
    kadi, sifre = veri["kadi"], veri["sifre"]
    hakem = AYAR.get("hakem", {})
    if kadi == hakem.get("kadi") and sifre == hakem.get("sifre"):
        session.clear()
        session.update(kadi=kadi, rol="hakem", takim=0)
        kaydet("giris", ip=request.remote_addr, kadi=kadi, rol="hakem", durum=200)
        konsol(f"HAKEM giriş yaptı ({request.remote_addr})")
        return jsonify(0)
    for t in AYAR["takimlar"]:
        if t["kadi"] == kadi and t["sifre"] == sifre:
            if not ip_izinli_mi(kadi):
                kaydet("giris", ip=request.remote_addr, kadi=kadi, durum=403)
                return Response("Bu IP adresinden bağlantıya izin verilmiyor.", 403)
            session.clear()
            session.update(kadi=kadi, rol="takim", takim=t["takim_numarasi"])
            kaydet("giris", ip=request.remote_addr, kadi=kadi, durum=200)
            konsol(f"Takım {t['takim_numarasi']} ({kadi}) giriş yaptı ({request.remote_addr})")
            return jsonify(t["takim_numarasi"])
    kaydet("giris", ip=request.remote_addr, kadi=kadi, durum=400)
    konsol(f"Hatalı giriş denemesi: {kadi!r} ({request.remote_addr})")
    return Response(HATA_GIRIS, 400)


@app.get("/api/sunucusaati")
@oturum_gerekli
def sunucusaati():
    return jsonify(sunucu_saati())


@app.post("/api/telemetri_gonder")
@oturum_gerekli
def telemetri_gonder():
    simdi = time.time()
    takim = session["takim"]
    p = request.get_json(silent=True)

    with KILIT:
        durum = TAKIMLAR.get(takim)
        if durum is None:      # hakem hesabı telemetri gönderemez
            return Response("Yetkisiz erişim denemesi.", 403)

        # 1) Hız sınırı: son 1 sn içinde zaten 2 paket kabul edildiyse reddet
        pencere = durum["kabul_zamanlari"]
        while pencere and simdi - pencere[0] >= 1.0:
            pencere.popleft()
        if len(pencere) >= 2:
            durum["reddedilen"] += 1
            durum["hiz_ihlali"] += 1
            hata_kaydi(takim, "2 Hz üstü gönderim (400 / 3)")
            kaydet("telemetri", takim=takim, durum=400, kod=HATA_HIZ)
            return Response(HATA_HIZ, 400)

        # 2) Format ve aralık kontrolü
        tur, mesaj = telemetri_dogrula(p)
        if tur == "format":
            durum["reddedilen"] += 1
            hata_kaydi(takim, f"Format: {mesaj} (204)")
            kaydet("telemetri", takim=takim, durum=204, neden=mesaj, govde=p)
            konsol(f"Takım {takim}: 204 format hatası -> {mesaj}")
            return Response(status=204)
        if tur == "aralik":
            durum["reddedilen"] += 1
            hata_kaydi(takim, f"Aralık: {mesaj} (400 / 2)")
            kaydet("telemetri", takim=takim, durum=400, kod=HATA_ARALIK, neden=mesaj, govde=p)
            konsol(f"Takım {takim}: 400 aralık hatası -> {mesaj}")
            return Response(HATA_ARALIK, 400)
        if int(p["takim_numarasi"]) != takim:
            durum["reddedilen"] += 1
            mesaj = f"takim_numarasi={p['takim_numarasi']}, oturum={takim}"
            hata_kaydi(takim, f"Takım no uyuşmuyor: {mesaj} (400 / 4)")
            kaydet("telemetri", takim=takim, durum=400, kod=HATA_TAKIM_NO, neden=mesaj)
            return Response(HATA_TAKIM_NO, 400)

        # 3) Kabul: istatistikleri güncelle
        if durum["son_telemetri_zamani"] is not None:
            bosluk = simdi - durum["son_telemetri_zamani"]
            durum["en_uzun_bosluk"] = max(durum["en_uzun_bosluk"], bosluk)
            if bosluk > 1.0:
                durum["bosluk_sayisi"] += 1
                konsol(f"Takım {takim}: {bosluk:.2f} sn telemetri boşluğu (ceza adayı)")
        pencere.append(simdi)
        durum["son_5sn"].append(simdi)
        while durum["son_5sn"] and simdi - durum["son_5sn"][0] > 5.0:
            durum["son_5sn"].popleft()
        durum["son_telemetri"] = p
        durum["son_telemetri_zamani"] = simdi
        durum["toplam"] += 1

        cevap = {"sunucusaati": sunucu_saati(simdi), "konumBilgileri": konum_bilgileri(simdi)}

    kaydet("telemetri", takim=takim, durum=200, govde=p)
    return jsonify(cevap)


@app.post("/api/kilitlenme_bilgisi")
@oturum_gerekli
def kilitlenme_bilgisi():
    takim = session["takim"]
    p = request.get_json(silent=True)
    if not isinstance(p, dict) or "kilitlenmeBitisZamani" not in p \
            or "otonom_kilitlenme" not in p:
        hata_kaydi(takim, "Kilitlenme paketi format hatası (204)")
        kaydet("kilitlenme", takim=takim, durum=204, govde=p)
        return Response(status=204)
    tur, mesaj = saat_dogrula(p["kilitlenmeBitisZamani"], "kilitlenmeBitisZamani")
    if tur is None and p["otonom_kilitlenme"] not in (0, 1):
        tur, mesaj = "aralik", "otonom_kilitlenme 0 veya 1 olmalı"
    if tur:
        kod = 204 if tur == "format" else 400
        hata_kaydi(takim, f"Kilitlenme: {mesaj} ({kod})")
        kaydet("kilitlenme", takim=takim, durum=kod, neden=mesaj, govde=p)
        return Response(status=204) if kod == 204 else Response(HATA_ARALIK, 400)
    with KILIT:
        KILITLENMELER.append({
            "alinma": sunucu_saati(), "takim": takim,
            "bitis": p["kilitlenmeBitisZamani"], "otonom": p["otonom_kilitlenme"],
        })
    kaydet("kilitlenme", takim=takim, durum=200, govde=p)
    konsol(f"Takım {takim}: KİLİTLENME bildirildi, bitiş {saat_metni(p['kilitlenmeBitisZamani'])}, "
           f"otonom={p['otonom_kilitlenme']}")
    return Response("", 200)


@app.post("/api/kamikaze_bilgisi")
@oturum_gerekli
def kamikaze_bilgisi():
    takim = session["takim"]
    p = request.get_json(silent=True)
    if isinstance(p, dict) and "qrMetni " in p and "qrMetni" not in p:
        # Dokümandaki örnekte anahtar sonunda boşluk var ("qrMetni "); ikisini de kabul et.
        p["qrMetni"] = p.pop("qrMetni ")
    if not isinstance(p, dict) or not isinstance(p.get("qrMetni"), str) \
            or "kamikazeBaslangicZamani" not in p or "kamikazeBitisZamani" not in p:
        hata_kaydi(takim, "Kamikaze paketi format hatası (204)")
        kaydet("kamikaze", takim=takim, durum=204, govde=p)
        return Response(status=204)
    for ad in ("kamikazeBaslangicZamani", "kamikazeBitisZamani"):
        tur, mesaj = saat_dogrula(p[ad], ad)
        if tur:
            kod = 204 if tur == "format" else 400
            hata_kaydi(takim, f"Kamikaze: {mesaj} ({kod})")
            kaydet("kamikaze", takim=takim, durum=kod, neden=mesaj, govde=p)
            return Response(status=204) if kod == 204 else Response(HATA_ARALIK, 400)
    dogru = p["qrMetni"].strip() == str(AYAR["qr"]["metin"])
    with KILIT:
        KAMIKAZELER.append({
            "alinma": sunucu_saati(), "takim": takim,
            "baslangic": p["kamikazeBaslangicZamani"], "bitis": p["kamikazeBitisZamani"],
            "metin": p["qrMetni"], "dogru": dogru,
        })
    kaydet("kamikaze", takim=takim, durum=200, govde=p, dogru=dogru)
    konsol(f"Takım {takim}: KAMİKAZE bildirildi, QR={p['qrMetni']!r} "
           f"({'DOĞRU' if dogru else 'YANLIŞ'})")
    return Response("", 200)


@app.get("/api/qr_koordinati")
@oturum_gerekli
def qr_koordinati():
    return jsonify({"qrEnlem": AYAR["qr"]["enlem"], "qrBoylam": AYAR["qr"]["boylam"]})


@app.get("/api/hss_koordinatlari")
@oturum_gerekli
def hss_koordinatlari():
    liste = []
    if HSS_AKTIF:
        for i, h in enumerate(AYAR.get("hss", [])):
            liste.append({"id": i, "hssEnlem": h["enlem"], "hssBoylam": h["boylam"],
                          "hssYaricap": h["yaricap_m"]})
    return jsonify({"sunucusaati": sunucu_saati(), "hss_koordinat_bilgileri": liste})


# --- Hakem uç noktaları (dokümanda yok, test için) --------------------------

@app.post("/api/hakem/hss")
@hakem_gerekli
def hakem_hss():
    global HSS_AKTIF
    p = request.get_json(silent=True) or {}
    HSS_AKTIF = bool(p.get("aktif"))
    kaydet("hss", aktif=HSS_AKTIF)
    konsol(f"HSS {'AKTİF EDİLDİ (duyuru)' if HSS_AKTIF else 'kapatıldı'}")
    return jsonify({"aktif": HSS_AKTIF})


@app.get("/panel/durum")
def panel_durum():
    simdi = time.time()
    with KILIT:
        takimlar = []
        for t in TAKIMLAR.values():
            while t["son_5sn"] and simdi - t["son_5sn"][0] > 5.0:
                t["son_5sn"].popleft()
            p = t["son_telemetri"] or {}
            yas = None if t["son_telemetri_zamani"] is None else simdi - t["son_telemetri_zamani"]
            takimlar.append({
                "no": t["takim_numarasi"], "kadi": t["kadi"],
                "yas": yas, "hz": len(t["son_5sn"]) / 5.0,
                "toplam": t["toplam"], "reddedilen": t["reddedilen"],
                "hiz_ihlali": t["hiz_ihlali"], "bosluk": t["bosluk_sayisi"],
                "en_uzun_bosluk": t["en_uzun_bosluk"],
                "otonom": p.get("iha_otonom"), "kilitlenme": p.get("iha_kilitlenme"),
                "enlem": p.get("iha_enlem"), "boylam": p.get("iha_boylam"),
                "irtifa": p.get("iha_irtifa"), "batarya": p.get("iha_batarya"),
                "gps": saat_metni(p.get("gps_saati")) if p else "",
                "son_hata": t["son_hata"],
                "hata_yasi": None if t["son_hata_zamani"] is None else simdi - t["son_hata_zamani"],
            })
        return jsonify({
            "sunucu_saati": saat_metni(sunucu_saati(simdi)),
            "hss_aktif": HSS_AKTIF,
            "takimlar": takimlar,
            "kilitlenmeler": [dict(k, alinma=saat_metni(k["alinma"]), bitis=saat_metni(k["bitis"]))
                              for k in KILITLENMELER[-20:]][::-1],
            "kamikazeler": [dict(k, alinma=saat_metni(k["alinma"]),
                                 baslangic=saat_metni(k["baslangic"]), bitis=saat_metni(k["bitis"]))
                            for k in KAMIKAZELER[-20:]][::-1],
            "oturum": session.get("rol"),
        })


@app.get("/")
def kok():
    return redirect("/panel")


@app.get("/panel")
def panel():
    return Response(PANEL_HTML, mimetype="text/html")


@app.errorhandler(404)
def bulunamadi(_):
    return Response("Geçersiz URL.", 404)


@app.errorhandler(500)
def sunucu_hatasi(_):
    return Response("Sunucu içi hata.", 500)


PANEL_HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Test Sunucusu - Hakem Paneli</title>
<style>
 :root{--bg:#f6f6f3;--kart:#fff;--yazi:#1d1d1b;--soluk:#6b6b66;--cizgi:#ddd;--iyi:#2e7d32;--kotu:#c62828;--uyari:#b26a00}
 @media (prefers-color-scheme:dark){:root{--bg:#1b1b1a;--kart:#262624;--yazi:#eee;--soluk:#a3a39c;--cizgi:#3a3a37;--iyi:#66bb6a;--kotu:#ef5350;--uyari:#ffb74d}}
 body{font:14px/1.5 system-ui,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--yazi)}
 h1{font-size:18px;margin:0 0 4px} h2{font-size:15px;margin:20px 0 8px}
 .kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:8px;padding:12px;overflow-x:auto}
 table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
 th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--cizgi);white-space:nowrap}
 th{color:var(--soluk);font-weight:500}
 .iyi{color:var(--iyi)} .kotu{color:var(--kotu)} .uyari{color:var(--uyari)} .soluk{color:var(--soluk)}
 button{font:inherit;padding:5px 12px;border-radius:6px;border:1px solid var(--cizgi);background:var(--kart);color:var(--yazi);cursor:pointer}
 input{font:inherit;padding:4px 8px;border-radius:6px;border:1px solid var(--cizgi);background:var(--bg);color:var(--yazi);width:120px}
 .satir{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
</style></head><body>
<h1>Test yarışma sunucusu</h1>
<div class="soluk">Sunucu saati: <b id="saat">-</b> · Bu sayfa her saniye yenilenir</div>

<h2>Takımlar</h2>
<div class="kart"><table><thead><tr>
<th>No</th><th>Kullanıcı</th><th>Son paket</th><th>Hız</th><th>Kabul</th><th>Red</th>
<th>2 Hz ihlali</th><th>&gt;1 sn boşluk</th><th>En uzun boşluk</th><th>Otonom</th><th>Kilit</th>
<th>Konum</th><th>İrtifa</th><th>Batarya</th><th>GPS saati</th><th>Son hata</th></tr></thead>
<tbody id="takimlar"></tbody></table></div>

<h2>Hava savunma sistemi</h2>
<div class="kart satir">
 Durum: <b id="hss">-</b>
 <button onclick="hss(true)">Duyur (aç)</button><button onclick="hss(false)">Kapat</button>
 <span class="soluk">Hakem girişi gerekir:</span>
 <input id="hk" placeholder="hakem adı"><input id="hs" type="password" placeholder="şifre">
 <button onclick="hakemGiris()">Giriş</button> <span id="hmsg" class="soluk"></span>
</div>

<h2>Kilitlenme bildirimleri</h2>
<div class="kart"><table><thead><tr><th>Alındı</th><th>Takım</th><th>Kilitlenme bitişi</th><th>Otonom</th></tr></thead><tbody id="kilit"></tbody></table></div>

<h2>Kamikaze bildirimleri</h2>
<div class="kart"><table><thead><tr><th>Alındı</th><th>Takım</th><th>Başlangıç</th><th>Bitiş</th><th>QR metni</th><th>Sonuç</th></tr></thead><tbody id="kami"></tbody></table></div>

<script>
const f=(v,n=1)=>v==null?'-':Number(v).toFixed(n);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function yenile(){
 try{
  const d=await (await fetch('/panel/durum')).json();
  document.getElementById('saat').textContent=d.sunucu_saati;
  document.getElementById('hss').innerHTML=d.hss_aktif?'<span class="uyari">AKTİF</span>':'kapalı';
  document.getElementById('takimlar').innerHTML=d.takimlar.map(t=>{
   const yas=t.yas==null?'<span class="soluk">hiç</span>':
     `<span class="${t.yas>1?'kotu':'iyi'}">${f(t.yas,1)} sn önce</span>`;
   const hz=`<span class="${t.hz>=1&&t.hz<=2?'iyi':(t.hz>0?'uyari':'soluk')}">${f(t.hz,1)} Hz</span>`;
   const hata=t.son_hata?`<span class="${t.hata_yasi<5?'kotu':'soluk'}">${esc(t.son_hata)}</span>`:'';
   return `<tr><td>${t.no}</td><td>${esc(t.kadi)}</td><td>${yas}</td><td>${hz}</td><td>${t.toplam}</td>
    <td>${t.reddedilen}</td><td class="${t.hiz_ihlali?'kotu':''}">${t.hiz_ihlali}</td>
    <td class="${t.bosluk?'kotu':''}">${t.bosluk}</td><td>${f(t.en_uzun_bosluk,2)} sn</td>
    <td>${t.otonom??'-'}</td><td>${t.kilitlenme??'-'}</td>
    <td>${t.enlem==null?'-':f(t.enlem,6)+', '+f(t.boylam,6)}</td><td>${f(t.irtifa)}</td>
    <td>${f(t.batarya,0)}</td><td>${esc(t.gps)}</td><td>${hata}</td></tr>`}).join('');
  document.getElementById('kilit').innerHTML=d.kilitlenmeler.map(k=>
   `<tr><td>${k.alinma}</td><td>${k.takim}</td><td>${k.bitis}</td><td>${k.otonom}</td></tr>`).join('')||'<tr><td colspan=4 class="soluk">Henüz yok</td></tr>';
  document.getElementById('kami').innerHTML=d.kamikazeler.map(k=>
   `<tr><td>${k.alinma}</td><td>${k.takim}</td><td>${k.baslangic}</td><td>${k.bitis}</td><td>${esc(k.metin)}</td>
    <td class="${k.dogru?'iyi':'kotu'}">${k.dogru?'Doğru':'Yanlış'}</td></tr>`).join('')||'<tr><td colspan=6 class="soluk">Henüz yok</td></tr>';
 }catch(e){document.getElementById('saat').textContent='bağlantı yok';}
}
async function hakemGiris(){
 const r=await fetch('/api/giris',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({kadi:hk.value,sifre:hs.value})});
 hmsg.textContent=r.status==200?'Hakem girişi tamam':'Giriş başarısız ('+r.status+')';
}
async function hss(aktif){
 const r=await fetch('/api/hakem/hss',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({aktif})});
 hmsg.textContent=r.status==200?'':(r.status==401?'Önce hakem girişi yapın':'Yetki yok ('+r.status+')');
 yenile();
}
yenile(); setInterval(yenile,1000);
</script></body></html>"""


# ---------------------------------------------------------------------------
# Başlatma
# ---------------------------------------------------------------------------

def main():
    global LOG_DOSYASI
    ap = argparse.ArgumentParser(description="TEKNOFEST Savaşan İHA test sunucusu")
    ap.add_argument("--ayarlar", default="ayarlar.yaml")
    args = ap.parse_args()

    ayarlari_yukle(args.ayarlar)
    app.secret_key = AYAR.get("gizli_anahtar") or os.urandom(32)

    kayit_klasoru = Path(AYAR.get("kayit_klasoru", "kayitlar"))
    kayit_klasoru.mkdir(parents=True, exist_ok=True)
    dosya = kayit_klasoru / datetime.datetime.now().strftime("oturum_%Y%m%d_%H%M%S.jsonl")
    LOG_DOSYASI = open(dosya, "a", encoding="utf-8")

    host, port = AYAR.get("host", "0.0.0.0"), int(AYAR.get("port", 5000))
    konsol(f"Test sunucusu başlıyor: http://{host}:{port}  (panel: /panel)")
    konsol(f"Kayıt dosyası: {dosya}")
    konsol(f"Takımlar: {[t['kadi'] for t in AYAR['takimlar']]}  "
           f"Sahte rakip: {len(AYAR.get('sahte_rakipler', []))}  "
           f"IP kontrolü: {'açık' if AYAR.get('ip_kontrolu') else 'kapalı'}")

    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        import logging
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        konsol("waitress yüklü değil, Flask'ın kendi sunucusu kullanılıyor "
               "(çalışır ama 'pip install waitress' önerilir)")
        app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
