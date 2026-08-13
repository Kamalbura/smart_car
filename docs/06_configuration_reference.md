# Configuration Reference

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 06_configuration_reference.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

All configuration is centralized in YAML files under the `config/` directory. The primary configuration file is `system.yaml`, which contains settings for all services.

---

## Configuration Files

| File | Purpose |
|------|---------|
| `config/system.yaml` | Primary system configuration |
| `config/logging.yaml` | Logging configuration |
| `config/settings.yaml` | Additional settings |
| `config/settings.json` | JSON settings (legacy) |
| `config/system.local.json` | Local overrides |

---

## system.yaml Structure

```yaml
# Full configuration file structure
ipc: { ... }
audio: { ... }
wakeword: { ... }
stt: { ... }
tts: { ... }
llm: { ... }
vision: { ... }
remote_interface: { ... }
nav: { ... }
display: { ... }
led_ring: { ... }
uart: { ... }
logging: { ... }
```

---

## Section: ipc

Controls ZeroMQ inter-process communication.

```yaml
ipc:
  upstream: tcp://127.0.0.1:6010
  downstream: tcp://127.0.0.1:6011
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| upstream | string | tcp://127.0.0.1:6010 | URL for upstream bus (module → orchestrator) |
| downstream | string | tcp://127.0.0.1:6011 | URL for downstream bus (orchestrator → modules) |

---

## Section: audio

Audio hardware configuration for voice pipeline.

```yaml
audio:
  input_device: null
  sample_rate: 48000
  frame_size: 512
  resample_rate: 16000
  channels: 1
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| input_device | string/null | null | ALSA device name, null for default |
| sample_rate | int | 48000 | Microphone sample rate (Hz) |
| frame_size | int | 512 | Samples per frame |
| resample_rate | int | 16000 | Resampled rate for STT (Hz) |
| channels | int | 1 | Number of audio channels |

---

## Section: wakeword

Porcupine wakeword detection configuration.

```yaml
wakeword:
  enabled: true
  engine: porcupine
  model_path: models/wakeword/hey-robo_en_raspberry-pi_v3_0_0.ppn
  sensitivity: 0.5
  access_key: ${PICOVOICE_ACCESS_KEY}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable wakeword detection |
| engine | string | porcupine | Wakeword engine (only porcupine supported) |
| model_path | string | - | Path to .ppn keyword file |
| sensitivity | float | 0.5 | Detection sensitivity (0.0-1.0) |
| access_key | string | - | Picovoice API key (from env) |

---

## Section: stt

Speech-to-text configuration.

```yaml
stt:
  enabled: true
  provider: azure
  language: en-US
  timeout: 5
  silence_timeout: 2.0
  min_phrase_length: 0.5
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable STT |
| provider | string | azure | STT provider (azure only) |
| language | string | en-US | Recognition language |
| timeout | int | 5 | Max recording time (seconds) |
| silence_timeout | float | 2.0 | Silence before stop (seconds) |
| min_phrase_length | float | 0.5 | Minimum phrase length (seconds) |

### Azure STT Environment Variables

```bash
AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=eastus
```

---

## Section: tts

Text-to-speech configuration.

```yaml
tts:
  enabled: true
  provider: azure
  voice: en-US-JennyNeural
  rate: "+0%"
  pitch: "+0Hz"
  volume: "+0dB"
  audio_device: default
  cache_enabled: true
  cache_dir: .cache/tts
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable TTS |
| provider | string | azure | TTS provider (azure only) |
| voice | string | en-US-JennyNeural | Voice name |
| rate | string | "+0%" | Speaking rate adjustment |
| pitch | string | "+0Hz" | Pitch adjustment |
| volume | string | "+0dB" | Volume adjustment |
| audio_device | string | default | ALSA output device |
| cache_enabled | bool | true | Enable TTS caching |
| cache_dir | string | .cache/tts | Cache directory |

### Azure TTS Environment Variables

```bash
AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=eastus
```

---

## Section: llm

Language model configuration.

```yaml
llm:
  enabled: true
  provider: azure
  model: gpt-4o
  api_version: "2024-12-01-preview"
  max_tokens: 150
  temperature: 0.7
  timeout: 10
  system_prompt: |
    You are a helpful robot assistant...
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable LLM |
| provider | string | azure | Provider (azure only) |
| model | string | gpt-4o | Model deployment name |
| api_version | string | 2024-12-01-preview | Azure API version |
| max_tokens | int | 150 | Max response tokens |
| temperature | float | 0.7 | Sampling temperature |
| timeout | int | 10 | Request timeout (seconds) |
| system_prompt | string | - | System prompt for robot persona |

