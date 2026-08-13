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

    private val http = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .build()

    @Volatile
    private var api: RobotApi = createApi(BuildConfig.ROBOT_BASE_URL)

    private val io = dispatcher

    private fun createApi(baseUrl: String): RobotApi {
        val safeUrl = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        return Retrofit.Builder()
            .baseUrl(safeUrl)
            .client(http)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(RobotApi::class.java)
    }

    fun updateBaseUrl(baseUrl: String) {
        api = createApi(baseUrl)
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
