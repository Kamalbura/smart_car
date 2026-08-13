# Mobile App Integration

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 07_mobile_app_integration.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

The Android companion app provides remote supervision and control of the smart_car robot. It communicates with the Raspberry Pi over HTTP/REST, polling for telemetry and sending control intents.

---

## App Architecture

### Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Kotlin |
| UI Framework | Jetpack Compose |
| Architecture | MVVM |
| HTTP Client | Retrofit + OkHttp |
| Navigation | Single-screen tabs |
| Build System | Gradle (Kotlin DSL) |

### Package Structure

```
mobile_app/
├── app/
│   ├── src/main/java/com/example/smartcar/
│   │   ├── MainActivity.kt
│   │   ├── ui/
│   │   │   ├── MainScreen.kt           # All UI components
│   │   │   ├── AppViewModel.kt         # ViewModel
│   │   │   └── theme/
│   │   ├── data/
│   │   │   ├── RobotRepository.kt      # HTTP layer
│   │   │   ├── RobotApiService.kt      # Retrofit interface
│   │   │   └── AppState.kt             # State models
│   │   └── util/
│   └── src/main/res/
└── build.gradle.kts
```

---

## Network Communication

### Connection Model

```
┌─────────────────────────────────────────────────────────────────┐
│                        ANDROID APP                              │
│                                                                 │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐   │
│  │  ViewModel    │◄──►│  Repository   │◄──►│ OkHttp/Retrofit│   │
│  └───────────────┘    └───────────────┘    └───────────────┘   │
│                                                   │              │
└───────────────────────────────────────────────────┼──────────────┘
                                                    │
                                                    │ HTTP
                                                    ▼
                                            ┌───────────────┐
                                            │  Tailscale    │
                                            │ 100.111.13.60 │
                                            └───────┬───────┘
                                                    │
                                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                       RASPBERRY PI                                 │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                   remote-interface                          │   │
│  │                     Port 8770                               │   │
│  │                                                             │   │
│  │   /health    /status    /telemetry    /intent    /stream   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                │                                   │
│                                │ ZeroMQ                            │
│                                ▼                                   │
│                        ┌───────────────┐                           │
│                        │  orchestrator │                           │
│                        └───────────────┘                           │
└───────────────────────────────────────────────────────────────────┘
```

### Base URL Configuration

```kotlin
// RobotRepository.kt
private const val BASE_URL = "http://100.111.13.60:8770"
```

The app connects via Tailscale VPN to the Pi's private IP.

---

## HTTP API Contract

### GET /health

Health check endpoint.

**Request**: None

**Response**:
```json
{
  "status": "ok"
}
```

**Usage**: Connection validation on app startup.

---

### GET /status

Primary telemetry endpoint. Returns complete robot state.

**Request**: None

**Response**:
```json
{
  "connected": true,
  "display_state": "idle",
  "display_text": "Ready",
  "vision_mode": "detection",
  "vision_paused": false,
  "last_detection": {
    "label": "person",
    "confidence": 0.87,
    "bbox": [100, 50, 200, 300],
    "ts": 1769931845.123
  },
  "sensor": {
    "s1": 16,
    "s2": 12,
    "s3": -1,
    "mq2": 478,
    "min_distance": 12,
    "obstacle": false,
    "warning": false,
    "is_safe": false
  },
  "last_llm_response": "Moving forward now",
  "last_tts_text": "Moving forward now",
  "last_tts_status": "done",
  "session_active": true,
  "last_session_touch": 1769931845
}
```

**Polling**: Every 1 second.

---

### GET /telemetry

Alias for /status. Returns identical response.

---

### POST /intent

Send control intent to robot.

**Request**:
```json
{
  "intent": "start",
  "extras": {}
}
```

**Supported Intents**:

| Intent | Description | Extras |
|--------|-------------|--------|
| start | Move forward | - |
| stop | Stop motors | - |
| left | Turn left | - |
| right | Turn right | - |
| listen | Trigger voice listening | - |
| capture | Capture single frame | - |
| vision_mode | Set vision mode | `{"mode": "detection\|capture\|off"}` |
| pause_vision | Pause/resume vision | `{"paused": true\|false}` |

**Response**:
```json
{
  "status": "accepted",
  "intent": "start"
}
```

