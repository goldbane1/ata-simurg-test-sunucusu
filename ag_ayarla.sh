#!/usr/bin/env bash
# =============================================================================
# ag_ayarla.sh - Test sunucusunun IP ve port ayarlarını tek komutla yapar
#
#   * Pi'nin ethernet (eth0) IP adresini ayarlar (NetworkManager / nmcli)
#   * Sunucunun portunu ayarlar.yaml içinde değiştirir (önce yedek alır)
#   * Servisi yeniden başlatır ve sunucunun cevap verdiğini kontrol eder
#
# Kullanım:
#   ./ag_ayarla.sh --durum                         Sadece mevcut durumu göster
#   sudo ./ag_ayarla.sh                            Soru sorarak (etkileşimli) ayarla
#   sudo ./ag_ayarla.sh --ip 192.168.50.25/24      Sadece IP'yi değiştir
#   sudo ./ag_ayarla.sh --port 8080                Sadece portu değiştir
#   sudo ./ag_ayarla.sh --ip 10.0.0.25/24 --port 5000
#   sudo ./ag_ayarla.sh --dhcp                     Ethernet'i otomatik IP'ye döndür
#   ./ag_ayarla.sh --ip 10.0.0.25/24 --deneme      Hiçbir şeyi değiştirmeden ne
#                                                  yapılacağını göster
# =============================================================================

set -euo pipefail

# --- Sabitler (gerekirse buradan değiştirin) ---------------------------------
PROJE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AYAR_DOSYASI="${AYAR_DOSYASI:-$PROJE_DIR/ayarlar.yaml}"
SERVIS="teknofest-sunucu"
PROFIL="test-agi"          # nmcli bağlantı profilinin adı
ARAYUZ="eth0"              # Pi'nin ethernet girişi

ARGUMANLAR=("$@")
DENEME=0
YENI_IP=""
YENI_GW=""
YENI_PORT=""
DHCP=0
SADECE_DURUM=0

# --- Ekran çıktısı ------------------------------------------------------------
if [[ -t 1 ]]; then
    YESIL=$'\e[32m'; KIRMIZI=$'\e[31m'; SARI=$'\e[33m'; KALIN=$'\e[1m'; SIFIR=$'\e[0m'
else
    YESIL=""; KIRMIZI=""; SARI=""; KALIN=""; SIFIR=""
fi
bilgi()  { echo "${KALIN}==>${SIFIR} $*"; }
tamam()  { echo "  ${YESIL}✓${SIFIR} $*"; }
uyari()  { echo "  ${SARI}!${SIFIR} $*"; }
hata()   { echo "  ${KIRMIZI}✗ HATA:${SIFIR} $*" >&2; exit 1; }

# Deneme modunda komutu çalıştırmaz, sadece yazar
calistir() {
    if (( DENEME )); then
        echo "  [deneme] $*"
    else
        "$@"
    fi
}

kullanim() {
    sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

# --- Doğrulama ---------------------------------------------------------------
ip_gecerli() {
    # Beklenen biçim: 192.168.50.25/24
    local ip="$1"
    [[ "$ip" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})/([0-9]{1,2})$ ]] || return 1
    local i
    for i in 1 2 3 4; do
        (( BASH_REMATCH[i] <= 255 )) || return 1
    done
    (( BASH_REMATCH[5] >= 8 && BASH_REMATCH[5] <= 30 )) || return 1
    [[ "${BASH_REMATCH[1]}" != "127" ]] || return 1   # 127.x başka cihazdan erişilemez
}

