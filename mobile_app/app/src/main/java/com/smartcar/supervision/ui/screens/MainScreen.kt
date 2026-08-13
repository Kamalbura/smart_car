package com.smartcar.supervision.ui.screens

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.view.ViewGroup
import android.widget.ImageView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import com.smartcar.supervision.BuildConfig
import com.smartcar.supervision.data.AppSettings
import com.smartcar.supervision.ui.AppStatus
import com.smartcar.supervision.ui.BackendLogService
import com.smartcar.supervision.ui.AppViewModel
import com.smartcar.supervision.ui.ConnectionStatus
import com.smartcar.supervision.ui.LogCategory
import com.smartcar.supervision.ui.TaskPhase
import com.smartcar.supervision.ui.TaskType
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private enum class MainTab(val label: String) {
    HOME("HOME"),
    CONTROL("CTRL"),
    VISION("VSN"),
    SENSORS("SNS"),
    LOGS("LOGS"),
    SETTINGS("SET"),
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun MainScreen(viewModel: AppViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var selectedTab by rememberSaveable { mutableStateOf(MainTab.HOME) }

    LaunchedEffect(Unit) {
        viewModel.bindContext(context)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("Smart Car Console")
                        Text(
                            "${state.appStatus} • ${connectionLabel(state.connection)} • ${state.blockingReason ?: "ready"}",
                            style = MaterialTheme.typography.labelSmall
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.refreshNow() }) {
                        Icon(imageVector = Icons.Filled.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = selectedTab == MainTab.HOME,
                    onClick = { selectedTab = MainTab.HOME },
                    icon = { Icon(Icons.Filled.Info, contentDescription = null) },
                    label = { Text(MainTab.HOME.label) },
                )
                NavigationBarItem(
                    selected = selectedTab == MainTab.CONTROL,
                    onClick = { selectedTab = MainTab.CONTROL },
                    icon = { Icon(Icons.Filled.Tune, contentDescription = null) },
                    label = { Text(MainTab.CONTROL.label) },
                )
                NavigationBarItem(
                    selected = selectedTab == MainTab.VISION,
                    onClick = { selectedTab = MainTab.VISION },
                    icon = { Icon(Icons.Filled.Visibility, contentDescription = null) },
                    label = { Text(MainTab.VISION.label) },
                )
                NavigationBarItem(
                    selected = selectedTab == MainTab.SENSORS,
                    onClick = { selectedTab = MainTab.SENSORS },
                    icon = { Icon(Icons.Filled.Tune, contentDescription = null) },
                    label = { Text(MainTab.SENSORS.label) },
                )
                NavigationBarItem(
                    selected = selectedTab == MainTab.LOGS,
                    onClick = { selectedTab = MainTab.LOGS },
                    icon = { Icon(Icons.Filled.Info, contentDescription = null) },
                    label = { Text(MainTab.LOGS.label) },
                )
                NavigationBarItem(
                    selected = selectedTab == MainTab.SETTINGS,
                    onClick = { selectedTab = MainTab.SETTINGS },
                    icon = { Icon(Icons.Filled.Settings, contentDescription = null) },
                    label = { Text(MainTab.SETTINGS.label) },
                )
            }
        }
    ) { innerPadding ->
        val contentModifier = Modifier
            .fillMaxSize()
            .padding(innerPadding)

        when (selectedTab) {
            MainTab.HOME -> HomeScreen(
                modifier = contentModifier,
                viewModel = viewModel,
                onOpenSettings = { selectedTab = MainTab.SETTINGS },
            )
            MainTab.CONTROL -> ControlScreen(
                modifier = contentModifier,
                viewModel = viewModel,
                onOpenStatus = { selectedTab = MainTab.HOME },
                onOpenSettings = { selectedTab = MainTab.SETTINGS },
            )
            MainTab.SENSORS -> SensorsScreen(
                modifier = contentModifier,
                viewModel = viewModel,
            )
            MainTab.VISION -> VisionScreen(
                modifier = contentModifier,
                viewModel = viewModel,
                onOpenSettings = { selectedTab = MainTab.SETTINGS },
            )
            MainTab.LOGS -> LogsScreen(
                modifier = contentModifier,
                viewModel = viewModel,
            )
            MainTab.SETTINGS -> SettingsScreen(
                modifier = contentModifier,
                viewModel = viewModel,
            )
        }
    }
}

