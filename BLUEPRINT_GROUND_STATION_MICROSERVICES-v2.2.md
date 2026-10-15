# DEOS Yer İstasyonu Mikroservis Mimarisi Uygulama Blueprint'i (v2.2 Master - Medya Bağımsız Evrensel Çerçeve & Tam ICD Uyumlu)

Bu doküman, **DEOS (Dokuz Eylül Otonom Sistemler)** elektrikli otonom yarış aracı Yer Kontrol İstasyonu (`DEOS_NODE_GROUND_CONTROL = 0x02`) yazılımının mikroservis mimarisinde sıfırdan inşa edilmesi için güncel **DEOS v1.1 (`0x11`) Medya Bağımsız Çekirdek Protokol** ve modüler ICD şartnamelerine (`DOC-ICD-CORE-001`, `DOC-ICD-TRP-LORA-007`, `DOC-ICD-NET-003 v1.4`, `DOC-ICD-DIAG-004 v1.2`, `DOC-ICD-DATA-002 v1.1`, `DOC-ICD-NODE-BMS-012`, `DOC-ICD-NODE-TRAC-008`, `DOC-ICD-NODE-STR-009`, `DOC-ICD-NODE-BRK-010`, `DOC-ICD-SRV-LGHT-012 v1.2`) tam uyumlu olarak birleştirilmiş **Master Uygulama Rehberidir**.

> **KRİTİK MİMARİ KURAL (`DOC-ICD-CORE-001` & `DOC-ICD-TRP-CANFD-005`):**
> DEOS v1.1 mimarisinde **29-bit Extended CAN ID**, bit kaydırma ve CAN-FD DLC yuvarlama/padding kuralları **yalnızca araç içi fiziksel CAN-FD omurgasında** geçerlidir. Yer Kontrol İstasyonu (LoRa), Textual UI (TCP) ve ROS 2 Köprüsü (UDP) gibi harici sistemler **kesinlikle 29-bit CAN ID hesaplamaz ve CAN Frame üretmez**. Tüm harici düğümler **Medya Bağımsız Standart DEOS Taşıma Çerçevesi (Universal DEOS Transport Frame / `deos_message_t`)** ile konuşur. Araçtaki Ana Beyin (`DEOS_NODE_MAIN_STM32 = 0x03`, Router), LoRa'dan gelen Evrensel DEOS Çerçevesini soyup hedef bir CAN düğümü ise otomatik olarak 29-bit CAN-FD çerçevesine dönüştürür.

---

## 1. Mimari Genel Bakış ve Katmanlı Simetri

Sistem, `docker-compose` çatısı altında izole bir köprü ağı (`deos-net`) üzerinde haberleşen **5 konteynerden** oluşur. **Encoder** ve **Decoder** servisleri saf **Evrensel DEOS Çerçevesi (Universal DEOS Frame)** seviyesinde tam simetrik ve durumsuz (stateless) çalışır; tüm LoRa L2 taşıma zarflaması (`0xAA 0x55`, `Flag`, `Length`, `CRC16-CCITT`), UART yönetimi ve çift yönlü ACK/Retry (ARQ) mekanizması **Linker** servisine devredilmiştir.

```text
                             ┌────────────────────────┐
                             │       Web Arayüzü      │
                             │        (web-ui)        │
                             └───────┬────────▲───────┘
                     command/request │        │ telemetry/#
                             (JSON)  │        │ command/status (JSON)
                                     ▼        │
┌────────────────────────────────────┴────────┴───────────────────────────────────┐
│ CODEC KATMANI (Durumsuz - Saf Medya Bağımsız DEOS Evrensel Çerçevesi ile Çalışır)│
│                                                                                 │
│   ┌─────────────────┐                                  ┌─────────────────┐      │
│   │     Encoder     │                                  │     Decoder     │      │
│   │    (encoder)    │                                  │    (decoder)    │      │
│   └────────┬────────┘                                  └────────▲────────┘      │
└────────────┼────────────────────────────────────────────────────┼───────────────┘
             │ lora/tx/reliable (ACK=1)                           │ lora/rx/frame
             │ lora/tx/unreliable (ACK=0)                         │ (Saf DEOS Frame)
             │ (Saf DEOS Frame Bytes)                             │
             ▼                                                    │
┌─────────────────────────────────────────────────────────────────┴───────────────┐
│ TAŞIMA VE DONANIM KATMANI (Durumlu - LoRa L2 Zarfı, ACK/Retry, CRC16 ve UART)   │
│                                                                                 │
│                        Linker Mikroservisi (linker)                             │
│                                                                                 │
│   - TX: Saf DEOS Frame'e AA 55 + Flag + Len + CRC16 ekler, UART'a basar.        │
│   - ARQ (TX): Flag 0x01 ise 500-1000 ms ACK timer başlatır (Max 3 retry).       │
│   - RX: UART'tan AA 55 senkronizasyonu yapar, CRC16-CCITT doğrular.             │
│   - ACK (RX->TX): Gelen pakette Flag 0x01 (ACK_REQ) ise derhal UART'a           │
│     Flag 0x02 (IS_ACK) + Gelen_CRC16 yanıtı basar.                              │
│   - ACK (TX Onayı): Gelen paket Flag 0x02 (IS_ACK) ise eşleşen CRC timer'ını    │
│     durdurur ve UI'a command/status basar.                                      │
│   - Soyma: Veri paketinin L2 zarfını soyup saf DEOS Frame'i Decoder'a verir.    │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ UART (pyserial: /dev/ttyUSB0)
                                         ▼
                            ┌────────────────────────┐
                            │  Ebyte E220-900T22D    │
                            │  (LoRa Donanımı)       │
                            └────────────────────────┘
```

### Konteyner Görev Tanımları
1. **`mosquitto` (Eclipse Mosquitto Broker):** Servisler arası asenkron Pub/Sub mesajlaşmasını yönetir. Port `1883` konteyner içi iletişim, Port `9001` ise tarayıcı WebSocket bağlantısı için ayrılmıştır.
2. **`encoder` (Komut Kodlayıcı - Durumsuz / Stateless):**
   * UI'dan gelen JSON komutlarını Pydantic v2 şemaları ve ICD kurallarına göre doğrular:
     * `PING`, `GET_NODE_INFO`, `SUBSCRIBE` ve `UNSUBSCRIBE` komutlarının Broadcast (`0xFE`, `0xFF`) adreslere gönderilmesini engeller (Unicast zorunluluğu).
     * BMS servis mesajlarının `0x30 (BMS_GATEWAY)` yerine doğrudan `0x20 (BMS_MAIN)` veya `0x21 (BMS_AUX)` düğümlerine yönlendirilmesini denetler.
     * Aydınlatma (`LIGHTING = 0x08`) mesajlarının her zaman `0x03 (MAIN_STM32)` düğümüne yönlendirilmesini denetler.
   * Kaynak düğüm kimliğini her zaman `Source = DEOS_NODE_GROUND_CONTROL (0x02)` ve protokol sürümünü `Version = 0x11` olarak atar.
   * Yalnızca **Saf DEOS Evrensel Çerçevesi (Universal DEOS Frame)** üretir (Başlık + Payload). `0xAA 0x55`, `Flag`, dış `Length` veya `CRC16` zarflaması yapmaz.
   * Komutta ACK isteniyorsa (`ack: true`) `lora/tx/reliable` konusuna, istenmiyorsa (`ack: false`) `lora/tx/unreliable` konusuna saf binary bayt dizisi olarak yayınlar.
