# AssemblyAI — GlovesOn için çıkarılmış notlar

5 Eylül 2026'da resmî dokümantasyondan derlendi. Amaç genel bir özet değil:
**bu projede kullanacağımız her alanın adı, limiti ve doğru kullanımı.**

---

## 1. Maliyet — önce bunu bil

**Voice Agent API: $0.075 / dakika ($4.50 / saat)**, bağlı geçen konuşma süresi
üzerinden saniye saniye faturalanıyor.

Ücretsiz kotanın (185 saat pre-recorded, 333 saat streaming transkripsiyon) **Voice
Agent'ı kapsadığı yazmıyor** — o kota transkripsiyon tarafı için. Yani sesli ajanla
yaptığın her dakika para.

Pratikte ne demek: bir saatlik test $4.50. 25 günlük geliştirme boyunca dikkatli
davranırsan toplam 20-50 dolar bandında kalır. Dikkatsiz davranmanın tek yolu var
ve şu:

> **Sekmeyi açık unutma.** Oturum açık kaldığı sürece sayaç işliyor. Test bitince
> "End session"a bas ya da sekmeyi kapat. Temiz kapatmazsan 30 saniyelik faturalı
> bir devam penceresi kalıyor.

Arayüzdeki `session.end` bunu hallediyor, `pagehide` olayında da otomatik gönderiliyor
— ama tarayıcıyı zorla kapatırsan devreye girmez.

Hackathon ödülünün yarısı ($5k) AAI kredisi, ama o kazanırsan geliyor. Şimdilik kendi
cebin.

---

## 2. Türkçe — kesin cevap

| | Durum |
|---|---|
| **Giriş (konuşma → metin)** | **Destekleniyor.** 18 dilden biri, Universal-3.5 Pro Streaming ile |
| **Çıkış (metin → konuşma)** | **Desteklenmiyor.** Sadece 6 dil: İngilizce, İtalyanca, İspanyolca, Almanca, Portekizce, Fransızca. Türkçe "yakında" listesinde |

**Sonuç:** demo İngilizce. Türkçe konuşup İngilizce cevap alan bir ajan teknik olarak
mümkün ama tuhaf; jüri de zaten İngilizce.

Pitch'te bir cümlelik kullanımı var: *"Girişte Türkçe bugün çalışıyor, çıkış yol
haritasında — yani aynı ajan Türk depolarında konuşulan dili bugün anlıyor."*

---

## 3. Sesler

**Amerikan aksanı:** `alba`, `eve`, `george`, `jane`, `jean`, `mary`, `michael`
**İngiliz aksanı:** `anna`, `charles`, `paul`, `vera`
**Diğer diller:** `giovanni` (İT), `lola` (ES), `juergen` (DE), `rafael` (PT), `estelle` (FR)

Bizde `eve` seçili (Amerikan). Önce `anna` (İngiliz) vardı; kulakta yorgun/bıkkın
duruyordu ve bu, "elleri dolu bir işçiye yardım eden uyanık bir sesi" istediğimiz
yerde yanlış sinyaldi.

Önemli kısıt: **ses oturum başladıktan sonra değiştirilemiyor**, yani seçim
bağlantıdan önce yapılıyor.

Deneme artık ucuz: `session_config` her `/api/voice-token` isteğinde `agent.json`'dan
kuruluyor, yani `voice_id`'yi değiştirip push etmek yeterli — `./publish.sh`
gerekmiyor. Bir sonraki oturum yeni sesle açılır.

---

## 4. HTTP tools — bizim gateway'in sözleşmesi

```json
{
  "name": "...",
  "description": "...",
  "parameters": { /* JSON Schema */ },
  "execution_mode": "interactive" | "hold",
  "timeout_seconds": 10,
  "http": {
    "url": "https://...",
    "http_method": "GET|POST|PUT|PATCH|DELETE",
    "headers": [{ "name": "X-Tool-Secret", "value": "..." }]
  }
}
```

**Parametreler nasıl gidiyor:**