@Composable
private fun HomeScreen(
    modifier: Modifier,
    viewModel: AppViewModel,
    onOpenSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val now = System.currentTimeMillis()
    val sessionActive = (state.telemetry?.remote_session_active == true) || (state.status?.remote_session_active == true)
    val lastIntentAge = state.lastIntentAt?.let { now - it }
    val commandRecent = lastIntentAge != null && lastIntentAge < 5_000
    val lastIntentLabel = state.lastIntentSent ?: "UNAVAILABLE"
    val motor = state.telemetry?.motor
    val motorActive = motor?.let { it.left != 0 || it.right != 0 } ?: false
    val safety = state.telemetry?.sensor

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Robot Status", style = MaterialTheme.typography.titleLarge)
                val statusLabel = when (state.appStatus) {
                    AppStatus.ONLINE_IDLE -> "READY"
                    AppStatus.ONLINE_BUSY -> "BUSY"
                    AppStatus.ONLINE_EXECUTING_TASK -> "BUSY"
                    AppStatus.ERROR -> "ERROR"
                    AppStatus.OFFLINE, AppStatus.CONNECTING -> "OFFLINE"
                }
                Text(statusLabel, style = MaterialTheme.typography.headlineSmall)
                Text(
                    "Connection: " + when (state.connection) {
                        ConnectionStatus.Online -> "ONLINE"
                        ConnectionStatus.Offline -> "OFFLINE"
                        is ConnectionStatus.Error -> "ERROR"
                    }
                )
                Text("Blocking: ${state.blockingReason ?: "UNAVAILABLE"}")
                Text("Remote session: ${triState(sessionActive)}")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { viewModel.refreshNow() }) { Text("Retry now") }
                    TextButton(onClick = onOpenSettings) { Text("Open settings") }
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("System snapshot", style = MaterialTheme.typography.titleMedium)
                Text("Task: ${state.task.label.ifBlank { "UNAVAILABLE" }}")
                Text("Last command: $lastIntentLabel")
                Text("Last result: ${state.lastIntentResult ?: "UNAVAILABLE"}")
                if (commandRecent) {
                    Text("Command sent @ ${formatTimestamp(state.lastIntentAt)}")
                }
                Text("Motor active: ${triState(motorActive)}")
                Text("Vision mode: ${confidenceLabel(state.telemetry?.vision_mode, state.lastTelemetryAt)}")
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Safety", style = MaterialTheme.typography.titleMedium)
                Text("Is safe: ${confidenceLabel(safety?.is_safe, state.telemetry?.sensor_ts)}")
                Text("Obstacle: ${confidenceLabel(safety?.obstacle, state.telemetry?.sensor_ts)}")
                Text("Warning: ${confidenceLabel(safety?.warning, state.telemetry?.sensor_ts)}")
                Text("Sensor buffer: ${state.telemetry?.sensor_buffer ?: "UNAVAILABLE"}")
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Quick indicators", style = MaterialTheme.typography.titleMedium)
                val llm = state.telemetry?.last_llm_response ?: "UNAVAILABLE"
                val tts = state.telemetry?.last_tts_text ?: "UNAVAILABLE"
                val ttsStatus = state.telemetry?.last_tts_status ?: "UNAVAILABLE"
                val det = state.telemetry?.vision_last_detection
                Text("Last LLM response: ${confidenceLabel(llm, state.telemetry?.last_llm_ts)}")
                Text("Last TTS: ${confidenceLabel(tts, state.telemetry?.last_tts_ts)}")
                Text("TTS status: $ttsStatus")
                if (det == null) {
                    Text("Last detection: UNAVAILABLE")
                } else {
                    Text("Last detection: ${det.label ?: "UNAVAILABLE"} conf=${det.confidence ?: "?"}")
                }
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }
}

