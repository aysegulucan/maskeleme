

## Kurulum

```bash
pip install pymupdf pikepdf
```

## 1. Adım — Eşleştirme dosyasını doldurun

`anahtar_kelimeler.csv` şu an 32 satır placeholder içeriyor:

```
anahtar_kelime,karsilik
ANAHTAR_KELIME_01,1
ANAHTAR_KELIME_02,2
...
```

`anahtar_kelime` sütununa PDF'lerde geçen gerçek kelime/ifadeleri,
 `karsilik` sütununa neyle değiştirileceğini yazın:

```
anahtar_kelime,karsilik
```

## 2. Adım — Ayarları düzenleyin ve çalıştırın

Komut satırı argümanı **yok**. `mask_pdf.py` dosyasını açın, en üstteki
"AYARLAR" bölümündeki dört satırı kendi durumunuza göre düzenleyin:

```python
# PDF_INPUT_PATH: Tek bir PDF dosyası ya da PDF'lerin bulunduğu bir klasör
#                 olabilir (klasörse içindeki tüm .pdf dosyaları işlenir).
PDF_INPUT_PATH = "raporlar/"

# ANAHTAR_KELIMELER_CSV: Anahtar kelime/karşılık eşleştirme tablosunun yolu.
ANAHTAR_KELIMELER_CSV = "anahtar_kelimeler.csv"

# OUTPUT_DIR: Maskelenmiş PDF'lerin yazılacağı klasör (yoksa oluşturulur).
OUTPUT_DIR = "maskeli/"

# DRY_RUN: True yapılırsa dosyalar DEĞİŞTİRİLMEZ, yalnızca kaç eşleşme
#          bulunduğu konsolda gösterilir.
DRY_RUN = False
```

- Tek bir dosyayı işlemek isterseniz `PDF_INPUT_PATH`'i o dosyanın yoluna
  ayarlayın (örn. `"rapor.pdf"`).
- Klasördeki tüm PDF'leri  işlemek isterseniz
  `PDF_INPUT_PATH`'i klasör yoluna ayarlayın (örn. `"raporlar_klasoru/"`).
- Önce sadece kaç eşleşme bulunduğunu görmek isterseniz (dosyaları
  değiştirmeden) `DRY_RUN = True` yapın; sonuçtan emin olunca `False`'a
  çevirip gerçek çıktıyı üretin.

Ayarları kaydettikten sonra, hiçbir argüman vermeden çalıştırın:

```bash
python mask_pdf.py
```

Çalıştırdıktan sonra konsolda her anahtar kelime için kaç eşleşme bulunduğunu
gösteren bir özet çıkar — "hiç bulunamadı" uyarısı çıkan kelimeler için
yazımı/boşlukları PDF'teki haliyle birebir eşleştiğinizden emin olun.

## Bilinen kısıt: karşılık, orijinal kelimeden çok uzunsa

PDF'lerde metin sabit konumda durur; Word gibi "reflow" (metnin otomatik
kayması) yoktur. Script bunu şöyle yönetir:

- **Karşılık orijinalden kısa veya benzer uzunluktaysa** : sorunsuz çalışır, en fazla küçük bir boşluk
  kalabilir.
- **Karşılık orijinalden çok uzunsa**:
  script font boyutunu otomatik küçültür; yine de sığmıyorsa **konsolda
  uyarı verir** ("orijinal alana sığmıyor — PDF'i gözle kontrol edin") ve o
  belirli örnekte komşu metinle görsel çakışma olabilir.

**Öneri:** `karsilik` değerlerini mümkün olduğunca kısa tutun. Konsolda uyarı çıkan dosyaları mutlaka açıp gözle kontrol
edin.

## Silme 

İşlem, eşleşen metnin PDF'in **içerik akışından tamamen
çıkarılmasıdır**. PyMuPDF varsayılan
ayarlarla kaydettiğinde, silinen orijinal metin dosyanın içinde
"kullanılmayan/referanssız obje" olarak (görünmez ama pikepdf gibi bir
araçla çıkarılabilir şekilde) kalabiliyordu. Bu, aşağıdaki iki önlemle
engellenir:

1. Dosya kaydedilirken agresif "garbage collection" (`garbage=4`) uygulanır
   — bu tür referanssız objeler dosyadan tamamen silinir.
2. Script, kaydettiği **her dosyayı otomatik olarak yeniden açıp** orijinal
   anahtar kelimelerin dosyanın hiçbir yerinde (görünür metin, gizli
   objeler, ham baytlar) kalmadığını doğrular ve sonucu konsolda raporlar.
   Bir kelime hâlâ bulunursa **"KRİTİK UYARI"** ile açıkça belirtilir ve o
   dosyayı kullanmamanız söylenir.

Bu davranış pikepdf ile ham dosya içeriği taranarak doğrulanmıştır;
düzeltme sonrasında hiçbir iz kalmadığı teyit edilmiştir.

## Büyük/küçük harf ve Türkçe İ/I/ı/i

Türkçe'de İngilizce'den farklı olarak 4 ayrı "i" harfi vardır (İ/i noktalı,
I/ı noktasız). Hem PyMuPDF'in hem Python'un standart büyük/küçük harf
dönüşümü bu ayrımı hatalı yapar (örn. "İstanbul".lower() Türkçe'de olması
gerekenden farklı bir sonuç verir). Bu nedenle script'e Türkçe'ye özel bir
varyant üretici eklenmiştir:

- 

## Türkçe karakterler (görüntüleme)

Script, ş/ğ/ı/İ/ç/ö/ü karakterlerinin doğru görünmesi için sistemde bulunan
bir Unicode font (DejaVu Sans) kullanır. Farklı bir ortamda çalıştırırsanız
ve bu font bulunamazsa, script bir uyarı basar — bu durumda `TR_FONT_CANDIDATES`
listesine kendi sisteminizdeki bir Unicode TTF font yolunu ekleyin.
