package com.smartcar.supervision.data

import com.smartcar.supervision.BuildConfig
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import okhttp3.CertificatePinner
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.io.IOException

data class SnapshotBundle(
    val status: TelemetrySnapshot? = null,
    val telemetry: TelemetrySnapshot? = null,
)

sealed class IntentResult {
    data class Accepted(val body: Map<String, Any>) : IntentResult()
    data class Rejected(val reason: String) : IntentResult()
    data class TimedOut(val reason: String) : IntentResult()
    data class Failed(val reason: String) : IntentResult()
}

class RobotRepository(
    dispatcher: CoroutineDispatcher = Dispatchers.IO,
) {
    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    @Volatile
    private var authToken: String = ""

    @Volatile
    private var http: OkHttpClient = buildClient(host = null, pin = "")

    @Volatile
    private var api: RobotApi = createApi(BuildConfig.ROBOT_BASE_URL)

    private val io = dispatcher

    /**
     * Build the HTTP client.
     *
     * The bearer token is applied by an interceptor on the *client* rather
     * than per call, so every endpoint is covered by one change and none can
     * be forgotten. Certificate pinning has to be here too, which is why the
     * client is rebuilt whenever the host or pin changes: OkHttp fixes the
     * pinner at build time and pins are per-host.
     */
    private fun buildClient(host: String?, pin: String): OkHttpClient {
        val builder = OkHttpClient.Builder()
            .connectTimeout(3, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .writeTimeout(5, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val token = authToken
                val request = if (token.isBlank()) {
                    chain.request()
                } else {
                    chain.request().newBuilder()
                        .addHeader("Authorization", "Bearer $token")
                        .build()
                }
                chain.proceed(request)
            }

        if (!host.isNullOrBlank() && pin.isNotBlank()) {
            builder.certificatePinner(
                CertificatePinner.Builder().add(host, pin).build()
            )
        }
        return builder.build()
    }

    private fun createApi(baseUrl: String): RobotApi {
        val safeUrl = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        return Retrofit.Builder()
            .baseUrl(safeUrl)
            .client(http)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(RobotApi::class.java)
    }

    /**
     * Apply connection settings. Replaces updateBaseUrl(), because the token
     * and pin must be applied at the same moment as the URL — updating one
     * without the others leaves the app talking to the right host with the
     * wrong credentials, or to a new host still pinned to the old key.
     */
    fun configure(baseUrl: String, token: String, pin: String) {
        authToken = token
        val host = runCatching { java.net.URI(baseUrl).host }.getOrNull()
        http = buildClient(host, pin)
        api = createApi(baseUrl)
        sharedClient = http
    }

    @Deprecated("Use configure(), which also applies the token and pin")
    fun updateBaseUrl(baseUrl: String) {
        configure(baseUrl, authToken, "")
    }

    companion object {
        /**
         * The configured client, for the MJPEG view.
         *
         * MjpegStreamingView cannot use Retrofit — it parses a multipart
         * stream by hand — and used to construct its own bare OkHttpClient,
         * which meant it silently bypassed both the auth token and the
         * certificate pin. Exposing the configured instance is less elegant
         * than threading it through two composables, and far harder to get
         * wrong.
         */
        @Volatile
        var sharedClient: OkHttpClient = OkHttpClient.Builder().build()
            private set
    }

    fun snapshotStream(pollMs: Long = 1000L): Flow<Result<SnapshotBundle>> = flow {
        var backoffMs = pollMs
        val maxBackoffMs = 8000L
        while (true) {
            val statusResult = runCatching { api.getStatus() }
            val telemetryResult = runCatching { api.getTelemetry() }
            val result = if (statusResult.isFailure && telemetryResult.isFailure) {
                Result.failure(statusResult.exceptionOrNull() ?: telemetryResult.exceptionOrNull()!!)
            } else {
                Result.success(
                    SnapshotBundle(
                        status = statusResult.getOrNull(),
                        telemetry = telemetryResult.getOrNull(),
                    )
                )
            }
            emit(result)
            backoffMs = if (result.isSuccess) pollMs else minOf(backoffMs * 2, maxBackoffMs)
            delay(backoffMs)
        }
    }.flowOn(io)

    suspend fun fetchSnapshotOnce(): Result<SnapshotBundle> {
        val statusResult = runCatching { api.getStatus() }
        val telemetryResult = runCatching { api.getTelemetry() }
        return if (statusResult.isFailure && telemetryResult.isFailure) {
            Result.failure(statusResult.exceptionOrNull() ?: telemetryResult.exceptionOrNull()!!)
        } else {
            Result.success(
                SnapshotBundle(
                    status = statusResult.getOrNull(),
                    telemetry = telemetryResult.getOrNull(),
                )
            )
        }
    }

    suspend fun checkHealth(): Result<HealthStatus> {
        return runCatching { api.getHealth() }
    }

    suspend fun fetchLogs(service: String, lines: Int): Result<LogLinesResponse> {
        return runCatching { api.getLogs(service, lines) }
    }

    suspend fun sendIntent(intent: String, extras: Map<String, Any> = emptyMap()): IntentResult {
        val request = IntentRequest(
            intent = intent,
            extras = if (extras.isEmpty()) null else extras,
        )
        return try {
            val response = api.postIntent(request)
            if (response.isSuccessful) {
                val body = response.body()?.toMap() ?: emptyMap()
                IntentResult.Accepted(body)
            } else {
                IntentResult.Rejected("http_${response.code()}")
            }
        } catch (err: SocketTimeoutException) {
            IntentResult.TimedOut("timeout")
        } catch (err: UnknownHostException) {
            IntentResult.Failed("unreachable")
        } catch (err: IOException) {
            IntentResult.Failed(err.message ?: "io_error")
        } catch (err: Exception) {
            IntentResult.Failed(err.message ?: "intent_error")
        }
    }
}