- `GET` / `DELETE` → query string'e. Değerler string'e çevriliyor, null olanlar atılıyor
- `POST` / `PUT` / `PATCH` → JSON gövdesine, tipler korunarak

Bizim tool'lar buna uyuyor: okuma uçları GET (query), mal girişi POST (gövde).

**Sert limitler:**

| | Değer |
|---|---|
| Cevap boyutu | **8 KiB** — aşarsan kesiliyor |
| Uç nokta | **Sadece HTTPS, sadece public host.** Private IP ve loopback yasak |
| Yönlendirme | **Takip edilmiyor.** 301/302 dönen bir adres çalışmaz |
| Zaman aşımı | `timeout_seconds` ile |
| Hata | 2xx olmayan cevaplar ve zaman aşımları modele kısa bir metin olarak dönüyor, model toparlamayı deniyor |

`localhost` yasağının sebebi bu: AssemblyAI tool'u **kendi sunucusundan** çağırıyor.
Tünel ya da bir dağıtım şart, tercih değil.

**Header güvenliği:** header değerleri şifreli saklanıyor ve yazma-amaçlı — geri
okunmuyor, sadece adı ve son yazılma zamanı görünüyor. Yani `TOOL_SHARED_SECRET`
oraya güvenle gidiyor.

---

## 5. Turn detection — dokunma

| Alan | Aralık | Varsayılan |
|---|---|---|
| `input.turn_detection.vad_threshold` | 0.0–1.0 | 0.5 |
| `input.turn_detection.min_silence` | ms | adaptif |
| `input.turn_detection.max_silence` | ms | adaptif |
| `input.turn_detection.interrupt_response` | bool | `true` (barge-in açık) |
| `input.turn_detection.interruption_delay` | 0–1000 ms | moda göre |

Dokümantasyonun kendi tavsiyesi net: **"Leave it on default."** Hiçbir ayar
vermezsen ajan konuşanın temposuna uyum sağlıyor. `min_silence` ya da `max_silence`
verdiğin anda bu adaptif davranış kapanıyor.

`interruption_delay`'i yükseltmenin tek meşru sebebi: "hı hı" gibi kısa onay sesleri
ajanın sözünü kesiyorsa.

**İlk karar `turn_detection` bloğunu hiç yazmamaktı.** İlk canlı oturumda bozuldu:
konuşanın öbekler arasındaki kısa duraklamaları cümle sonu sanıldı ve tek bir cümle
("post a goods receipt, twenty pieces of 4711") ikiye bölündü. Uyarlanabilir tempo
akıcı, aralıksız konuşma üzerine kalibreli; ana dili İngilizce olmayan bir konuşmacıda
yetmiyor.

**Yeni karar:** `min_silence: 800`, `max_silence: 2000`, barge-in açık.

**Bedeli açıkça söylenmeli:** bu iki alanı elle vermek uyarlanabilir tempoyu kapatıyor.
Artık herkese aynı sabit ayar uygulanıyor. Demo için doğru takas, ama "her konuşana
uyum sağlıyor" iddiası artık geçerli değil — sunumda bu cümle kurulmayacak.

Değerler ölçülerek seçilmedi, ilk deneme olarak konuldu. Kesilme sürerse `min_silence`
yükseltilir; ajan geç cevap veriyormuş gibi hissettirirse `max_silence` düşürülür.

---

## 6. Malzeme numarası sorunu — çözümü hazır

Bu, planın 8. gününe risk olarak yazdığımız şeydi. İki alan var, ikisi de `input`
altında:

| Alan | Tip | Limit | Ne işe yarıyor |
|---|---|---|---|
| `input.transcription_prompt` | string | **1750 karakter** | Sahneyi tarif ediyor: nerede, kim konuşuyor, hangi terimler geçiyor |
| `input.keyterms` | string dizisi | **100 terim** | Tanıma modelini o kelimelere doğru eğiyor (word boost) |