### System Prompt Template

```yaml
system_prompt: |
  You are a helpful robot assistant named Robo.
  You can move in these directions: forward, backward, left, right, stopped.
  
  Always respond with valid JSON:
  {
    "speak": "your verbal response",
    "direction": "forward|backward|left|right|stopped"
  }
  
  If you don't understand, say so and stay stopped.
  Be concise and friendly.
```

### Azure OpenAI Environment Variables

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

---

## Section: vision

Computer vision configuration.

```yaml
vision:
  enabled: true
  model: yolov8n
  model_path: models/yolov8n.pt
  confidence: 0.5
  target_fps: 10
  resolution: [640, 480]
  camera_backend: picamera2
  device: 0
  annotate_frames: true
  classes: null  # All COCO classes
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable vision |
| model | string | yolov8n | YOLO model name |
| model_path | string | models/yolov8n.pt | Path to weights |
| confidence | float | 0.5 | Detection threshold |
| target_fps | int | 10 | Target frame rate |
| resolution | list | [640, 480] | Camera resolution [W, H] |
| camera_backend | string | picamera2 | Camera library |
| device | int | 0 | Camera device index |
| annotate_frames | bool | true | Draw boxes on frames |
| classes | list/null | null | Filter classes, null = all |

---

## Section: remote_interface

HTTP API server configuration.

```yaml
remote_interface:
  enabled: true
  host: 0.0.0.0
  port: 8770
  mjpeg_fps: 10
  session_timeout_sec: 300
  cors_origins:
    - "*"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable HTTP server |
| host | string | 0.0.0.0 | Bind address |
| port | int | 8770 | HTTP port |
| mjpeg_fps | int | 10 | MJPEG stream FPS |
| session_timeout_sec | int | 300 | Session inactivity timeout |
| cors_origins | list | ["*"] | CORS allowed origins |

---

## Section: nav

Navigation and motor control configuration.

```yaml
nav:
  default_speed: 255
  collision_avoidance:
    enabled: true
    min_distance_cm: 20
    warning_distance_cm: 40
  auto_stop_timeout_sec: 30
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| default_speed | int | 255 | Motor PWM (0-255) |
| collision_avoidance.enabled | bool | true | Enable collision detection |
| collision_avoidance.min_distance_cm | int | 20 | Stop distance (cm) |
| collision_avoidance.warning_distance_cm | int | 40 | Warning distance (cm) |
| auto_stop_timeout_sec | int | 30 | Auto-stop after idle (seconds) |

---

## Section: display

OLED display configuration.

```yaml
display:
  enabled: true
  type: waveshare_oled
  width: 128
  height: 64
  spi_bus: 0
  spi_device: 0
  dc_pin: 24
  rst_pin: 25
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable display |
| type | string | waveshare_oled | Display type |
| width | int | 128 | Display width (pixels) |
| height | int | 64 | Display height (pixels) |
| spi_bus | int | 0 | SPI bus number |
| spi_device | int | 0 | SPI device number |
| dc_pin | int | 24 | Data/Command GPIO |
| rst_pin | int | 25 | Reset GPIO |

---

## Section: led_ring

NeoPixel LED ring configuration.

