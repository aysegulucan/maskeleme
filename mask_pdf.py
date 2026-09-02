"""
KULLANIM
--------
Komut satırı argümanı YOK. Aşağıdaki "AYARLAR" bölümündeki üç yolu (PDF
girdisi, anahtar_kelimeler.csv, çıktı klasörü) bu dosyanın içinde düzenleyip
kaydedin, sonra çalıştırın:

    python mask_pdf.py

GEREKSİNİMLER
-------------
    pip install pymupdf pikepdf
"""
import csv
import sys
from pathlib import Path

import pikepdf
import pymupdf

# =============================================================================
# AYARLAR — çalıştırmadan önce bu üç satırı kendi yollarınızla güncelleyin
# =============================================================================
# PDF_INPUT_PATH: Tek bir PDF dosyası ya da PDF'lerin bulunduğu bir klasör
#                 olabilir (klasörse içindeki tüm .pdf dosyaları işlenir).
PDF_INPUT_PATH = "raporlar/"

# ANAHTAR_KELIMELER_CSV: Anahtar kelime/karşılık eşleştirme tablosunun yolu.
ANAHTAR_KELIMELER_CSV = "anahtar_kelimeler.csv"

# OUTPUT_DIR: Maskelenmiş PDF'lerin yazılacağı klasör (yoksa oluşturulur).
OUTPUT_DIR = "maskeli/"

# DRY_RUN: True yapılırsa dosyalar DEĞİŞTİRİLMEZ, yalnızca kaç eşleşme
#          bulunduğu konsolda gösterilir. Önce True ile kontrol edip, sonuçtan
#          emin olduktan sonra False yaparak gerçek çıktıyı üretmeniz önerilir.
DRY_RUN = False
# =============================================================================

# Türkçe karakterleri (ş, ğ, ı, İ, ç, ö, ü) doğru göstermek için Unicode
# destekli bir font kullanıyoruz. PDF'in kendi (Base-14) fontları Türkçe
# karakterleri desteklemez ve kutucuk/soru işareti olarak görünür.
TR_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",   # macOS'ta bulunabilir
    "/Library/Fonts/Arial Unicode.ttf",
]


def find_tr_font() -> str | None:
    for path in TR_FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def verify_fully_removed(pdf_path: Path, keywords: list[str]) -> list[str]:
    """Kaydedilen PDF'i pikepdf ile açıp, orijinal anahtar kelimelerin
    dosyanın HİÇBİR yerinde (görünür sayfa içeriği, yetim/referanssız
    objeler, ham bayt seviyesi) kalıp kalmadığını doğrular.
    Bulunan kelimelerin listesini döndürür (boşsa: tamamen temiz)."""
    still_present = set()

    raw = pdf_path.read_bytes()
    for kw in keywords:
        if kw.encode("utf-8") in raw:
            still_present.add(kw)

    try:
        with pikepdf.open(pdf_path) as pdf:
            for obj in pdf.objects:
                if not isinstance(obj, pikepdf.Stream):
                    continue
                try:
                    data = obj.read_bytes()
                except Exception:
                    continue
                for kw in keywords:
                    if kw.encode("utf-8") in data:
                        still_present.add(kw)
    except Exception as e:
        print(f"[uyarı] {pdf_path.name}: pikepdf ile doğrulama yapılamadı ({e})", file=sys.stderr)

    return sorted(still_present)


# Türkçe'de İngilizce'den farklı olarak 4 ayrı "i" harfi vardır: İ/i (noktalı)
# ve I/ı (noktasız). PyMuPDF'in dahili büyük/küçük harf duyarsız araması ve
# Python'un standart .upper()/.lower()'ı bu ayrımı doğru yapmaz (örn.
# "İstanbul".lower() -> "i̇stanbul" gibi hatalı/birleşik karakterli bir sonuç
# verir, "istanbul" değil). Bu yüzden aramayı, kelimenin gerçekçi tüm
# yazım/büyük-küçük harf varyantlarını deneyerek yapıyoruz.
_TR_LOWER_MAP = str.maketrans({"İ": "i", "I": "ı"})
_TR_UPPER_MAP = str.maketrans({"i": "İ", "ı": "I"})
_ASCII_FOLD_MAP = str.maketrans({"İ": "I", "ı": "i"})  # Türkçe klavyesiz/ASCII yazım


def _tr_lower(s: str) -> str:
    return s.translate(_TR_LOWER_MAP).lower()


def _tr_upper(s: str) -> str:
    return s.translate(_TR_UPPER_MAP).upper()


def case_variants(keyword: str) -> list[str]:
    """Bir anahtar kelimenin PDF'te karşılaşılabilecek gerçekçi tüm
    büyük/küçük harf ve Türkçe İ/I/ı/i yazım varyantlarını üretir."""
    ascii_folded = keyword.translate(_ASCII_FOLD_MAP)
    variants = {
        keyword,
        keyword.upper(), keyword.lower(), keyword.title(),
        _tr_upper(keyword), _tr_lower(keyword),
        ascii_folded, ascii_folded.upper(), ascii_folded.lower(), ascii_folded.title(),
    }
    return [v for v in variants if v]