@Composable
private fun ControlScreen(
    modifier: Modifier,
    viewModel: AppViewModel,
    onOpenStatus: () -> Unit,
    onOpenSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val intentsEnabled = state.appStatus == AppStatus.ONLINE_IDLE
    val sessionActive = (state.telemetry?.remote_session_active == true) || (state.status?.remote_session_active == true)
    val stopEnabled = sessionActive
    val lastIntentAge = state.lastIntentAt?.let { System.currentTimeMillis() - it }
    val commandRecent = lastIntentAge != null && lastIntentAge < 5_000
    val lastIntentLabel = state.lastIntentSent ?: "UNAVAILABLE"
    val hasFailure = state.connection is ConnectionStatus.Error || !sessionActive ||
        state.lastIntentResult?.startsWith("rejected") == true ||
        state.lastIntentResult?.startsWith("timed_out") == true ||
        state.lastIntentResult?.startsWith("failed") == true
    var confirmScan by rememberSaveable { mutableStateOf(false) }
    var confirmStop by rememberSaveable { mutableStateOf(false) }
    var confirmStartForward by rememberSaveable { mutableStateOf(false) }
    var actionBlockedReason by rememberSaveable { mutableStateOf<String?>(null) }
    var customMessage by rememberSaveable { mutableStateOf("") }

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        if (!intentsEnabled || !sessionActive) {
            Card {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Control offline", style = MaterialTheme.typography.titleMedium)
                    Text("Reason: ${state.blockingReason ?: "session inactive"}")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = onOpenStatus) { Text("View status") }
                        TextButton(onClick = onOpenSettings) { Text("Open settings") }
                    }
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Task Flow", style = MaterialTheme.typography.titleMedium)
                Text("Task: ${state.task.type}")
                Text("Phase: ${state.task.phase}")
                Text("Status: ${state.task.label}")
                Text("Blocking: ${state.blockingReason ?: "none"}")
                Button(
                    onClick = {
                        val blocked = if (intentsEnabled) null else state.blockingReason ?: "invalid_state"
                        viewModel.logUiAction("start_scan_observe_stop", intentsEnabled, blocked)
                        if (intentsEnabled) {
                            confirmScan = true
                        } else {
                            actionBlockedReason = state.blockingReason ?: "invalid_state"
                        }
                    },
                    enabled = intentsEnabled
                ) {
                    Text("Start scan → observe → stop")
                }
                Button(
                    onClick = {
                        val allowed = intentsEnabled && state.task.phase == TaskPhase.OBSERVE
                        val blocked = if (allowed) null else state.blockingReason ?: "invalid_state"
                        viewModel.logUiAction("mark_observe", allowed, blocked)
                        if (intentsEnabled && state.task.phase == TaskPhase.OBSERVE) {
                            viewModel.markObservation()
                        } else {
                            actionBlockedReason = state.blockingReason ?: "invalid_state"
                        }
                    },
                    enabled = intentsEnabled && state.task.phase == TaskPhase.OBSERVE
                ) {
                    Text("Mark observe")
                }
                Button(
                    onClick = {
                        val allowed = stopEnabled && state.task.type != TaskType.NONE
                        val blocked = if (allowed) null else state.blockingReason ?: "invalid_state"
                        viewModel.logUiAction("stop_task", allowed, blocked)
                        if (stopEnabled && state.task.type != TaskType.NONE) {
                            confirmStop = true
                        } else {
                            actionBlockedReason = state.blockingReason ?: "invalid_state"
                        }
                    },
                    enabled = stopEnabled && state.task.type != TaskType.NONE
                ) {
                    Text("Stop task")
                }
                Button(
                    onClick = {
                        val allowed = !state.intentInFlight && state.task.type != TaskType.NONE
                        val blocked = if (allowed) null else state.blockingReason ?: "invalid_state"
                        viewModel.logUiAction("clear_task", allowed, blocked)
                        if (!state.intentInFlight && state.task.type != TaskType.NONE) {
                            viewModel.clearTask()
                        } else {
                            actionBlockedReason = state.blockingReason ?: "invalid_state"
                        }
                    },
                    enabled = !state.intentInFlight && state.task.type != TaskType.NONE
                ) {
                    Text("Clear task")
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Motion Control", style = MaterialTheme.typography.titleMedium)
                Text("Controls require an active remote session")
                Button(
                    onClick = {
                        viewModel.logUiAction("stop", stopEnabled, if (stopEnabled) null else state.blockingReason)
                        if (stopEnabled) {
                            confirmStop = true
                        } else {
                            actionBlockedReason = state.blockingReason ?: "invalid_state"
                        }
                    },
                    enabled = stopEnabled,
                    modifier = Modifier.fillMaxWidth().height(56.dp),
                    colors = androidx.compose.material3.ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error,
                        contentColor = MaterialTheme.colorScheme.onError,
                    )
                ) { Text("STOP") }

                Row(modifier = Modifier.fillMaxSize(), horizontalArrangement = Arrangement.Center) {
                    Button(
                        onClick = {
                            viewModel.logUiAction("start_forward", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                            if (intentsEnabled) {
                                confirmStartForward = true
                            } else {
                                actionBlockedReason = state.blockingReason ?: "invalid_state"
                            }
                        },
                        enabled = intentsEnabled,
                    ) {
                        Text("Forward")
                    }
                }
                Row(horizontalArrangement = Arrangement.SpaceBetween) {
                    Button(
                        onClick = {
                            viewModel.logUiAction("rotate_left", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                            viewModel.sendIntent("rotate_left")
                        },
                        enabled = intentsEnabled,
                    ) { Text("Left") }
                    Button(
                        onClick = {
                            viewModel.logUiAction("rotate_right", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                            viewModel.sendIntent("rotate_right")
                        },
                        enabled = intentsEnabled,
                    ) { Text("Right") }
                }
                Row(modifier = Modifier.fillMaxSize(), horizontalArrangement = Arrangement.Center) {
                    Button(
                        onClick = {
                            viewModel.logUiAction("move_backward", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                            viewModel.sendIntent("move_backward")
                        },
                        enabled = intentsEnabled,
                    ) { Text("Backward") }
                }
                Row(modifier = Modifier.fillMaxSize(), horizontalArrangement = Arrangement.Center) {
                    Button(
                        onClick = {
                            viewModel.logUiAction("scan", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                            if (intentsEnabled) {
                                confirmScan = true
                            } else {
                                actionBlockedReason = state.blockingReason ?: "invalid_state"
                            }
                        },
                        enabled = intentsEnabled,
                    ) { Text("Scan") }
                }

                if (!intentsEnabled) {
                    Text("Controls disabled: ${state.blockingReason ?: "invalid_state"}")
                }
                if (!stopEnabled) {
                    Text("Stop disabled: ${state.blockingReason ?: "invalid_state"}")
                }
                if (commandRecent) {
                    Text("Command sent: $lastIntentLabel @ ${formatTimestamp(state.lastIntentAt)}")
                } else {
                    Text("Last command: $lastIntentLabel")
                    Text("Last result: ${state.lastIntentResult ?: "UNAVAILABLE"}")
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Assistant Control", style = MaterialTheme.typography.titleMedium)
                Button(onClick = {
                    viewModel.logUiAction("invoke_assistant", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                    viewModel.sendIntent("invoke_assistant")
                }, enabled = intentsEnabled) {
                    Text("Invoke Assistant")
                }
                OutlinedTextField(
                    value = customMessage,
                    onValueChange = { customMessage = it },
                    label = { Text("Custom message") },
                    singleLine = false,
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(onClick = {
                    viewModel.logUiAction("assistant_text", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                    viewModel.sendIntent("assistant_text", mapOf("text" to customMessage.trim()))
                    customMessage = ""
                }, enabled = intentsEnabled && customMessage.isNotBlank()) {
                    Text("Send to Assistant")
                }
            }
        }

        if (hasFailure) {
            Card {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Failure surface", style = MaterialTheme.typography.titleMedium)
                    if (state.connection is ConnectionStatus.Error) {
                        Text("Network failure: ${(state.connection as ConnectionStatus.Error).message}")
                    }
                    if (!sessionActive) {
                        Text("Session loss: remote session inactive")
                    }
                    if (state.lastIntentResult?.startsWith("rejected") == true) {
                        Text("Intent rejected: ${state.lastIntentResult}")
                    }
                    if (state.lastIntentResult?.startsWith("timed_out") == true) {
                        Text("Intent timeout: ${state.lastIntentResult}")
                    }
                    if (state.lastIntentResult?.startsWith("failed") == true) {
                        Text("Intent failure: ${state.lastIntentResult}")
                    }
                }
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }

    if (actionBlockedReason != null) {
        AlertDialog(
            onDismissRequest = { actionBlockedReason = null },
            title = { Text("Action blocked") },
            text = { Text("Reason: ${actionBlockedReason}") },
            confirmButton = {
                TextButton(onClick = { actionBlockedReason = null }) { Text("OK") }
            }
        )
    }

    if (confirmScan) {
        AlertDialog(
            onDismissRequest = { confirmScan = false },
            title = { Text("Confirm scan") },
            text = { Text("Send scan intent to the robot?") },
            confirmButton = {
                Button(onClick = {
                    confirmScan = false
                    viewModel.logUiAction("confirm_scan", true, null)
                    viewModel.startScanObserveTask()
                }) { Text("Confirm") }
            },
            dismissButton = {
                TextButton(onClick = { confirmScan = false }) { Text("Cancel") }
            }
        )
    }

    if (confirmStop) {
        AlertDialog(
            onDismissRequest = { confirmStop = false },
            title = { Text("Confirm stop") },
            text = { Text("Send stop intent to the robot?") },
            confirmButton = {
                Button(onClick = {
                    confirmStop = false
                    viewModel.logUiAction("confirm_stop", true, null)
                    viewModel.stopTask()
                }) { Text("Confirm") }
            },
            dismissButton = {
                TextButton(onClick = { confirmStop = false }) { Text("Cancel") }
            }
        )
    }

    if (confirmStartForward) {
        AlertDialog(
            onDismissRequest = { confirmStartForward = false },
            title = { Text("Confirm forward") },
            text = { Text("Send start forward intent to the robot?") },
            confirmButton = {
                Button(onClick = {
                    confirmStartForward = false
                    viewModel.logUiAction("confirm_start_forward", true, null)
                    viewModel.sendIntent("start")
                }) { Text("Confirm") }
            },
            dismissButton = {
                TextButton(onClick = { confirmStartForward = false }) { Text("Cancel") }
            }
        )
    }
}

@Composable
private fun VisionScreen(
    modifier: Modifier,
    viewModel: AppViewModel,
    onOpenSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val sessionActive = (state.telemetry?.remote_session_active == true) || (state.status?.remote_session_active == true)
    val intentsEnabled = state.appStatus == AppStatus.ONLINE_IDLE && sessionActive
    val streamUrl = resolveStreamUrl(state.telemetry?.stream_url ?: state.status?.stream_url, state.settings)
    val visionMode = state.telemetry?.vision_mode ?: state.status?.vision_mode
    val visionModeLabel = when (visionMode) {
        "off" -> "OFF"
        "on" -> "ON_NO_STREAM"
        "on_with_stream" -> "ON_WITH_STREAM"
        null -> "UNKNOWN"
        else -> visionMode.uppercase()
    }
    val canStream = intentsEnabled && visionMode == "on_with_stream" && streamUrl.isNotBlank()
    var isStreaming by rememberSaveable { mutableStateOf(false) }
    var streamError by rememberSaveable { mutableStateOf<String?>(null) }
    var overlayEnabled by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(canStream) {
        if (!canStream) {
            isStreaming = false
        }
    }

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        if (!intentsEnabled) {
            Card {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Vision offline", style = MaterialTheme.typography.titleMedium)
                    Text("Reason: ${state.blockingReason ?: "session inactive"}")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = onOpenSettings) { Text("Open settings") }
                    }
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Vision mode: $visionModeLabel", style = MaterialTheme.typography.titleMedium)
                Text("Stream URL: ${if (streamUrl.isBlank()) "missing" else "available"}")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        viewModel.logUiAction("enable_vision", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                        viewModel.sendIntent("enable_vision")
                    }, enabled = intentsEnabled) { Text("Vision ON") }
                    Button(onClick = {
                        viewModel.logUiAction("disable_vision", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                        viewModel.sendIntent("disable_vision")
                    }, enabled = intentsEnabled) { Text("Vision OFF") }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        viewModel.logUiAction("enable_stream", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                        viewModel.sendIntent("enable_stream")
                    }, enabled = intentsEnabled) { Text("Stream ON") }
                    Button(onClick = {
                        viewModel.logUiAction("disable_stream", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                        viewModel.sendIntent("disable_stream")
                    }, enabled = intentsEnabled) { Text("Stream OFF") }
                }

                HorizontalDivider()
                Text("Streaming", style = MaterialTheme.typography.titleMedium)
                if (streamUrl.isBlank()) {
                    Text("No stream URL provided by backend")
                    Text("Streaming disabled: stream URL missing")
                } else if (!intentsEnabled) {
                    Text("Streaming disabled: ${state.blockingReason ?: "invalid_state"}")
                } else if (visionMode != "on_with_stream") {
                    Text("Streaming disabled: vision mode is not on_with_stream")
                    Text("Enable streaming via intent first")
                } else {
                    if (streamError != null) {
                        Text("Stream error: ${streamError}")
                    }
                    if (!isStreaming) {
                        Button(onClick = {
                            streamError = null
                            isStreaming = true
                            viewModel.logUiAction("vision_stream_start", canStream, if (canStream) null else state.blockingReason)
                        }, enabled = canStream) {
                            Text("Start stream")
                        }
                    } else {
                        Button(onClick = {
                            isStreaming = false
                            viewModel.logUiAction("vision_stream_stop", true, null)
                        }) { Text("Stop stream") }
                        MjpegStreamingView(
                            url = streamUrl,
                            onError = { msg ->
                                streamError = msg
                                isStreaming = false
                                viewModel.logUiAction("vision_stream_error", false, msg)
                            },
                            onStop = { isStreaming = false },
                        )
                    }
                }

                HorizontalDivider()
                Text("Vision metadata overlay", style = MaterialTheme.typography.titleMedium)
                Button(onClick = { overlayEnabled = !overlayEnabled }) {
                    Text(if (overlayEnabled) "Disable overlay" else "Enable overlay")
                }

                if (overlayEnabled) {
                    val det = state.telemetry?.vision_last_detection
                    if (det == null) {
                        Text("No detection available")
                    } else {
                        Text("Latest detection", style = MaterialTheme.typography.titleMedium)
                        Text("Label: ${confidenceLabel(det.label, state.lastTelemetryAt)}")
                        Text("Confidence: ${confidenceLabel(det.confidence, state.lastTelemetryAt)}")
                        Text("BBox: ${confidenceLabel(det.bbox?.joinToString(prefix = "[", postfix = "]"), state.lastTelemetryAt)}")
                        Text("Timestamp: ${confidenceLabel(det.ts, state.lastTelemetryAt)}")
                    }
                } else {
                    Text("Overlay is off")
                }

                HorizontalDivider()
                Text("Capture", style = MaterialTheme.typography.titleMedium)
                Button(
                    onClick = {
                        viewModel.logUiAction("capture_frame", intentsEnabled, if (intentsEnabled) null else state.blockingReason)
                        viewModel.sendIntent("capture_frame")
                    },
                    enabled = intentsEnabled
                ) {
                    Text("Capture frame")
                }
                if (state.lastIntentSent == "capture_frame") {
                    Text("Capture status: ${state.lastIntentResult ?: "pending"}")
                    Text("Capture ts: ${formatTimestamp(state.lastIntentAt)}")
                }

                HorizontalDivider()
                Text("Detection history", style = MaterialTheme.typography.titleMedium)
                val history = state.telemetry?.detection_history.orEmpty()
                if (history.isEmpty()) {
                    Text("No detections yet")
                } else {
                    val recent = history.takeLast(10).reversed()
                    recent.forEachIndexed { index, item ->
                        val style = if (index == 0) MaterialTheme.typography.titleSmall else MaterialTheme.typography.bodySmall
                        Text(
                            "${item.label ?: "unknown"} " +
                                "conf=${item.confidence ?: "?"} " +
                                "bbox=${item.bbox?.joinToString(prefix = "[", postfix = "]") ?: "[]"}",
                            style = style,
                        )
                    }
                }
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }
}

@Composable
private fun SensorsScreen(
    modifier: Modifier,
    viewModel: AppViewModel,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val sessionActive = (state.telemetry?.remote_session_active == true) || (state.status?.remote_session_active == true)

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Robot state", style = MaterialTheme.typography.titleMedium)
                Text("Session: ${triState(sessionActive)}")
                Text("Status mode: ${confidenceLabel(state.status?.mode, state.lastStatusAt)}")
                Text("Status display: ${confidenceLabel(state.status?.display_text, state.lastStatusAt)}")
                Text("Telemetry mode: ${confidenceLabel(state.telemetry?.mode, state.lastTelemetryAt)}")
                Text("Telemetry display: ${confidenceLabel(state.telemetry?.display_text, state.lastTelemetryAt)}")
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Sensor health", style = MaterialTheme.typography.titleMedium)
                Text("Sensor timestamp: ${confidenceLabel(state.telemetry?.sensor_ts, state.lastTelemetryAt)}")
                Text("Buffer size: ${state.telemetry?.sensor_buffer ?: "unknown"}")
                Text("Safety stop: ${confidenceLabel(state.telemetry?.safety_stop, state.lastTelemetryAt)}")
                Text("Blocking: ${state.blockingReason ?: "none"}")
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Motor feedback", style = MaterialTheme.typography.titleMedium)
                val motor = state.telemetry?.motor
                Text("Motor enabled: ${confidenceLabel(state.telemetry?.motor_enabled, state.lastTelemetryAt)}")
                Text("Left motor: ${confidenceLabel(motor?.left, state.lastTelemetryAt)}")
                Text("Right motor: ${confidenceLabel(motor?.right, state.lastTelemetryAt)}")
                Text("Intent busy: ${triState(state.intentInFlight)}")
                Text("Last intent: ${state.lastIntentSent ?: "unknown"}")
                Text("Last intent result: ${state.lastIntentResult ?: "unknown"}")
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Sensor values", style = MaterialTheme.typography.titleMedium)
                val sensor = state.telemetry?.sensor
                Text("Is safe: ${confidenceLabel(sensor?.is_safe, state.telemetry?.sensor_ts)}")
                Text("Obstacle: ${confidenceLabel(sensor?.obstacle, state.telemetry?.sensor_ts)}")
                Text("Warning: ${confidenceLabel(sensor?.warning, state.telemetry?.sensor_ts)}")
                Text("Raw telemetry: ${state.telemetry?.toString() ?: "telemetry_missing"}")
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }
}

@Composable
private fun LogsScreen(
    modifier: Modifier,
    viewModel: AppViewModel,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var showUi by rememberSaveable { mutableStateOf(true) }
    var showNetwork by rememberSaveable { mutableStateOf(true) }
    var showIntent by rememberSaveable { mutableStateOf(true) }
    var showState by rememberSaveable { mutableStateOf(true) }
    val backendServices = listOf(
        BackendLogService.APP,
        BackendLogService.REMOTE_INTERFACE,
        BackendLogService.ORCHESTRATOR,
        BackendLogService.UART,
        BackendLogService.VISION,
        BackendLogService.LLM_TTS,
    )
    var selectedServices by remember {
        mutableStateOf(backendServices.associateWith { true })
    }
    val scrollState = rememberScrollState()

    val filtered = state.logs.filter { entry ->
        when (entry.category) {
            LogCategory.UI -> showUi
            LogCategory.NETWORK -> showNetwork
            LogCategory.INTENT -> showIntent
            LogCategory.STATE -> showState
        }
    }

    val lastCritical = filtered.lastOrNull { entry ->
        when (entry.category) {
            LogCategory.INTENT -> {
                val result = entry.data["result"]?.toString() ?: ""
                result.contains("rejected") || result.contains("failed") || result.contains("timed_out")
            }
            LogCategory.NETWORK -> entry.event.contains("error")
            LogCategory.STATE -> entry.event.contains("error")
            LogCategory.UI -> false
        }
    }

    val byCategory = filtered.groupBy { it.category }

    LaunchedEffect(filtered.size) {
        scrollState.animateScrollTo(scrollState.maxValue)
    }

    Column(
        modifier = modifier
            .verticalScroll(scrollState)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Backend logs", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Auto refresh")
                    Switch(
                        checked = state.logAutoRefresh,
                        onCheckedChange = { viewModel.setLogAutoRefresh(it) }
                    )
                    Text("Lines: ${state.logLinesLimit}")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { viewModel.refreshBackendLogs() }) { Text("Refresh now") }
                    Text("Updated: ${formatTimestamp(state.backendLogsUpdatedAt)}")
                }
                backendServices.forEach { service ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(service.label)
                        Switch(
                            checked = selectedServices[service] == true,
                            onCheckedChange = { enabled ->
                                selectedServices = selectedServices.toMutableMap().also { it[service] = enabled }
                            }
                        )
                    }
                }
            }
        }

        backendServices.filter { selectedServices[it] == true }.forEach { service ->
            val snapshot = state.backendLogs[service]
            val appLogLines = filtered.takeLast(200).map { it.toDisplayLine() }
            Card {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(service.label, style = MaterialTheme.typography.titleMedium)
                    if (service == BackendLogService.APP) {
                        if (appLogLines.isEmpty()) {
                            Text("No app logs")
                        } else {
                            appLogLines.forEach { line ->
                                Text(line, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    } else if (snapshot == null) {
                        Text("No data yet")
                    } else {
                        if (!snapshot.error.isNullOrBlank()) {
                            Text("Error: ${snapshot.error}")
                        }
                        if (snapshot.lines.isEmpty()) {
                            Text("No log lines")
                        } else {
                            snapshot.lines.takeLast(200).forEach { line ->
                                Text(line, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Log controls", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("UI (button actions)")
                    Switch(checked = showUi, onCheckedChange = { showUi = it })
                    Text("Network (HTTP)")
                    Switch(checked = showNetwork, onCheckedChange = { showNetwork = it })
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Intent (sent/result)")
                    Switch(checked = showIntent, onCheckedChange = { showIntent = it })
                    Text("State (app)")
                    Switch(checked = showState, onCheckedChange = { showState = it })
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { viewModel.exportLogs(context) }) {
                        Text("Export JSONL")
                    }
                    TextButton(onClick = { viewModel.clearLogs() }) {
                        Text("Clear logs")
                    }
                }
                Text("Log export: ${state.logExportResult ?: "not exported"}")
            }
        }

        if (lastCritical != null) {
            Card {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Last critical log", style = MaterialTheme.typography.titleMedium)
                    Text(lastCritical.toDisplayLine())
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Logs", style = MaterialTheme.typography.titleMedium)
                Text("Showing ${filtered.size} of ${state.logs.size}")
                if (filtered.isEmpty()) {
                    Text("No logs match current filters")
                } else {
                    val order = listOf(LogCategory.INTENT, LogCategory.UI, LogCategory.NETWORK, LogCategory.STATE)
                    order.forEach { category ->
                        val entries = byCategory[category].orEmpty()
                        if (entries.isNotEmpty()) {
                            Text(category.name, style = MaterialTheme.typography.titleSmall)
                            entries.takeLast(100).forEach { entry ->
                                val style = if (entry.category == LogCategory.INTENT) {
                                    MaterialTheme.typography.bodyMedium
                                } else {
                                    MaterialTheme.typography.bodySmall
                                }
                                Text(entry.toDisplayLine(), maxLines = 3, overflow = TextOverflow.Ellipsis, style = style)
                            }
                        }
                    }
                }
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }
}

@Composable
private fun SettingsScreen(
    modifier: Modifier,
    viewModel: AppViewModel,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var ip by rememberSaveable { mutableStateOf(state.settings?.robotIp ?: "") }
    var port by rememberSaveable { mutableStateOf(state.settings?.robotPort?.toString() ?: "") }
    var pollMs by rememberSaveable { mutableStateOf(state.settings?.pollIntervalMs?.toString() ?: "1000") }
    var debugEnabled by rememberSaveable { mutableStateOf(state.settings?.debugEnabled ?: false) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var showDiagnostics by rememberSaveable { mutableStateOf(false) }
    var showLimitations by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(state.settings) {
        val settings = state.settings
        if (settings != null) {
            ip = settings.robotIp
            port = settings.robotPort.toString()
            pollMs = settings.pollIntervalMs.toString()
            debugEnabled = settings.debugEnabled
        }
    }

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Connection", style = MaterialTheme.typography.titleMedium)
                Text("Base URL (read-only): ${state.settings?.baseUrl() ?: BuildConfig.ROBOT_BASE_URL}")
                OutlinedTextField(
                    value = ip,
                    onValueChange = { ip = it.trim() },
                    label = { Text("Robot IP") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = port,
                    onValueChange = { port = it.trim() },
                    label = { Text("Port") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = pollMs,
                    onValueChange = { pollMs = it.trim() },
                    label = { Text("Poll interval (ms)") },
                    singleLine = true,
                )
                if (errorMessage != null) {
                    Text(errorMessage!!, color = MaterialTheme.colorScheme.error)
                }
                Button(onClick = {
                    val parsedPort = port.toIntOrNull()
                    val parsedPoll = pollMs.toLongOrNull()
                    val ipValue = ip.trim()
                    errorMessage = when {
                        ipValue.isBlank() -> "IP address is required"
                        parsedPort == null || parsedPort <= 0 -> "Port must be a positive integer"
                        parsedPoll == null || parsedPoll < 250L -> "Poll interval must be at least 250ms"
                        else -> null
                    }
                    if (errorMessage == null) {
                        viewModel.updateSettings(
                            AppSettings(
                                robotIp = ipValue,
                                robotPort = parsedPort!!,
                                pollIntervalMs = parsedPoll!!,
                                debugEnabled = debugEnabled,
                            )
                        )
                    }
                }) {
                    Text("Apply settings")
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Diagnostics", style = MaterialTheme.typography.titleMedium)
                Text("App version: ${BuildConfig.VERSION_NAME}")
                Text("Log export: ${state.logExportResult ?: "not exported"}")
                Button(onClick = { viewModel.exportLogs(context) }) {
                    Text("Export logs")
                }
                TextButton(onClick = { showDiagnostics = !showDiagnostics }) {
                    Text(if (showDiagnostics) "Hide runtime details" else "Show runtime details")
                }
                if (showDiagnostics) {
                    Text("Robot base URL: ${state.settings?.baseUrl() ?: BuildConfig.ROBOT_BASE_URL}")
                    Text("Last status: ${formatTimestamp(state.lastStatusAt)}")
                    Text("Last telemetry: ${formatTimestamp(state.lastTelemetryAt)}")
                    Text("Last intent: ${state.lastIntentSent ?: "unknown"}")
                    Text("Last intent result: ${state.lastIntentResult ?: "unknown"}")
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                TextButton(onClick = { showLimitations = !showLimitations }) {
                    Text(if (showLimitations) "Hide known limitations" else "Show known limitations")
                }
                if (showLimitations) {
                    Text("Known limitations", style = MaterialTheme.typography.titleMedium)
                    Text("- No auto-retry for intents")
                    Text("- Telemetry may be stale or missing fields")
                    Text("- Streaming depends on backend-provided URL and format")
                }
            }
        }

        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Advanced", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Debug panel")
                    Switch(checked = debugEnabled, onCheckedChange = { debugEnabled = it })
                }
                Text(
                    "Enables extra diagnostics on app screens.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }
}

@Composable
private fun MjpegStreamingView(
    url: String,
    onError: (String) -> Unit,
    onStop: () -> Unit,
) {
    val context = LocalContext.current
    val client = remember { OkHttpClient.Builder().build() }
    var latestBitmap by remember { mutableStateOf<Bitmap?>(null) }
    val scope = rememberCoroutineScope()

    DisposableEffect(url) {
        val job = scope.launch(Dispatchers.IO) {
            try {
                val request = Request.Builder().url(url).build()
                val response = client.newCall(request).execute()
                if (!response.isSuccessful) {
                    withContext(Dispatchers.Main) { onError("http_${response.code}") }
                    response.close()
                    return@launch
                }
                val contentType = response.header("Content-Type")
                val boundary = parseBoundary(contentType)
                val body = response.body ?: run {
                    withContext(Dispatchers.Main) { onError("empty_body") }
                    response.close()
                    return@launch
                }
                val source = body.source()
                while (isActive) {
                    val line = source.readUtf8Line() ?: break
                    if (!line.startsWith(boundary)) {
                        continue
                    }
                    var contentLength = -1
                    while (true) {
                        val header = source.readUtf8Line() ?: break
                        if (header.isBlank()) break
                        val parts = header.split(":", limit = 2)
                        if (parts.size == 2 && parts[0].trim().equals("Content-Length", true)) {
                            contentLength = parts[1].trim().toIntOrNull() ?: -1
                        }
                    }
                    if (contentLength <= 0) {
                        continue
                    }
                    val bytes = source.readByteArray(contentLength.toLong())
                    val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                    if (bitmap != null) {
                        withContext(Dispatchers.Main) { latestBitmap = bitmap }
                    }
                    source.readUtf8Line()
                }
                response.close()
            } catch (err: CancellationException) {
                // Ignore cancellation
            } catch (err: Exception) {
                withContext(Dispatchers.Main) { onError(err.message ?: "stream_error") }
            }
        }

        onDispose {
            job.cancel()
            onStop()
        }
    }

    AndroidView(
        factory = {
            val view = ImageView(context)
            view.layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
            view.adjustViewBounds = true
            view
        },
        update = { view ->
            view.setImageBitmap(latestBitmap)
        },
        modifier = Modifier.padding(top = 8.dp)
    )
}

private fun triState(value: Boolean?): String = when (value) {
    null -> "UNAVAILABLE"
    true -> "true"
    false -> "false"
}

private fun connectionLabel(status: ConnectionStatus): String = when (status) {
    ConnectionStatus.Online -> "ONLINE"
    ConnectionStatus.Offline -> "OFFLINE"
    is ConnectionStatus.Error -> "ERROR"
}

private fun confidenceLabel(value: Any?, lastTs: Long?): String {
    val now = System.currentTimeMillis()
    val freshness = if (lastTs == null) "UNAVAILABLE" else if (now - lastTs > 5_000) "STALE" else "LIVE"
    val v = value?.toString() ?: "UNAVAILABLE"
    return "$v ($freshness)"
}

private fun resolveStreamUrl(raw: String?, settings: AppSettings?): String {
    val value = raw?.trim().orEmpty()
    if (value.isBlank()) return ""
    if (value.startsWith("http://") || value.startsWith("https://")) return value
    val base = settings?.baseUrl() ?: BuildConfig.ROBOT_BASE_URL
    return base.trimEnd('/') + "/" + value.trimStart('/')
}

private fun parseBoundary(contentType: String?): String {
    if (contentType.isNullOrBlank()) return "--frame"
    val boundary = contentType.split(";")
        .map { it.trim() }
        .firstOrNull { it.startsWith("boundary=") }
        ?.substringAfter("boundary=")
        ?.trim('"')
        ?: "frame"
    return if (boundary.startsWith("--")) boundary else "--$boundary"
}

private fun formatTimestamp(ts: Long?): String {
    if (ts == null) return "UNAVAILABLE"
    val formatter = DateTimeFormatter.ofPattern("HH:mm:ss")
    return Instant.ofEpochMilli(ts).atZone(ZoneId.systemDefault()).format(formatter)
}