3. **`decoder` (Telemetri ve Yanıt Çözümleyici - Durumsuz / Stateless):**
   * Linker'dan gelen **Saf DEOS Evrensel Çerçevesi** verisini (`lora/rx/frame`) çözer.
   * L2 zarf arama, `0xAA 0x55` veya `CRC16` kontrolleriyle uğraşmaz (bu temizliği Linker yapmıştır).
   * DEOS Başlık alanlarını (`Destination`, `Source`, `Priority`, `Version`, `Message Class`, `Service`, `Command`, `Sequence`, `Payload Length`) ve `Payload` baytlarını ayrıştırır.
   * `DOC-ICD-DATA-002` sinyal ölçekleme kurallarına göre ($\text{PhysicalValue} = \text{RawValue} \times \text{Scale} + \text{Offset}$, Little-Endian) fiziksel büyüklükleri hesaplar.
   * Liste tipi çoklu paket akışlarını (`DIAGNOSTIC / GET_FAULTS` için `0x0000 END_OF_FAULT_LIST` ve `BMS` hücre voltajı / sıcaklık / balancing listeleri için `Index = 0x00 END_OF_LIST`) 100 ms akış yapısına uygun şekilde birleştirerek ilgili `telemetry/<servis>` konusuna JSON formatında dağıtır.
4. **`linker` (Taşıma ve Donanım Yöneticisi - Durumlu / Stateful):**
   * Host makinedeki `/dev/ttyUSB0` seri portunu yönetir (kopmalara karşı `auto-reconnect with exponential backoff`).
   * **TX Zarflama (`DOC-ICD-TRP-LORA-007`):** Encoder'dan gelen saf DEOS Frame'i alır. Konu `reliable` ise `Flag: 0x01` (`LORA_FLAG_ACK_REQ`), `unreliable` ise `Flag: 0x00` (`LORA_FLAG_NONE`) atar. Paketin başına `0xAA 0x55`, `Flag (1B)`, `Length (1B, len(deos_frame))`, sonuna ise `Flag + Length + DEOS Frame` üzerinden hesapladığı Little-Endian `CRC16-CCITT (2B)` değerini ekleyip UART'a basar.
   * **Otomatik Tekrar (ARQ):** `Flag: 0x01` ile giden paketler için `500-600 ms` (konfigüre edilebilir `500-1000 ms`) zamanlayıcı başlatır, eşleşen CRC16 değerini taşıyan ACK gelmezse `MAX_RETRIES=3` defaya kadar paketi yeniden basar. Sonucu (`SENT`, `ACKED`, `RETRYING`, `TIMEOUT`) `command/status` konusuna bildirir.
   * **RX Doğrulama, Karşı ACK Üretimi ve Zarf Soyma:** UART akışında `0xAA 0x55` arar, `CRC16-CCITT` doğrular.
     * Gelen paket `Flag == 0x02` (`LORA_FLAG_IS_ACK`) ve `Length == 2` ise: içindeki 2 baytlık onaylanan CRC16 değerini okur, aktif retry timer'ını durdurur ve `command/status` konusuna başarı yayınlar.
     * Gelen paket `Flag == 0x00` veya `Flag == 0x01` ise: Eğer `Flag == 0x01` (`LORA_FLAG_ACK_REQ` - araçtan yere gelen kritik mesaj) ise **hiç vakit kaybetmeden** `[0xAA, 0x55, 0x02, 0x02, Rx_CRC_LSB, Rx_CRC_MSB, New_CRC_LSB, New_CRC_MSB]` ACK paketini UART'a geri basar. Ardından L2 zarfını (`AA 55 Flag Length` ve `CRC16`) soyarak içindeki saf DEOS Frame'i `lora/rx/frame` konusuna yayınlar.
5. **`web-ui` (Operatör Paneli ve Dashboard):**
   * Web tabanlı telemetri izleme, abonelik yönetimi (`SUBSCRIBE`/`UNSUBSCRIBE`, `0xFFFF` On-Change modu), düğüm sağlık/bilgi sorgulama (`PING`, `GET_NODE_INFO`, `GET_FAULTS`, `CLEAR_FAULTS`), parametre konfigürasyonu (`GET/SET/SAVE_PARAMETER`) ve gerçek zamanlı kontrol arayüzü sunar.

---

## 2. Dizin Yapısı (Monorepo Standardı)

```text
deos-ground-station/
├── docker-compose.yml
├── mosquitto/
│   └── mosquitto.conf
├── shared/
│   ├── pyproject.toml
│   └── deos_core/
│       ├── __init__.py
│       ├── enums.py          # Node ID, Priority, Class, Service, Command, State, Mode, Result Enum'ları
│       ├── crc.py            # Standart CRC16-CCITT (Polinom: 0x1021, Seed: 0xFFFF, Little-Endian)
│       ├── framing.py        # Universal DEOS Frame (Seviye 1: 9B/8B) ve LoRa L2 Zarfı (Seviye 2) paketleme/çözme
│       ├── models.py         # Pydantic v2 komut/telemetri şemaları ve ICD adresleme validatörleri
│       ├── scaling.py        # ICD PhysicalValue = RawValue * Scale + Offset dönüşüm yardımcıları
│       └── registry.py       # Servis bazlı Parameter ID (0x0001+) ve Node bazlı Fault ID (0x0000-0x0108) sözlükleri
└── services/
    ├── linker/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── main.py           # UART yönetimi, LoRa L2 Zarf Ekleme/Soyma, Çift Yönlü ACK/Retry FSM
    ├── encoder/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── main.py           # JSON Komut -> Saf DEOS Evrensel Çerçevesi (Binary)
    ├── decoder/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── main.py           # Saf DEOS Evrensel Çerçevesi -> Ölçeklenmiş JSON Telemetri
    └── web-ui/
        ├── Dockerfile
        ├── requirements.txt
        ├── app.py
        └── static/
            ├── index.html
            └── app.js
```

---

## 3. Protokol Seviyeleri ve Paket Yapıları

### 3.1. Seviye 1: Medya Bağımsız Standart DEOS Taşıma Çerçevesi (Encoder & Decoder Arasındaki Saf Veri)

Encoder'ın ürettiği ve Decoder'ın tükettiği donanım bağımsız çerçevedir:

$$\underbrace{\text{Sabit DEOS Başlığı (Header)}}_{9\text{ Byte (veya 8 Byte Wire Modu)}} + \underbrace{\text{Payload}}_{N\text{ Byte (Little-Endian)}}$$

