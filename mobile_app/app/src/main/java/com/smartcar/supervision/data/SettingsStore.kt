package com.smartcar.supervision.data

import android.content.Context

private const val PREFS_NAME = "smartcar_settings"
private const val KEY_IP = "robot_ip"
private const val KEY_PORT = "robot_port"
private const val KEY_POLL_MS = "poll_interval_ms"
private const val KEY_DEBUG = "debug_enabled"

 data class AppSettings(
    val robotIp: String,
    val robotPort: Int,
    val pollIntervalMs: Long,
    val debugEnabled: Boolean,
 ) {
    fun baseUrl(): String = "http://$robotIp:$robotPort/"
 }

class SettingsStore(private val context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun loadDefaults(defaultIp: String, defaultPort: Int): AppSettings {
        val ip = prefs.getString(KEY_IP, defaultIp) ?: defaultIp
        val port = prefs.getInt(KEY_PORT, defaultPort)
        val pollMs = prefs.getLong(KEY_POLL_MS, 1000L)
        val debug = prefs.getBoolean(KEY_DEBUG, false)
        return AppSettings(ip, port, pollMs, debug)
    }

    fun save(settings: AppSettings) {
        prefs.edit()
            .putString(KEY_IP, settings.robotIp)
            .putInt(KEY_PORT, settings.robotPort)
            .putLong(KEY_POLL_MS, settings.pollIntervalMs)
            .putBoolean(KEY_DEBUG, settings.debugEnabled)
            .apply()
    }
}
