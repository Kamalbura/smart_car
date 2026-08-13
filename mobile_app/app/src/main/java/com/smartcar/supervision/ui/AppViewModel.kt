package com.smartcar.supervision.ui

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.smartcar.supervision.BuildConfig
import com.smartcar.supervision.data.AppSettings
import com.smartcar.supervision.data.IntentResult
import com.smartcar.supervision.data.RobotRepository
import com.smartcar.supervision.data.SettingsStore
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File
import android.os.Environment
import java.net.URI
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

class AppViewModel(
    private val repo: RobotRepository = RobotRepository(),
) : ViewModel() {
    private val _state = MutableStateFlow(AppState())
    val state: StateFlow<AppState> = _state.asStateFlow()
    private val logger = AppLogger(1000)
    private var lastTelemetryLogAt: Long = 0L
    private var pollJob: Job? = null
    private var logPollJob: Job? = null
    private var settingsStore: SettingsStore? = null
    private var contextBound = false

    init {
        log(LogCategory.STATE, "app_start")
        _state.value = _state.value.copy(appStatus = AppStatus.CONNECTING)
    }

    fun bindContext(context: Context) {
        if (contextBound) return
        contextBound = true
        val store = SettingsStore(context.applicationContext)
        settingsStore = store
        val (defaultIp, defaultPort) = parseDefaultIpPort()
        val settings = store.loadDefaults(defaultIp, defaultPort)
        _state.value = _state.value.copy(
            settings = settings,
            debugPanelVisible = settings.debugEnabled,
        )
        repo.updateBaseUrl(settings.baseUrl())
        startPolling(settings.pollIntervalMs)
        startLogPolling(settings.pollIntervalMs)
        refreshNow()
        refreshBackendLogs()
        log(LogCategory.STATE, "settings_loaded", data = mapOf("base_url" to settings.baseUrl()))
    }

    fun updateSettings(settings: AppSettings) {
        settingsStore?.save(settings)
        _state.value = _state.value.copy(
            settings = settings,
            debugPanelVisible = settings.debugEnabled,
        )
        repo.updateBaseUrl(settings.baseUrl())
        startPolling(settings.pollIntervalMs)
        startLogPolling(settings.pollIntervalMs)
        refreshNow()
        refreshBackendLogs()
        log(LogCategory.STATE, "settings_updated", data = mapOf("base_url" to settings.baseUrl()))
    }

    fun refreshNow() {
        viewModelScope.launch {
            val now = System.currentTimeMillis()
            _state.value = _state.value.copy(lastConnectAttemptAt = now)

            val snapshotResult = repo.fetchSnapshotOnce()
            snapshotResult.onSuccess { snapshot ->
                val current = _state.value
                val remoteEvent = snapshot.telemetry?.remote_event?.let { it.toString() }
                _state.value = current.copy(
                    connection = ConnectionStatus.Online,
                    status = snapshot.status ?: current.status,
                    telemetry = snapshot.telemetry ?: current.telemetry,
                    lastStatusAt = if (snapshot.status != null) now else current.lastStatusAt,
                    lastTelemetryAt = if (snapshot.telemetry != null) now else current.lastTelemetryAt,
                    lastRemoteEvent = remoteEvent ?: current.lastRemoteEvent,
                )
                log(LogCategory.NETWORK, "refresh_ok")
            }.onFailure { err ->
                _state.value = _state.value.copy(
                    connection = ConnectionStatus.Error(err.message ?: "refresh_error")
                )
                log(LogCategory.NETWORK, "refresh_error", message = err.message ?: "unknown")
            }

            val health = repo.checkHealth()
            health.onSuccess {
                _state.value = _state.value.copy(health = it)
            }.onFailure { err ->
                log(LogCategory.NETWORK, "health_error", message = err.message ?: "unknown")
            }

            refreshAppStatus()
        }
    }

    private fun startPolling(pollMs: Long) {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            repo.snapshotStream(pollMs).collect { result ->
                val now = System.currentTimeMillis()
                _state.value = _state.value.copy(lastConnectAttemptAt = now)
                result.onSuccess { snapshot ->
                    val current = _state.value
                    val remoteEvent = snapshot.telemetry?.remote_event?.let { it.toString() }
                    _state.value = current.copy(
                        connection = ConnectionStatus.Online,
                        status = snapshot.status ?: current.status,
                        telemetry = snapshot.telemetry ?: current.telemetry,
                        lastStatusAt = if (snapshot.status != null) now else current.lastStatusAt,
                        lastTelemetryAt = if (snapshot.telemetry != null) now else current.lastTelemetryAt,
                        lastRemoteEvent = remoteEvent ?: current.lastRemoteEvent,
                    )
                    if (now - lastTelemetryLogAt > 30_000) {
                        log(LogCategory.NETWORK, "telemetry_ok")
                        lastTelemetryLogAt = now
                    }
                    refreshAppStatus()
                }.onFailure { err ->
                    _state.value = _state.value.copy(
                        connection = ConnectionStatus.Error(err.message ?: "telemetry_error")
                    )
                    log(LogCategory.NETWORK, "telemetry_error", message = err.message ?: "unknown")
                    refreshAppStatus()
                }
            }
        }
    }

    private fun startLogPolling(pollMs: Long) {
        logPollJob?.cancel()
        logPollJob = viewModelScope.launch {
            while (isActive) {
                if (_state.value.logAutoRefresh) {
                    fetchBackendLogsOnce()
                }
                delay(pollMs)
            }
        }
    }

    fun setLogAutoRefresh(enabled: Boolean) {
        _state.value = _state.value.copy(logAutoRefresh = enabled)
    }

    fun refreshBackendLogs() {
        viewModelScope.launch {
            fetchBackendLogsOnce()
        }
    }

    private suspend fun fetchBackendLogsOnce() {
        val limit = _state.value.logLinesLimit
        val services = listOf(
            BackendLogService.REMOTE_INTERFACE,
            BackendLogService.ORCHESTRATOR,
            BackendLogService.UART,
            BackendLogService.VISION,
            BackendLogService.LLM_TTS,
        )
        val now = System.currentTimeMillis()
        val snapshots = mutableMapOf<BackendLogService, BackendLogSnapshot>()
        services.forEach { service ->
            val result = repo.fetchLogs(service.apiName, limit)
            result.onSuccess { payload ->
                snapshots[service] = BackendLogSnapshot(
                    lines = payload.lines.orEmpty(),
                    sources = payload.sources.orEmpty(),
                    error = payload.error,
                    updatedAt = payload.ts?.let { it * 1000L } ?: now,
                )
            }.onFailure { err ->
                snapshots[service] = BackendLogSnapshot(
                    lines = emptyList(),
                    sources = emptyList(),
                    error = err.message ?: "log_fetch_error",
                    updatedAt = now,
                )
            }
        }
        val current = _state.value
        _state.value = current.copy(
            backendLogs = current.backendLogs + snapshots,
            backendLogsUpdatedAt = now,
        )
    }

    fun sendIntent(
        intent: String,
        extras: Map<String, Any> = emptyMap(),
        onComplete: ((IntentResult) -> Unit)? = null,
    ) {
        viewModelScope.launch {
            val baseUrl = _state.value.settings?.baseUrl() ?: BuildConfig.ROBOT_BASE_URL
            val payload = mapOf(
                "intent" to intent,
                "direction" to extras["direction"],
                "speed" to extras["speed"],
                "duration_ms" to extras["duration_ms"],
                "extras" to if (extras.isEmpty()) null else extras,
            )
            _state.value = _state.value.copy(intentInFlight = true)
            _state.value = _state.value.copy(lastIntentSent = intent, lastIntentAt = System.currentTimeMillis())
            log(
                LogCategory.INTENT,
                "intent_sent",
                data = mapOf(
                    "intent" to intent,
                    "payload" to payload,
                    "url" to baseUrl.trimEnd('/') + "/intent",
                )
            )
            refreshAppStatus()
            val result = repo.sendIntent(intent, extras)
            val message = when (result) {
                is IntentResult.Accepted -> "accepted"
                is IntentResult.Rejected -> "rejected: ${result.reason}"
                is IntentResult.TimedOut -> "timed_out: ${result.reason}"
                is IntentResult.Failed -> "failed: ${result.reason}"
            }
            _state.value = _state.value.copy(lastIntentResult = message, lastIntentResultAt = System.currentTimeMillis())
            _state.value = _state.value.copy(intentInFlight = false)
            log(
                LogCategory.INTENT,
                "intent_result",
                data = mapOf(
                    "intent" to intent,
                    "result" to message,
                    "payload" to payload,
                )
            )
            refreshAppStatus()
            onComplete?.invoke(result)
        }
    }

    fun startScanObserveTask() {
        _state.value = _state.value.copy(
            task = TaskState(
                type = TaskType.SCAN_OBSERVE_STOP,
                phase = TaskPhase.EXECUTING,
                label = "Scanning",
            )
        )
        log(LogCategory.STATE, "task_start", data = mapOf("task" to "scan_observe_stop"))
        sendIntent("scan") { result ->
            val label = when (result) {
                is IntentResult.Accepted -> "Observe"
                is IntentResult.Rejected -> "Scan rejected"
                is IntentResult.TimedOut -> "Scan timed out"
                is IntentResult.Failed -> "Scan failed"
            }
            val phase = when (result) {
                is IntentResult.Accepted -> TaskPhase.OBSERVE
                else -> TaskPhase.STOPPED
            }
            _state.value = _state.value.copy(
                task = TaskState(
                    type = TaskType.SCAN_OBSERVE_STOP,
                    phase = phase,
                    label = label,
                )
            )
            log(LogCategory.STATE, "task_update", data = mapOf("task" to "scan_observe_stop", "phase" to phase.name))
            refreshAppStatus()
        }
    }

    fun markObservation() {
        val current = _state.value.task
        if (current.type != TaskType.SCAN_OBSERVE_STOP) return
        _state.value = _state.value.copy(
            task = current.copy(
                phase = TaskPhase.OBSERVE,
                label = "Observe",
            )
        )
        log(LogCategory.STATE, "task_mark_observe")
        refreshAppStatus()
    }

    fun stopTask() {
        val current = _state.value.task
        if (current.type == TaskType.NONE) {
            sendIntent("stop")
            return
        }
        _state.value = _state.value.copy(
            task = current.copy(
                phase = TaskPhase.EXECUTING,
                label = "Stopping",
            )
        )
        sendIntent("stop") {
            _state.value = _state.value.copy(
                task = current.copy(
                    phase = TaskPhase.STOPPED,
                    label = "Stopped",
                )
            )
            log(LogCategory.STATE, "task_stop")
            refreshAppStatus()
        }
    }

    fun clearTask() {
        _state.value = _state.value.copy(task = TaskState())
        log(LogCategory.STATE, "task_clear")
        refreshAppStatus()
    }

    fun toggleDebugPanel() {
        val current = _state.value
        val newValue = !current.debugPanelVisible
        _state.value = current.copy(debugPanelVisible = newValue)
        val settings = current.settings
        if (settings != null) {
            val updated = settings.copy(debugEnabled = newValue)
            settingsStore?.save(updated)
            _state.value = _state.value.copy(settings = updated)
        }
    }

    fun logUiAction(action: String, enabled: Boolean, blockedReason: String?) {
        val now = System.currentTimeMillis()
        val current = _state.value
        _state.value = current.copy(
            lastUiAction = action,
            lastUiActionAt = now,
            lastUiActionEnabled = enabled,
            lastUiActionBlockedReason = blockedReason,
        )
        log(
            LogCategory.UI,
            "ui_action",
            data = mapOf(
                "action" to action,
                "enabled" to enabled,
                "blocked_reason" to blockedReason,
                "app_status" to current.appStatus.name,
                "blocking_reason" to current.blockingReason,
            )
        )
    }

    fun clearLogs() {
        _state.value = _state.value.copy(logs = emptyList())
        log(LogCategory.STATE, "log_clear")
    }

    private fun log(
        category: LogCategory,
        event: String,
        message: String? = null,
        data: Map<String, Any?> = emptyMap(),
    ) {
        val snapshot = appStateSnapshot(_state.value)
        val entry = AppLogEntry(
            ts = System.currentTimeMillis(),
            category = category,
            event = event,
            message = message,
            data = data + mapOf(
                "app_state" to snapshot,
                "last_ui_action" to _state.value.lastUiAction,
                "last_intent_sent" to _state.value.lastIntentSent,
                "last_intent_result" to _state.value.lastIntentResult,
            ),
        )
        val updated = logger.append(_state.value.logs, entry)
        _state.value = _state.value.copy(logs = updated)
    }

    private fun appStateSnapshot(state: AppState): Map<String, Any?> {
        val connection = when (state.connection) {
            ConnectionStatus.Online -> "online"
            ConnectionStatus.Offline -> "offline"
            is ConnectionStatus.Error -> "error"
        }
        val sessionActive = (state.telemetry?.remote_session_active == true) ||
            (state.status?.remote_session_active == true)
        return mapOf(
            "connection" to connection,
            "app_status" to state.appStatus.name,
            "blocking_reason" to state.blockingReason,
            "intent_in_flight" to state.intentInFlight,
            "task_phase" to state.task.phase.name,
            "remote_session_active" to sessionActive,
        )
    }

    fun exportLogs(context: Context) {
        val now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"))
        val externalRoot = Environment.getExternalStorageDirectory()
        val logDir = File(externalRoot, "smart_car/logs")
        if (!logDir.exists() && !logDir.mkdirs()) {
            _state.value = _state.value.copy(logExportResult = "error: mkdir_failed ${logDir.absolutePath}")
            log(LogCategory.STATE, "export_failed", message = "mkdir_failed", data = mapOf("path" to logDir.absolutePath))
            return
        }
        val file = File(logDir, "app_logs_${now}.jsonl")
        val content = _state.value.logs.joinToString(separator = "\n") { it.toJsonLine() }
        try {
            file.writeText(content)
            _state.value = _state.value.copy(logExportResult = "saved: ${file.absolutePath}")
            log(LogCategory.STATE, "export_success", data = mapOf("path" to file.absolutePath, "bytes" to file.length()))
        } catch (err: Exception) {
            _state.value = _state.value.copy(logExportResult = "error: ${err.message ?: "unknown"}")
            log(
                LogCategory.STATE,
                "export_failed",
                message = err.message ?: "unknown",
                data = mapOf("path" to file.absolutePath)
            )
        }
    }

    private fun refreshAppStatus() {
        val current = _state.value
        val sessionActive = (current.telemetry?.remote_session_active == true) ||
            (current.status?.remote_session_active == true)
        val busy = current.intentInFlight
        val executingTask = current.task.phase == TaskPhase.EXECUTING

        val status = when (current.connection) {
            ConnectionStatus.Offline -> AppStatus.OFFLINE
            is ConnectionStatus.Error -> AppStatus.ERROR
            ConnectionStatus.Online -> {
                if (!sessionActive) {
                    AppStatus.ERROR
                } else if (executingTask) {
                    AppStatus.ONLINE_EXECUTING_TASK
                } else if (busy) {
                    AppStatus.ONLINE_BUSY
                } else {
                    AppStatus.ONLINE_IDLE
                }
            }
        }

        val blockingReason = when {
            status == AppStatus.OFFLINE -> "offline"
            status == AppStatus.ERROR && !sessionActive -> "no_remote_session"
            status == AppStatus.ERROR -> "error"
            executingTask -> "task_executing"
            busy -> "intent_in_flight"
            else -> null
        }

        val changed = current.appStatus != status || current.blockingReason != blockingReason
        _state.value = current.copy(appStatus = status, blockingReason = blockingReason)
        if (changed) {
            log(
                LogCategory.STATE,
                "app_status_change",
                data = mapOf(
                    "from" to current.appStatus.name,
                    "to" to status.name,
                    "blocking_reason" to blockingReason,
                )
            )
        }
    }

    private fun parseDefaultIpPort(): Pair<String, Int> {
        return try {
            val uri = URI(BuildConfig.ROBOT_BASE_URL)
            val host = uri.host ?: BuildConfig.ROBOT_BASE_URL
                .removePrefix("http://")
                .removePrefix("https://")
                .substringBefore("/")
                .substringBefore(":")
            val port = if (uri.port != -1) uri.port else if (uri.scheme == "https") 443 else 80
            host to port
        } catch (err: Exception) {
            val cleaned = BuildConfig.ROBOT_BASE_URL
                .removePrefix("http://")
                .removePrefix("https://")
            val host = cleaned.substringBefore("/").substringBefore(":")
            val port = cleaned.substringAfter(":", "80").substringBefore("/").toIntOrNull() ?: 80
            host to port
        }
    }
}