> **ICD Uyumluluk ve Firmware Hizalama Notu (`DEOS_FRAME_LAYOUT`):**
> `DOC-ICD-CORE-001 (v1.1, Bölüm 9.1)` Evrensel Çerçeve başlığını **9 Byte** (`Payload Length` dahil, `9 + N` byte) olarak tanımlarken; `DOC-ICD-TRP-LORA-007 (Bölüm 2-3)` ve `DOC-ICD-TRP-ETH-006 (Bölüm 2-5)` içindeki C/Python örnekleri `deos_message_t` sabit başlığını **8 Byte** (`8 + N` byte; uzunluk bilgisi LoRa/TCP dış zarfındaki `Length` baytından `Length - 8` ile okunur) olarak göstermektedir.
> Bu nedenle `shared/deos_core/framing.py` içinde `DEOS_FRAME_LAYOUT` ortam değişkeni ile seçilebilir iki şema hazır bulundurulmalıdır (Agent, çalışma dizinindeki C header dosyası varsa ona göre, yoksa `UNIVERSAL_9B` olarak varsayılanı ayarlar):

#### A) `UNIVERSAL_9B`: `DOC-ICD-CORE-001` (Bölüm 9.1) 9-Bayt Başlık Şeması ($9 + N$ Bayt)
| Byte Ofset | Alan Adı | Tip | Boyut | Açıklama |
| :--- | :--- | :--- | :--- | :--- |
| **0** | `destination` | `uint8_t` | 1 Byte | Hedef düğüm kimliği (`deos_node_id_t`, Örn: `0x03` Main STM32, `0x10` Traction) |
| **1** | `source` | `uint8_t` | 1 Byte | Kaynak düğüm kimliği (Yer İstasyonu TX için sabit: `0x02` `DEOS_NODE_GROUND_CONTROL`) |
| **2** | `priority` | `uint8_t` | 1 Byte | Mesaj önceliği (`0x00` `EMERGENCY` .. `0x07` `BACKGROUND`) |
| **3** | `version` | `uint8_t` | 1 Byte | DEOS protokol sürümü (Sabit: `0x11` = v1.1) |
| **4** | `message_class` | `uint8_t` | 1 Byte | Mesaj sınıfı (`0x00` `SAFETY` .. `0x07` `NETWORK`) |
| **5** | `service` | `uint8_t` | 1 Byte | Fonksiyonel servis (`0x00` `SYSTEM` .. `0x08` `LIGHTING`) |
| **6** | `command` | `uint8_t` | 1 Byte | Servise ait komut ID |
| **7** | `sequence` | `uint8_t` | 1 Byte | Mesaj takip sayacı (`0x00` – `0xFF`, her TX mesajında 1 artar, mod 256) |
| **8** | `payload_length` | `uint8_t` | 1 Byte | Arkadan gelen dinamik veri bayt sayısı ($N$, `0` – `60` bayt) |
| **9 .. 9+N-1** | `payload` | `uint8_t[N]` | $N$ Byte | Komuta veya telemetriye özgü gerçek veri yükü (Little-Endian) |

* **Paketleme (`UNIVERSAL_9B`):** `struct.pack('<9B', dest, src, prio, ver, msg_class, service, cmd, seq, len(payload)) + payload`

#### B) `COMMON_8B`: `DOC-ICD-TRP-LORA-007` & `DOC-ICD-TRP-ETH-006` 8-Bayt `deos_message_t` Başlık Şeması ($8 + N$ Bayt)
| Byte Ofset | Alan Adı | Tip | Boyut | Açıklama |
| :--- | :--- | :--- | :--- | :--- |
| **0** | `priority` | `uint8_t` | 1 Byte | Mesaj önceliği (`0x00`–`0x07`) |
| **1** | `message_class` | `uint8_t` | 1 Byte | Mesaj sınıfı (`0x00`–`0x07`) |
| **2** | `service` | `uint8_t` | 1 Byte | Fonksiyonel servis (`0x00`–`0x08`) |
| **3** | `destination` | `uint8_t` | 1 Byte | Hedef düğüm kimliği (`deos_node_id_t`) |
| **4** | `source` | `uint8_t` | 1 Byte | Kaynak düğüm kimliği (`0x02` Ground Control) |
| **5** | `version` | `uint8_t` | 1 Byte | Protokol sürümü (`0x11` = v1.1) |
| **6** | `sequence` | `uint8_t` | 1 Byte | Mesaj sıra numarası (`0x00`–`0xFF`) |
| **7** | `command` | `uint8_t` | 1 Byte | Servise ait komut ID |
| **8 .. 8+N-1** | `payload` | `uint8_t[N]` | $N$ Byte | Dinamik veri baytları ($N$ bayt; boş tampon baytları havaya basılmaz) |

* **Paketleme (`COMMON_8B`):** `struct.pack('<8B', prio, msg_class, service, dest, src, ver, seq, cmd) + payload`

---

### 3.2. Seviye 2: LoRa Taşıma Zarfı (`DOC-ICD-TRP-LORA-007` Wire Format - Yalnızca Linker Yönetir)

Linker'ın UART hattına bastığı ve UART'tan okuduğu tam fiziksel çerçeve:

$$\underbrace{\text{0xAA 0x55}}_{2\text{ Byte (Magic)}} + \underbrace{\text{Flag}}_{1\text{ Byte}} + \underbrace{\text{Length } L}_{1\text{ Byte}} + \underbrace{\text{Payload (Saf DEOS Frame veya ACK CRC)}}_{L\text{ Byte}} + \underbrace{\text{CRC16-CCITT}}_{2\text{ Byte (Little-Endian)}}$$

* **MAGIC_1 & MAGIC_2 (2 Byte):** Sabit `0xAA 0x55`. Alıcı UART akışında bu iki baytı yan yana görene kadar tüm baytları çöpe atar.
* **Flag (1 Byte):**
  * `0x00` (`LORA_FLAG_NONE`): Normal veri paketi, alıcıdan ACK beklenmez.
  * `0x01` (`LORA_FLAG_ACK_REQ`): Kritik veri/komut paketi, alıcıdan kesinlikle ACK beklenir.
  * `0x02` (`LORA_FLAG_IS_ACK`): Alındı onay (ACK) paketi. Bu pakette DEOS Frame yerine onaylanan paketin 2 baytlık `CRC16` değeri taşınır ($L = 2$).
* **Length $L$ (1 Byte):** İçerideki Payload alanının bayt uzunluğu.
  * Normal veri paketlerinde (`Flag = 0x00` veya `0x01`): $L = \text{len(deos\_frame)}$ ($9+N$ veya $8+N$).
  * ACK paketlerinde (`Flag = 0x02`): $L = 2$.
* **CRC16-CCITT (2 Byte, Little-Endian):**
  * **MAGIC baytları (`0xAA 0x55`) CRC hesabına DAHİL EDİLMEZ.**
  * Hesaplama `Flag (1B) + Length (1B) + Payload (L Byte)` alanları üzerinden yapılır.
  * Polinom: `0x1021`, Başlangıç değeri (Seed): `0xFFFF`.
  * Hatta **Little-Endian** (`crc.to_bytes(2, 'little')`, önce LSB sonra MSB) olarak basılır.

---

## 4. DEOS v1.1 Tam Protokol Sabitleri ve Kayıt Defterleri (`enums.py` & `registry.py`)

