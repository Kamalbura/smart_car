package com.smartcar.supervision.data

data class IntentRequest(
    val intent: String,
    val direction: String? = null,
    val speed: Int? = null,
    val duration_ms: Int? = null,
    val extras: Map<String, Any>? = null,
)

data class IntentResponse(
    val ok: Boolean? = null,
    val message: String? = null,
    val data: Map<String, Any>? = null,
)

fun IntentResponse.toMap(): Map<String, Any> {
    val payload = mutableMapOf<String, Any>()
    if (ok != null) payload["ok"] = ok
    if (message != null) payload["message"] = message
    if (data != null) payload["data"] = data
    return payload
}