gw_gecerli() {
    [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

port_gecerli() {
    # 1024 altı portlar yönetici yetkisi ister; servis normal kullanıcıyla çalışıyor
    [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 1024 && $1 <= 65535 ))
}

# --- Mevcut durumu okuma -----------------------------------------------------
mevcut_port() {
    sed -nE 's/^port:[[:space:]]*([0-9]+).*/\1/p' "$AYAR_DOSYASI" | head -n1
}

mevcut_ip() {
    ip -4 -br addr show "$ARAYUZ" 2>/dev/null | awk '{print $3}'
}

durum_goster() {
    bilgi "Mevcut durum"
    local ip_bilgi port servis
    ip_bilgi="$(ip -4 -br addr show "$ARAYUZ" 2>/dev/null || true)"
    if [[ -n "$ip_bilgi" ]]; then
        echo "  Ethernet ($ARAYUZ)  : $(awk '{print $2, $3}' <<<"$ip_bilgi")"
    else
        echo "  Ethernet ($ARAYUZ)  : IPv4 adresi yok"
    fi
    if command -v nmcli >/dev/null 2>&1; then
        if nmcli -t -f NAME con show 2>/dev/null | grep -qx "$PROFIL"; then
            echo "  nmcli profili     : $PROFIL ($(nmcli -g ipv4.method con show "$PROFIL" 2>/dev/null))"
        else
            echo "  nmcli profili     : '$PROFIL' henüz yok"
        fi
    fi
    echo "  Wi-Fi / diğer IP  : $(hostname -I 2>/dev/null || echo '-')"
    port="$(mevcut_port)"
    echo "  Sunucu portu      : ${port:-bulunamadı} (ayarlar.yaml)"
    servis="$(systemctl is-active "$SERVIS" 2>/dev/null || true)"
    echo "  Servis            : ${servis:-bilinmiyor}"
    local adres
    adres="$(mevcut_ip)"
    if [[ -n "$adres" && -n "$port" ]]; then
        echo "  Panel             : ${KALIN}http://${adres%/*}:${port}/panel${SIFIR}"
    fi
    echo
}

# --- Ayarlama adımları -------------------------------------------------------
ip_ayarla() {
    bilgi "Ethernet IP adresi ayarlanıyor: $YENI_IP ${YENI_GW:+(ağ geçidi $YENI_GW)}"
    command -v nmcli >/dev/null 2>&1 || (( DENEME )) || hata "nmcli bulunamadı (NetworkManager kurulu değil)"

    # Ağ geçidi verilmediyse bu bağlantı internet yolu olmasın (Wi-Fi interneti bozulmasın)
    local varsayilan_yol="no"
    [[ -z "$YENI_GW" ]] && varsayilan_yol="yes"
    # autoconnect-priority: Pi'de eth0 için hazır gelen DHCP profilinin önüne geçer
    local ayarlar=(ipv4.method manual ipv4.addresses "$YENI_IP" ipv4.gateway "$YENI_GW"
                   ipv4.never-default "$varsayilan_yol"
                   connection.autoconnect yes connection.autoconnect-priority 10)

    if profil_var; then
        calistir nmcli con mod "$PROFIL" "${ayarlar[@]}"
    else
        calistir nmcli con add type ethernet ifname "$ARAYUZ" con-name "$PROFIL" "${ayarlar[@]}"
    fi
    if etkinlestir; then
        tamam "IP adresi uygulandı"
    fi
}

profil_var() {
    (( DENEME )) && return 0
    nmcli -t -f NAME con show | grep -qx "$PROFIL"
}

etkinlestir() {
    if (( DENEME )); then
        echo "  [deneme] nmcli con up $PROFIL"
        return 0
    fi
    if nmcli con up "$PROFIL" >/dev/null 2>&1; then
        return 0
    fi
    uyari "Ayar kaydedildi ama şu an etkinleşmedi. Ethernet kablosu takılı değilse normal;"
    uyari "kablo takılınca otomatik etkinleşir."
    return 1
}

dhcp_ayarla() {
    bilgi "Ethernet otomatik IP'ye (DHCP) döndürülüyor"
    if profil_var; then
        calistir nmcli con mod "$PROFIL" ipv4.method auto ipv4.addresses "" ipv4.gateway "" \
            ipv4.never-default no
        etkinlestir || true
        tamam "Otomatik IP'ye döndürüldü"
    else
        uyari "'$PROFIL' profili yok, değiştirilecek bir şey yok"
    fi
}

port_ayarla() {
    local eski
    eski="$(mevcut_port)"
    [[ -n "$eski" ]] || hata "ayarlar.yaml içinde 'port:' satırı bulunamadı"
    if [[ "$eski" == "$YENI_PORT" ]]; then
        tamam "Port zaten $YENI_PORT, değişiklik yok"
        return
    fi
    bilgi "Port değiştiriliyor: $eski -> $YENI_PORT"

    # Başka bir program bu portu kullanıyor mu?
    if command -v ss >/dev/null 2>&1 && ss -ltnH "sport = :$YENI_PORT" 2>/dev/null | grep -q .; then
        hata "$YENI_PORT portu başka bir program tarafından kullanılıyor"
    fi

    local yedek sahip
    yedek="$AYAR_DOSYASI.yedek_$(date +%Y%m%d_%H%M%S)"
    sahip="$(stat -c '%U:%G' "$AYAR_DOSYASI")"
    calistir cp -p "$AYAR_DOSYASI" "$yedek"
    calistir sed -i -E "s/^port:[[:space:]]*[0-9]+/port: $YENI_PORT/" "$AYAR_DOSYASI"
    # sudo ile değişen dosya root'a geçmesin; sonra normal kullanıcı da düzenleyebilsin
    calistir chown "$sahip" "$AYAR_DOSYASI" "$yedek"
    (( DENEME )) || [[ "$(mevcut_port)" == "$YENI_PORT" ]] || hata "Port yazılamadı, yedek: $yedek"
    tamam "ayarlar.yaml güncellendi (yedek: $(basename "$yedek"))"
}

servis_yenile() {
    local port
    port="${YENI_PORT:-$(mevcut_port)}"
    bilgi "Servis yeniden başlatılıyor"
    if (( ! DENEME )) && ! systemctl cat "$SERVIS" >/dev/null 2>&1; then
        uyari "$SERVIS servisi kurulu değil; sunucuyu elle yeniden başlatın"
        return
    fi
    calistir systemctl restart "$SERVIS"
    (( DENEME )) && return

    # Sunucu 10 saniye içinde cevap vermeli
    local kod="000" i
    for i in $(seq 1 20); do
        kod="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/panel/durum" || true)"
        [[ "$kod" == "200" ]] && break
        sleep 0.5
    done
    if [[ "$kod" == "200" ]]; then
        tamam "Sunucu $port portunda cevap veriyor"
    else
        hata "Sunucu cevap vermiyor. Kayıtlara bakın: journalctl -u $SERVIS -n 30"
    fi
}