### 4.1. Priority Registry (`DOC-ICD-CORE-001` Bölüm 3)
* `0x00`: `DEOS_PRIO_EMERGENCY` (Acil durdurma ve en kritik safety mesajları / E-Stop)
* `0x01`: `DEOS_PRIO_CRITICAL_CONTROL` (Kritik gerçek zamanlı kontrol)
* `0x02`: `DEOS_PRIO_CONTROL` (Normal sürüş kontrol mesajları)
* `0x03`: `DEOS_PRIO_STATUS` (Durum ve geri besleme mesajları)
* `0x04`: `DEOS_PRIO_CONFIG` (Konfigürasyon ve kalibrasyon)
* `0x05`: `DEOS_PRIO_NETWORK` (Network management / heartbeat / ping-pong / abonelik)
* `0x06`: `DEOS_PRIO_LOW` (Düşük öncelikli servis trafiği)
* `0x07`: `DEOS_PRIO_BACKGROUND` (Arka plan / geliştirme trafiği)

### 4.2. Logical Node ID Registry (`DOC-ICD-CORE-001` Bölüm 4)
* `0x00`: `DEOS_NODE_INVALID`
* `0x01`: `DEOS_NODE_TEXTUAL` (Raspberry Pi / Textual Operatör Arayüzü - TCP 5000)
* `0x02`: `DEOS_NODE_GROUND_CONTROL` (**Bu Sistem** - Uzak Yer Kontrol İstasyonu - LoRa)
* `0x03`: `DEOS_NODE_MAIN_STM32` (STM32H563ZI Araç Ana Kontrol, Router ve **Lighting Servis Sahibi**)
* `0x04`: `DEOS_NODE_ROS_BRIDGE` (Gömülü Linux / ROS 2 Köprüsü - UDP 5001)
* `0x10`: `DEOS_NODE_TRACTION` (STM32 Traction / Tahrik ECU)
* `0x11`: `DEOS_NODE_STEERING` (STM32 Steering / Direksiyon ECU)
* `0x12`: `DEOS_NODE_BRAKE` (STM32 Brake / Fren ECU)
* `0x13`: `DEOS_NODE_IMU` (Main STM32 `0x03` üzerinde barındırılan 6-eksen IMU sanal düğümü)
* `0x20`: `DEOS_NODE_BMS_MAIN` (BMS Gateway `0x30` arkasındaki Daly BMS #1 Ana HV Batarya sanal düğümü)
* `0x21`: `DEOS_NODE_BMS_AUX` (BMS Gateway `0x30` arkasındaki Daly BMS #2 Yardımcı LV Batarya sanal düğümü)
* `0x30`: `DEOS_NODE_BMS_GATEWAY` (Classic CAN – CAN-FD Donanımsal Köprü; yalnızca kendi `SYSTEM` ve `DIAGNOSTIC` servislerini destekler)
* `0xF0`: `DEOS_NODE_DIAG_TOOL` (Harici diagnostik ve servis aracı)
* `0xFE`: `DEOS_NODE_CAN_BROADCAST` (Sadece CAN-FD hattındaki düğümlere yayın)
* `0xFF`: `DEOS_NODE_GLOBAL_BROADCAST` (`DEOS_NODE_BROADCAST` - Tüm ağ arayüzlerine genel yayın)

### 4.3. Message Class & Service Registry (`DOC-ICD-CORE-001` Bölüm 5 & 6)
* **Message Class (`deos_message_class_t`):** `0x00 SAFETY`, `0x01 COMMAND`, `0x02 STATUS`, `0x03 EVENT`, `0x04 REQUEST`, `0x05 RESPONSE`, `0x06 CONFIG`, `0x07 NETWORK`.
* **Service ID (`deos_service_id_t`):** `0x00 SYSTEM`, `0x01 TRACTION`, `0x02 STEERING`, `0x03 BRAKE`, `0x04 BMS`, `0x05 CALIBRATION`, `0x06 DIAGNOSTIC`, `0x07 SENSORS`, `0x08 LIGHTING`.

### 4.4. State, Mode ve Generic Result Code (`DOC-ICD-CORE-001` Bölüm 11.1 & 12)
* **State (`deos_state_t`):** `0x00 INIT`, `0x01 STANDBY`, `0x02 READY`, `0x03 ACTIVE`, `0x04 CALIBRATING`, `0x05 SAFE`, `0x06 FAULT`, `0xFF UNKNOWN`.
* **Mode (`deos_mode_t`):** `0x00 NORMAL`, `0x01 MANUAL`, `0x02 AUTONOMOUS`, `0x03 SERVICE`, `0x04 TEST`, `0xFF UNKNOWN`.
* **Result Code (`deos_result_t`):** `0x00 SUCCESS`, `0x01 UNSUPPORTED`, `0x02 INVALID_PARAMETER`, `0x03 OUT_OF_RANGE`, `0x04 NOT_ALLOWED`, `0x05 BUSY`, `0x06 NOT_READY`, `0x07 INTERNAL_ERROR`.

---

## 5. Servis Bazlı Komut, Telemetri, Parametre ve Arıza Spesifikasyonları

Decoder ve Encoder servisleri aşağıdaki binary payload yapılarını (**Little-Endian**) eksiksiz desteklemelidir:

### 5.1. SYSTEM Servisi (`0x00` - `DOC-ICD-NET-003 v1.4`)
* **Komut ID'leri:**
  * `0x01 GET_STATE` (`REQUEST`, 0B) / `RESPONSE` (`1B`: `state`)
  * `0x02 SET_STATE` (`COMMAND`, `1B`: `target_state`)
  * `0x03 GET_MODE` (`REQUEST`, 0B) / `RESPONSE` (`1B`: `mode`)
  * `0x04 SET_MODE` (`COMMAND`, `1B`: `target_mode`)
  * `0x05 RESET_NODE` (`COMMAND` veya Acil Durumda `SAFETY` E-STOP `1B`: `0=Normal, 1=E-STOP`)
  * `0x06 GET_NODE_INFO` (`REQUEST`, 0B, **Unicast Zorunlu**).
    * **Standart Cevap (`RESPONSE`, 20 Byte `<BBBBBBBBIII`):**
      * `result_code (uint8)`, `node_id (uint8)`, `hw_type (uint8)`, `proto_version (uint8)`, `fw_major (uint8)`, `fw_minor (uint8)`, `fw_patch (uint8)`, `reserved (uint8)`, `git_hash (uint32)`, `supported_services (uint32 bitmask: 1 << service_id)`, `uptime_s (uint32)`.
  * `0x07 HEARTBEAT` (`NETWORK`, **1 Byte Payload**: `current_state (uint8_t, deos_state_t)`).
  * `0x08 PING` / `0x09 PONG` (`NETWORK`, Priority=`0x05`, **PING Unicast Zorunlu**, **4 Byte Payload `<I`**: `ping_id (uint32_t)`). RTT: $\text{RTT} = T_{\text{pong}} - T_{\text{ping}}$.
  * `0x0A SUBSCRIBE` (`REQUEST`, Priority=`0x04`/`0x05`, **Unicast Zorunlu**, **6 Byte Payload `<BBHH`**):
    * `target_service (uint8)`, `target_command (uint8)`, `interval_ms (uint16: 0=İptal, 10..65534=Periyodik ms, 0xFFFF=DEOS_INTERVAL_ON_CHANGE)`, `lease_ttl_s (uint16: 0=Sonsuz, >0=Saniye)`.
    * **Cevap (`RESPONSE`, 5 Byte `<BBBH`):** `result_code (uint8)`, `target_service (uint8)`, `target_command (uint8)`, `actual_interval_ms (uint16)`.
  * `0x0B UNSUBSCRIBE` (`REQUEST`, **Unicast Zorunlu**, **2 Byte Payload `<BB`**): `target_service (uint8)`, `target_command (uint8, 0xFF=tümü)`. Cevap: Generic Response (`1B result_code`).
  * `0x0C GET_SUBSCRIPTIONS` (`REQUEST`).

### 5.2. TRACTION Servisi (`0x01` - Hedef: `DEOS_NODE_TRACTION = 0x10` - `DOC-ICD-NODE-TRAC-008`)
* **Kontrol Komutları (`COMMAND = 0x01`):**
  * `0x01 SET_SPEED`: `target_speed` (`uint16_t`, `0.01 m/s`) [+ opsiyonel `target_accel` (`0.01 m/s²`)].
  * `0x04 SET_GEAR`: `target_gear` (`uint8_t` Enum: `0:N, 1:D, 2:R, 3:P`).
  * `0x05 SET_TORQUE`: `dynamic_torque_limit` (`uint16_t`, `0.01 %`).
* **Durum Telemetrisi (`GET_STATUS = 0x02` / `STATUS = 0x02`, 8 Byte Payload `<HHhh`):**
  * Offset 0 (2B, `uint16_t`): `current_speed` ($\times 0.01\text{ m/s}$)
  * Offset 2 (2B, `uint16_t`): `motor_current` ($\times 0.1\text{ A}$)
  * Offset 4 (2B, `int16_t`): `inverter_temp` ($\times 0.1\text{ }^\circ\text{C}$)
  * Offset 6 (2B, `int16_t`): `motor_temp` ($\times 0.1\text{ }^\circ\text{C}$)
* **Konfigürasyon Parametreleri (`registry.py`):**
  * `0x0001 PID_KP` (`uint16`, `0.01`), `0x0002 PID_KI` (`uint16`, `0.01`), `0x0003 PID_KD` (`uint16`, `0.01`), `0x0010 MAX_CURRENT` (`uint16`, `0.1 A`), `0x0011 MAX_SPEED` (`uint16`, `0.01 m/s`), `0x0012 ACCEL_LIMIT` (`uint16`, `0.01 m/s²`), `0x0013 CMD_TIMEOUT_MS` (`uint16`, `1 ms`), `0x0014 POLE_PAIRS` (`uint8`, `1`), `0x0015 GEAR_RATIO` (`uint16`, `0.01`), `0x0020 WHEEL_CIRCUM_MM` (`uint16`, `1 mm`), `0x0022 REGEN_CUTOFF_SPD` (`uint16`, `0.01 m/s`).

### 5.3. STEERING Servisi (`0x02` - Hedef: `DEOS_NODE_STEERING = 0x11` - `DOC-ICD-NODE-STR-009`)
* **Kontrol Komutları (`COMMAND = 0x01`):**
  * `0x01 SET_TARGET_ANGLE`: `target_steering_angle` (`int16_t`, `0.01 deg`, Negatif: Sol, Pozitif: Sağ) [+ opsiyonel `target_angular_velocity` (`uint16_t`, `0.01 deg/s`)].
  * `0x04 SET_CONTROL_MODE`: `steering_control_mode` (`uint8_t` Enum).
* **Durum Telemetrisi (`GET_STATUS = 0x02` / `STATUS = 0x02`, 9 Byte Payload `<hHhhB`):**
  * Offset 0 (2B, `int16_t`): `current_angle` ($\times 0.01\text{ deg}$)
  * Offset 2 (2B, `uint16_t`): `motor_current` ($\times 0.1\text{ A}$)
  * Offset 4 (2B, `int16_t`): `motor_temp` ($\times 0.1\text{ }^\circ\text{C}$)
  * Offset 6 (2B, `int16_t`): `chassis_yaw_rate` ($\times 0.01\text{ deg/s}$)
  * Offset 8 (1B, `uint8_t`): `is_tracking_target` (`0: No, 1: Yes`)
* **Konfigürasyon Parametreleri (`registry.py`):**
  * `0x0001..0x0003 PID_KP/KI/KD` (`uint16`, `0.01`), `0x0004 PID_I_MAX` (`uint16`, `0.01 %`), `0x0005 FEEDFORWARD_K` (`uint16`, `0.01`), `0x0006 DEADBAND` (`uint16`, `0.01 deg`), `0x0010 ZERO_OFFSET` (`int16`, `0.01 deg`), `0x0011 MIN_ANGLE` (`int16`, `0.01 deg`), `0x0012 MAX_ANGLE` (`int16`, `0.01 deg`), `0x0013 CURRENT_LIMIT` (`uint16`, `0.1 A`), `0x0014 MAX_ANGULAR_VEL` (`uint16`, `0.01 deg/s`), `0x0015 MAX_ANGULAR_ACC` (`uint16`, `0.01 deg/s²`), `0x0016 SOFT_STOP_MARGIN` (`uint16`, `0.01 deg`), `0x0017 MAX_TRACK_ERR` (`uint16`, `0.01 deg`), `0x0018 TRACK_TIMEOUT_MS` (`uint16`, `1 ms`).

### 5.4. BRAKE Servisi (`0x03` - Hedef: `DEOS_NODE_BRAKE = 0x12` - `DOC-ICD-NODE-BRK-010`)
* **Kontrol Komutları:**
  * `0x01` (`COMMAND`): `target_brake_demand` (`uint16_t`, `0.01 %`)
  * `0x03` (`COMMAND` / `SAFETY`): `target_deceleration` (`uint16_t`, `0.01 m/s²`) veya `SAFETY` altında `estop_brake_override` (`uint8_t` Boolean)
  * `0x04` (`COMMAND`): `brake_control_mode` (`uint8_t` Enum)
  * `0x05` (`COMMAND`): `target_park_brake` (`uint8_t` Enum - EPB)
  * `0x06` (`COMMAND`): `brake_prefill_cmd` (`uint8_t` Boolean)
* **Durum Telemetrisi (`GET_STATUS = 0x02` / `STATUS = 0x02`, 10 Byte Payload `<HHHhBB`):**
  * Offset 0 (2B, `uint16_t`): `current_position` ($\times 0.01\text{ mm}$)
  * Offset 2 (2B, `uint16_t`): `actuator_force` ($\times 1\text{ N}$)
  * Offset 4 (2B, `uint16_t`): `motor_current` ($\times 0.1\text{ A}$)
  * Offset 6 (2B, `int16_t`): `chassis_long_accel` ($\times 0.01\text{ m/s}^2$)
  * Offset 8 (1B, `uint8_t`): `brake_system_active` (`0: Idle, 1: Active`)
  * Offset 9 (1B, `uint8_t`): `park_brake_state` (`0: Released, 1: Engaged`)
* **Konfigürasyon Parametreleri (`registry.py`):**
  * `0x0001..0x0003 PID_KP/KI/KD` (`uint16`, `0.01`), `0x0010 MIN_POSITION` (`uint16`, `0.01 mm`), `0x0011 MAX_POSITION` (`uint16`, `0.01 mm`), `0x0012 CURRENT_LIMIT` (`uint16`, `0.1 A`), `0x0013 SLEW_RATE_LIMIT` (`uint16`, `0.01 %/ms`), `0x0014 CMD_TIMEOUT_MS` (`uint16`, `1 ms`), `0x0015 KISS_POINT_OFFSET` (`uint16`, `0.01 mm`), `0x0016 MAX_FORCE_LIMIT` (`uint16`, `1 N`).

### 5.5. BMS Servisi (`0x04` - Hedef: `BMS_MAIN = 0x20` veya `BMS_AUX = 0x21` - `DOC-ICD-NODE-BMS-012`)
> **KURAL:** BMS servis mesajları asla `BMS_GATEWAY (0x30)` adresine gönderilmez; doğrudan `0x20` veya `0x21` adresine gönderilir.
* **`0x01 GET_STATUS` (`REQUEST`, 0B) $\rightarrow$ `0x02 STATUS` (`RESPONSE` / `STATUS`, 16 Byte Payload `<HhHhHHHBB`):**
  * Offset 0 (2B, `uint16_t`): `pack_voltage` ($\times 0.01\text{ V}$)
  * Offset 2 (2B, `int16_t`): `pack_current` ($\times 0.1\text{ A}$)
  * Offset 4 (2B, `uint16_t`): `soc` ($\times 0.01\text{ %}$)
  * Offset 6 (2B, `int16_t`): `bms_temp` ($\times 0.1\text{ }^\circ\text{C}$)
  * Offset 8 (2B, `uint16_t`): `min_cell_voltage` ($\times 0.001\text{ V}$)
  * Offset 10 (2B, `uint16_t`): `max_cell_voltage` ($\times 0.001\text{ V}$)
  * Offset 12 (2B, `uint16_t`): `nominal_pack_voltage` ($\times 0.01\text{ V}$)
  * Offset 14 (1B, `uint8_t`): `cell_count`
  * Offset 15 (1B, `uint8_t`): `temp_sensor_count`
* **Liste Tipi BMS Komutları (100 ms aralıklı ardışık `RESPONSE` çerçeveleri, `index == 0x00` $\rightarrow$ `END_OF_LIST`):**
  * `0x03 GET_CELL_VOLTAGES` (`REQUEST`, 0B) $\rightarrow$ `0x04 CELL_VOLTAGE` (`RESPONSE`, 3 Byte `<BH`): `cell_index` (`uint8_t`, `1..N`, `0x00`=Bitiş), `cell_voltage` (`uint16_t`, $\times 0.001\text{ V}$).
  * `0x05 GET_TEMPERATURES` (`REQUEST`, 0B) $\rightarrow$ `0x06 TEMPERATURE` (`RESPONSE`, 3 Byte `<Bh`): `sensor_index` (`uint8_t`, `1..N`, `0x00`=Bitiş), `temperature` (`int16_t`, $\times 0.1\text{ }^\circ\text{C}$).
  * `0x07 GET_BALANCING` (`REQUEST`, 0B) $\rightarrow$ `0x08 BALANCING` (`RESPONSE`, 2 Byte `<BB`): `cell_index` (`uint8_t`, `1..N`, `0x00`=Bitiş), `balancing_state` (`uint8_t`, `0x00`=Inactive, `0x01`=Active).

### 5.6. DIAGNOSTIC Servisi (`0x06` - Tüm Düğümler - `DOC-ICD-DIAG-004 v1.2`)
* `0x01 GET_HEALTH` (`REQUEST`, 0B)
* `0x02 GET_FAULTS` (`REQUEST`, 0B) $\rightarrow$ Hedef düğümdeki tüm arızaları 100 ms aralıklarla tek tek `RESPONSE` (`Command = 0x02`) olarak döner.
  * **Fault Response Payload (10 Byte `<HBBHI`):**
    * Offset 0 (2B, `uint16_t`): `fault_id` (`0x0000` = `END_OF_FAULT_LIST`)
    * Offset 2 (1B, `uint8_t`): `severity` (`0x01 INFO`, `0x02 WARNING`, `0x03 ERROR`, `0x04 CRITICAL`)
    * Offset 3 (1B, `uint8_t`): `state` (`0x00 INACTIVE`, `0x01 ACTIVE`, `0x02 LATCHED`)
    * Offset 4 (2B, `uint16_t`): `occurrence_count`
    * Offset 6 (4B, `uint32_t`): `last_occurrence_ms` (Node uptime ms)
* `0x03 CLEAR_FAULTS` (`COMMAND`, 0B): Hedef düğümün saklanan fault kayıtlarını temizler.
* **Tam Fault ID Sözlüğü (`registry.py`):**
  * **Ortak Kodlar (Tüm Düğümler):** `0x0000: END_OF_FAULT_LIST`, `0x0001: Internal Software Error`, `0x0002: Watchdog Reset Detected`, `0x0003: Invalid Configuration`, `0x0004: Communication Timeout`, `0x0005: RX Buffer / Queue Overflow`, `0x0006: TX Failure`, `0x0007: Protocol / Invalid Message Error`, `0x0008: Local Storage Error`, `0x0010: Subscription Table Full`, `0x0011: Subscription Broadcast Rejected`, `0x0012: Subscription Malformed Payload`, `0x0013: Subscription Handler Not Found`, `0x0014: Subscription Dispatch Failed`.
  * **Main STM32 (`0x03`):** `0x0100: CAN-FD Bus Off`, `0x0101: Ethernet Link Failure`, `0x0102: LoRa Communication Failure`, `0x0103: Router Queue Overflow`, `0x0104: Invalid / Unknown Route`.
  * **Traction (`0x10`):** `0x0100: Motor / Inverter Comm Lost`, `0x0101: Motor Overcurrent`, `0x0102: Motor Overtemperature`, `0x0103: Speed Feedback Invalid`, `0x0104: Overspeed Detected`, `0x0105: Actuator / Motor Response Timeout`.
  * **Steering (`0x11`):** `0x0100: Steering Encoder Comm Lost`, `0x0101: Steering Position Invalid`, `0x0102: Steering Angle Out of Range`, `0x0103: Steering Motor Overcurrent`, `0x0104: Steering Actuator Stall`, `0x0105: Steering Response Timeout`.
  * **Brake (`0x12`):** `0x0100: Brake Position Feedback Invalid`, `0x0101: Brake Actuator Overcurrent`, `0x0102: Brake Actuator Stall`, `0x0103: Brake Position Out of Range`, `0x0104: Brake Response Timeout`.
  * **BMS Main (`0x20`) & BMS Aux (`0x21`):** `0x0100: Pack Overvoltage`, `0x0101: Pack Undervoltage`, `0x0102: Charge Overcurrent`, `0x0103: Discharge Overcurrent`, `0x0104: Overtemperature`, `0x0105: Undertemperature`, `0x0106: Cell Voltage Imbalance`, `0x0107: BMS Internal Fault`, `0x0108: Invalid BMS Measurement`.
  * **BMS Gateway (`0x30`):** `0x0100: BMS Main Comm Lost`, `0x0101: BMS Aux Comm Lost`, `0x0102: Classic CAN Bus Off`, `0x0103: CAN-FD Bus Off`, `0x0104: Invalid BMS Frame`, `0x0105: BMS Protocol / CRC Error`.
  * **Ground Control (`0x02`):** `0x0100: LoRa Communication Lost`, `0x0101: Invalid LoRa / DEOS Message`, `0x0102: Transport Timeout`.

### 5.7. LIGHTING Servisi (`0x08` - Hedef: `DEOS_NODE_MAIN_STM32 = 0x03` - `DOC-ICD-SRV-LGHT-012 v1.2`)
> **KURAL:** Aydınlatma bağımsız bir düğüm değildir; tüm mesajlarda `Destination = 0x03 (DEOS_NODE_MAIN_STM32)` ve `Service = 0x08 (DEOS_SERVICE_LIGHTING)` olmalıdır.
* **Light ID Enum (`uint8_t`):** `0x01 HEADLIGHT`, `0x02 BRAKE`, `0x03 TURN_LEFT`, `0x04 TURN_RIGHT`, `0xFF ALL`.
* **Light State Enum (`uint8_t`):** `0x00 OFF`, `0x01 ON`, `0x02 BLINKING`, `0x03 FAULT`.
* **Komutlar:**
  * `0x01 TURN_ON` (`COMMAND`, 1 Byte `<B`: `light_id`)
  * `0x02 TURN_OFF` (`COMMAND`, 1 Byte `<B`: `light_id`)
  * `0x03 GET_STATUS` (`REQUEST`, 0 veya 1 Byte: opsiyonel `light_id`)
  * `0x04 STATUS` (`STATUS` / `RESPONSE`, **6 Byte Payload `<BBBBBB`**):
    * `headlight_state`, `brake_light_state`, `turn_left_state`, `turn_right_state`, `hazard_state`, `fault_flags` (bitmask).

### 5.8. Ortak Parametre Konfigürasyonu (`DOC-ICD-DATA-002 v1.1`)
Konfigüre edilebilir servislerde (`TRACTION`, `STEERING`, `BRAKE` vb.) `Message Class = DEOS_CLASS_CONFIG (0x06)` veya okuma için `DEOS_CLASS_REQUEST (0x04)` ile ortak komut ID'leri kullanılır:
* `0xE0`: `DEOS_CMD_GET_PARAMETER` (Payload: `uint16_t param_id` `<H`)
* `0xE1`: `DEOS_CMD_SET_PARAMETER` (Payload: `uint16_t param_id` + ham ölçekli değer)
* `0xE2`: `DEOS_CMD_SAVE_PARAMETERS` (EEPROM/Flash kalıcı kayıt)

---

## 6. MQTT Topic ve Veri Sözleşmesi (Data Contracts)

| Topic Adı | Yön | Format | Açıklama |
| :--- | :--- | :--- | :--- |
| `command/request` | UI $\rightarrow$ Encoder | JSON | Operatörün gönderdiği yüksek seviyeli komut/istek/abonelik |
| `lora/tx/reliable` | Encoder $\rightarrow$ Linker | Binary (`bytes`) | Saf DEOS Evrensel Çerçevesi, Linker `Flag=0x01` (`ACK_REQ`) ile sarar |
| `lora/tx/unreliable` | Encoder $\rightarrow$ Linker | Binary (`bytes`) | Saf DEOS Evrensel Çerçevesi, Linker `Flag=0x00` (`NONE`) ile sarar |
| `lora/rx/frame` | Linker $\rightarrow$ Decoder | Binary (`bytes`) | L2 zarfı soyulmuş, CRC16 doğrulanmış Saf DEOS Evrensel Çerçevesi |
| `command/status` | Linker $\rightarrow$ UI | JSON | Komut gönderim, CRC16, ACK, retry ve zaman aşımı durumları |
| `telemetry/system` | Decoder $\rightarrow$ UI | JSON | `PING/PONG` (RTT), `HEARTBEAT` (State), `GET_NODE_INFO` (20B), `SUBSCRIBE` yanıtları |
| `telemetry/bms/main` | Decoder $\rightarrow$ UI | JSON | Ana batarya (`0x20`) genel durum, hücre voltaj, sıcaklık ve balancing listeleri |
| `telemetry/bms/aux` | Decoder $\rightarrow$ UI | JSON | Yardımcı batarya (`0x21`) genel durum, hücre voltaj, sıcaklık ve balancing listeleri |
| `telemetry/traction` | Decoder $\rightarrow$ UI | JSON | Çözümlenmiş tahrik/motor telemetrisi (`0x10`) |
| `telemetry/steering` | Decoder $\rightarrow$ UI | JSON | Çözümlenmiş direksiyon telemetrisi (`0x11`) |
| `telemetry/brake` | Decoder $\rightarrow$ UI | JSON | Çözümlenmiş fren ve EPB telemetrisi (`0x12`) |
| `telemetry/lighting` | Decoder $\rightarrow$ UI | JSON | Çözümlenmiş aydınlatma durum telemetrisi (`0x03` / Servis `0x08`) |
| `telemetry/diagnostic`| Decoder $\rightarrow$ UI | JSON | Çözümlenmiş düğüm bazlı arıza kayıtları (`GET_FAULTS`) ve `END_OF_FAULT_LIST` bildirimleri |
| `telemetry/sensors` | Decoder $\rightarrow$ UI | JSON | IMU (`0x13`) ve sensör servis (`0x07`) verileri |
| `telemetry/config` | Decoder $\rightarrow$ UI | JSON | Parametre okuma/yazma (`0xE0..0xE2`) ve kalibrasyon (`0x05`) yanıtları |

---

## 7. Linker İletim ve Alım Mantığı (FSM & Çift Yönlü ACK)

### 7.1. Standart CRC16-CCITT (`shared/deos_core/crc.py`)
```python
def crc16_ccitt(data: bytes, seed: int = 0xFFFF) -> int:
    crc = seed
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
```

### 7.2. TX Zarflama ve Gönderim (Encoder $\rightarrow$ UART)
```python
LORA_FLAG_NONE = 0x00
LORA_FLAG_ACK_REQ = 0x01
LORA_FLAG_IS_ACK = 0x02

def on_tx_frame(topic: str, deos_frame: bytes):
    flag = LORA_FLAG_ACK_REQ if topic.endswith("reliable") else LORA_FLAG_NONE
    length = len(deos_frame)

    # L2 Zarf Alanı: Flag (1B) + Length (1B) + Saf DEOS Frame (L Byte)
    # Not: MAGIC baytları (0xAA 0x55) CRC hesabına DAHİL EDİLMEZ!
    envelope_body = bytes([flag, length]) + deos_frame
    crc = crc16_ccitt(envelope_body)

    # Tam Wire Paketi: [0xAA, 0x55] + Flag + Length + DEOS Frame + CRC16 (Little-Endian)
    wire_packet = b"\xaa\x55" + envelope_body + crc.to_bytes(2, "little")

    ser.write(wire_packet)

    if flag == LORA_FLAG_ACK_REQ:
        start_ack_timer(expected_ack_crc=crc, wire_packet=wire_packet)
    else:
        mqtt_client.publish("command/status", json.dumps({
            "status": "SENT_NO_ACK_REQUIRED",
            "crc": hex(crc)
        }))
```

### 7.3. RX Ayrıştırma, Çift Yönlü ACK Yönetimi ve Zarf Soyma (UART $\rightarrow$ Decoder)
```python
def send_lora_ack(acked_crc: int):
    # ACK Paketi: [0xAA 0x55] [Flag: 0x02] [Length: 0x02] [Acked_CRC (2B LE)] [New_CRC16 (2B LE)]
    ack_payload = acked_crc.to_bytes(2, "little")
    ack_body = bytes([LORA_FLAG_IS_ACK, 0x02]) + ack_payload
    ack_crc = crc16_ccitt(ack_body)
    ack_wire = b"\xaa\x55" + ack_body + ack_crc.to_bytes(2, "little")
    ser.write(ack_wire)

# buffer: bytearray
while len(buffer) >= 6:
    idx = buffer.find(b"\xaa\x55")
    if idx == -1:
        # Son bayt 0xAA ise bir sonraki okumada 0x55 gelebilir, onu koru
        if buffer.endswith(b"\xaa"):
            del buffer[:-1]
        else:
            buffer.clear()
        break
    if idx > 0:
        del buffer[:idx]

    if len(buffer) < 4:
        break

    flag = buffer[2]
    length = buffer[3]
    total_len = 4 + length + 2  # AA 55 (2B) + Flag (1B) + Length (1B) + Payload (L) + CRC16 (2B)

    if len(buffer) < total_len:
        break  # Paket henüz tamamlanmadı, UART'tan kalan baytları bekle

    raw_packet = bytes(buffer[:total_len])
    del buffer[:total_len]

    # CRC16 Doğrulama (MAGIC baytları hariç: Flag + Length + Payload)
    calc_crc = crc16_ccitt(raw_packet[2:-2])
    rx_crc = int.from_bytes(raw_packet[-2:], "little")
    if calc_crc != rx_crc:
        continue  # Bozuk paket, çöpe at

    if flag == LORA_FLAG_IS_ACK and length == 2:
        acked_crc = int.from_bytes(raw_packet[4:6], "little")
        handle_ack_received(acked_crc)
    else:
        # Araçtan gelen pakette ACK talep edildiyse (Flag == 0x01) derhal ACK gönder
        if flag == LORA_FLAG_ACK_REQ:
            send_lora_ack(rx_crc)

        # L2 Zarfını soy: AA 55 Flag Length (4 Byte) ve CRC16 (2 Byte) atılır
        pure_deos_frame = raw_packet[4:-2]
        mqtt_client.publish("lora/rx/frame", pure_deos_frame)
```

---

## 8. Docker Compose Konfigürasyonu (`docker-compose.yml`)

```yaml
version: "3.8"

networks:
  deos-net:
    driver: bridge

services:
  mosquitto:
    image: eclipse-mosquitto:2.0
    container_name: deos_mosquitto
    restart: unless-stopped
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf
    networks:
      - deos-net

  linker:
    build:
      context: .
      dockerfile: services/linker/Dockerfile
    container_name: deos_linker
    restart: unless-stopped
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"
    group_add:
      - dialout
    environment:
      - MQTT_BROKER=mosquitto
      - MQTT_PORT=1883
      - SERIAL_PORT=/dev/ttyUSB0
      - BAUD_RATE=9600
      - ACK_TIMEOUT_MS=600
      - MAX_RETRIES=3
    depends_on:
      - mosquitto
    networks:
      - deos-net

  encoder:
    build:
      context: .
      dockerfile: services/encoder/Dockerfile
    container_name: deos_encoder
    restart: unless-stopped
    environment:
      - MQTT_BROKER=mosquitto
      - MQTT_PORT=1883
      - DEOS_SOURCE_NODE=0x02
      - DEOS_PROTOCOL_VERSION=0x11
      - DEOS_FRAME_LAYOUT=UNIVERSAL_9B
    depends_on:
      - mosquitto
    networks:
      - deos-net

  decoder:
    build:
      context: .
      dockerfile: services/decoder/Dockerfile
    container_name: deos_decoder
    restart: unless-stopped
    environment:
      - MQTT_BROKER=mosquitto
      - MQTT_PORT=1883
      - DEOS_FRAME_LAYOUT=UNIVERSAL_9B
    depends_on:
      - mosquitto
    networks:
      - deos-net

  web-ui:
    build:
      context: .
      dockerfile: services/web-ui/Dockerfile
    container_name: deos_web_ui
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - MQTT_BROKER=mosquitto
      - MQTT_PORT=1883
    depends_on:
      - mosquitto
    networks:
      - deos-net
```

---

## 9. Antigravity Agent Görev Direktifi (Prompt Direktifi)

VS Code'da Antigravity Agent'a projeyi başlatırken verilecek yönerge:
> *"Lütfen `BLUEPRINT_GROUND_STATION_MICROSERVICES.md` dosyasında ve dizindeki güncel DEOS v1.1 ICD dokümanlarında tanımlanan simetrik mikroservis mimarisini kur. ÖNEMLİ: Yer istasyonu kesinlikle 29-bit CAN ID veya CAN Frame üretmemelidir; Encoder ve Decoder servisleri yalnızca medya bağımsız Saf DEOS Evrensel Çerçevesi (Universal DEOS Transport Frame) seviyesinde simetrik çalışmalıdır. Encoder `lora/tx/reliable` ve `lora/tx/unreliable` konularına saf DEOS çerçevesi basmalı, Decoder ise `lora/rx/frame` konusundan saf DEOS çerçevesi okumalıdır. `0xAA 0x55` magic baytları, `Flag` (`0x00`, `0x01`, `0x02`), `Length` ve Little-Endian `CRC16-CCITT (0x1021, seed=0xFFFF)` L2 zarflaması ile soyma işlemlerinin tamamını Linker servisi üstlenmelidir. Linker hem giden `Flag=0x01` paketler için ARQ mekanizmasını, hem de araçtan gelen `Flag=0x01` paketlere otomatik `Flag=0x02` ACK yanıtı dönme davranışını barındırmalıdır. Tüm servislerin (`SYSTEM`, `TRACTION`, `STEERING`, `BRAKE`, `BMS_MAIN`/`BMS_AUX`, `DIAGNOSTIC`, `LIGHTING`, `CONFIG`) ölçekleme, parametre/arıza sözlükleri (`registry.py`), liste akışı (100 ms / `END_OF_LIST`) ve dinamik abonelik (`SUBSCRIBE`/`UNSUBSCRIBE`, `0xFFFF` On-Change) özelliklerini eksiksiz uygula."*
