package ai.progenius.emefa.network

import ai.progenius.emefa.BuildConfig

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class EmefaApi(private val serverUrl: String) {
    data class Enrollment(val deviceId: String, val token: String)
    data class Reply(
        val status: String,
        val answer: String?,
        val error: String?,
        val pendingAction: String?,
    )

    suspend fun enroll(deviceName: String, enrollmentCode: String): Enrollment = withContext(Dispatchers.IO) {
        val response = post(
            path = "/v1/devices/enroll",
            body = JSONObject()
                .put("name", deviceName)
                .put("enrollment_code", enrollmentCode),
            token = null,
        )
        Enrollment(
            deviceId = response.getString("device_id"),
            token = response.getString("token"),
        )
    }

    suspend fun run(message: String, token: String): Reply = withContext(Dispatchers.IO) {
        val response = post(
            path = "/v1/agent/runs",
            body = JSONObject().put("message", message),
            token = token,
        )
        val pending = response.optJSONObject("pending_action")?.optString("name")
        Reply(
            status = response.getString("status"),
            answer = response.optString("answer").takeIf { it.isNotBlank() && it != "null" },
            error = response.optString("error").takeIf { it.isNotBlank() && it != "null" },
            pendingAction = pending,
        )
    }

    suspend fun revoke(token: String) = withContext(Dispatchers.IO) {
        val connection = URL(validatedBase() + "/v1/devices/me").openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "DELETE"
            connection.connectTimeout = 15_000
            connection.readTimeout = 15_000
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("Accept", "application/json")
            val status = connection.responseCode
            if (status != HttpURLConnection.HTTP_NO_CONTENT) {
                throw IOException("Révocation refusée par le serveur ($status)")
            }
        } finally {
            connection.disconnect()
        }
    }

    private fun validatedBase(): String {
        val base = serverUrl.trim().trimEnd('/')
        val isDebugLocal = BuildConfig.DEBUG && (
            base.startsWith("http://10.0.2.2") || base.startsWith("http://127.0.0.1")
        )
        require(base.startsWith("https://") || isDebugLocal) {
            "Utilisez une adresse HTTPS sécurisée."
        }
        return base
    }

    private fun post(path: String, body: JSONObject, token: String?): JSONObject {
        val base = validatedBase()
        val connection = URL(base + path).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 15_000
            connection.readTimeout = 45_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setRequestProperty("Accept", "application/json")
            if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }

            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrNull()
                throw IOException(detail?.takeIf { it.isNotBlank() } ?: "Erreur serveur ($status)")
            }
            return JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }
}
