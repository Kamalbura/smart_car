package com.smartcar.supervision.data

import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class TelemetrySnapshot(
    val remote_session_active: Boolean? = null,
    val remote_last_seen: Long? = null,
    val mode: String? = null,
    val display_text: String? = null,
    val vision_mode: String? = null,
    val stream_url: String? = null,
    val vision_active: Boolean? = null,
    val vision_paused: Boolean? = null,
    val motor_enabled: Boolean? = null,
    val motor: MotorState? = null,
    val safety_stop: Boolean? = null,
    val safety_alert: String? = null,
    val sensor: SensorData? = null,
    val sensor_ts: Long? = null,
    val sensor_buffer: List<SensorData>? = null,
    val vision_last_detection: VisionDetection? = null,
    val detection_history: List<VisionDetection>? = null,
    val last_llm_response: String? = null,
    val last_llm_ts: Long? = null,
    val last_tts_text: String? = null,
    val last_tts_status: String? = null,
    val last_tts_ts: Long? = null,
    val health: HealthStatus? = null,
    val remote_event: RemoteEvent? = null,
)

@JsonClass(generateAdapter = true)
data class SensorData(
    val s1: Int? = null,
    val s2: Int? = null,
    val s3: Int? = null,
    val mq2: Int? = null,
    val lmotor: Int? = null,
    val rmotor: Int? = null,
    val min_distance: Int? = null,
    val obstacle: Boolean? = null,
    val warning: Boolean? = null,
    val is_safe: Boolean? = null,
)

@JsonClass(generateAdapter = true)
data class MotorState(
    val left: Int? = null,
    val right: Int? = null,
    val ts: Long? = null,
)

@JsonClass(generateAdapter = true)
data class VisionDetection(
    val label: String? = null,
    val bbox: List<Int>? = null,
    val confidence: Double? = null,
    val ts: Double? = null,
    val request_id: String? = null,
)

@JsonClass(generateAdapter = true)
data class HealthStatus(
    val ok: Boolean? = null,
    val timestamp: Long? = null,
)

@JsonClass(generateAdapter = true)
data class RemoteEvent(
    val event: String? = null,
    val reason: String? = null,
    val intent: String? = null,
    val direction: String? = null,
    val timestamp: Long? = null,
)

@JsonClass(generateAdapter = true)
data class LogLinesResponse(
    val service: String? = null,
    val lines: List<String>? = null,
    val sources: List<String>? = null,
    val ts: Long? = null,
    val error: String? = null,
)
