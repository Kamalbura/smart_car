package com.smartcar.supervision.data

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

interface RobotApi {
    @GET("status")
    suspend fun getStatus(): TelemetrySnapshot

    @GET("telemetry")
    suspend fun getTelemetry(): TelemetrySnapshot

    @GET("health")
    suspend fun getHealth(): HealthStatus

    @POST("intent")
    suspend fun postIntent(@Body payload: IntentRequest): Response<IntentResponse>

    @GET("logs")
    suspend fun getLogs(
        @Query("service") service: String,
        @Query("lines") lines: Int,
    ): LogLinesResponse
}
