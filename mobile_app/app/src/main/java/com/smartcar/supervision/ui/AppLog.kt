package com.smartcar.supervision.ui

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

enum class LogCategory {
    UI,
    NETWORK,
    INTENT,
    STATE,
}

data class AppLogEntry(
    val ts: Long,
    val category: LogCategory,
    val event: String,
    val message: String? = null,
    val data: Map<String, Any?> = emptyMap(),
) {
    fun toJsonLine(): String {
        val payload = mapOf(
            "ts" to ts,
            "ts_iso" to formatTimestamp(ts),
            "category" to category.name.lowercase(),
            "event" to event,
            "message" to message,
            "data" to data,
        )
        return JsonEncoder.encode(payload)
    }

    fun toDisplayLine(): String {
        val time = DateTimeFormatter.ofPattern("HH:mm:ss").format(
            Instant.ofEpochMilli(ts).atZone(ZoneId.systemDefault())
        )
        val base = "$time [${category.name}] $event"
        val msg = message?.takeIf { it.isNotBlank() }?.let { " • $it" }.orEmpty()
        val dataPart = if (data.isEmpty()) "" else " • ${data.entries.joinToString { "${it.key}=${it.value}" }}"
        return "$base$msg$dataPart"
    }

    private fun formatTimestamp(value: Long): String {
        return DateTimeFormatter.ISO_INSTANT.format(Instant.ofEpochMilli(value))
    }
}

class AppLogger(
    private val maxEntries: Int = 1000,
) {
    fun append(existing: List<AppLogEntry>, entry: AppLogEntry): List<AppLogEntry> {
        return (existing + entry).takeLast(maxEntries)
    }
}

private object JsonEncoder {
    fun encode(value: Any?): String = encodeValue(value)

    private fun encodeValue(value: Any?): String = when (value) {
        null -> "null"
        is Boolean, is Int, is Long, is Double, is Float -> value.toString()
        is Number -> value.toString()
        is String -> "\"${escape(value)}\""
        is Map<*, *> -> encodeMap(value)
        is Iterable<*> -> encodeList(value)
        else -> "\"${escape(value.toString())}\""
    }

    private fun encodeMap(map: Map<*, *>): String {
        val entries = map.entries.joinToString(separator = ",") { entry ->
            val key = entry.key?.toString() ?: ""
            "\"${escape(key)}\":${encodeValue(entry.value)}"
        }
        return "{$entries}"
    }

    private fun encodeList(list: Iterable<*>): String {
        val entries = list.joinToString(separator = ",") { encodeValue(it) }
        return "[$entries]"
    }

    private fun escape(value: String): String {
        return value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
    }
}