**HTTP Status**: 202 Accepted (async processing)

---

### GET /stream/mjpeg

Live MJPEG video stream.

**Request**: None

**Response**: 
- Content-Type: `multipart/x-mixed-replace; boundary=frame`
- Continuous JPEG frames

**Usage**: WebView or custom MJPEG decoder.

---

## Data Models (Kotlin)

### TelemetryState

```kotlin
data class TelemetryState(
    val connected: Boolean = false,
    val displayState: String = "unknown",
    val displayText: String = "",
    val visionMode: String = "off",
    val visionPaused: Boolean = false,
    val lastDetection: DetectionResult? = null,
    val sensor: SensorData? = null,
    val lastLlmResponse: String = "",
    val lastTtsText: String = "",
    val lastTtsStatus: String = "",
    val sessionActive: Boolean = false,
    val lastSessionTouch: Long = 0
)
```

### SensorData

```kotlin
data class SensorData(
    val s1: Int = -1,
    val s2: Int = -1,
    val s3: Int = -1,
    val mq2: Int = 0,
    val minDistance: Int = -1,
    val obstacle: Boolean = false,
    val warning: Boolean = false,
    val isSafe: Boolean = true
)
```

### DetectionResult

```kotlin
data class DetectionResult(
    val label: String,
    val confidence: Float,
    val bbox: List<Int>,
    val ts: Double
)
```

### IntentRequest

```kotlin
data class IntentRequest(
    val intent: String,
    val extras: Map<String, Any> = emptyMap()
)
```

---

## UI Structure

### Tab Navigation

The app uses a single-screen tabbed interface:

| Tab Index | Name | Purpose |
|-----------|------|---------|
| 0 | Dashboard | Primary control interface |
| 1 | Vision | Camera stream + detection |
| 2 | Telemetry | Sensor data display |
| 3 | Logs | Event history |
| 4 | Settings | Connection settings |

### Dashboard Tab

**Components**:
- Connection status indicator (green/red dot)
- Current phase display (IDLE, LISTENING, etc.)
- D-pad directional controls
- Voice trigger button
- Emergency stop button

**Actions**:
- Forward: `POST /intent {"intent": "start"}`
- Stop: `POST /intent {"intent": "stop"}`
- Left: `POST /intent {"intent": "left"}`
- Right: `POST /intent {"intent": "right"}`
- Voice: `POST /intent {"intent": "listen"}`

### Vision Tab

**Components**:
- MJPEG stream view (WebView or custom decoder)
- Vision mode toggle (detection/capture/off)
- Pause/resume toggle
- Capture button
- Detection overlay (when available)

**Actions**:
- Mode toggle: `POST /intent {"intent": "vision_mode", "extras": {"mode": "..."}}`
- Pause toggle: `POST /intent {"intent": "pause_vision", "extras": {"paused": true}}`
- Capture: `POST /intent {"intent": "capture"}`

### Telemetry Tab

**Components**:
- Distance sensors (S1, S2, S3) with visual bars
- Gas sensor (MQ2) level
- Obstacle/warning indicators
- Is-safe status
- Last LLM response
- Last TTS text

**Data Source**: Parsed from `/status` response.

### Logs Tab

**Components**:
- Scrollable event list
- Timestamp + event type + details
- Filter by type

**Data**: Accumulated from polling responses (not persisted).

### Settings Tab

**Components**:
- Pi IP address input
- Port input
- Connection test button
- Polling interval selector
- Theme toggle

---

## ViewModel Layer

### AppViewModel

```kotlin
class AppViewModel : ViewModel() {
    private val repository = RobotRepository()
    
    private val _uiState = MutableStateFlow(AppUiState())
    val uiState: StateFlow<AppUiState> = _uiState.asStateFlow()
    
    private val _telemetry = MutableStateFlow(TelemetryState())
    val telemetry: StateFlow<TelemetryState> = _telemetry.asStateFlow()
    
    init {
        startPolling()
    }
    
    fun sendIntent(intent: String, extras: Map<String, Any> = emptyMap()) {
        viewModelScope.launch {
            repository.sendIntent(IntentRequest(intent, extras))
        }
    }
    
    private fun startPolling() {
        viewModelScope.launch {
            while (true) {
                try {
                    val status = repository.getStatus()
                    _telemetry.value = status
                    _uiState.update { it.copy(connected = true) }
                } catch (e: Exception) {
                    _uiState.update { it.copy(connected = false) }
                }
                delay(1000) // Poll every second
            }
        }
    }
}
```

