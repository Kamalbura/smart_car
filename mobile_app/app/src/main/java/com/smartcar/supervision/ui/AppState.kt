package com.smartcar.supervision.ui

import com.smartcar.supervision.data.HealthStatus
import com.smartcar.supervision.data.TelemetrySnapshot

sealed class ConnectionStatus {
    data object Online : ConnectionStatus()
    data object Offline : ConnectionStatus()
    data class Error(val message: String) : ConnectionStatus()
}

data class AppState(
    val connection: ConnectionStatus = ConnectionStatus.Offline,
    val appStatus: AppStatus = AppStatus.OFFLINE,
    val blockingReason: String? = null,
    val status: TelemetrySnapshot? = null,
    val telemetry: TelemetrySnapshot? = null,
    val health: HealthStatus? = null,
    val lastStatusAt: Long? = null,
    val lastTelemetryAt: Long? = null,
    val lastConnectAttemptAt: Long? = null,
    val intentInFlight: Boolean = false,
    val task: TaskState = TaskState(),
    val lastIntentResult: String? = null,
    val lastIntentSent: String? = null,
    val lastIntentAt: Long? = null,
    val lastIntentResultAt: Long? = null,
    val lastUiAction: String? = null,
    val lastUiActionAt: Long? = null,
    val lastUiActionEnabled: Boolean? = null,
    val lastUiActionBlockedReason: String? = null,
    val lastRemoteEvent: String? = null,
    val logs: List<AppLogEntry> = emptyList(),
    val logExportResult: String? = null,
    val backendLogs: Map<BackendLogService, BackendLogSnapshot> = emptyMap(),
    val backendLogsUpdatedAt: Long? = null,
    val logAutoRefresh: Boolean = true,
    val logLinesLimit: Int = 200,
    val debugPanelVisible: Boolean = false,
    val settings: com.smartcar.supervision.data.AppSettings? = null,
)

enum class BackendLogService(val label: String, val apiName: String) {
    APP("App", "app"),
    REMOTE_INTERFACE("Remote Interface", "remote_interface"),
    ORCHESTRATOR("Orchestrator", "orchestrator"),
    UART("UART", "uart"),
    VISION("Vision", "vision"),
    LLM_TTS("LLM / TTS", "llm_tts"),
}

data class BackendLogSnapshot(
    val lines: List<String> = emptyList(),
    val sources: List<String> = emptyList(),
    val error: String? = null,
    val updatedAt: Long? = null,
)

enum class AppStatus {
    OFFLINE,
    CONNECTING,
    ONLINE_IDLE,
    ONLINE_BUSY,
    ONLINE_EXECUTING_TASK,
    ERROR,
}

enum class TaskType {
    NONE,
    SCAN_OBSERVE_STOP,
}

enum class TaskPhase {
    IDLE,
    EXECUTING,
    OBSERVE,
    STOPPED,
}

data class TaskState(
    val type: TaskType = TaskType.NONE,
    val phase: TaskPhase = TaskPhase.IDLE,
    val label: String = "",
)