```yaml
led_ring:
  enabled: true
  pin: 18
  count: 16
  brightness: 0.5
  order: GRB
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| enabled | bool | true | Enable LED ring |
| pin | int | 18 | GPIO pin (PWM capable) |
| count | int | 16 | Number of LEDs |
| brightness | float | 0.5 | Brightness (0.0-1.0) |
| order | string | GRB | Color order |

---

## Section: uart

Serial UART configuration for ESP32.

```yaml
uart:
  port: /dev/ttyUSB0
  baudrate: 115200
  timeout: 1.0
  buffer_size: 20
  auto_reconnect: true
  reconnect_delay_sec: 5
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| port | string | /dev/ttyUSB0 | Serial port |
| baudrate | int | 115200 | Baud rate |
| timeout | float | 1.0 | Read timeout (seconds) |
| buffer_size | int | 20 | Sensor data buffer size |
| auto_reconnect | bool | true | Auto-reconnect on disconnect |
| reconnect_delay_sec | int | 5 | Reconnect delay (seconds) |

---

## Section: logging

Logging configuration.

```yaml
logging:
  level: INFO
  file_level: DEBUG
  log_dir: logs
  max_bytes: 10485760
  backup_count: 5
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| level | string | INFO | Console log level |
| file_level | string | DEBUG | File log level |
| log_dir | string | logs | Log directory |
| max_bytes | int | 10485760 | Max log file size (10MB) |
| backup_count | int | 5 | Number of backup files |
| format | string | - | Log message format |

---

## Environment Variables

### Required

| Variable | Used By | Description |
|----------|---------|-------------|
| AZURE_SPEECH_KEY | stt, tts | Azure Cognitive Services key |
| AZURE_SPEECH_REGION | stt, tts | Azure region |
| AZURE_OPENAI_ENDPOINT | llm | Azure OpenAI endpoint URL |
| AZURE_OPENAI_API_KEY | llm | Azure OpenAI API key |
| AZURE_OPENAI_DEPLOYMENT | llm | Model deployment name |
| PICOVOICE_ACCESS_KEY | wakeword | Picovoice API key |

### Optional

| Variable | Used By | Description |
|----------|---------|-------------|
| SMART_CAR_CONFIG | all | Override config file path |
| LOG_LEVEL | all | Override log level |

---

## Configuration Loading

### Load Order

1. Default values (hardcoded)
2. `config/system.yaml` (primary)
3. `config/system.local.json` (local overrides)
4. Environment variables (highest priority)

### Environment Variable Substitution

YAML values can reference environment variables:

```yaml
llm:
  access_key: ${AZURE_OPENAI_API_KEY}
```

---

## Configuration Validation

### On Startup

Each service validates its configuration section on startup:
- Required fields must be present
- Types must match
- Ranges must be valid

### Error Handling

Invalid configuration causes:
1. Error message in log
2. Service exits with code 1
3. systemd restart (up to limit)

---

## Example Minimal Configuration

```yaml
# Minimum viable configuration

ipc:
  upstream: tcp://127.0.0.1:6010
  downstream: tcp://127.0.0.1:6011

wakeword:
  enabled: true
  model_path: models/wakeword/hey-robo_en_raspberry-pi_v3_0_0.ppn
  access_key: ${PICOVOICE_ACCESS_KEY}

stt:
  enabled: true
  provider: azure

tts:
  enabled: true
  provider: azure
  voice: en-US-JennyNeural

llm:
  enabled: true
  provider: azure
  model: gpt-4o

vision:
  enabled: true
  model: yolov8n

remote_interface:
  enabled: true
  port: 8770

uart:
  port: /dev/ttyUSB0
  baudrate: 115200
```

---

## References

| Document | Purpose |
|----------|---------|
| [05_services_reference.md](05_services_reference.md) | Service-specific settings |
| [09_deployment_and_operations.md](09_deployment_and_operations.md) | Deployment |