Kritik ayrım: bunlar ajanın **nasıl cevap vereceğini** değil, **konuşanın nasıl
yazıya dökülmesini** etkiliyor. İçine davranış talimatı yazma.

Dokümantasyon bunların özellikle şunlarda işe yaradığını söylüyor: ürün kodları,
SKU'lar, referans numaraları, kısaltmalar, özel isimler. Yani MATNR ve raf kodları
tam hedef kitlesi.

**Yapıldı:** `agent.json` içine 851 karakterlik bir `transcription_prompt` (depo
sahnesi, numaraların nasıl söylendiği, malzeme isimleri) ve 56 terimlik `keyterms`
listesi eklendi (100 limitinin altında; sayı listeye terim eklendikçe büyüdü).

---

## 7. Diğer kullanılabilir alanlar

- **`input.transcription_mode`** — `balanced` (varsayılan), `min_latency`,
  `max_accuracy`. Malzeme numaraları yanlış okunmaya devam ederse `max_accuracy`
  denenecek ilk şey; bedeli gecikme
- **`input.voice_focus`** — bir aç/kapa değil, bir MOD. Değerleri `near-field`
  (varsayılan) ve `far-field`; yani hiç yazmasan bile gürültü bastırma zaten
  çalışıyor. "Devreye alınacak" demek yanlıştı — açıktı, sadece mod seçilmemişti.
  Depo işçisi mikrofonun ağzında değil (eldivenli, kutu taşıyor), o yüzden
  `agent.json`'a **`far-field`** yazıldı. Senaryodan türetildi, ölçülerek değil.
  `input.voice_focus_threshold` (0.0–1.0, varsayılan **0.85**, `voice_focus`
  set edilmişse geçerli) default'ta bırakıldı — turn_detection'daki dersle aynı:
  gerçek kayıt olmadan sayı uydurma. Construction-time: STT bağlantısı açılırken
  uygulanıyor, oturum ortasında değişmez. Ölçüm protokolü: `docs/noise-test.md`.
- **`input.language_codes`** — beklenen dilleri bildirmek
- **`output.volume`** — 0-100, oturum ortasında değiştirilebiliyor

---

## 8. Oturum kurulumu — dikkat edilecek tek şey

`agent_id` ile satır içi ayarlar **birbirini dışlıyor.** İlk `session.update`
mesajında `agent_id` gönderiyorsan, o mesajda **başka hiçbir alan olamaz.**

Bizim `web/index.html` şunu gönderiyor, doğru:

```js
ws.send(JSON.stringify({ type: 'session.update', session: { agent_id: agentId } }));
```

Ayarları oturum bazında denemek istersen `agent_id`'yi çıkarıp her şeyi satır içi
vermen gerekiyor — hızlı deneme için kullanışlı ama bizim akışımız publish tabanlı.

Oturum başladıktan sonra **değiştirilemeyenler:** `greeting`, `voice`, `output.format`.
**Değiştirilebilenler:** `system_prompt`, `keyterms`, `transcription_prompt`,
`turn_detection`, `volume`.

---

## 9. Prompt yazımı — dokümantasyonun kendi tavsiyeleri

- **En kritik kural en üste.** "Uzun promptlar dikkati seyreltir"
- **Markdown kullanma.** TTS onu harfiyen okuyor: `**alba**` yazarsan kullanıcı
  "yıldız yıldız alba yıldız yıldız" duyuyor
- Kaçınılacak ifadeleri **tam metin olarak** yaz, "kibar olma" gibi belirsiz
  yönergeler verme
- Kötü örneği iyi örnekle eşleştir
- Kuralları gerçek konuşma kayıtlarına karşı test et, tahminle değil
- "Great question!" ve "I'd be happy to help" gibi kalıpları açıkça yasakla
- Tanımlayıcıları sesli okurken: nokta için "dot", eğik çizgi için "slash"

**Yapıldı:** sistem promptu bu tavsiyelere göre yeniden yazıldı. Yazma kuralı artık
en üstte, tek başlık altında; markdown yasağı ve yasak kalıplar açıkça belirtildi.
