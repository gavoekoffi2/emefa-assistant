package ai.progenius.emefa.storage

import android.content.Context

class DevicePreferences(context: Context) {
    private val preferences = context.getSharedPreferences("emefa_device", Context.MODE_PRIVATE)
    private val tokenVault = TokenVault(preferences)

    var serverUrl: String
        get() = preferences.getString("server_url", "") ?: ""
        set(value) = preferences.edit().putString("server_url", value).apply()

    var token: String?
        get() {
            tokenVault.read()?.let { return it }
            val legacy = preferences.getString("device_token", null)
            if (!legacy.isNullOrBlank()) {
                tokenVault.write(legacy)
                return legacy
            }
            return null
        }
        set(value) {
            if (value == null) tokenVault.clear() else tokenVault.write(value)
        }

    var deviceId: String?
        get() = preferences.getString("device_id", null)
        set(value) = preferences.edit().putString("device_id", value).apply()

    fun saveEnrollment(serverUrl: String, deviceId: String, token: String) {
        preferences.edit()
            .putString("server_url", serverUrl.trim().trimEnd('/'))
            .putString("device_id", deviceId)
            .apply()
        tokenVault.write(token)
    }

    fun clearEnrollment() {
        tokenVault.clear()
        preferences.edit().clear().apply()
    }
}