def load_mapping(csv_path: Path) -> list[tuple[str, str]]:
    """CSV'den (anahtar_kelime, karsilik) çiftlerini okur.
    Boş/placeholder anahtar kelimeler (henüz doldurulmamış satırlar) atlanır."""
    pairs = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = (row.get("anahtar_kelime") or "").strip()
            val = (row.get("karsilik") or "").strip()
            if not kw or kw.startswith("ANAHTAR_KELIME_"):
                continue  # henüz doldurulmamış placeholder satır
            pairs.append((kw, val))
    # Uzun anahtar kelimeleri önce işle: biri diğerinin alt dizesiyse
    # uzun olanın önce
    # eşleşmesi yanlış kısmi değişimi önler.
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def fit_font_size(value: str, max_width: float, font: "pymupdf.Font", start_size: float, min_size: float = 5.0) -> float:
    """Karşılık metni orijinal kelimenin kapladığı genişliğe sığmıyorsa
    (örn. kısa bir kelime yerine uzun bir kod yazılıyorsa), üst üste binmeyi
    önlemek için font boyutunu kademeli olarak küçültür."""
    size = start_size
    while size > min_size and font.text_length(value, fontsize=size) > max_width:
        size -= 0.5
    return size


def estimate_font_size(page: "pymupdf.Page", rect: "pymupdf.Rect", text_dict=None) -> float:
    """Belirtilen dikdörtgenle örtüşen metin span'ının orijinal font boyutunu bulur.
    Bulunamazsa, dikdörtgenin yüksekliğinden kabaca tahmin eder."""
    text_dict = text_dict or page.get_text("dict")
    best_overlap, best_size = 0.0, None
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_rect = pymupdf.Rect(span["bbox"])
                overlap = span_rect.intersect(rect).get_area()
                if overlap > best_overlap:
                    best_overlap, best_size = overlap, span["size"]
    if best_size:
        return best_size
    return max(rect.height * 0.7, 6.0)


def mask_pdf(input_path: Path, output_path: Path, mapping: list[tuple[str, str]],
             tr_font: str | None, dry_run: bool = False) -> tuple[dict, list[str]]:
    doc = pymupdf.open(input_path)
    match_counts = {kw: 0 for kw, _ in mapping}
    overflow_warnings = []
    font_obj = pymupdf.Font(fontfile=tr_font) if tr_font else pymupdf.Font("helv")

    for page in doc:
        text_dict = page.get_text("dict")
        # (dikdörtgen, karşılık, tahmini_font_boyutu) listesi topla.
        # PyMuPDF'in search_for'u genel olarak büyük/küçük harf duyarsızdır
        # ama Türkçe'ye özgü İ/I/ı/i harflerinde güvenilir değildir (örn.
        # "İstanbul" araması "Istanbul" yazılmış olanı bulamayabilir) — bu
        # yüzden kelimenin tüm gerçekçi yazım varyantlarını (case_variants)
        # deniyoruz. Aynı bölgenin birden fazla varyant/kelimeyle tekrar
        # eşleşmesini önlemek için görülen dikdörtgenleri takip ediyoruz.
        seen_rect_keys = set()
        replacements = []
        for keyword, value in mapping:
            for variant in case_variants(keyword):
                for rect in page.search_for(variant):
                    rect_key = (round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1))
                    if rect_key in seen_rect_keys:
                        continue
                    seen_rect_keys.add(rect_key)
                    size = estimate_font_size(page, rect, text_dict)
                    replacements.append((rect, value, size))
                    match_counts[keyword] += 1

        if dry_run or not replacements:
            continue

        # 1) Eşleşen bölgeleri beyazla kapat (redaksiyon)
        for rect, _, _ in replacements:
            page.add_redact_annot(rect, text=None, fill=(1, 1, 1), cross_out=False)
        page.apply_redactions()

        # 2) Karşılık gelen metni aynı konuma, Türkçe destekli fontla yaz.
        # Karşılık, orijinal kelimeden uzunsa (örn. kısa bir kelime yerine
        # uzun bir kod), bitişik metinle üst üste binmemesi için font
        # boyutu otomatik küçültülür.
        for rect, value, size in replacements:
            fitted_size = fit_font_size(value, rect.width, font_obj, size)
            if font_obj.text_length(value, fontsize=fitted_size) > rect.width * 1.4:
                overflow_warnings.append(
                    f"  sayfa {page.number + 1}: '{value}' orijinal alana sığmıyor "
                    f"(en küçük fontta bile taşıyor) — PDF'i gözle kontrol edin"
                )
            insert_point = pymupdf.Point(rect.x0, rect.y1 - 0.22 * rect.height)
            if tr_font:
                page.insert_text(insert_point, value, fontsize=fitted_size,
                                  fontname="TRFont", fontfile=tr_font, color=(0, 0, 0))
            else:
                page.insert_text(insert_point, value, fontsize=fitted_size, color=(0, 0, 0))

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # ÖNEMLİ: garbage=4 + clean=True olmadan, PDF'in "silinen" orijinal
        # içerik akışı (content stream) dosyanın içinde referanssız/kullanılmayan
        # bir obje olarak KALABİLİR — görünmez ama dosyanın ham baytlarında hâlâ
        # var olur ve bir metin düzenleyici veya pikepdf gibi bir araçla geri
        # çıkarılabilir. garbage=4 bu tür referanssız objeleri dosyadan tamamen
        # siler. Bunu bizzat test ederek doğruladık (bkz. konuşma).
        doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return match_counts, overflow_warnings


