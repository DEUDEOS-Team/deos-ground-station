# DEOS Yer Kontrol İstasyonu (Ground Control Station)

![DEOS Protocol](https://img.shields.io/badge/DEOS_Protocol-v1.1_(0x11)-blue.svg)
![Core Engine](https://img.shields.io/badge/Core_Engine-deos--protocol_(ANSI_C99)-informational.svg)
![Architecture](https://img.shields.io/badge/Architecture-Microservices-success.svg)
![Transport](https://img.shields.io/badge/Transport-LoRa_UART_(CRC16--CCITT)-orange.svg)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)
![Tests](https://img.shields.io/badge/Unit_Tests-42_Passed-brightgreen.svg)

**Dokuz Eylül Otonom Sistemler (DEOS)** elektrikli otonom yarış aracının uzaktan telemetri izleme, gerçek zamanlı kontrol, dinamik abonelik yönetimi, arıza teşhisi (Diagnostics) ve parametre konfigürasyonu için geliştirilmiş mikroservis tabanlı **Yer Kontrol İstasyonu (`DEOS_NODE_GROUND_CONTROL = 0x02`)** yazılımıdır.

Bu proje, araç içi yazılımla aynı kaynak olan [`deos-protocol`](file:///home/alper/deos_ground_station/deos-protocol) (saf ANSI C99) submodule'ündeki `deos_icd.h` ve `deos_types.h` şartnamelerini **Tek Doğruluk Kaynağı (Single Source of Truth)** kabul ederek `ctypes` C köprüsü üzerinden **DEOS v1.1 (`0x11`)** protokolü ile bit-bit uyumlu çalışacak şekilde tasarlanmıştır.

---

## Temel Özellikler

* **C99 Motoruyla Bit-Bit Protokol Uyumu (`c_bridge.py` & `payloads.py`):** `UNIVERSAL_9B` çerçeve kodlama/çözme işlemleri, isim çözücüler ve Little-Endian codec'ler doğrudan derlenmiş `libdeos_protocol.so` (`deos_frame.c`, `deos_codec.c`, `deos_registry.c`) C kütüphanesi üzerinden yürütülür. `deos-protocol` submodule'üne dokunulmadan tüm kontrol ve telemetri veri yükleri `deos_types.h` içindeki packed C struct'ları ile birebir (`_pack_ = 1`) paketlenir ve açılır.
* **Medya Bağımsız Evrensel Çerçeve & 4-Bayt Kontrol Komutları:** Yer İstasyonu 29-bit CAN ID hesaplamaz; `DEOS_NODE_MAIN_STM32 (0x03)` Router düğümüne saf `deos_message_t` gönderir. `TRACTION` (`SET_TARGET_SPEED`), `STEERING` (`SET_TARGET_ANGLE`) ve `BRAKE` (`SET_TARGET`) komutları araçtaki C struct boyutlarıyla uyumlu sabit **4 bayt** (`uint16` / `int16`) formatında paketlenir.
* **Güvenilir LoRa L2 Taşıma Katmanı (`Linker`) & Sembolik İzleme:** `0xAA 0x55` senkronizasyonu, `CRC16-CCITT (0x1021)` doğrulaması, çift yönlü **ACK / ARQ** mekanizmasının yanı sıra TX/RX paketlerinde `deos_node_name`, `deos_class_name`, `deos_service_name` ve `deos_command_name` C fonksiyonlarıyla resmi sembolik isim çözümü yapar.
* **Dinamik USB Hotplug & Auto-Reconnect:** `/dev:/dev` bind mount ve ayrıcalıklı izinler sayesinde LoRa USB dönüştürücü çalışma anında takılıp çıkarılabilir; konteyneri yeniden başlatmaya gerek kalmadan otomatik bağlanır.
* **Canlı Donanım Güvenlik Koruması (`Hardware Guard`):** USB modülü bağlı değilken gönderilen komutlar reddedilerek operatöre `ERROR_NO_HARDWARE` uyarısı verilir; arayüz sağ üstünde canlı bağlantı rozeti (`LoRa USB: Connected / Disconnected / Mock Mode`) yer alır ve tekrarlayan bağlantı logları tekilleştirilir.
* **Genişletilmiş Servis & Telemetri Desteği (`SENSORS` IMU & `CALIBRATION`):** `decoder` seviyesinde `SENSORS (0x07)` 9-eksen IMU telemetrisi (`telemetry/sensors`), `CALIBRATION (0x05)` yanıtları (`telemetry/calibration`) ve `GET_NODE_INFO` yanıtlarında `HardwareType` (`hw_type_name`: `STM32H5`, `ESP32` vb.) çözümlemesi desteklenir.
* **Dinamik Telemetri Abonelik Motoru & Çoklu Paket Akışı:** Periyodik (`10..65534 ms`), kira süreli (`Lease TTL`) veya **On-Change (`0xFFFF`)** abonelikleri destekler; `BMS` ve `DIAGNOSTIC` (`GET_FAULTS`) parçalı listelerini otomatik birleştirir.
* **Standart Genişletilmiş Arıza Kütüphanesi (`Fault Registry`):** `CommonFaultId` (`0x0000` - `0x00A2`) standardındaki Sistem, Telemetri, Router, Protokol, CAN-FD (`0x0045 CAN_TX_SEND_FAILED`), LoRa, Ethernet ve Dağıtıcı (Dispatcher) arızalarını Türkçe açıklamalarıyla görüntüler.

---

## Sistem Mimarisi

Sistem, `docker-compose` çatısı altında izole bir köprü ağı (`deos-net`) üzerinde haberleşen **5 konteynerden** ve çekirdekteki **C99 protokol köprüsünden** oluşur:

```text
                             ┌────────────────────────┐
                             │       Web Arayüzü      │
                             │        (web-ui)        │
                             └───────┬────────▲───────┘
                     command/request │        │ telemetry/# (sensors, calibration dahil)
                             (JSON)  │        │ command/status (wire_hex + C sembolik info)
                                     │        │ telemetry/hardware (JSON)
                                     ▼        │
┌────────────────────────────────────┴────────┴───────────────────────────────────┐
│ CODEC KATMANI (shared/deos_core + libdeos_protocol.so [ANSI C99])               │
│                                                                                 │
│   ┌─────────────────┐                                  ┌─────────────────┐      │
│   │     Encoder     │                                  │     Decoder     │      │
│   │  payloads.py -> │                                  │ C decode ->     │      │
│   │  C frame_encode │                                  │ payloads.py     │      │
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
│   - Trace: C c_decode_frame ile wire_hex + sembolik frame_info yayınlar.        │
│   - ARQ (TX): Flag 0x01 ise 1200 ms ACK timer başlatır (Max 3 retry).           │
│   - RX: UART'tan AA 55 senkronizasyonu yapar, CRC16-CCITT doğrular.             │
│   - ACK (RX->TX): Gelen pakette Flag 0x01 (ACK_REQ) ise derhal UART'a           │
│     Flag 0x02 (IS_ACK) + Gelen_CRC16 yanıtı basar.                              │
│   - Soyma: L2 zarfını soyup saf DEOS Frame'i C isim loguyla Decoder'a verir.    │
│   - Health: Donanım bağlantı değişimini telemetry/hardware konusuna bildirir.   │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ UART (pyserial: /dev/ttyUSB0 @ 115200)
                                         ▼
                            ┌────────────────────────┐
                            │  Ebyte E220-900T22D    │
                            │  (LoRa Donanımı)       │
                            └────────────────────────┘
```

### Mikroservislerin Görevleri
1. **`mosquitto`:** Servisler arası asenkron MQTT Pub/Sub mesajlaşmasını yönetir (`1883` TCP, `9001` WebSocket).
2. **`encoder`:** Web arayüzünden gelen JSON komutlarını Pydantic v2 ve servis-bazlı ICD kurallarına göre doğrular, `payloads.py` packed C struct'ları ile serileştirir ve C `deos_frame_encode` üzerinden saf DEOS Evrensel Çerçevesi olarak `lora/tx/reliable` veya `lora/tx/unreliable` konularına basar.
3. **`decoder`:** Linker'dan gelen saf DEOS Evrensel Çerçevesini (`lora/rx/frame`) C `deos_frame_decode` ile çözer, `payloads.py` packed C struct'larıyla açıp mühendislik birimlerine ölçekler ve ilgili `telemetry/<servis>` (`telemetry/sensors` IMU ve `telemetry/calibration` dahil) konusuna JSON olarak yayınlar.
4. **`linker`:** Seri port (`/dev/ttyUSB0`) bağlantısını, donanım tak-çıkar izlemesini, LoRa L2 çerçevelemesini (`0xAA 0x55 + Flag + Length + Payload + CRC16`), çift yönlü ARQ tekrar gönderimini ve C sembolik isimleriyle zenginleştirilmiş `command/status` TX/RX izleme kayıtlarını yönetir.
5. **`web-ui`:** FastAPI ve modern HTML5/JS operatör paneli; durum (`State`) ve sürüş modu (`Mode`) geçişleri, canlı telemetri, abonelik yöneticisi, parametre kalibrasyonu, arıza (DTC) listesi, `hw_type_name` destekli düğüm bilgisi ve `[TX LORA]` C sembolik trace konsolunu sunar.

---

## Dizin Yapısı

```text
deos_ground_station/
├── .dockerignore             # Docker build context temizliği (build/, .venv, docs vb. hariç)
├── docker-compose.yml        # 5 servis, Multi-Stage build, /dev:/dev hotplug & :ro submodule mount
├── BLUEPRINT_GROUND_STATION_MICROSERVICES.md
├── README.md
├── deos-protocol/            # Git Submodule - Saf ANSI C99 Protokol Çekirdeği (salt-okunur baz alınır)
│   ├── include/deos/         # Resmi pusula başlıkları: deos_icd.h, deos_types.h, deos_frame.h vb.
│   └── src/                  # deos_frame.c, deos_codec.c, deos_registry.c
├── mosquitto/
│   └── mosquitto.conf
├── shared/
│   ├── pyproject.toml
│   └── deos_core/
│       ├── __init__.py
│       ├── c_bridge.py       # libdeos_protocol.so için binary-safe ctypes köprüsü & yerel build önbelleği
│       ├── payloads.py       # deos_types.h packed struct'ları (_pack_=1) ve parametre paketleyiciler
│       ├── enums.py          # deos_icd.h & deos_types.h uyumlu Node, Service, Command, HardwareType, CommonFaultId
│       ├── crc.py            # Standart CRC16-CCITT (Polinom: 0x1021, Seed: 0xFFFF, Little-Endian)
│       ├── framing.py        # C motoruna bağlı UniversalDeosFrame (9B) + LoRa L2 Zarfı
│       ├── models.py         # Pydantic v2 komut şemaları, servis-bazlı MessageClass çıkarımı ve ICD kuralları
│       ├── scaling.py        # PhysicalValue = RawValue * Scale + Offset dönüşümleri (IMU dahil)
│       └── registry.py       # Parametre listeleri ve Türkçe DTC / Fault sözlükleri (0x0000 - 0x00A2)
├── services/
│   ├── linker/               # Multi-Stage Dockerfile + UART, LoRa L2, ARQ FSM, C sembolik trace
│   ├── encoder/              # Multi-Stage Dockerfile + JSON Komut -> C Struct Payload -> C Frame Encode
│   ├── decoder/              # Multi-Stage Dockerfile + C Frame Decode -> C Struct -> JSON Telemetri (+IMU)
│   └── web-ui/               # Multi-Stage Dockerfile + FastAPI Dashboard & WebSocket (Port 8000)
└── tests/                    # 42 Birim & C99 Parite Testi (ABI, framing, symmetry, ARQ, header drift)
```

---

## Protokol Özeti

### 1. Seviye 1: Medya Bağımsız Evrensel DEOS Çerçevesi (`Encoder` $\leftrightarrow$ `Decoder`)
`shared/deos_core/framing.py` üzerinde `DEOS_FRAME_LAYOUT` ortam değişkeni ile seçilebilen iki başlık profili desteklenir:
* **`UNIVERSAL_9B` (`DOC-ICD-CORE-001` Bölüm 9.1 / `deos_frame.c` - Varsayılan):**
  `[Destination(1B)] [Source(1B)] [Priority(1B)] [Version(1B)] [Class(1B)] [Service(1B)] [Command(1B)] [Sequence(1B)] [Payload_Len(1B)] + [Payload(N Byte)]` ($9+N$ Byte) — doğrudan `libdeos_protocol.so` içindeki `deos_frame_encode` / `deos_frame_decode` ile çalıştırılır.
* **`COMMON_8B` (Geriye Dönük Uyumluluk Profili):**
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
| `0x04` | `DEOS_NODE_ROS_BRIDGE` | `SYSTEM`, `TRACTION`, `STEERING`, `BRAKE`, `SENSORS` | ROS 2 Otonom Sürüş Köprüsü |
| `0x10` | `DEOS_NODE_TRACTION` | `TRACTION (0x01)`, `CALIBRATION (0x05)`, `SYSTEM`, `DIAGNOSTIC` | Tahrik / İnvertör ECU |
| `0x11` | `DEOS_NODE_STEERING` | `STEERING (0x02)`, `CALIBRATION (0x05)`, `SYSTEM`, `DIAGNOSTIC` | Direksiyon ECU |
| `0x12` | `DEOS_NODE_BRAKE` | `BRAKE (0x03)`, `CALIBRATION (0x05)`, `SYSTEM`, `DIAGNOSTIC` | Fren & EPB ECU |
| `0x13` | `DEOS_NODE_IMU` | `SENSORS (0x07)`, `SYSTEM`, `DIAGNOSTIC` | Main STM32 Üzerinde Sanal 9-Eksen IMU |
| `0x20` | `DEOS_NODE_BMS_MAIN` | `BMS (0x04)`, `SYSTEM`, `DIAGNOSTIC` | Ana HV Batarya (Daly BMS #1 Sanal Düğümü) |
| `0x21` | `DEOS_NODE_BMS_AUX` | `BMS (0x04)`, `SYSTEM`, `DIAGNOSTIC` | Yardımcı LV Batarya (Daly BMS #2 Sanal Düğümü) |
| `0x30` | `DEOS_NODE_BMS_GATEWAY` | `SYSTEM (0x00)`, `DIAGNOSTIC (0x06)` | Classic CAN – CAN-FD Köprü Donanımı |
| `0xFE` | `DEOS_NODE_CAN_BROADCAST` | CAN Veriyolu Geneli Yayın | CAN Omurgasındaki Tüm ECU'lar |
| `0xFF` | `DEOS_NODE_GLOBAL_BROADCAST`| Genel Sistem Yayını | Araç ve Yer İstasyonundaki Tüm Düğümler |

---

## MQTT Topic Sözleşmesi

| Topic Adı | Yön | Format | Açıklama |
| :--- | :--- | :--- | :--- |
| `command/request` | `web-ui` $\rightarrow$ `encoder` | JSON | Operatörün gönderdiği komut, durum geçişi veya abonelik isteği |
| `lora/tx/reliable` | `encoder` $\rightarrow$ `linker` | Binary | Saf DEOS Çerçevesi (`Flag=0x01 ACK_REQ` ile zarflanır) |
| `lora/tx/unreliable` | `encoder` $\rightarrow$ `linker` | Binary | Saf DEOS Çerçevesi (`Flag=0x00 NONE` ile zarflanır) |
| `lora/rx/frame` | `linker` $\rightarrow$ `decoder` | Binary | L2 zarfı soyulmuş, CRC16 doğrulanmış Saf DEOS Çerçevesi |
| `command/status` | `linker` $\rightarrow$ `web-ui` | JSON | ARQ durumu, giden `wire_hex`, C sembolik `frame_info` (`dest_name`, `class_name`, `command_name`) ve `ERROR_NO_HARDWARE` |
| `telemetry/hardware`| `linker` $\rightarrow$ `web-ui` | JSON | Canlı LoRa USB bağlantı durumu (`connected`, `port`, `baud`, `mode`, `error`) |
| `telemetry/system` | `decoder` $\rightarrow$ `web-ui` | JSON | `PING/PONG` (RTT), `HEARTBEAT` (State), `GET_NODE_INFO` (`hw_type_name` dahil), `SUBSCRIBE` yanıtları |
| `telemetry/traction` | `decoder` $\rightarrow$ `web-ui` | JSON | Hız (`m/s`), motor akımı (`A`), invertör/motor sıcaklıkları (`°C`), vites ve patinaj |
| `telemetry/steering` | `decoder` $\rightarrow$ `web-ui` | JSON | Direksiyon açısı (`deg`), motor akımı/sıcaklığı, şasi yaw rate (`deg/s`) |
| `telemetry/brake` | `decoder` $\rightarrow$ `web-ui` | JSON | Fren pozisyonu (`mm`), kuvvet (`N`), boyuna ivme (`m/s²`), EPB durumu |
| `telemetry/bms/main` | `decoder` $\rightarrow$ `web-ui` | JSON | Ana batarya (`0x20`) durum, hücre voltaj, sıcaklık ve balans listeleri |
| `telemetry/bms/aux` | `decoder` $\rightarrow$ `web-ui` | JSON | Yardımcı batarya (`0x21`) durum, hücre voltaj, sıcaklık ve balans listeleri |
| `telemetry/calibration`| `decoder` $\rightarrow$ `web-ui` | JSON | Kalibrasyon komut yanıtları (`CALIBRATION = 0x05`) |
| `telemetry/diagnostic`| `decoder` $\rightarrow$ `web-ui` | JSON | Düğüm bazlı arıza kayıtları (`GET_FAULTS`) ve `END_OF_FAULT_LIST` bildirimleri |
| `telemetry/sensors` | `decoder` $\rightarrow$ `web-ui` | JSON | 9-eksen IMU telemetrisi (`accel_mps2`, `gyro_deg_s`, `mag_ut` — decoder katmanında hazır) |
| `telemetry/lighting` | `decoder` $\rightarrow$ `web-ui` | JSON | Ön far, fren lambası, sağ/sol sinyal, dörtlü flaşör ve arıza bayrakları |
| `telemetry/config` | `decoder` $\rightarrow$ `web-ui` | JSON | Parametre okuma/yazma (`0xE0..0xE3`) yanıtları |

---

## Kurulum ve Çalıştırma

### 1. Ön Gereksinimler ve Submodule Klonlama
* **Linux İşletim Sistemi** (Ubuntu 20.04/22.04/24.04 önerilir)
* **Docker** ve **Docker Compose**
* Host üzerinde birim testlerini çalıştırmak için **`gcc`** (`libdeos_protocol.so` yerel geliştirme önbelleği ve C99 parite testleri için; Docker imajları Multi-Stage build ile kendi içinde derler).
* Projeyi alt modüllerle (`deos-protocol`, `docs`) birlikte klonlayın veya güncelleyin:
  ```bash
  git clone --recurse-submodules https://github.com/DEUDEOS-Team/deos-ground-station.git
  # Zaten klonladıysanız:
  git submodule update --init --recursive
  ```
* Kullanıcının seri port erişim grubu üyeliği:
  ```bash
  sudo usermod -aG dialout $USER
  ```

### 2. Multi-Stage Docker Build ve Yapılandırma (`docker-compose.yml`)
Tüm Python servis `Dockerfile`'ları (`encoder`, `decoder`, `linker`, `web-ui`) 2 aşamalı build kullanır:
1. **`protocol-builder` aşaması:** `deos-protocol/src/*.c` kaynaklarını `gcc -std=c99 -O2 -fPIC -shared` ile `/build/libdeos_protocol.so` olarak derler.
2. **Runtime aşaması:** Temiz `python:3.12-slim` imajına yalnızca `/usr/local/lib/libdeos_protocol.so` ve `deos-protocol/include` kopyalanır (`gcc` runtime imajına taşınmaz).

Varsayılan ortam değişkenleri:
```yaml
# Linker Servisi
SERIAL_PORT=/dev/ttyUSB0
BAUD_RATE=115200       # LoRa UART donanım hızı
ACK_TIMEOUT_MS=1200    # LoRa hava süresine uygun ARQ zaman aşımı
MAX_RETRIES=3          # Maksimum yeniden gönderim denemesi
SERIAL_MOCK=false      # Gerçek donanım olmadığında yazılımsal test için 'true' yapılabilir
DEOS_PROTOCOL_LIB_PATH=/usr/local/lib/libdeos_protocol.so

# Encoder & Decoder Servisleri
DEOS_SOURCE_NODE=0x02
DEOS_PROTOCOL_VERSION=0x11
DEOS_FRAME_LAYOUT=UNIVERSAL_9B
DEOS_PROTOCOL_LIB_PATH=/usr/local/lib/libdeos_protocol.so
```

> **Not:** `./shared`, `./services/web-ui/static`, servis `main.py`/`app.py` dosyaları ve salt-okunur `./deos-protocol:/app/deos-protocol:ro` konteynerlere bağlıdır. Python/arayüz değişiklikleri konteyner rebuild gerektirmez (`hot-reload`).

### 3. Servisleri Başlatma
```bash
# Multi-stage imajları derleyip tüm mikroservisleri arka planda başlatın
docker compose up -d --build

# Canlı log akışını izleyin
docker compose logs -f
```

### 4. Arayüz ve Bağlantı Noktaları
* **Web Operatör Paneli (`web-ui`):** [`http://localhost:8000`](http://localhost:8000)
* **MQTT Broker (Konteyner İçi / TCP):** `localhost:1883`
* **MQTT WebSocket:** `ws://localhost:9001`

### 5. Birim ve C99 Protokol Parite Testlerini Çalıştırma
Sistem; CRC16, framing, `ctypes` ABI hizalaması (`sizeof`/`offsetof`), packed C struct & `deos_icd.h` enum/parametre paritesi, çift yönlü C99 $\leftrightarrow$ Python tel-seviyesi paket uyumu, simetri ve Linker ARQ mekanizmalarını doğrulayan **42 adet otomatik test** içerir:

```bash
.venv/bin/python -m unittest discover -v tests
```

---

## Referans ICD ve Submodule Kaynakları

* **Resmi Protokol Çekirdeği:** [`deos-protocol`](file:///home/alper/deos_ground_station/deos-protocol) (`include/deos/deos_icd.h`, `include/deos/deos_types.h`, `src/deos_frame.c`, `src/deos_codec.c`, `src/deos_registry.c`)
* **ICD Şartnameleri (`docs/icd/`):**

| Doküman Kodu | Sürüm | Başlık ve Kapsam |
| :--- | :--- | :--- |
| `DOC-ICD-CORE-001` | v1.1 | DEOS Core Protocol Architecture (Medya Bağımsız Çekirdek Protokol) |
| `DOC-ICD-DATA-002` | v1.1 | Data Types & Parameter Configuration (Veri Tipleri ve Ortak Parametreler) |
| `DOC-ICD-NET-003` | v1.4 | Network & System Management (`SYSTEM`, `PING/PONG`, `GET_NODE_INFO`, `SUBSCRIBE` & On-Change) |
| `DOC-ICD-DIAG-004` | v1.2 | Fault Management & Diagnostics (`DIAGNOSTIC`, `GET_FAULTS`, `CLEAR_FAULTS`, Fault Registry) |
| `DOC-ICD-TRP-CANFD-005` | v1.1 | CAN-FD Transport Adapter (Araç İçi 29-bit CAN ID & DLC Yuvarlama Kuralları) |
| `DOC-ICD-TRP-ETH-006` | v1.1 | Ethernet Transport Adapter (Textual TCP 5000 & ROS 2 Bridge UDP 5001) |
| `DOC-ICD-TRP-LORA-007` | v1.1 | LoRa Transport Adapter (LoRa UART Çerçeveleme, CRC16-CCITT & ARQ) |
| `DOC-ICD-NODE-TRAC-008` | v1.1 | Traction Node & Service (`0x10` Tahrik Düğümü ve `0x01` Servisi) |
| `DOC-ICD-NODE-STR-009` | v1.1 | Steering Node & Service (`0x11` Direksiyon Düğümü ve `0x02` Servisi) |
| `DOC-ICD-NODE-BRK-010` | v1.1 | Brake Node & Service (`0x12` Fren Düğümü ve `0x03` Servisi) |
| `DOC-ICD-NODE-BMS-012` | v1.1 | BMS Service & Gateway Protocol (`0x20` BMS Main, `0x21` BMS Aux, `0x30` Gateway) |
| `DOC-ICD-SRV-LGHT-012` | v1.2 | Lighting Service (`0x08` Aydınlatma Servisi - Hedef: `0x03` Main STM32) |

---

**Geliştirici Ekip:** Dokuz Eylül Otonom Sistemler (DEOS)