### State Management

```kotlin
data class AppUiState(
    val connected: Boolean = false,
    val selectedTab: Int = 0,
    val isLoading: Boolean = false,
    val error: String? = null
)
```

---

## Repository Layer

### RobotRepository

```kotlin
class RobotRepository {
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    
    private val retrofit = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
    
    private val api = retrofit.create(RobotApiService::class.java)
    
    suspend fun getHealth(): HealthResponse = api.getHealth()
    suspend fun getStatus(): TelemetryState = api.getStatus()
    suspend fun sendIntent(request: IntentRequest): IntentResponse = api.sendIntent(request)
}
```

### RobotApiService

```kotlin
interface RobotApiService {
    @GET("health")
    suspend fun getHealth(): HealthResponse
    
    @GET("status")
    suspend fun getStatus(): TelemetryState
    
    @GET("telemetry")
    suspend fun getTelemetry(): TelemetryState
    
    @POST("intent")
    suspend fun sendIntent(@Body request: IntentRequest): IntentResponse
}
```

---

## Error Handling

### Network Errors

| Error | Handling |
|-------|----------|
| Connection refused | Show "Disconnected" status |
| Timeout | Retry on next poll |
| HTTP 4xx | Show error message |
| HTTP 5xx | Show error message |
| Parse error | Log and ignore |

### Retry Strategy

- Polling continues regardless of errors
- Intent commands show toast on failure
- No exponential backoff (constant 1s interval)

### Offline Mode

When disconnected:
- All tabs remain visible
- Telemetry shows stale data
- Intents show error toast
- Connection indicator turns red

---

## Session Management

### Session Lifecycle

1. **Start**: First successful `/status` call
2. **Maintain**: Each poll touches session
3. **Expire**: 300s inactivity (server-side)

### Server-Side Behavior

The Pi's remote-interface tracks session state:
- `session_active`: true while connected
- `last_session_touch`: Unix timestamp

If session expires, robot may auto-stop (configurable).

---

## MJPEG Streaming

### Implementation Options

1. **WebView** (current):
   ```kotlin
   WebView(
       modifier = Modifier.fillMaxSize()
   ) {
       loadUrl("http://100.111.13.60:8770/stream/mjpeg")
   }
   ```

2. **Custom Decoder**:
   ```kotlin
   // Parse multipart stream
   // Extract JPEG frames
   // Display in Image composable
   ```

### Stream Characteristics

| Property | Value |
|----------|-------|
| Format | Motion JPEG |
| Resolution | 640×480 |
| Frame rate | ~10 FPS |
| Latency | 200-500ms |

---

## Build Configuration

### build.gradle.kts (app)

```kotlin
android {
    namespace = "com.example.smartcar"
    compileSdk = 34
    
    defaultConfig {
        applicationId = "com.example.smartcar"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }
}

dependencies {
    // Compose
    implementation(platform("androidx.compose:compose-bom:2024.01.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    
    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    
    // Lifecycle
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.7.0")
}
```

---

## Testing

### Manual Testing

1. Launch app
2. Verify connection indicator
3. Test each D-pad button
4. Verify telemetry updates
5. Test MJPEG stream

### Network Testing

```bash
# From PC, test endpoints
curl http://100.111.13.60:8770/health
curl http://100.111.13.60:8770/status
curl -X POST http://100.111.13.60:8770/intent \
  -H "Content-Type: application/json" \
  -d '{"intent": "start"}'
```

---

## Known Limitations

1. **No offline persistence**: All state lost on app restart
2. **Single Pi support**: Cannot switch between multiple robots
3. **No authentication**: Plain HTTP, no auth tokens
4. **Hardcoded IP**: Tailscale IP embedded in code
5. **No intent queuing**: Failed intents not retried

---

## References

| Document | Purpose |
|----------|---------|
| [04_ipc_and_data_flow.md](04_ipc_and_data_flow.md) | Server-side IPC |
| [05_services_reference.md](05_services_reference.md) | remote-interface details |
| [11_execution_flows.md](11_execution_flows.md) | Remote control flow |
