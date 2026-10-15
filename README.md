# DEOS Yer Kontrol İstasyonu (Ground Control Station)

![DEOS Protocol](https://img.shields.io/badge/DEOS_Protocol-v1.1_(0x11)-blue.svg)
![Architecture](https://img.shields.io/badge/Architecture-Microservices-success.svg)
![Transport](https://img.shields.io/badge/Transport-LoRa_UART_(CRC16--CCITT)-orange.svg)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)

**Dokuz Eylül Otonom Sistemler (DEOS)** elektrikli otonom yarış aracının uzaktan telemetri izleme, gerçek zamanlı kontrol, dinamik abonelik yönetimi, arıza teşhisi (Diagnostics) ve parametre konfigürasyonu için geliştirilmiş mikroservis tabanlı **Yer Kontrol İstasyonu (`DEOS_NODE_GROUND_CONTROL = 0x02`)** yazılımıdır.

Bu proje, **DEOS v1.1 (`0x11`) Medya Bağımsız Çekirdek Protokol** mimarisi ve modüler ICD (Interface Control Document) şartnameleri ile tam uyumlu olarak tasarlanmıştır.

---

## Temel Özellikler

* **Medya Bağımsız Evrensel Çerçeve (`Universal DEOS Frame`):** Yer İstasyonu donanımsal 29-bit CAN ID hesaplaması veya DLC yuvarlaması yapmaz; doğrudan medya bağımsız `deos_message_t` çerçevesi üretir ve tüketir. Araç içi CAN-FD dönüşümü araç üzerindeki `DEOS_NODE_MAIN_STM32 (0x03)` Router düğümü tarafından otomatik gerçekleştirilir.
* **Katmanlı Simetrik Codec Mimarisi:** `Encoder` ve `Decoder` servisleri tamamen durumsuz (stateless) olarak saf DEOS Evrensel Çerçevesi seviyesinde simetrik çalışır.
* **Güvenilir LoRa L2 Taşıma Katmanı (`Linker`):** `0xAA 0x55` senkronizasyonu, `CRC16-CCITT (0x1021)` doğrulaması, kopmalara karşı otomatik yeniden bağlanma (`auto-reconnect`) ve kritik komutlar için çift yönlü **ACK / Otomatik Tekrar Gönderim (ARQ)** mekanizmasını tek merkezden yönetir.
* **Dinamik Telemetri Abonelik Motoru (`Subscription Engine`):** Bant genişliğini korumak için polling yerine periyodik (`10..65534 ms`), kira süreli (`Lease TTL`) veya yalnızca durum değiştiğinde tetiklenen **On-Change (`0xFFFF`)** telemetri aboneliklerini (`SUBSCRIBE` / `UNSUBSCRIBE`) destekler.
* **Çoklu Paket (Stream) Liste Yönetimi:** `BMS` (hücre voltajları, sıcaklıklar, balans durumu) ve `DIAGNOSTIC` (`GET_FAULTS`) servislerinden 100 ms aralıklarla akan parçalı yanıtları (`END_OF_LIST` / `END_OF_FAULT_LIST`) otomatik birleştirir.

---

## Sistem Mimarisi

Sistem, `docker-compose` çatısı altında izole bir köprü ağı (`deos-net`) üzerinde haberleşen **5 konteynerden** oluşur:

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

### Mikroservislerin Görevleri
1. **`mosquitto`:** Servisler arası asenkron MQTT Pub/Sub mesajlaşmasını yönetir (`1883` TCP, `9001` WebSocket).
2. **`encoder`:** Web arayüzünden gelen yüksek seviyeli JSON komutlarını Pydantic v2 ve ICD kurallarına göre doğrular (Unicast zorunlulukları, BMS/Lighting hedef düğüm kontrolleri), ölçekler ve saf DEOS Evrensel Çerçevesi olarak `lora/tx/reliable` veya `lora/tx/unreliable` konularına basar.
3. **`decoder`:** Linker'dan gelen doğrulanmış saf DEOS Evrensel Çerçevesini (`lora/rx/frame`) ayrıştırır, Little-Endian ham verileri fiziksel birimlere ($\text{Physical} = \text{Raw} \times \text{Scale} + \text{Offset}$) dönüştürür ve ilgili `telemetry/<servis>` konusuna JSON olarak yayınlar.
4. **`linker`:** Seri port (`/dev/ttyUSB0`) bağlantısını, LoRa L2 çerçevelemesini (`0xAA 0x55 + Flag + Length + Payload + CRC16`), giden kritik paketler için ARQ tekrar gönderimini ve araçtan gelen kritik paketler için anlık ACK yanıtlarını yönetir.
5. **`web-ui`:** Operatör kontrol paneli, canlı telemetri grafikleri, abonelik yöneticisi, parametre ayar ekranı ve arıza (Fault) izleme arayüzünü sunar.

---

## Dizin Yapısı

```text
deos-ground-station/
├── docker-compose.yml
├── BLUEPRINT_GROUND_STATION_MICROSERVICES.md
├── README.md
├── mosquitto/
│   └── mosquitto.conf
├── shared/
│   ├── pyproject.toml
│   └── deos_core/
│       ├── __init__.py
│       ├── enums.py          # Node ID, Priority, Class, Service, Command, State, Mode, Result Enum'ları
│       ├── crc.py            # Standart CRC16-CCITT (Polinom: 0x1021, Seed: 0xFFFF, Little-Endian)
│       ├── framing.py        # Universal DEOS Frame (9B/8B) ve LoRa L2 Zarfı paketleme/çözme
│       ├── models.py         # Pydantic v2 komut/telemetri şemaları ve ICD adresleme validatörleri
│       ├── scaling.py        # ICD PhysicalValue = RawValue * Scale + Offset dönüşüm yardımcıları
│       └── registry.py       # Servis bazlı Parameter ID ve Node bazlı Fault ID sözlükleri
└── services/
    ├── linker/               # UART, LoRa L2 Zarf Ekleme/Soyma, Çift Yönlü ACK/Retry FSM
    ├── encoder/              # JSON Komut -> Saf DEOS Evrensel Çerçevesi (Binary)
    ├── decoder/              # Saf DEOS Evrensel Çerçevesi -> Ölçeklenmiş JSON Telemetri
    └── web-ui/               # Operatör Dashboard & Web Arayüzü (Port 8000)
```

---

## Protokol Özeti

### 1. Seviye 1: Medya Bağımsız Evrensel DEOS Çerçevesi (`Encoder` $\leftrightarrow$ `Decoder`)
`shared/deos_core/framing.py` üzerinde `DEOS_FRAME_LAYOUT` ortam değişkeni ile seçilebilen iki başlık profili desteklenir:
* **`UNIVERSAL_9B` (`DOC-ICD-CORE-001` Bölüm 9.1 - Varsayılan):**
  `[Destination(1B)] [Source(1B)] [Priority(1B)] [Version(1B)] [Class(1B)] [Service(1B)] [Command(1B)] [Sequence(1B)] [Payload_Len(1B)] + [Payload(N Byte)]` ($9+N$ Byte)
* **`COMMON_8B` (`DOC-ICD-TRP-LORA-007` & `ETH-006` `deos_message_t`):**
  `[Priority(1B)] [Class(1B)] [Service(1B)] [Destination(1B)] [Source(1B)] [Version(1B)] [Sequence(1B)] [Command(1B)] + [Payload(N Byte)]` ($8+N$ Byte)

### 2. Seviye 2: LoRa Fiziksel Taşıma Zarfı (`Linker` $\leftrightarrow$ `UART`)
$$\underbrace{\text{0xAA 0x55}}_{2\text{ B (Magic)}} + \underbrace{\text{Flag}}_{1\text{ B}} + \underbrace{\text{Length } L}_{1\text{ B}} + \underbrace{\text{Payload (Saf DEOS Frame / ACK CRC)}}_{L\text{ Byte}} + \underbrace{\text{CRC16-CCITT}}_{2\text{ B (LE)}}$$
* **Flag Değerleri:** `0x00` (`LORA_FLAG_NONE`), `0x01` (`LORA_FLAG_ACK_REQ`), `0x02` (`LORA_FLAG_IS_ACK`).
* **CRC16-CCITT:** `0xAA 0x55` hariç `Flag + Length + Payload` üzerinden hesaplanır (Polinom: `0x1021`, Seed: `0xFFFF`, Little-Endian).

### 3. Desteklenen Düğümler ve Servisler

| Node ID | Sembolik Ad | Birincil / Desteklenen Servisler | Açıklama |
| :--- | :--- | :--- | :--- |
| `0x02` | `DEOS_NODE_GROUND_CONTROL` | `SYSTEM (0x00)`, `DIAGNOSTIC (0x06)` | **Yer Kontrol İstasyonu (Bu Sistem)** |
| `0x03` | `DEOS_NODE_MAIN_STM32` | `SYSTEM`, `LIGHTING (0x08)`, `DIAGNOSTIC`, Tüm Servisler | Ana Kontrolcü, Router & Aydınlatma Sahibi |
| `0x10` | `DEOS_NODE_TRACTION` | `TRACTION (0x01)`, `CALIBRATION (0x05)`, `SYSTEM`, `DIAGNOSTIC` | Tahrik / İnvertör ECU |
| `0x11` | `DEOS_NODE_STEERING` | `STEERING (0x02)`, `CALIBRATION (0x05)`, `SYSTEM`, `DIAGNOSTIC` | Direksiyon ECU |
| `0x12` | `DEOS_NODE_BRAKE` | `BRAKE (0x03)`, `CALIBRATION (0x05)`, `SYSTEM`, `DIAGNOSTIC` | Fren & EPB ECU |
| `0x13` | `DEOS_NODE_IMU` | `SENSORS (0x07)`, `SYSTEM`, `DIAGNOSTIC` | Main STM32 Üzerinde Sanal 6-Eksen IMU |
| `0x20` | `DEOS_NODE_BMS_MAIN` | `BMS (0x04)`, `SYSTEM`, `DIAGNOSTIC` | Ana HV Batarya (Daly BMS #1 Sanal Düğümü) |
| `0x21` | `DEOS_NODE_BMS_AUX` | `BMS (0x04)`, `SYSTEM`, `DIAGNOSTIC` | Yardımcı LV Batarya (Daly BMS #2 Sanal Düğümü) |
| `0x30` | `DEOS_NODE_BMS_GATEWAY` | `SYSTEM (0x00)`, `DIAGNOSTIC (0x06)` | Classic CAN – CAN-FD Köprü Donanımı |

---

## MQTT Topic Sözleşmesi

| Topic Adı | Yön | Format | Açıklama |
| :--- | :--- | :--- | :--- |
| `command/request` | `web-ui` $\rightarrow$ `encoder` | JSON | Operatörün gönderdiği yüksek seviyeli komut / abonelik / config isteği |
| `lora/tx/reliable` | `encoder` $\rightarrow$ `linker` | Binary | Saf DEOS Çerçevesi (`Flag=0x01 ACK_REQ` ile zarflanır) |
| `lora/tx/unreliable` | `encoder` $\rightarrow$ `linker` | Binary | Saf DEOS Çerçevesi (`Flag=0x00 NONE` ile zarflanır) |
| `lora/rx/frame` | `linker` $\rightarrow$ `decoder` | Binary | L2 zarfı soyulmuş, CRC16 doğrulanmış Saf DEOS Çerçevesi |
| `command/status` | `linker` $\rightarrow$ `web-ui` | JSON | Komut gönderim, CRC16, ACK, retry ve zaman aşımı durumları |
| `telemetry/system` | `decoder` $\rightarrow$ `web-ui` | JSON | `PING/PONG` (RTT), `HEARTBEAT` (State), `GET_NODE_INFO`, `SUBSCRIBE` yanıtları |
| `telemetry/traction` | `decoder` $\rightarrow$ `web-ui` | JSON | Hız (`m/s`), motor akımı (`A`), invertör ve motor sıcaklıkları (`°C`) |
| `telemetry/steering` | `decoder` $\rightarrow$ `web-ui` | JSON | Direksiyon açısı (`deg`), motor akımı/sıcaklığı, şasi yaw rate (`deg/s`) |
| `telemetry/brake` | `decoder` $\rightarrow$ `web-ui` | JSON | Fren pozisyonu (`mm`), kuvvet (`N`), boyuna ivme (`m/s²`), EPB durumu |
| `telemetry/bms/main` | `decoder` $\rightarrow$ `web-ui` | JSON | Ana batarya (`0x20`) durum, hücre voltaj, sıcaklık ve balans listeleri |
| `telemetry/bms/aux` | `decoder` $\rightarrow$ `web-ui` | JSON | Yardımcı batarya (`0x21`) durum, hücre voltaj, sıcaklık ve balans listeleri |
| `telemetry/lighting` | `decoder` $\rightarrow$ `web-ui` | JSON | Ön far, fren lambası, sağ/sol sinyal, dörtlü flaşör ve arıza bayrakları |
| `telemetry/diagnostic`| `decoder` $\rightarrow$ `web-ui` | JSON | Düğüm bazlı arıza kayıtları (`GET_FAULTS`) ve `END_OF_FAULT_LIST` bildirimleri |
| `telemetry/config` | `decoder` $\rightarrow$ `web-ui` | JSON | Parametre okuma/yazma (`0xE0..0xE2`) ve kalibrasyon yanıtları |

---

## Kurulum ve Çalıştırma

### 1. Ön Gereksinimler
* **Docker** ve **Docker Compose**
* LoRa UART modülü bağlıyken Linux host üzerinde seri port erişim izni (`/dev/ttyUSB0`, `dialout` grubu)

### 2. Seri Port ve Ortam Yapılandırması
`docker-compose.yml` içindeki ortam değişkenlerini donanımınıza ve araçtaki STM32 firmware başlık yapısına göre kontrol edin:

```yaml
# Linker Servisi
SERIAL_PORT=/dev/ttyUSB0
BAUD_RATE=9600
ACK_TIMEOUT_MS=600
MAX_RETRIES=3

# Encoder & Decoder Servisleri
DEOS_SOURCE_NODE=0x02
DEOS_PROTOCOL_VERSION=0x11
DEOS_FRAME_LAYOUT=UNIVERSAL_9B  # veya COMMON_8B
```

### 3. Servisleri Başlatma
```bash
# Tüm mikroservisleri derleyip arka planda başlatın
docker compose up -d --build

# Logları canlı izleyin
docker compose logs -f
```

### 4. Arayüz ve Bağlantı Noktaları
* **Web Operatör Paneli (`web-ui`):** `http://localhost:8000`
* **MQTT Broker (Konteyner İçi / TCP):** `localhost:1883`
* **MQTT WebSocket:** `ws://localhost:9001`

---

## Referans ICD Dokümanları

Bu depodaki kod tabanı aşağıdaki resmi **DEOS v1.1** şartnamelerini referans alır:

| Doküman Kodu | Sürüm | Başlık ve Kapsam |
| :--- | :--- | :--- |
| `DOC-ICD-CORE-001` | v1.1 | DEOS Core Protocol Architecture (Medya Bağımsız Çekirdek Protokol) |
| `DOC-ICD-DATA-002` | v1.1 | Data Types & Parameter Configuration (Veri Tipleri ve Ortak Parametreler) |
| `DOC-ICD-NET-003` | v1.4 | Network & System Management (`SYSTEM`, `PING/PONG`, `GET_NODE_INFO`, `SUBSCRIBE` & On-Change) |
| `DOC-ICD-DIAG-004` | v1.2 | Fault Management & Diagnostics (`DIAGNOSTIC`, `GET_FAULTS`, `CLEAR_FAULTS`, Fault Registry) |
| `DOC-ICD-TRP-CANFD-005` | v1.1 | CAN-FD Transport Adapter (Araç İçi 29-bit CAN ID & DLC Yuvarlama Kuralları) |
| `DOC-ICD-TRP-ETH-006` | v1.1 | Ethernet Transport Adapter (Textual TCP 5000 & ROS 2 Bridge UDP 5001) |
| `DOC-ICD-TRP-LORA-007` | v1.1 | LoRa Transport Adapter (LoRa UART Çerçeveleme, CRC16-CCITT & ARQ) |
| `DOC-ICD-NODE-TRAC-008` | v1.1 | Traction Node & Service (`0x10` Tahrik Дüğümü ve `0x01` Servisi) |
| `DOC-ICD-NODE-STR-009` | v1.1 | Steering Node & Service (`0x11` Direksiyon Düğümü ve `0x02` Servisi) |
| `DOC-ICD-NODE-BRK-010` | v1.1 | Brake Node & Service (`0x12` Fren Düğümü ve `0x03` Servisi) |
| `DOC-ICD-NODE-BMS-012` | v1.1 | BMS Service & Gateway Protocol (`0x20` BMS Main, `0x21` BMS Aux, `0x30` Gateway) |
| `DOC-ICD-SRV-LGHT-012` | v1.2 | Lighting Service (`0x08` Aydınlatma Servisi - Hedef: `0x03` Main STM32) |

---

**Geliştirici Ekip:** Dokuz Eylül Otonom Sistemler (DEOS)
