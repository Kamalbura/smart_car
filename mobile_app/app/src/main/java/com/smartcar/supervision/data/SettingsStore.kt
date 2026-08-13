package com.smartcar.supervision.data

import android.content.Context

private const val PREFS_NAME = "smartcar_settings"
private const val KEY_IP = "robot_ip"
private const val KEY_PORT = "robot_port"
private const val KEY_POLL_MS = "poll_interval_ms"
private const val KEY_DEBUG = "debug_enabled"
private const val KEY_TOKEN = "robot_auth_token"
private const val KEY_PIN = "robot_cert_pin"
private const val KEY_TLS = "robot_use_tls"

 data class AppSettings(
    val robotIp: String,
    val robotPort: Int,
    val pollIntervalMs: Long,
    val debugEnabled: Boolean,
    /** Bearer token. Required by the robot whenever REMOTE_AUTH_TOKEN is set. */
    val authToken: String = "",
    /**
     * Public-key pin for the robot's self-signed certificate, in OkHttp's
     * format: `sha256/<base64>`. Printed by deploy/tls/generate-cert.sh.
     *
     * Pinning rather than trusting a CA is deliberate. This app talks to
     * exactly one device that you own, so there is no reason to accept a
     * certificate signed by any of the hundreds of CAs Android trusts — the
     * only key that should ever be accepted is the one on your robot.
     */
    val certPin: String = "",
    val useTls: Boolean = true,
 ) {
    fun baseUrl(): String {
        val scheme = if (useTls) "https" else "http"
        return "$scheme://$robotIp:$robotPort/"
    }
 }

class SettingsStore(private val context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun loadDefaults(defaultIp: String, defaultPort: Int): AppSettings {
        val ip = prefs.getString(KEY_IP, defaultIp) ?: defaultIp
        val port = prefs.getInt(KEY_PORT, defaultPort)
        val pollMs = prefs.getLong(KEY_POLL_MS, 1000L)
        val debug = prefs.getBoolean(KEY_DEBUG, false)
        val token = prefs.getString(KEY_TOKEN, "") ?: ""
        val pin = prefs.getString(KEY_PIN, "") ?: ""
        val tls = prefs.getBoolean(KEY_TLS, true)
        return AppSettings(ip, port, pollMs, debug, token, pin, tls)
    }

    fun save(settings: AppSettings) {
        prefs.edit()
            .putString(KEY_IP, settings.robotIp)
            .putInt(KEY_PORT, settings.robotPort)
            .putLong(KEY_POLL_MS, settings.pollIntervalMs)
            .putBoolean(KEY_DEBUG, settings.debugEnabled)
            .putString(KEY_TOKEN, settings.authToken)
            .putString(KEY_PIN, settings.certPin)
            .putBoolean(KEY_TLS, settings.useTls)
            .apply()
    }
}