# --- Etkileşimli mod -----------------------------------------------------------
sorarak_ayarla() {
    durum_goster
    local girdi
    read -r -p "Yeni ethernet IP'si (ör. 192.168.50.25/24, boş = değiştirme): " girdi
    YENI_IP="$girdi"
    if [[ -n "$YENI_IP" ]]; then
        read -r -p "Ağ geçidi (çoğu test ağında boş bırakın): " girdi
        YENI_GW="$girdi"
    fi
    read -r -p "Yeni sunucu portu (boş = değiştirme): " girdi
    YENI_PORT="$girdi"
    if [[ -z "$YENI_IP" && -z "$YENI_PORT" ]]; then
        echo "Değişiklik yok, çıkılıyor."
        exit 0
    fi
}

# --- Argümanlar ----------------------------------------------------------------
if (( $# == 0 )); then
    ETKILESIMLI=1
else
    ETKILESIMLI=0
fi

while (( $# )); do
    case "$1" in
        --ip)      YENI_IP="${2:-}"; shift 2 ;;
        --gateway) YENI_GW="${2:-}"; shift 2 ;;
        --port)    YENI_PORT="${2:-}"; shift 2 ;;
        --dhcp)    DHCP=1; shift ;;
        --durum)   SADECE_DURUM=1; shift ;;
        --deneme)  DENEME=1; shift ;;
        -h|--help|--yardim) kullanim ;;
        *) hata "Bilinmeyen seçenek: $1  (yardım için: $0 --yardim)" ;;
    esac
done

[[ -f "$AYAR_DOSYASI" ]] || hata "ayarlar.yaml bulunamadı: $AYAR_DOSYASI"

if (( SADECE_DURUM )); then
    durum_goster
    exit 0
fi

if (( EUID != 0 && ! DENEME )); then
    hata "Ağ ayarı için yönetici yetkisi gerekir. Şöyle çalıştırın: sudo $0 ${ARGUMANLAR[*]}"
fi

(( ETKILESIMLI )) && sorarak_ayarla

# --- Doğrula ---------------------------------------------------------------------
if [[ -n "$YENI_IP" ]]; then
    ip_gecerli "$YENI_IP" || hata "Geçersiz IP: '$YENI_IP'. Biçim: 192.168.50.25/24 (127.x kullanılamaz)"
fi
if [[ -n "$YENI_GW" ]]; then
    gw_gecerli "$YENI_GW" || hata "Geçersiz ağ geçidi: '$YENI_GW'"
fi
if [[ -n "$YENI_PORT" ]]; then
    port_gecerli "$YENI_PORT" || hata "Geçersiz port: '$YENI_PORT'. 1024 ile 65535 arasında olmalı"
fi
if (( DHCP )) && [[ -n "$YENI_IP" ]]; then
    hata "--dhcp ve --ip birlikte kullanılamaz"
fi

(( DENEME )) && bilgi "${SARI}DENEME MODU: hiçbir şey değiştirilmeyecek${SIFIR}"

# --- Uygula ----------------------------------------------------------------------
(( DHCP ))            && dhcp_ayarla
[[ -n "$YENI_IP" ]]   && ip_ayarla
[[ -n "$YENI_PORT" ]] && port_ayarla
servis_yenile
echo
durum_goster
