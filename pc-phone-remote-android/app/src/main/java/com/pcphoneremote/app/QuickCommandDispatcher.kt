package com.pcphoneremote.app

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

object QuickCommandDispatcher {
    private const val PREFS = "pc_remote_settings"
    private const val PREF_PROFILES = "device_profiles"
    private const val PREF_SELECTED_PROFILE = "selected_profile"
    private val executor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())

    fun activeProfile(context: Context): JSONObject? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = prefs.getString(PREF_PROFILES, "[]") ?: "[]"
        val arr = try { JSONArray(raw) } catch (_: Exception) { return null }
        if (arr.length() == 0) return null
        val idx = prefs.getInt(PREF_SELECTED_PROFILE, 0).coerceIn(0, arr.length() - 1)
        return arr.optJSONObject(idx)
    }

    fun send(context: Context, payload: JSONObject, successLabel: String) {
        val appCtx = context.applicationContext
        val profile = activeProfile(appCtx)
        if (profile == null) {
            mainHandler.post {
                Toast.makeText(appCtx, "PC Phone Remote: Add a PC first", Toast.LENGTH_SHORT).show()
            }
            return
        }
        val host = profile.optString("host", "").trim()
        val port = profile.optString("port", "8765").ifBlank { "8765" }
        val pin = profile.optString("pin", "")
        val pcName = profile.optString("name", "PC").ifBlank { "PC" }

        executor.execute {
            try {
                RemoteClient(host, port, pin).call(payload)
                mainHandler.post {
                    Toast.makeText(appCtx, "$pcName: $successLabel", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                mainHandler.post {
                    Toast.makeText(appCtx, "$pcName: ${e.message ?: "Error"}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
}