def main():
    # Tüm ayarlar dosyanın başındaki "AYARLAR" bölümünden okunur — komut
    # satırı argümanı gerekmez, sadece yukarıdaki üç satırı düzenleyip
    # "python mask_pdf.py" ile çalıştırın.
    mapping_path = Path(ANAHTAR_KELIMELER_CSV)
    if not mapping_path.exists():
        print(f"[hata] Eşleştirme dosyası bulunamadı: {mapping_path}", file=sys.stderr)
        print("       AYARLAR bölümündeki ANAHTAR_KELIMELER_CSV yolunu kontrol edin.", file=sys.stderr)
        sys.exit(1)
    mapping = load_mapping(mapping_path)
    if not mapping:
        print(
            f"[hata] {mapping_path} içinde doldurulmuş satır yok. "
            f"'anahtar_kelime' sütununu ANAHTAR_KELIME_XX placeholder'ları yerine "
            f"gerçek kelimelerle doldurun.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"[bilgi] {len(mapping)} anahtar kelime/karşılık çifti yüklendi.")

    tr_font = find_tr_font()
    if not tr_font:
        print("[uyarı] Türkçe karakter destekli font bulunamadı; ş/ğ/ı/İ gibi karakterler bozuk görünebilir.", file=sys.stderr)

    in_path = Path(PDF_INPUT_PATH)
    if not in_path.exists():
        print(f"[hata] {in_path} bulunamadı. AYARLAR bölümündeki PDF_INPUT_PATH yolunu kontrol edin.", file=sys.stderr)
        sys.exit(1)
    files = sorted(in_path.glob("*.pdf")) if in_path.is_dir() else [in_path]
    if not files:
        print(f"[hata] {in_path} altında .pdf bulunamadı", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(OUTPUT_DIR)
    total_counts = {kw: 0 for kw, _ in mapping}
    all_overflow_warnings = []
    all_leak_warnings = []
    original_keywords = [kw for kw, _ in mapping]

    for f in files:
        out_path = out_dir / f"maskeli_{f.name}"
        counts, overflow_warnings = mask_pdf(f, out_path, mapping, tr_font, dry_run=DRY_RUN)
        found = sum(counts.values())
        action = "bulundu (dry-run, dosya değiştirilmedi)" if DRY_RUN else f"değiştirildi -> {out_path.name}"
        print(f"[{f.name}] {found} eşleşme {action}")
        for kw, c in counts.items():
            total_counts[kw] += c
        if overflow_warnings:
            all_overflow_warnings.append(f"[{f.name}]")
            all_overflow_warnings.extend(overflow_warnings)

        if not DRY_RUN:
            leaked = verify_fully_removed(out_path, original_keywords)
            if leaked:
                all_leak_warnings.append(f"[{f.name}] HÂLÂ DOSYADA BULUNAN: {', '.join(leaked)}")
            else:
                print(f"  [doğrulandı] {out_path.name}: orijinal anahtar kelimelerin hiçbiri dosyada kalmadı.")

    print("\n[özet] Anahtar kelime başına toplam eşleşme sayısı:")
    for kw, c in total_counts.items():
        flag = "" if c > 0 else "  <-- hiç bulunamadı, yazımı/büyük-küçük harfi kontrol edin"
        print(f"  {kw}: {c}{flag}")

    if all_overflow_warnings:
        print("\n[uyarı] Bazı karşılıklar orijinal kelimenin kapladığı alana sığmadı "
              "(çok küçük fontla bile taşıyor), komşu metinle üst üste binmiş olabilir:")
        for w in all_overflow_warnings:
            print(w)

    if all_leak_warnings:
        print("\n[!!! KRİTİK UYARI !!!] Aşağıdaki dosyalarda orijinal anahtar kelimelerden "
              "biri veya birkaçı hâlâ dosyanın içinde (görünmüyor olsa bile) tespit edildi. "
              "Bu dosyaları KULLANMAYIN, sebebini araştırın:")
        for w in all_leak_warnings:
            print("  " + w)
    elif not DRY_RUN:
        print("\n[tamam] Tüm çıktı dosyaları doğrulandı: orijinal anahtar kelimelerden hiçbiri dosyalarda kalmadı.")


if __name__ == "__main__":
    main()
