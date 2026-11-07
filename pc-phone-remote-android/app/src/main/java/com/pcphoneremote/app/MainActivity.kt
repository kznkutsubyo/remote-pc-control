package com.pcphoneremote.app

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.util.Base64
import android.view.View
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStream
import java.text.DateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.roundToInt

data class DeviceProfileModel(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val host: String,
    val port: String = "8765",
    val pin: String = "",
    val mac: String = ""
) {
    val endpoint: String
        get() = if (host.startsWith("http://") || host.startsWith("https://")) host else "$host:${port.ifEmpty { "8765" }}"
}

data class SharedFileItem(val name: String, val size: Long)
data class ProcessItem(val name: String, val pid: Int, val memMb: Double)
data class HistoryItem(val label: String, val ok: Boolean, val time: Long)

data class RemoteThemePalette(
    val isLight: Boolean,
    val bg: Color,
    val surface1: Color,
    val surface2: Color,
    val surfaceGlass: Color,
    val border: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val accent: Color,
    val accentSecondary: Color,
    val success: Color,
    val warning: Color,
    val danger: Color
)

class MainActivity : ComponentActivity() {
    companion object {
        private const val PREFS = "pc_remote_settings"
        private const val PREF_PROFILES = "device_profiles"
        private const val PREF_SELECTED_PROFILE = "selected_profile"
        private const val PREF_TAB = "selected_tab"
        private const val PREF_LIGHT_THEME = "light_theme"
        private const val PICK_UPLOAD = 40
        private const val SAVE_DOWNLOAD = 41
    }

    private lateinit var prefs: SharedPreferences
    private val uiHandler = Handler(Looper.getMainLooper())
    private val worker: ExecutorService = Executors.newSingleThreadExecutor()
    private val clients = ConcurrentHashMap<String, RemoteClient>()

    // Observable Compose state
    private var profilesState by mutableStateOf<List<DeviceProfileModel>>(emptyList())
    private var selectedProfileIndex by mutableIntStateOf(0)
    private var currentTab by mutableIntStateOf(0)
    private var isLightTheme by mutableStateOf(false)
    private var paletteIndex by mutableIntStateOf(0)
    private var langCode by mutableStateOf("ru")
    private var reduceMotion by mutableStateOf(false)

    private var busyState by mutableStateOf(false)
    private var bannerMessage by mutableStateOf("")
    private var bannerColorType by mutableStateOf("muted") // muted, success, warn, danger

    private val statusesMap = mutableStateMapOf<String, JSONObject>()
    private val sharedFilesMap = mutableStateMapOf<String, List<SharedFileItem>>()
    private val processesMap = mutableStateMapOf<String, List<ProcessItem>>()
    private var enrollmentRefreshTick by mutableIntStateOf(0)

    private var pickerDevice: DeviceProfileModel? = null
    private var pendingDownloadName: String? = null
    private var deepLinkEnrollCode by mutableStateOf<String?>(null)

    // Touchpad throttling
    private var pendingDx = 0f
    private var pendingDy = 0f
    private var touchMoveScheduled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        isLightTheme = prefs.getBoolean(PREF_LIGHT_THEME, false)
        paletteIndex = prefs.getInt("palette", 0).coerceIn(0, 4)
        langCode = prefs.getString("lang", "ru") ?: "ru"
        reduceMotion = prefs.getBoolean("reduce_motion", false)

        val loaded = loadProfilesFromPrefs()
        profilesState = loaded
        selectedProfileIndex = prefs.getInt(PREF_SELECTED_PROFILE, 0).coerceIn(0, (loaded.size - 1).coerceAtLeast(0))
        val initialTab = prefs.getInt(PREF_TAB, if (loaded.isEmpty()) 3 else 0).coerceIn(0, 3)
        currentTab = initialTab
        persistProfilesToPrefs()
        bannerMessage = tr("idle")

        handleIncomingIntent(intent)

        setContent {
            val palette = remember(isLightTheme, paletteIndex) {
                buildPalette(isLightTheme, paletteIndex)
            }
            SideEffect {
                updateSystemBars(palette)
            }
            MaterialTheme(
                colorScheme = if (palette.isLight) {
                    lightColorScheme(
                        primary = palette.accent,
                        background = palette.bg,
                        surface = palette.surface1,
                        onBackground = palette.textPrimary,
                        onSurface = palette.textPrimary
                    )
                } else {
                    darkColorScheme(
                        primary = palette.accent,
                        background = palette.bg,
                        surface = palette.surface1,
                        onBackground = palette.textPrimary,
                        onSurface = palette.textPrimary
                    )
                }
            ) {
                RemoteAppRoot(palette)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme == "pcphone") {
            val raw = data.toString()
            if (data.host == "enroll") {
                deepLinkEnrollCode = raw
            } else if (data.host == "add") {
                importCodeOrUri(raw)
            }
        }
    }

    override fun onDestroy() {
        uiHandler.removeCallbacksAndMessages(null)
        worker.shutdownNow()
        super.onDestroy()
    }

    private fun updateSystemBars(palette: RemoteThemePalette) {
        val window = window ?: return
        window.statusBarColor = android.graphics.Color.argb(
            255,
            (palette.bg.red * 255).roundToInt(),
            (palette.bg.green * 255).roundToInt(),
            (palette.bg.blue * 255).roundToInt()
        )
        window.navigationBarColor = android.graphics.Color.argb(
            255,
            (palette.surface1.red * 255).roundToInt(),
            (palette.surface1.green * 255).roundToInt(),
            (palette.surface1.blue * 255).roundToInt()
        )
        var flags = if (palette.isLight) View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR else 0
        if (Build.VERSION.SDK_INT >= 26 && palette.isLight) {
            flags = flags or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        }
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = flags
    }

    private fun buildPalette(light: Boolean, index: Int): RemoteThemePalette {
        val darkAccents = listOf(
            Color(0xFF8B7CFF), // Violet
            Color(0xFF3DD68C), // Mint
            Color(0xFF38BDF8), // Ocean
            Color(0xFFF5B14C), // Amber
            Color(0xFFFF7AB6)  // Rose
        )
        val lightAccents = listOf(
            Color(0xFF6353E8),
            Color(0xFF0E9F6E),
            Color(0xFF0284C7),
            Color(0xFFD97706),
            Color(0xFFDB2777)
        )
        val accent = if (light) lightAccents[index.coerceIn(0, 4)] else darkAccents[index.coerceIn(0, 4)]
        val accent2 = if (light) Color(0xFF0EA5E9) else Color(0xFF38BDF8)
        return if (light) {
            RemoteThemePalette(
                isLight = true,
                bg = Color(0xFFF5F5F8),
                surface1 = Color(0xFFFFFFFF),
                surface2 = Color(0xFFECEEF4),
                surfaceGlass = Color(0xE6FFFFFF),
                border = Color(0xFFE0E2EC),
                textPrimary = Color(0xFF16161D),
                textSecondary = Color(0xFF646674),
                accent = accent,
                accentSecondary = accent2,
                success = Color(0xFF10B981),
                warning = Color(0xFFD97706),
                danger = Color(0xFFE11D48)
            )
        } else {
            RemoteThemePalette(
                isLight = false,
                bg = Color(0xFF0B0B10),
                surface1 = Color(0xFF15151C),
                surface2 = Color(0xFF1E1E28),
                surfaceGlass = Color(0xCC1E1E28),
                border = Color(0xFF282836),
                textPrimary = Color(0xFFF4F4F8),
                textSecondary = Color(0xFF9898AA),
                accent = accent,
                accentSecondary = accent2,
                success = Color(0xFF3DD68C),
                warning = Color(0xFFF5B14C),
                danger = Color(0xFFFF5C7C)
            )
        }
    }

    private fun tr(key: String): String = Translations.tr(langCode, key)

    private fun activeProfile(): DeviceProfileModel? {
        if (profilesState.isEmpty()) return null
        return profilesState[selectedProfileIndex.coerceIn(0, profilesState.size - 1)]
    }

    private fun loadProfilesFromPrefs(): List<DeviceProfileModel> {
        val out = mutableListOf<DeviceProfileModel>()
        try {
            val arr = JSONArray(prefs.getString(PREF_PROFILES, "[]") ?: "[]")
            for (i in 0 until arr.length()) {
                val item = arr.optJSONObject(i) ?: continue
                val host = item.optString("host", "").trim()
                if (host.isEmpty()) continue
                out.add(
                    DeviceProfileModel(
                        id = item.optString("id", UUID.randomUUID().toString()),
                        name = item.optString("name", "My PC").ifBlank { "My PC" },
                        host = host,
                        port = item.optString("port", "8765").ifBlank { "8765" },
                        pin = item.optString("pin", ""),
                        mac = item.optString("mac", "")
                    )
                )
            }
        } catch (_: Exception) {
        }
        return out
    }

    private fun persistProfilesToPrefs() {
        val arr = JSONArray()
        for (p in profilesState) {
            arr.put(
                JSONObject()
                    .put("id", p.id)
                    .put("name", p.name)
                    .put("host", p.host)
                    .put("port", p.port)
                    .put("pin", p.pin)
                    .put("mac", p.mac)
            )
        }
        prefs.edit()
            .putString(PREF_PROFILES, arr.toString())
            .putInt(PREF_SELECTED_PROFILE, selectedProfileIndex)
            .apply()
    }

    private fun selectTab(tab: Int) {
        currentTab = tab.coerceIn(0, 3)
        prefs.edit().putInt(PREF_TAB, currentTab).apply()
    }

    private fun toggleThemeMode(light: Boolean) {
        isLightTheme = light
        prefs.edit().putBoolean(PREF_LIGHT_THEME, light).apply()
    }

    private fun setBanner(msg: String, type: String = "muted") {
        bannerMessage = msg
        bannerColorType = type
    }

    private fun addHistory(profile: DeviceProfileModel, label: String, ok: Boolean) {
        try {
            val prev = JSONArray(prefs.getString("history_${profile.id}", "[]") ?: "[]")
            val next = JSONArray()
            next.put(JSONObject().put("label", label).put("ok", ok).put("time", System.currentTimeMillis()))
            for (i in 0 until minOf(prev.length(), 19)) {
                next.put(prev.opt(i))
            }
            prefs.edit().putString("history_${profile.id}", next.toString()).apply()
        } catch (_: Exception) {
        }
    }

    private fun getHistory(profile: DeviceProfileModel): List<HistoryItem> {
        val out = mutableListOf<HistoryItem>()
        try {
            val arr = JSONArray(prefs.getString("history_${profile.id}", "[]") ?: "[]")
            for (i in 0 until minOf(arr.length(), 6)) {
                val item = arr.optJSONObject(i) ?: continue
                out.add(
                    HistoryItem(
                        label = item.optString("label", ""),
                        ok = item.optBoolean("ok", true),
                        time = item.optLong("time", 0L)
                    )
                )
            }
        } catch (_: Exception) {
        }
        return out
    }

    private fun getOrCreateClient(profile: DeviceProfileModel): RemoteClient {
        return clients.getOrPut(profile.id) {
            RemoteClient(profile.host, profile.port, profile.pin)
        }
    }

    private fun runRpc(
        profile: DeviceProfileModel,
        payload: JSONObject,
        historyLabel: String? = null,
        allowConcurrent: Boolean = false,
        onError: ((String) -> Unit)? = null,
        onSuccess: (JSONObject) -> Unit = {}
    ) {
        if (busyState && !allowConcurrent) {
            Toast.makeText(this, tr("inProgress"), Toast.LENGTH_SHORT).show()
            return
        }
        if (!allowConcurrent) {
            busyState = true
            setBanner(tr("sending"), "warn")
        }
        worker.execute {
            var response: JSONObject? = null
            var errorText: String? = null
            try {
                val client = getOrCreateClient(profile)
                response = client.call(payload)
            } catch (e: Exception) {
                errorText = e.message ?: e.javaClass.simpleName
            }
            uiHandler.post {
                if (!allowConcurrent) busyState = false
                if (historyLabel != null) {
                    addHistory(profile, historyLabel, errorText == null)
                }
                if (errorText == null && response != null) {
                    if (!allowConcurrent) setBanner(tr("done"), "success")
                    onSuccess(response)
                } else {
                    val localizedErr = tr(errorText ?: "Error")
                    if (!allowConcurrent) setBanner(tr("errorPrefix") + localizedErr, "danger")
                    onError?.invoke(localizedErr)
                }
            }
        }
    }

    private fun refreshDeviceStatus(profile: DeviceProfileModel) {
        runRpc(profile, JSONObject().put("action", "status")) { result ->
            statusesMap[profile.id] = result
            val detectedMac = result.optString("mac", "").trim()
            if (detectedMac.isNotEmpty() && profile.mac.isEmpty()) {
                val idx = profilesState.indexOfFirst { it.id == profile.id }
                if (idx >= 0) {
                    val updated = profilesState.toMutableList()
                    updated[idx] = updated[idx].copy(mac = detectedMac)
                    profilesState = updated
                    persistProfilesToPrefs()
                }
            }
            setBanner(tr("connectionOk"), "success")
        }
    }

    private fun refreshSharedFiles(profile: DeviceProfileModel) {
        runRpc(profile, JSONObject().put("action", "files.list")) { result ->
            val arr = result.optJSONArray("files") ?: JSONArray()
            val list = mutableListOf<SharedFileItem>()
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                list.add(SharedFileItem(obj.optString("name", ""), obj.optLong("size", 0L)))
            }
            sharedFilesMap[profile.id] = list
        }
    }

    private fun refreshProcesses(profile: DeviceProfileModel) {
        runRpc(profile, JSONObject().put("action", "processes.list")) { result ->
            val arr = result.optJSONArray("processes") ?: JSONArray()
            val list = mutableListOf<ProcessItem>()
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                list.add(
                    ProcessItem(
                        name = obj.optString("name", ""),
                        pid = obj.optInt("pid", 0),
                        memMb = obj.optDouble("mem_mb", 0.0)
                    )
                )
            }
            processesMap[profile.id] = list
        }
    }

    private fun queueTouchMove(profile: DeviceProfileModel, dx: Float, dy: Float) {
        pendingDx += dx
        pendingDy += dy
        if (touchMoveScheduled) return
        touchMoveScheduled = true
        uiHandler.postDelayed({
            touchMoveScheduled = false
            val sendX = pendingDx.roundToInt().coerceIn(-400, 400)
            val sendY = pendingDy.roundToInt().coerceIn(-400, 400)
            pendingDx = 0f
            pendingDy = 0f
            if (sendX != 0 || sendY != 0) {
                val req = JSONObject()
                    .put("action", "touchpad")
                    .put("mode", "move")
                    .put("dx", sendX)
                    .put("dy", sendY)
                runRpc(profile, req, allowConcurrent = true)
            }
        }, 42L)
    }

    private fun importCodeOrUri(
        rawInput: String,
        hostOverride: String = "",
        onComplete: ((Boolean, String) -> Unit)? = null
    ) {
        val raw = rawInput.trim()
        // Check if it's a Windows Unlock enrollment URI (`pcphone://enroll?...`)
        val parsedEnroll = UnlockCrypto.parseEnrollCode(raw)
        if (parsedEnroll != null) {
            var targetProfile = activeProfile()
            var effectiveHost = hostOverride.trim().ifEmpty { parsedEnroll.host }
            var effectivePort = parsedEnroll.port.ifBlank { "8765" }
            if (!effectiveHost.startsWith("http://") && !effectiveHost.startsWith("https://") && effectiveHost.contains(":")) {
                val hPart = effectiveHost.substringBeforeLast(":").trim()
                val pPart = effectiveHost.substringAfterLast(":").trim()
                if (hPart.isNotEmpty() && pPart.all { it.isDigit() }) {
                    effectiveHost = hPart
                    effectivePort = pPart
                }
            }
            if (effectiveHost.isNotEmpty() && parsedEnroll.pin.isNotEmpty()) {
                val exactIdx = profilesState.indexOfFirst {
                    it.host.equals(effectiveHost, ignoreCase = true) && it.port == effectivePort
                }
                val samePinIdx = profilesState.indexOfFirst {
                    it.pin == parsedEnroll.pin && (
                        it.name.equals(parsedEnroll.pcName, ignoreCase = true) ||
                            it.host.startsWith("172.")
                        )
                }
                if (exactIdx >= 0) {
                    val updated = profilesState.toMutableList()
                    updated[exactIdx] = updated[exactIdx].copy(pin = parsedEnroll.pin)
                    profilesState = updated
                    persistProfilesToPrefs()
                    clients.remove(updated[exactIdx].id)
                    selectedProfileIndex = exactIdx
                    targetProfile = updated[exactIdx]
                } else if (samePinIdx >= 0) {
                    val updated = profilesState.toMutableList()
                    val patched = updated[samePinIdx].copy(
                        name = parsedEnroll.pcName.ifBlank { updated[samePinIdx].name },
                        host = effectiveHost,
                        port = effectivePort,
                        pin = parsedEnroll.pin
                    )
                    updated[samePinIdx] = patched
                    profilesState = updated
                    persistProfilesToPrefs()
                    clients.remove(patched.id)
                    selectedProfileIndex = samePinIdx
                    targetProfile = patched
                } else {
                    val created = DeviceProfileModel(
                        name = parsedEnroll.pcName.ifBlank { tr("defaultProfileName") },
                        host = effectiveHost,
                        port = effectivePort,
                        pin = parsedEnroll.pin
                    )
                    profilesState = profilesState + created
                    selectedProfileIndex = profilesState.size - 1
                    persistProfilesToPrefs()
                    targetProfile = created
                }
            }
            if (targetProfile == null) {
                val msg = tr("missingHost")
                setBanner(msg, "danger")
                onComplete?.invoke(false, msg)
                return
            }
            val finalProfile = targetProfile
            try {
                val (req, commitFn) = UnlockCrypto.buildEnrollmentRequest(this, finalProfile.id, parsedEnroll)
                runRpc(
                    finalProfile,
                    req,
                    historyLabel = tr("unlockBindBtn"),
                    onError = { err ->
                        onComplete?.invoke(false, err)
                    },
                    onSuccess = {
                        commitFn()
                        enrollmentRefreshTick++
                        refreshDeviceStatus(finalProfile)
                        onComplete?.invoke(true, tr("unlockEnrolledBadge"))
                    }
                )
            } catch (e: Exception) {
                val msg = e.message ?: tr("importProfileError")
                setBanner(msg, "danger")
                onComplete?.invoke(false, msg)
            }
            return
        }

        // Standard device profile import (`pcphone://add?...` or JSON)
        try {
            val item = if (raw.startsWith("{")) {
                JSONObject(raw)
            } else {
                val uri = Uri.parse(raw)
                if (uri.scheme != "pcphone" || uri.host != "add") throw IllegalArgumentException()
                JSONObject()
                    .put("name", uri.getQueryParameter("name") ?: tr("defaultProfileName"))
                    .put("host", uri.getQueryParameter("host") ?: "")
                    .put("port", uri.getQueryParameter("port") ?: "8765")
                    .put("pin", uri.getQueryParameter("pin") ?: "")
            }
            val profile = DeviceProfileModel(
                name = item.optString("name", tr("defaultProfileName")).ifBlank { tr("defaultProfileName") },
                host = item.optString("host", "").trim(),
                port = item.optString("port", "8765").ifBlank { "8765" },
                pin = item.optString("pin", "")
            )
            RemoteClient(profile.host, profile.port, profile.pin)
            if (profile.pin.isEmpty()) throw IllegalArgumentException()
            profilesState = profilesState + profile
            selectedProfileIndex = profilesState.size - 1
            persistProfilesToPrefs()
            selectTab(0)
            setBanner(tr("importProfileSaved"), "success")
            onComplete?.invoke(true, tr("importProfileSaved"))
        } catch (_: Exception) {
            setBanner(tr("importProfileError"), "danger")
            onComplete?.invoke(false, tr("importProfileError"))
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data ?: return
        val device = pickerDevice ?: return
        if (resultCode != Activity.RESULT_OK) return

        if (requestCode == PICK_UPLOAD) {
            var displayName = "upload"
            try {
                contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor: Cursor ->
                    if (cursor.moveToFirst()) displayName = cursor.getString(0)
                }
            } catch (_: Exception) {
            }
            val finalName = displayName
            busyState = true
            setBanner(tr("sending"), "warn")
            worker.execute {
                var err: String? = null
                try {
                    val bytes = RemoteClient.readLimited(contentResolver.openInputStream(uri), RemoteClient.FILE_LIMIT)
                    val payload = JSONObject()
                        .put("action", "files.put")
                        .put("name", finalName)
                        .put("data", Base64.encodeToString(bytes, Base64.NO_WRAP))
                    getOrCreateClient(device).call(payload)
                } catch (e: Exception) {
                    err = e.message ?: "Error"
                }
                val finalErr = err
                uiHandler.post {
                    busyState = false
                    addHistory(device, tr("sendFile"), finalErr == null)
                    if (finalErr == null) {
                        setBanner(tr("done"), "success")
                        refreshSharedFiles(device)
                    } else {
                        setBanner(tr("errorPrefix") + tr(finalErr), "danger")
                    }
                }
            }
        } else if (requestCode == SAVE_DOWNLOAD && pendingDownloadName != null) {
            val fileName = pendingDownloadName!!
            pendingDownloadName = null
            busyState = true
            setBanner(tr("sending"), "warn")
            worker.execute {
                var err: String? = null
                try {
                    val resp = getOrCreateClient(device).call(
                        JSONObject().put("action", "files.get").put("name", fileName)
                    )
                    val bytes = Base64.decode(resp.getString("data"), Base64.DEFAULT)
                    if (bytes.size > RemoteClient.FILE_LIMIT) throw Exception("fileLimit")
                    contentResolver.openOutputStream(uri, "wt")?.use { out: OutputStream ->
                        out.write(bytes)
                    } ?: throw Exception("fileUnavailable")
                } catch (e: Exception) {
                    err = e.message ?: "Error"
                }
                val finalErr = err
                uiHandler.post {
                    busyState = false
                    addHistory(device, tr("download"), finalErr == null)
                    if (finalErr == null) setBanner(tr("done"), "success")
                    else setBanner(tr("errorPrefix") + tr(finalErr), "danger")
                }
            }
        }
    }

    private fun launchRdpClient(profile: DeviceProfileModel, stateJson: JSONObject?, onNeedConfigure: (JSONObject?) -> Unit) {
        var rdp = stateJson?.optJSONObject("rdp")
        try {
            if (prefs.contains("rdp_${profile.id}")) {
                rdp = JSONObject(prefs.getString("rdp_${profile.id}", "{}") ?: "{}")
            }
        } catch (_: Exception) {
        }
        val host = rdp?.optString("host")?.trim() ?: ""
        if (host.isEmpty()) {
            onNeedConfigure(rdp)
            return
        }
        val port = rdp?.optInt("port", 3389) ?: 3389
        val address = if (host.contains(":") && !host.startsWith("[")) "[$host]" else host
        var uri = "rdp://full%20address=" + Uri.encode("s:$address:$port")
        val username = rdp?.optString("username", "") ?: ""
        if (username.isNotEmpty()) uri += "&username=" + Uri.encode("s:$username")
        val gateway = rdp?.optString("gateway", "") ?: ""
        if (gateway.isNotEmpty()) uri += "&gatewayhostname=" + Uri.encode("s:$gateway") + "&gatewayusagemethod=i:1"
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)))
        } catch (_: ActivityNotFoundException) {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=com.microsoft.rdc.androidx")))
            } catch (_: Exception) {
                Toast.makeText(this, tr("rdpInstall"), Toast.LENGTH_LONG).show()
            }
        }
    }

    // =========================================================================
    // JETPACK COMPOSE UI
    // =========================================================================

    @Composable
    private fun RemoteAppRoot(palette: RemoteThemePalette) {
        val active = activeProfile()
        var showDeviceEditorIndex by remember { mutableStateOf<Int?>(null) }
        var showImportModal by remember { mutableStateOf(false) }
        var showUnlockSheet by remember { mutableStateOf(false) }
        var showEnrollModal by remember { mutableStateOf(false) }
        var showTimerModal by remember { mutableStateOf(false) }
        var showPowerModal by remember { mutableStateOf(false) }
        var showRdpConfigModal by remember { mutableStateOf<JSONObject?>(null) }
        var showDevicePickerModal by remember { mutableStateOf(false) }

        LaunchedEffect(deepLinkEnrollCode) {
            if (deepLinkEnrollCode != null) {
                showEnrollModal = true
            }
        }

        val enrollMeta = remember(active?.id, enrollmentRefreshTick) {
            if (active != null) UnlockCrypto.getEnrollmentMeta(this@MainActivity, active.id) else null
        }

        Scaffold(
            containerColor = palette.bg,
            bottomBar = {
                BottomGlassNavigation(
                    palette = palette,
                    selectedTab = currentTab,
                    onSelectTab = { selectTab(it) }
                )
            }
        ) { innerPadding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .background(palette.bg)
                    .padding(innerPadding)
            ) {
                // Top Active Device Pill & Quick Actions
                TopDevicePillBar(
                    palette = palette,
                    active = active,
                    statusJson = if (active != null) statusesMap[active.id] else null,
                    busy = busyState,
                    onSwitchDevice = {
                        if (profilesState.size > 1) showDevicePickerModal = true
                        else selectTab(3)
                    },
                    onRefresh = { if (active != null) refreshDeviceStatus(active) },
                    onToggleTheme = { toggleThemeMode(!isLightTheme) }
                )

                // Subtle status banner strip
                StatusFeedbackStrip(palette = palette)

                // Main Tab Content
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                ) {
                    when (currentTab) {
                        0 -> RemoteDashboardTab(
                            palette = palette,
                            profile = active,
                            enrollMeta = enrollMeta,
                            onAddDevice = { showDeviceEditorIndex = -1 },
                            onImportCode = { showImportModal = true },
                            onOpenUnlockSheet = { showUnlockSheet = true },
                            onOpenEnrollModal = { showEnrollModal = true },
                            onOpenTimerModal = { showTimerModal = true },
                            onOpenPowerModal = { showPowerModal = true }
                        )
                        1 -> StudioProTab(
                            palette = palette,
                            profile = active,
                            onAddDevice = { showDeviceEditorIndex = -1 }
                        )
                        2 -> ExchangeTab(
                            palette = palette,
                            profile = active,
                            onAddDevice = { showDeviceEditorIndex = -1 }
                        )
                        else -> SettingsAndDevicesTab(
                            palette = palette,
                            active = active,
                            enrollMeta = enrollMeta,
                            onAddDevice = { showDeviceEditorIndex = -1 },
                            onEditDevice = { idx -> showDeviceEditorIndex = idx },
                            onImportCode = { showImportModal = true },
                            onOpenEnrollModal = { showEnrollModal = true },
                            onOpenRdpModal = { rdpJson -> showRdpConfigModal = rdpJson ?: JSONObject() }
                        )
                    }
                }
            }
        }

        // Modals & Bottom Sheets
        if (showDeviceEditorIndex != null) {
            DeviceEditorModal(
                palette = palette,
                editIndex = showDeviceEditorIndex!!,
                onDismiss = { showDeviceEditorIndex = null }
            )
        }

        if (showImportModal) {
            ImportCodeModal(
                palette = palette,
                initialCode = "",
                onDismiss = { showImportModal = false }
            )
        }

        if (showEnrollModal) {
            EnrollWindowsUnlockModal(
                palette = palette,
                profile = active,
                initialCode = deepLinkEnrollCode ?: "",
                onDismiss = {
                    deepLinkEnrollCode = null
                    showEnrollModal = false
                }
            )
        }

        if (showUnlockSheet && active != null) {
            WindowsUnlockSheetModal(
                palette = palette,
                profile = active,
                enrollMeta = enrollMeta,
                statusJson = statusesMap[active.id],
                onOpenEnroll = {
                    showUnlockSheet = false
                    showEnrollModal = true
                },
                onOpenRdp = {
                    showUnlockSheet = false
                    launchRdpClient(active, statusesMap[active.id]) { rdp ->
                        showRdpConfigModal = rdp ?: JSONObject()
                    }
                },
                onDismiss = { showUnlockSheet = false }
            )
        }

        if (showTimerModal && active != null) {
            TimerSheetModal(
                palette = palette,
                profile = active,
                onDismiss = { showTimerModal = false }
            )
        }

        if (showPowerModal && active != null) {
            PowerHoldSheetModal(
                palette = palette,
                profile = active,
                onDismiss = { showPowerModal = false }
            )
        }

        if (showRdpConfigModal != null && active != null) {
            RdpConfigModal(
                palette = palette,
                profile = active,
                initialRdp = showRdpConfigModal!!,
                onDismiss = { showRdpConfigModal = null }
            )
        }

        if (showDevicePickerModal) {
            QuickDevicePickerModal(
                palette = palette,
                onAddDevice = {
                    showDevicePickerModal = false
                    showDeviceEditorIndex = -1
                },
                onDismiss = { showDevicePickerModal = false }
            )
        }
    }

    @Composable
    private fun TopDevicePillBar(
        palette: RemoteThemePalette,
        active: DeviceProfileModel?,
        statusJson: JSONObject?,
        busy: Boolean,
        onSwitchDevice: () -> Unit,
        onRefresh: () -> Unit,
        onToggleTheme: () -> Unit
    ) {
        val isOnline = statusJson != null
        val isLocked = statusJson?.optBoolean("locked", false) == true
        val dotColor = when {
            !isOnline -> palette.textSecondary
            isLocked -> palette.warning
            else -> palette.success
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Active PC Pill
            Surface(
                shape = RoundedCornerShape(999.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier
                    .weight(1f)
                    .clickable { onSwitchDevice() }
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .clip(CircleShape)
                            .background(dotColor)
                    )
                    Spacer(Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = active?.name ?: tr("onboardingTitle"),
                            color = palette.textPrimary,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = if (active == null) tr("notConfigured")
                            else if (!isOnline) tr("notChecked")
                            else if (isLocked) tr("sessionLocked")
                            else tr("online"),
                            color = palette.textSecondary,
                            fontSize = 11.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    Icon(
                        painter = painterResource(R.drawable.ic_chevron_right),
                        contentDescription = null,
                        tint = palette.textSecondary,
                        modifier = Modifier.size(18.dp)
                    )
                }
            }

            Spacer(Modifier.width(8.dp))

            // Refresh Button (exposes "Обновить" contentDescription for UIAutomator compatibility)
            Surface(
                shape = CircleShape,
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier
                    .size(44.dp)
                    .semantics { contentDescription = tr("refresh") }
                    .clickable(enabled = active != null && !busy) { onRefresh() }
            ) {
                Box(contentAlignment = Alignment.Center) {
                    if (busy) {
                        CircularProgressIndicator(
                            color = palette.accent,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(20.dp)
                        )
                    } else {
                        Icon(
                            painter = painterResource(R.drawable.ic_refresh_cw),
                            contentDescription = tr("refresh"),
                            tint = palette.accent,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                }
            }

            Spacer(Modifier.width(8.dp))

            // Quick Theme Toggle Button (exposes "Тема" contentDescription for UIAutomator compatibility)
            Surface(
                shape = CircleShape,
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier
                    .size(44.dp)
                    .semantics { contentDescription = tr("themeTitle") }
                    .clickable { onToggleTheme() }
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        text = if (palette.isLight) "☀" else "☾",
                        color = palette.accent,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }

    @Composable
    private fun StatusFeedbackStrip(palette: RemoteThemePalette) {
        val textColor = when (bannerColorType) {
            "success" -> palette.success
            "warn" -> palette.warning
            "danger" -> palette.danger
            else -> palette.textSecondary
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 22.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = bannerMessage.ifEmpty { tr("idle") },
                color = textColor,
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }

    // =========================================================================
    // TAB 1: REMOTE DASHBOARD (Пульт)
    // =========================================================================

    @Composable
    private fun RemoteDashboardTab(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel?,
        enrollMeta: UnlockCrypto.EnrollmentMeta?,
        onAddDevice: () -> Unit,
        onImportCode: () -> Unit,
        onOpenUnlockSheet: () -> Unit,
        onOpenEnrollModal: () -> Unit,
        onOpenTimerModal: () -> Unit,
        onOpenPowerModal: () -> Unit
    ) {
        if (profile == null) {
            EmptyDeviceOnboardingCard(
                palette = palette,
                onAddDevice = onAddDevice,
                onImportCode = onImportCode
            )
            return
        }

        val stateJson = statusesMap[profile.id]
        val unlockSnapshot = stateJson?.optJSONObject("unlock")
        val pcReportsEnrolled = unlockSnapshot?.optBoolean("enrolled", false) == true
        val isEnrolled = enrollMeta != null
        val isLocked = stateJson?.optBoolean("locked", false) == true

        val cpuVal = if (stateJson != null && stateJson.has("cpu")) stateJson.optDouble("cpu", 0.0).roundToInt() else null
        val ramVal = if (stateJson != null && stateJson.has("ram")) stateJson.optDouble("ram", 0.0).roundToInt() else null
        val diskVal = if (stateJson != null && stateJson.has("disk")) stateJson.optDouble("disk", 0.0).roundToInt() else null
        val batteryObj = stateJson?.optJSONObject("battery")
        val batteryVal = if (batteryObj != null && batteryObj.has("percent")) batteryObj.optInt("percent", 0) else null
        val uptimeSec = stateJson?.optLong("uptime", 0L) ?: 0L

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            // Pre-setup Warning Card: warns user that Windows login from phone is available after entering PIN/password in Windows configure.bat
            if (!isEnrolled) {
                Surface(
                    shape = RoundedCornerShape(22.dp),
                    color = palette.warning.copy(alpha = if (palette.isLight) 0.10f else 0.14f),
                    border = BorderStroke(1.dp, palette.warning.copy(alpha = 0.45f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                painter = painterResource(R.drawable.ic_log_in),
                                contentDescription = null,
                                tint = palette.warning,
                                modifier = Modifier.size(22.dp)
                            )
                            Spacer(Modifier.width(10.dp))
                            Text(
                                text = tr("unlockBannerTitle"),
                                color = palette.textPrimary,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                        Spacer(Modifier.height(6.dp))
                        Text(
                            text = tr("unlockBannerBody"),
                            color = palette.textSecondary,
                            fontSize = 12.5.sp,
                            lineHeight = 18.sp
                        )
                        Spacer(Modifier.height(12.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Button(
                                onClick = onOpenEnrollModal,
                                colors = ButtonDefaults.buttonColors(containerColor = palette.warning),
                                shape = RoundedCornerShape(12.dp),
                                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp)
                            ) {
                                Text(
                                    text = tr("unlockBindBtn"),
                                    color = Color(0xFF101014),
                                    fontSize = 12.5.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            OutlinedButton(
                                onClick = onOpenUnlockSheet,
                                shape = RoundedCornerShape(12.dp),
                                border = BorderStroke(1.dp, palette.border),
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)
                            ) {
                                Text(
                                    text = tr("remoteLogin"),
                                    color = palette.textPrimary,
                                    fontSize = 12.5.sp
                                )
                            }
                        }
                    }
                }
            }

            // Hero Status & Windows Sign-In Card
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(
                    1.dp,
                    if (isLocked) palette.warning.copy(alpha = 0.55f) else palette.border
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    // Status badges row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        val badgeBg = when {
                            stateJson == null -> palette.surface2
                            isLocked -> palette.warning.copy(alpha = 0.16f)
                            else -> palette.success.copy(alpha = 0.16f)
                        }
                        val badgeFg = when {
                            stateJson == null -> palette.textSecondary
                            isLocked -> palette.warning
                            else -> palette.success
                        }
                        Surface(
                            shape = RoundedCornerShape(999.dp),
                            color = badgeBg
                        ) {
                            Text(
                                text = when {
                                    stateJson == null -> "● ${tr("notChecked")}"
                                    isLocked -> tr("badgeLocked")
                                    else -> tr("badgeActive")
                                },
                                color = badgeFg,
                                fontSize = 11.5.sp,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(horizontal = 11.dp, vertical = 5.dp)
                            )
                        }

                        Text(
                            text = if (uptimeSec > 0) "⏱ ${formatDuration(uptimeSec)}" else "",
                            color = palette.textSecondary,
                            fontSize = 11.5.sp,
                            fontFamily = FontFamily.Monospace
                        )
                    }

                    Spacer(Modifier.height(18.dp))

                    // 3 Circular Ring Gauges (CPU %, RAM %, Battery/Disk %)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        CircularMetricGauge(
                            palette = palette,
                            label = "CPU",
                            percent = cpuVal,
                            ringColor = palette.accent
                        )
                        CircularMetricGauge(
                            palette = palette,
                            label = tr("memory"),
                            percent = ramVal,
                            ringColor = palette.success
                        )
                        CircularMetricGauge(
                            palette = palette,
                            label = if (batteryVal != null) tr("battery") else tr("diskC"),
                            percent = batteryVal ?: diskVal,
                            ringColor = palette.accentSecondary
                        )
                    }

                    Spacer(Modifier.height(18.dp))

                    // Primary Windows Sign-In / Unlock CTA Button
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(16.dp))
                            .background(
                                Brush.horizontalGradient(
                                    listOf(palette.accent, palette.accentSecondary)
                                )
                            )
                            .clickable { onOpenUnlockSheet() }
                            .padding(vertical = 14.dp, horizontal = 16.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.Center,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                painter = painterResource(R.drawable.ic_log_in),
                                contentDescription = null,
                                tint = Color.White,
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(Modifier.width(10.dp))
                            Column {
                                Text(
                                    text = if (isLocked) tr("unlockHeroReady") else tr("unlockHeroCta"),
                                    color = Color.White,
                                    fontSize = 15.sp,
                                    fontWeight = FontWeight.Bold
                                )
                                Text(
                                    text = if (isEnrolled) {
                                        if (enrollMeta!!.requiresPhonePin) {
                                            "${tr("unlockEnrolledBadge")} · ${tr("unlockSubPin")}"
                                        } else {
                                            "${tr("unlockEnrolledBadge")} · ${tr("unlockSubKey")}"
                                        }
                                    } else if (pcReportsEnrolled) {
                                        tr("unlockSubPcReady")
                                    } else {
                                        tr("unlockSubPrebind")
                                    },
                                    color = Color.White.copy(alpha = 0.85f),
                                    fontSize = 11.sp
                                )
                            }
                        }
                    }
                }
            }

            // 4 Quick Action Tiles (2x2 Grid)
            Text(
                text = tr("controlsTitle"),
                color = palette.textPrimary,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 2.dp)
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                QuickActionTile(
                    modifier = Modifier.weight(1f),
                    palette = palette,
                    iconRes = R.drawable.ic_action_lock,
                    iconTint = palette.accent,
                    title = tr("lockTitle"),
                    subtitle = tr("lockSub"),
                    onClick = {
                        runRpc(
                            profile,
                            JSONObject().put("action", "command").put("command", "lock"),
                            historyLabel = tr("lockTitle")
                        ) {
                            refreshDeviceStatus(profile)
                        }
                    }
                )
                QuickActionTile(
                    modifier = Modifier.weight(1f),
                    palette = palette,
                    iconRes = R.drawable.ic_action_sleep,
                    iconTint = palette.warning,
                    title = tr("sleepTitle"),
                    subtitle = tr("sleepSub"),
                    onClick = {
                        runRpc(
                            profile,
                            JSONObject().put("action", "command").put("command", "sleep"),
                            historyLabel = tr("sleepTitle")
                        )
                    }
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                QuickActionTile(
                    modifier = Modifier.weight(1f),
                    palette = palette,
                    iconRes = R.drawable.ic_clock,
                    iconTint = palette.accentSecondary,
                    title = tr("timer"),
                    subtitle = "1–180 ${tr("minutes")}",
                    onClick = onOpenTimerModal
                )
                QuickActionTile(
                    modifier = Modifier.weight(1f),
                    palette = palette,
                    iconRes = R.drawable.ic_action_power,
                    iconTint = palette.danger,
                    title = tr("powerTitle"),
                    subtitle = tr("powerSub"),
                    onClick = onOpenPowerModal
                )
            }

            // Compact Media & Sound Dock
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = tr("media"),
                        color = palette.textPrimary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        MediaIconButton(
                            modifier = Modifier.weight(1f),
                            palette = palette,
                            iconRes = R.drawable.ic_skip_back,
                            label = tr("previous"),
                            highlight = false
                        ) {
                            runRpc(profile, JSONObject().put("action", "media").put("key", "previous"), tr("previous"))
                        }
                        MediaIconButton(
                            modifier = Modifier.weight(1.25f),
                            palette = palette,
                            iconRes = R.drawable.ic_circle_play,
                            label = tr("play_pause"),
                            highlight = true
                        ) {
                            runRpc(profile, JSONObject().put("action", "media").put("key", "play_pause"), tr("play_pause"))
                        }
                        MediaIconButton(
                            modifier = Modifier.weight(1f),
                            palette = palette,
                            iconRes = R.drawable.ic_skip_forward,
                            label = tr("next"),
                            highlight = false
                        ) {
                            runRpc(profile, JSONObject().put("action", "media").put("key", "next"), tr("next"))
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        MediaIconButton(
                            modifier = Modifier.weight(1f),
                            palette = palette,
                            iconRes = R.drawable.ic_volume_1,
                            label = tr("volume_down"),
                            highlight = false
                        ) {
                            runRpc(profile, JSONObject().put("action", "media").put("key", "volume_down"), tr("volume_down"))
                        }
                        MediaIconButton(
                            modifier = Modifier.weight(1.25f),
                            palette = palette,
                            iconRes = R.drawable.ic_action_mute,
                            label = tr("mute"),
                            highlight = false
                        ) {
                            runRpc(profile, JSONObject().put("action", "media").put("key", "mute"), tr("mute"))
                        }
                        MediaIconButton(
                            modifier = Modifier.weight(1f),
                            palette = palette,
                            iconRes = R.drawable.ic_volume_2,
                            label = tr("volume_up"),
                            highlight = false
                        ) {
                            runRpc(profile, JSONObject().put("action", "media").put("key", "volume_up"), tr("volume_up"))
                        }
                    }
                }
            }

            // Recent Activity History
            val historyItems = getHistory(profile)
            if (historyItems.isNotEmpty()) {
                Surface(
                    shape = RoundedCornerShape(20.dp),
                    color = palette.surface1,
                    border = BorderStroke(1.dp, palette.border),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = tr("recent"),
                            color = palette.textPrimary,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(8.dp))
                        historyItems.take(4).forEach { item ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 5.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    painter = painterResource(if (item.ok) R.drawable.ic_check else R.drawable.ic_clock),
                                    contentDescription = null,
                                    tint = if (item.ok) palette.success else palette.danger,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(Modifier.width(10.dp))
                                Text(
                                    text = item.label,
                                    color = palette.textPrimary,
                                    fontSize = 13.sp,
                                    modifier = Modifier.weight(1f)
                                )
                                Text(
                                    text = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(item.time)),
                                    color = palette.textSecondary,
                                    fontSize = 11.sp,
                                    fontFamily = FontFamily.Monospace
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun CircularMetricGauge(
        palette: RemoteThemePalette,
        label: String,
        percent: Int?,
        ringColor: Color,
        size: Dp = 84.dp
    ) {
        val targetSweep = ((percent ?: 0).coerceIn(0, 100) / 100f) * 360f
        val animatedSweep by animateFloatAsState(
            targetValue = targetSweep,
            animationSpec = tween(durationMillis = if (reduceMotion) 0 else 500),
            label = label
        )

        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.size(size)
            ) {
                Canvas(modifier = Modifier.fillMaxSize().padding(6.dp)) {
                    val strokeWidth = 7.dp.toPx()
                    drawArc(
                        color = palette.surface2,
                        startAngle = 0f,
                        sweepAngle = 360f,
                        useCenter = false,
                        style = Stroke(width = strokeWidth, cap = StrokeCap.Round)
                    )
                    if (percent != null && animatedSweep > 0f) {
                        drawArc(
                            color = ringColor,
                            startAngle = -90f,
                            sweepAngle = animatedSweep,
                            useCenter = false,
                            style = Stroke(width = strokeWidth, cap = StrokeCap.Round)
                        )
                    }
                }
                Text(
                    text = if (percent != null) "$percent%" else "--",
                    color = palette.textPrimary,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
            }
            Spacer(Modifier.height(4.dp))
            Text(
                text = label,
                color = palette.textSecondary,
                fontSize = 11.5.sp
            )
        }
    }

    @Composable
    private fun QuickActionTile(
        modifier: Modifier = Modifier,
        palette: RemoteThemePalette,
        iconRes: Int,
        iconTint: Color,
        title: String,
        subtitle: String,
        onClick: () -> Unit
    ) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = palette.surface1,
            border = BorderStroke(1.dp, palette.border),
            modifier = modifier
                .semantics { contentDescription = title }
                .clickable { onClick() }
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier
                        .size(40.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(iconTint.copy(alpha = 0.15f))
                ) {
                    Icon(
                        painter = painterResource(iconRes),
                        contentDescription = title,
                        tint = iconTint,
                        modifier = Modifier.size(21.dp)
                    )
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(
                        text = title,
                        color = palette.textPrimary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1
                    )
                    Text(
                        text = subtitle,
                        color = palette.textSecondary,
                        fontSize = 11.sp,
                        maxLines = 1
                    )
                }
            }
        }
    }

    @Composable
    private fun MediaIconButton(
        modifier: Modifier = Modifier,
        palette: RemoteThemePalette,
        iconRes: Int,
        label: String,
        highlight: Boolean,
        onClick: () -> Unit
    ) {
        Surface(
            shape = RoundedCornerShape(14.dp),
            color = if (highlight) palette.accent.copy(alpha = 0.18f) else palette.surface2,
            border = BorderStroke(1.dp, if (highlight) palette.accent.copy(alpha = 0.45f) else palette.border),
            modifier = modifier
                .height(48.dp)
                .semantics { contentDescription = label }
                .clickable { onClick() }
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(
                    painter = painterResource(iconRes),
                    contentDescription = label,
                    tint = if (highlight) palette.accent else palette.textPrimary,
                    modifier = Modifier.size(22.dp)
                )
            }
        }
    }

    // =========================================================================
    // TAB 2: STUDIO PRO (Тачпад, Сценарии, Stream Deck, Wake-on-LAN, Процессы)
    // =========================================================================

    @Composable
    private fun StudioProTab(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel?,
        onAddDevice: () -> Unit
    ) {
        if (profile == null) {
            EmptyDeviceOnboardingCard(palette = palette, onAddDevice = onAddDevice, onImportCode = {})
            return
        }

        val stateJson = statusesMap[profile.id]
        var macInput by remember(profile.id, profile.mac, stateJson) {
            mutableStateOf(profile.mac.ifEmpty { stateJson?.optString("mac", "") ?: "" })
        }
        val procList = processesMap[profile.id] ?: emptyList()

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // 1. One-Tap Scenes (Сценарии в 1 тап)
            Text(
                text = tr("scenesTitle"),
                color = palette.textPrimary,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                val scenes = listOf(
                    Triple("movie", "🎬", tr("sceneMovie")),
                    Triple("night", "🌙", tr("sceneNight")),
                    Triple("work", "💼", tr("sceneWork")),
                    Triple("presentation", "📊", tr("scenePresentation")),
                    Triple("away", "🚶", tr("sceneAway"))
                )
                scenes.forEach { (sceneKey, emoji, sceneLabel) ->
                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = palette.surface1,
                        border = BorderStroke(1.dp, palette.border),
                        modifier = Modifier.clickable {
                            runRpc(
                                profile,
                                JSONObject().put("action", "scenes.run").put("scene", sceneKey),
                                historyLabel = sceneLabel
                            )
                        }
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 11.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(text = emoji, fontSize = 16.sp)
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = sceneLabel,
                                color = palette.textPrimary,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    }
                }
            }

            // 2. Interactive Touchpad & Presentation Remote
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = tr("touchpadTitle"),
                        color = palette.textPrimary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = tr("touchpadHint"),
                        color = palette.textSecondary,
                        fontSize = 11.5.sp
                    )
                    Spacer(Modifier.height(12.dp))

                    // Touchpad Surface
                    Box(
                        contentAlignment = Alignment.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(175.dp)
                            .clip(RoundedCornerShape(18.dp))
                            .background(palette.surface2)
                            .border(1.dp, palette.border, RoundedCornerShape(18.dp))
                            .pointerInput(profile.id) {
                                detectDragGestures { change, dragAmount ->
                                    change.consume()
                                    queueTouchMove(
                                        profile,
                                        dragAmount.x * 1.35f,
                                        dragAmount.y * 1.35f
                                    )
                                }
                            }
                            .pointerInput(profile.id) {
                                detectTapGestures(
                                    onTap = {
                                        runRpc(
                                            profile,
                                            JSONObject().put("action", "touchpad").put("mode", "click").put("button", "left"),
                                            allowConcurrent = true
                                        )
                                    },
                                    onDoubleTap = {
                                        runRpc(
                                            profile,
                                            JSONObject().put("action", "touchpad").put("mode", "click").put("button", "double"),
                                            allowConcurrent = true
                                        )
                                    },
                                    onLongPress = {
                                        runRpc(
                                            profile,
                                            JSONObject().put("action", "touchpad").put("mode", "click").put("button", "right"),
                                            allowConcurrent = true
                                        )
                                    }
                                )
                            }
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "✥ TOUCHPAD",
                                color = palette.textSecondary.copy(alpha = 0.55f),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 2.sp
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = tr("touchpadGestures"),
                                color = palette.textSecondary.copy(alpha = 0.55f),
                                fontSize = 10.5.sp
                            )
                        }
                    }

                    Spacer(Modifier.height(10.dp))

                    // Mouse & Scroll Row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        SmallDeckChip(Modifier.weight(1f), palette, tr("btnLeftClick")) {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "click").put("button", "left"), allowConcurrent = true)
                        }
                        SmallDeckChip(Modifier.weight(1f), palette, tr("btnRightClick")) {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "click").put("button", "right"), allowConcurrent = true)
                        }
                        SmallDeckChip(Modifier.weight(1f), palette, tr("btnScrollUp")) {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "scroll").put("delta", 240), allowConcurrent = true)
                        }
                        SmallDeckChip(Modifier.weight(1f), palette, tr("btnScrollDown")) {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "scroll").put("delta", -240), allowConcurrent = true)
                        }
                    }

                    Spacer(Modifier.height(8.dp))

                    // Presentation Remote Keys
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        SmallDeckChip(Modifier.weight(1f), palette, tr("btnSlideShow")) {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "key").put("key", "f5"), allowConcurrent = true)
                        }
                        SmallDeckChip(Modifier.weight(1f), palette, tr("btnPrevSlide")) {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "key").put("key", "left"), allowConcurrent = true)
                        }
                        SmallDeckChip(Modifier.weight(1f), palette, tr("btnNextSlide")) {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "key").put("key", "right"), allowConcurrent = true)
                        }
                        SmallDeckChip(Modifier.weight(1f), palette, "Esc") {
                            runRpc(profile, JSONObject().put("action", "touchpad").put("mode", "key").put("key", "esc"), allowConcurrent = true)
                        }
                    }
                }
            }

            // 3. Stream Deck 8-Macro Grid
            Text(
                text = tr("deckTitle"),
                color = palette.textPrimary,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold
            )

            val macros = listOf(
                Triple("desktop", "🖥", tr("deckDesktop")),
                Triple("task_manager", "📊", tr("deckTaskMgr")),
                Triple("screenshot", "📸", tr("deckScreenshot")),
                Triple("explorer", "📁", tr("deckExplorer")),
                Triple("browser", "🌐", tr("deckBrowser")),
                Triple("mute", "🔇", tr("deckMute")),
                Triple("play_pause", "⏯", tr("deckPlayPause")),
                Triple("lock", "🔒", tr("deckLock"))
            )
            for (rowIdx in 0 until 2) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    for (colIdx in 0 until 4) {
                        val (macroId, emoji, title) = macros[rowIdx * 4 + colIdx]
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = palette.surface1,
                            border = BorderStroke(1.dp, palette.border),
                            modifier = Modifier
                                .weight(1f)
                                .height(80.dp)
                                .clickable {
                                    runRpc(
                                        profile,
                                        JSONObject().put("action", "deck.run").put("macro", macroId),
                                        historyLabel = title
                                    )
                                }
                        ) {
                            Column(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(6.dp),
                                verticalArrangement = Arrangement.Center,
                                horizontalAlignment = Alignment.CenterHorizontally
                            ) {
                                Text(text = emoji, fontSize = 20.sp)
                                Spacer(Modifier.height(5.dp))
                                Text(
                                    text = title,
                                    color = palette.textPrimary,
                                    fontSize = 10.5.sp,
                                    fontWeight = FontWeight.Medium,
                                    textAlign = TextAlign.Center,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                        }
                    }
                }
            }

            // 4. Wake-on-LAN Card
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = tr("wolTitle"),
                        color = palette.textPrimary,
                        fontSize = 14.5.sp,
                        fontWeight = FontWeight.Bold
                    )
                    var showMac by remember { mutableStateOf(false) }
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = macInput,
                        onValueChange = {
                            macInput = it
                            val idx = profilesState.indexOfFirst { p -> p.id == profile.id }
                            if (idx >= 0) {
                                val list = profilesState.toMutableList()
                                list[idx] = list[idx].copy(mac = it.trim())
                                profilesState = list
                                persistProfilesToPrefs()
                            }
                        },
                        label = { Text(tr("wolMacLabel")) },
                        singleLine = true,
                        visualTransformation = if (showMac) VisualTransformation.None else PasswordVisualTransformation(),
                        trailingIcon = {
                            if (macInput.isNotEmpty()) {
                                TextButton(onClick = { showMac = !showMac }) {
                                    Text(if (showMac) tr("hide") else tr("show"), fontSize = 11.sp)
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(10.dp))
                    Button(
                        onClick = {
                            val targetMac = macInput.trim()
                            worker.execute {
                                var directOk = false
                                try {
                                    UnlockCrypto.sendDirectMagicPacket(targetMac, profile.host, langCode)
                                    directOk = true
                                } catch (_: Exception) {
                                }
                                uiHandler.post {
                                    if (directOk) {
                                        setBanner(tr("wolSentPrefix"), "success")
                                        addHistory(profile, "Wake-on-LAN", true)
                                    }
                                    // Also trigger relay/companion WOL if reachable
                                    runRpc(
                                        profile,
                                        JSONObject().put("action", "wol.wake").put("mac", targetMac),
                                        allowConcurrent = true
                                    )
                                }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            text = tr("wolWakeBtn"),
                            color = Color.White,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            // 5. Top Windows Processes Card
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = tr("processesTitle"),
                            color = palette.textPrimary,
                            fontSize = 14.5.sp,
                            fontWeight = FontWeight.Bold
                        )
                        TextButton(onClick = { refreshProcesses(profile) }) {
                            Text(text = tr("refresh"), color = palette.accent, fontSize = 12.5.sp)
                        }
                    }
                    if (procList.isEmpty()) {
                        Text(
                            text = tr("processesEmptyHint"),
                            color = palette.textSecondary,
                            fontSize = 12.sp
                        )
                    } else {
                        procList.forEach { proc ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 5.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = proc.name,
                                    color = palette.textPrimary,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Medium,
                                    modifier = Modifier.weight(1f)
                                )
                                Text(
                                    text = "PID ${proc.pid}",
                                    color = palette.textSecondary,
                                    fontSize = 11.sp,
                                    fontFamily = FontFamily.Monospace,
                                    modifier = Modifier.padding(horizontal = 8.dp)
                                )
                                Text(
                                    text = "${proc.memMb.roundToInt()} ${tr("unitMb")}",
                                    color = palette.accent,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun SmallDeckChip(
        modifier: Modifier = Modifier,
        palette: RemoteThemePalette,
        text: String,
        onClick: () -> Unit
    ) {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = palette.surface2,
            border = BorderStroke(1.dp, palette.border),
            modifier = modifier
                .height(38.dp)
                .clickable { onClick() }
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text(
                    text = text,
                    color = palette.textPrimary,
                    fontSize = 11.5.sp,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }

    // =========================================================================
    // TAB 3: EXCHANGE (Файлы и общий буфер текста)
    // =========================================================================

    @Composable
    private fun ExchangeTab(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel?,
        onAddDevice: () -> Unit
    ) {
        if (profile == null) {
            EmptyDeviceOnboardingCard(palette = palette, onAddDevice = onAddDevice, onImportCode = {})
            return
        }

        val files = sharedFilesMap[profile.id]
        var noteText by remember(profile.id) {
            mutableStateOf(prefs.getString("draft_${profile.id}", "") ?: "")
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Upload & Shared Files Card
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = tr("sharedFiles"),
                                color = palette.textPrimary,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = tr("fileLimit"),
                                color = palette.textSecondary,
                                fontSize = 11.5.sp
                            )
                        }
                        IconButton(
                            onClick = { refreshSharedFiles(profile) },
                            modifier = Modifier.semantics { contentDescription = tr("refresh") }
                        ) {
                            Icon(
                                painter = painterResource(R.drawable.ic_refresh_cw),
                                contentDescription = tr("refresh"),
                                tint = palette.accent
                            )
                        }
                    }

                    Spacer(Modifier.height(10.dp))

                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = palette.surface2,
                        border = BorderStroke(1.dp, palette.border),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(10.dp)) {
                            Text(
                                text = tr("filesSaveLocationTitle"),
                                color = palette.textPrimary,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                text = tr("filesSaveLocationBody"),
                                color = palette.textSecondary,
                                fontSize = 11.sp,
                                lineHeight = 15.sp
                            )
                        }
                    }

                    Spacer(Modifier.height(10.dp))

                    Button(
                        onClick = {
                            pickerDevice = profile
                            val pick = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                                type = "*/*"
                                addCategory(Intent.CATEGORY_OPENABLE)
                            }
                            @Suppress("DEPRECATION")
                            startActivityForResult(pick, PICK_UPLOAD)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Icon(
                            painter = painterResource(R.drawable.ic_upload),
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(text = tr("sendFile"), color = Color.White, fontWeight = FontWeight.Bold)
                    }

                    Spacer(Modifier.height(8.dp))

                    OutlinedButton(
                        onClick = {
                            runRpc(
                                profile,
                                JSONObject().put("action", "files.open_folder"),
                                historyLabel = tr("openPcFolderHistory")
                            )
                        },
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            text = tr("openPcFolderBtn"),
                            color = palette.textPrimary,
                            fontSize = 12.5.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }

                    Spacer(Modifier.height(12.dp))

                    when {
                        files == null -> {
                            Text(
                                text = tr("filesHint"),
                                color = palette.textSecondary,
                                fontSize = 12.5.sp
                            )
                        }
                        files.isEmpty() -> {
                            Text(
                                text = tr("emptyFiles"),
                                color = palette.textSecondary,
                                fontSize = 12.5.sp
                            )
                        }
                        else -> {
                            files.forEach { file ->
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 6.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(
                                        painter = painterResource(R.drawable.ic_file_text),
                                        contentDescription = null,
                                        tint = palette.success,
                                        modifier = Modifier.size(22.dp)
                                    )
                                    Spacer(Modifier.width(10.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = file.name,
                                            color = palette.textPrimary,
                                            fontSize = 13.5.sp,
                                            fontWeight = FontWeight.Medium
                                        )
                                        Text(
                                            text = formatSize(file.size),
                                            color = palette.textSecondary,
                                            fontSize = 11.sp
                                        )
                                    }
                                    IconButton(
                                        enabled = file.size <= RemoteClient.FILE_LIMIT,
                                        onClick = {
                                            pickerDevice = profile
                                            pendingDownloadName = file.name
                                            val saveIntent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                                                type = "application/octet-stream"
                                                addCategory(Intent.CATEGORY_OPENABLE)
                                                putExtra(Intent.EXTRA_TITLE, file.name)
                                            }
                                            @Suppress("DEPRECATION")
                                            startActivityForResult(saveIntent, SAVE_DOWNLOAD)
                                        }
                                    ) {
                                        Icon(
                                            painter = painterResource(R.drawable.ic_download),
                                            contentDescription = tr("download"),
                                            tint = palette.accent
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Shared Text / Clipboard Card
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = tr("sharedText"),
                        color = palette.textPrimary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(
                        value = noteText,
                        onValueChange = {
                            noteText = it
                            prefs.edit().putString("draft_${profile.id}", it).apply()
                        },
                        placeholder = { Text(tr("textHint")) },
                        minLines = 4,
                        maxLines = 8,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(10.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = {
                                runRpc(
                                    profile,
                                    JSONObject().put("action", "note.set").put("text", noteText),
                                    historyLabel = tr("sharedText")
                                )
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text(text = tr("send"), color = Color.White, fontWeight = FontWeight.Bold)
                        }
                        OutlinedButton(
                            onClick = {
                                runRpc(profile, JSONObject().put("action", "note.get")) { res ->
                                    val fetched = res.optString("text", "")
                                    noteText = fetched
                                    prefs.edit().putString("draft_${profile.id}", fetched).apply()
                                }
                            },
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Icon(
                                painter = painterResource(R.drawable.ic_download),
                                contentDescription = tr("receiveText"),
                                tint = palette.success,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        OutlinedButton(
                            onClick = {
                                val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                cm.setPrimaryClip(ClipData.newPlainText("PC Remote", noteText))
                                setBanner(tr("copied"), "success")
                            },
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Icon(
                                painter = painterResource(R.drawable.ic_copy),
                                contentDescription = tr("copyText"),
                                tint = palette.textPrimary,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                    }
                }
            }
        }
    }

    // =========================================================================
    // TAB 4: SETTINGS & DEVICES (Настройки и ПК)
    // =========================================================================

    @Composable
    private fun SettingsAndDevicesTab(
        palette: RemoteThemePalette,
        active: DeviceProfileModel?,
        enrollMeta: UnlockCrypto.EnrollmentMeta?,
        onAddDevice: () -> Unit,
        onEditDevice: (Int) -> Unit,
        onImportCode: () -> Unit,
        onOpenEnrollModal: () -> Unit,
        onOpenRdpModal: (JSONObject?) -> Unit
    ) {
        var showLanguagePicker by remember { mutableStateOf(false) }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // 1. Computers (Устройства ПК)
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = tr("profilesTitle"),
                            color = palette.textPrimary,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(
                                onClick = onImportCode,
                                shape = RoundedCornerShape(12.dp),
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp)
                            ) {
                                Text(text = tr("importProfileTitle"), fontSize = 12.sp)
                            }
                            Button(
                                onClick = onAddDevice,
                                colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                                shape = RoundedCornerShape(12.dp),
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                                modifier = Modifier.semantics { contentDescription = tr("addProfileTitle") }
                            ) {
                                Text(text = tr("addProfileTitle"), color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }

                    Spacer(Modifier.height(10.dp))

                    if (profilesState.isEmpty()) {
                        Text(
                            text = tr("onboardingSteps"),
                            color = palette.textSecondary,
                            fontSize = 12.5.sp
                        )
                    } else {
                        profilesState.forEachIndexed { idx, item ->
                            val isSelected = idx == selectedProfileIndex
                            Surface(
                                shape = RoundedCornerShape(16.dp),
                                color = if (isSelected) palette.accent.copy(alpha = 0.12f) else palette.surface2,
                                border = BorderStroke(1.dp, if (isSelected) palette.accent else palette.border),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp)
                                    .clickable {
                                        selectedProfileIndex = idx
                                        persistProfilesToPrefs()
                                        selectTab(0)
                                    }
                            ) {
                                Row(
                                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(
                                        painter = painterResource(R.drawable.ic_devices_tab),
                                        contentDescription = null,
                                        tint = if (isSelected) palette.accent else palette.textSecondary,
                                        modifier = Modifier.size(22.dp)
                                    )
                                    Spacer(Modifier.width(12.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = item.name,
                                            color = palette.textPrimary,
                                            fontSize = 14.5.sp,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Text(
                                            text = if (statusesMap.containsKey(item.id)) tr("online") else tr("selectedDeviceTitle"),
                                            color = palette.textSecondary,
                                            fontSize = 11.5.sp
                                        )
                                    }
                                    IconButton(onClick = { onEditDevice(idx) }) {
                                        Icon(
                                            painter = painterResource(R.drawable.ic_pencil),
                                            contentDescription = tr("edit"),
                                            tint = palette.textSecondary,
                                            modifier = Modifier.size(18.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 2. Windows Sign-In & RDP Security Card
            if (active != null) {
                Surface(
                    shape = RoundedCornerShape(22.dp),
                    color = palette.surface1,
                    border = BorderStroke(1.dp, palette.border),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = tr("remoteLogin"),
                            color = palette.textPrimary,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(6.dp))
                        if (enrollMeta != null) {
                            Text(
                                text = "✓ ${tr("unlockEnrolledBadge")} (${active.name})\n${if (enrollMeta.requiresPhonePin) tr("unlockSubPin") else tr("unlockSubKey")}",
                                color = palette.success,
                                fontSize = 12.sp,
                                lineHeight = 17.sp
                            )
                        } else {
                            Text(
                                text = tr("unlockSettingsHint"),
                                color = palette.textSecondary,
                                fontSize = 12.sp
                            )
                        }
                        Spacer(Modifier.height(10.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = onOpenEnrollModal,
                                colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                Text(text = tr("unlockBindBtn"), color = Color.White, fontSize = 12.5.sp, fontWeight = FontWeight.Bold)
                            }
                            if (enrollMeta != null) {
                                OutlinedButton(
                                    onClick = {
                                        UnlockCrypto.clearEnrollment(this@MainActivity, active.id)
                                        enrollmentRefreshTick++
                                        setBanner(tr("unlockKeyRemoved"), "muted")
                                    },
                                    shape = RoundedCornerShape(12.dp)
                                ) {
                                    Text(text = tr("unpairBtn"), color = palette.danger, fontSize = 12.5.sp)
                                }
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = {
                                val st = statusesMap[active.id]
                                var rdp = st?.optJSONObject("rdp")
                                if (prefs.contains("rdp_${active.id}")) {
                                    try {
                                        rdp = JSONObject(prefs.getString("rdp_${active.id}", "{}") ?: "{}")
                                    } catch (_: Exception) {
                                    }
                                }
                                onOpenRdpModal(rdp)
                            },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(text = "${tr("rdpSettingsBtn")} (${active.name})", color = palette.textPrimary, fontSize = 12.5.sp)
                        }
                    }
                }
            }

            // 3. Theme, Palette, Animations, Language
            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text(
                        text = tr("themeTitle"),
                        color = palette.textPrimary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(14.dp))
                            .background(palette.surface2)
                            .padding(4.dp)
                    ) {
                        val modes = listOf(false to tr("themeDark"), true to tr("themeLight"))
                        modes.forEach { (light, label) ->
                            val selected = isLightTheme == light
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier
                                    .weight(1f)
                                    .height(40.dp)
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(if (selected) palette.accent else Color.Transparent)
                                    .clickable { toggleThemeMode(light) }
                            ) {
                                Text(
                                    text = label,
                                    color = if (selected) Color.White else palette.textPrimary,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }

                    Text(
                        text = tr("paletteTitle"),
                        color = palette.textPrimary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold
                    )

                    val swatchColors = listOf(
                        Color(0xFF8B7CFF) to tr("violet"),
                        Color(0xFF3DD68C) to tr("mint"),
                        Color(0xFF38BDF8) to tr("ocean"),
                        Color(0xFFF5B14C) to tr("amber"),
                        Color(0xFFFF7AB6) to tr("rose")
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        swatchColors.forEachIndexed { idx, (swatchColor, name) ->
                            val selected = paletteIndex == idx
                            Column(
                                horizontalAlignment = Alignment.CenterHorizontally,
                                modifier = Modifier.clickable {
                                    paletteIndex = idx
                                    prefs.edit().putInt("palette", idx).apply()
                                }
                            ) {
                                Box(
                                    contentAlignment = Alignment.Center,
                                    modifier = Modifier
                                        .size(40.dp)
                                        .clip(CircleShape)
                                        .background(swatchColor)
                                        .border(
                                            width = if (selected) 3.dp else 1.dp,
                                            color = if (selected) palette.textPrimary else palette.border,
                                            shape = CircleShape
                                        )
                                ) {
                                    if (selected) {
                                        Icon(
                                            painter = painterResource(R.drawable.ic_check),
                                            contentDescription = name,
                                            tint = Color(0xFF101014),
                                            modifier = Modifier.size(18.dp)
                                        )
                                    }
                                }
                                Spacer(Modifier.height(4.dp))
                                Text(text = name, color = palette.textSecondary, fontSize = 10.5.sp)
                            }
                        }
                    }

                    // Animations Switch
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = tr("motionTitle"),
                            color = palette.textPrimary,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Switch(
                            checked = !reduceMotion,
                            onCheckedChange = { enabled ->
                                reduceMotion = !enabled
                                prefs.edit().putBoolean("reduce_motion", !enabled).apply()
                            }
                        )
                    }

                    // Language Button
                    OutlinedButton(
                        onClick = { showLanguagePicker = true },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        val langIdx = Translations.LANG_CODES.indexOf(langCode).coerceAtLeast(0)
                        Text(
                            text = "${tr("languageTitle")}: ${Translations.LANG_NAMES[langIdx]}",
                            color = palette.textPrimary
                        )
                    }

                    // Clear History Button
                    OutlinedButton(
                        onClick = {
                            val edit = prefs.edit()
                            for (key in prefs.all.keys) {
                                if (key.startsWith("history_")) edit.remove(key)
                            }
                            edit.apply()
                            setBanner(tr("done"), "success")
                        },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Icon(
                            painter = painterResource(R.drawable.ic_trash),
                            contentDescription = null,
                            tint = palette.danger,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(text = tr("clearHistory"), color = palette.danger)
                    }
                }
            }
        }

        if (showLanguagePicker) {
            Dialog(onDismissRequest = { showLanguagePicker = false }) {
                Surface(
                    shape = RoundedCornerShape(22.dp),
                    color = palette.surface1,
                    border = BorderStroke(1.dp, palette.border)
                ) {
                    Column(modifier = Modifier.padding(18.dp)) {
                        Text(
                            text = tr("languageTitle"),
                            color = palette.textPrimary,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(10.dp))
                        Translations.LANG_CODES.forEachIndexed { idx, code ->
                            TextButton(
                                onClick = {
                                    langCode = code
                                    prefs.edit().putString("lang", code).apply()
                                    showLanguagePicker = false
                                },
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text(
                                    text = Translations.LANG_NAMES[idx],
                                    color = if (code == langCode) palette.accent else palette.textPrimary,
                                    fontWeight = if (code == langCode) FontWeight.Bold else FontWeight.Normal,
                                    modifier = Modifier.fillMaxWidth()
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    // =========================================================================
    // BOTTOM NAVIGATION BAR
    // =========================================================================

    @Composable
    private fun BottomGlassNavigation(
        palette: RemoteThemePalette,
        selectedTab: Int,
        onSelectTab: (Int) -> Unit
    ) {
        val tabs = listOf(
            Triple(0, R.drawable.ic_remote_tab, tr("tabRemote")),
            Triple(1, R.drawable.ic_devices_tab, tr("tabStudio")),
            Triple(2, R.drawable.ic_arrow_down_up, tr("exchange")),
            Triple(3, R.drawable.ic_settings_tab, tr("tabSettings"))
        )

        Surface(
            color = palette.surface1,
            border = BorderStroke(1.dp, palette.border),
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceAround,
                verticalAlignment = Alignment.CenterVertically
            ) {
                tabs.forEach { (index, iconRes, label) ->
                    val selected = selectedTab == index
                    val itemColor = if (selected) palette.accent else palette.textSecondary
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(14.dp))
                            .background(if (selected) palette.accent.copy(alpha = 0.12f) else Color.Transparent)
                            .semantics { contentDescription = label }
                            .clickable { onSelectTab(index) }
                            .padding(vertical = 6.dp)
                    ) {
                        Icon(
                            painter = painterResource(iconRes),
                            contentDescription = label,
                            tint = itemColor,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(Modifier.height(3.dp))
                        Text(
                            text = label,
                            color = itemColor,
                            fontSize = 11.sp,
                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                            maxLines = 1
                        )
                    }
                }
            }
        }
    }

    // =========================================================================
    // WINDOWS SIGN-IN / UNLOCK MODAL & ENROLLMENT MODAL
    // =========================================================================

    @Composable
    private fun WindowsUnlockSheetModal(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel,
        enrollMeta: UnlockCrypto.EnrollmentMeta?,
        statusJson: JSONObject?,
        onOpenEnroll: () -> Unit,
        onOpenRdp: () -> Unit,
        onDismiss: () -> Unit
    ) {
        val hasSplitKeyVault = enrollMeta?.hasSplitKey == true
        val requiresPhonePin = enrollMeta?.requiresPhonePin == true
        var useManualPassword by remember(hasSplitKeyVault) { mutableStateOf(!hasSplitKeyVault) }
        var phonePinInput by remember { mutableStateOf("") }
        var showPhonePin by remember { mutableStateOf(false) }
        var passwordInput by remember { mutableStateOf("") }
        var showPassword by remember { mutableStateOf(false) }
        var stepState by remember { mutableIntStateOf(0) } // 0=idle, 1=challenge, 2=encrypt, 3=submit, 4=done
        var errorMsg by remember { mutableStateOf("") }
        var successMsg by remember { mutableStateOf("") }

        fun executeUnlockFlow() {
            if (enrollMeta == null) {
                errorMsg = tr("errEnrollFirst")
                return
            }
            if (useManualPassword && passwordInput.isEmpty()) {
                errorMsg = tr("errEnterWinPassword")
                return
            }
            if (!useManualPassword && requiresPhonePin) {
                if (phonePinInput.isEmpty()) {
                    errorMsg = tr("errEnterPhonePin")
                    return
                }
                if (!UnlockCrypto.checkPhonePinLocally(this@MainActivity, profile.id, phonePinInput.toCharArray())) {
                    errorMsg = tr("errWrongPhonePin")
                    return
                }
            }
            errorMsg = ""
            successMsg = ""
            stepState = 1

            val proceedToUnlock = {
                val capturedPw = if (useManualPassword) passwordInput.toCharArray() else null
                val capturedPin = if (!useManualPassword && requiresPhonePin) phonePinInput.toCharArray() else null
                worker.execute {
                    try {
                        val client = getOrCreateClient(profile)
                        val challenge = client.call(JSONObject().put("action", "unlock.challenge"))
                        uiHandler.post { stepState = 2 }

                        val submitPayload = UnlockCrypto.buildUnlockSubmitRequest(
                            context = this@MainActivity,
                            profileId = profile.id,
                            challenge = challenge,
                            passwordChars = capturedPw,
                            phonePinChars = capturedPin
                        )
                        uiHandler.post {
                            passwordInput = ""
                            phonePinInput = ""
                            stepState = 3
                        }

                        val submitResp = client.call(submitPayload)
                        uiHandler.post {
                            stepState = 4
                            val alreadyUnlocked = submitResp.optBoolean("already_unlocked", false) ||
                                submitResp.optString("message", "").contains("уже разблокирована")
                            val providerInstalled = submitResp.optBoolean("provider_installed", true) &&
                                !submitResp.optString("message", "").contains("Установить модуль")
                            successMsg = when {
                                alreadyUnlocked && providerInstalled -> tr("unlockAlreadyUnlocked")
                                alreadyUnlocked -> tr("unlockVerifiedNeedProvider")
                                else -> tr("unlockSuccess")
                            }
                            addHistory(profile, tr("remoteLogin"), true)
                            refreshDeviceStatus(profile)
                        }
                    } catch (e: Exception) {
                        uiHandler.post {
                            stepState = 0
                            val rawErr = e.message ?: ""
                            errorMsg = when {
                                rawErr.contains("Модуль экрана блокировки") -> tr("errProviderNotInstalled")
                                rawErr.contains("Windows lock screen provider did not respond") -> tr("errProviderTimeout")
                                rawErr.isNotEmpty() -> rawErr
                                else -> tr("errUnlockFailed")
                            }
                            addHistory(profile, tr("remoteLogin"), false)
                        }
                    }
                }
            }

            if (!useManualPassword && !requiresPhonePin) {
                UnlockCrypto.confirmUserPresence(
                    activity = this@MainActivity,
                    title = tr("unlockSheetTitle"),
                    subtitle = "${tr("biometricConfirmSub")} ${profile.name}",
                    cancelLabel = tr("cancel"),
                    onVerified = { proceedToUnlock() },
                    onCancelled = { reason ->
                        stepState = 0
                        errorMsg = reason
                    }
                )
            } else {
                proceedToUnlock()
            }
        }

        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(26.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier
                        .padding(20.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            contentAlignment = Alignment.Center,
                            modifier = Modifier
                                .size(42.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(palette.accent.copy(alpha = 0.16f))
                        ) {
                            Icon(
                                painter = painterResource(R.drawable.ic_log_in),
                                contentDescription = null,
                                tint = palette.accent,
                                modifier = Modifier.size(22.dp)
                            )
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = tr("unlockSheetTitle"),
                                color = palette.textPrimary,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = profile.name,
                                color = palette.textSecondary,
                                fontSize = 12.sp
                            )
                        }
                    }

                    // Mandatory Pre-Setup Warning Notice
                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = palette.warning.copy(alpha = 0.12f),
                        border = BorderStroke(1.dp, palette.warning.copy(alpha = 0.4f))
                    ) {
                        Text(
                            text = tr("unlockSheetWarning"),
                            color = palette.textPrimary,
                            fontSize = 11.5.sp,
                            lineHeight = 16.sp,
                            modifier = Modifier.padding(12.dp)
                        )
                    }

                    if (enrollMeta == null) {
                        Button(
                            onClick = onOpenEnroll,
                            colors = ButtonDefaults.buttonColors(containerColor = palette.warning),
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(
                                text = tr("unlockBindBtn"),
                                color = Color(0xFF101014),
                                fontWeight = FontWeight.Bold
                            )
                        }
                    } else {
                        // Mode Selector: Phone PIN / Split-Key + Biometrics vs Manual E2E Windows Password entry
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .background(palette.surface2)
                                .padding(4.dp)
                        ) {
                            if (hasSplitKeyVault) {
                                Box(
                                    contentAlignment = Alignment.Center,
                                    modifier = Modifier
                                        .weight(1f)
                                        .height(36.dp)
                                        .clip(RoundedCornerShape(9.dp))
                                        .background(if (!useManualPassword) palette.accent else Color.Transparent)
                                        .clickable { useManualPassword = false }
                                ) {
                                    Text(
                                        text = if (requiresPhonePin) tr("unlockTabPin") else tr("unlockTabBio"),
                                        color = if (!useManualPassword) Color.White else palette.textPrimary,
                                        fontSize = 11.5.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier
                                    .weight(1f)
                                    .height(36.dp)
                                    .clip(RoundedCornerShape(9.dp))
                                    .background(if (useManualPassword) palette.accent else Color.Transparent)
                                    .clickable { useManualPassword = true }
                            ) {
                                Text(
                                    text = tr("unlockTabPassword"),
                                    color = if (useManualPassword) Color.White else palette.textPrimary,
                                    fontSize = 11.5.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }

                        AnimatedVisibility(visible = !useManualPassword && requiresPhonePin) {
                            OutlinedTextField(
                                value = phonePinInput,
                                onValueChange = { phonePinInput = it },
                                label = { Text(tr("phonePinLabel")) },
                                placeholder = { Text(tr("phonePinPlaceholder")) },
                                singleLine = true,
                                visualTransformation = if (showPhonePin) VisualTransformation.None else PasswordVisualTransformation(),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                                trailingIcon = {
                                    TextButton(onClick = { showPhonePin = !showPhonePin }) {
                                        Text(if (showPhonePin) tr("hide") else tr("show"), fontSize = 11.sp)
                                    }
                                },
                                modifier = Modifier.fillMaxWidth()
                            )
                        }

                        AnimatedVisibility(visible = useManualPassword) {
                            OutlinedTextField(
                                value = passwordInput,
                                onValueChange = { passwordInput = it },
                                label = { Text(tr("winAccountPasswordLabel")) },
                                placeholder = { Text(tr("winAccountPasswordPlaceholder")) },
                                singleLine = true,
                                visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                                trailingIcon = {
                                    TextButton(onClick = { showPassword = !showPassword }) {
                                        Text(if (showPassword) tr("hide") else tr("show"), fontSize = 11.sp)
                                    }
                                },
                                modifier = Modifier.fillMaxWidth()
                            )
                        }

                        // 3-Step Cryptographic Progress Stepper
                        Surface(
                            shape = RoundedCornerShape(14.dp),
                            color = palette.surface2
                        ) {
                            Column(
                                modifier = Modifier.padding(12.dp),
                                verticalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                StepRow(palette, tr("unlockStep1"), active = stepState == 1, done = stepState > 1)
                                StepRow(palette, tr("unlockStep2"), active = stepState == 2, done = stepState > 2)
                                StepRow(palette, tr("unlockStep3"), active = stepState == 3, done = stepState > 3)
                            }
                        }

                        if (errorMsg.isNotEmpty()) {
                            Text(text = errorMsg, color = palette.danger, fontSize = 12.sp)
                        }
                        if (successMsg.isNotEmpty()) {
                            Text(text = "✓ $successMsg", color = palette.success, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                        }

                        Button(
                            onClick = { executeUnlockFlow() },
                            enabled = stepState == 0 || stepState == 4,
                            colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(
                                text = tr("unlockActionBtn"),
                                color = Color.White,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(vertical = 4.dp)
                            )
                        }
                    }

                    // Secondary RDP Client handoff
                    OutlinedButton(
                        onClick = onOpenRdp,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(text = tr("unlockRdpFallback"), color = palette.textPrimary, fontSize = 12.5.sp)
                    }

                    TextButton(
                        onClick = onDismiss,
                        modifier = Modifier.align(Alignment.End)
                    ) {
                        Text(text = tr("cancel"), color = palette.textSecondary)
                    }
                }
            }
        }
    }

    @Composable
    private fun StepRow(palette: RemoteThemePalette, label: String, active: Boolean, done: Boolean) {
        val color = when {
            done -> palette.success
            active -> palette.accent
            else -> palette.textSecondary
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = when {
                    done -> "✓"
                    active -> "◉"
                    else -> "○"
                },
                color = color,
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text = label,
                color = color,
                fontSize = 11.5.sp,
                fontWeight = if (active || done) FontWeight.SemiBold else FontWeight.Normal
            )
        }
    }

    @Composable
    private fun EnrollWindowsUnlockModal(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel?,
        initialCode: String,
        onDismiss: () -> Unit
    ) {
        var codeInput by remember(initialCode) { mutableStateOf(initialCode) }
        val parsedPreview = remember(codeInput) { UnlockCrypto.parseEnrollCode(codeInput) }
        var hostOverride by remember { mutableStateOf("") }
        LaunchedEffect(parsedPreview?.host) {
            val h = parsedPreview?.host.orEmpty()
            if (h.isNotEmpty()) {
                hostOverride = if (h.startsWith("172.") && profile != null && profile.host.isNotEmpty() && !profile.host.startsWith("172.")) {
                    profile.host
                } else {
                    h
                }
            }
        }
        var statusError by remember { mutableStateOf("") }

        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier
                        .padding(20.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(11.dp)
                ) {
                    Text(
                        text = tr("unlockBindBtn"),
                        color = palette.textPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = tr("enrollInstructions"),
                        color = palette.textSecondary,
                        fontSize = 12.sp,
                        lineHeight = 16.5.sp
                    )
                    var showEnrollHost by remember { mutableStateOf(false) }
                    OutlinedTextField(
                        value = codeInput,
                        onValueChange = { codeInput = it },
                        placeholder = { Text(tr("importPlaceholder")) },
                        minLines = 3,
                        maxLines = 4,
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (parsedPreview != null) {
                        OutlinedTextField(
                            value = hostOverride,
                            onValueChange = { hostOverride = it },
                            label = { Text(tr("hostLabel")) },
                            placeholder = { Text(tr("hostHint")) },
                            singleLine = true,
                            visualTransformation = if (showEnrollHost) VisualTransformation.None else PasswordVisualTransformation(),
                            trailingIcon = {
                                TextButton(onClick = { showEnrollHost = !showEnrollHost }) {
                                    Text(if (showEnrollHost) tr("hide") else tr("show"), fontSize = 11.sp)
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        )
                        if (hostOverride.startsWith("172.")) {
                            Text(
                                text = tr("enrollSubnetWarning"),
                                color = palette.warning,
                                fontSize = 11.5.sp,
                                lineHeight = 15.sp
                            )
                        }
                    }
                    if (statusError.isNotEmpty()) {
                        Text(text = statusError, color = palette.danger, fontSize = 12.sp)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TextButton(onClick = onDismiss) {
                            Text(text = tr("cancel"), color = palette.textSecondary)
                        }
                        Spacer(Modifier.width(8.dp))
                        Button(
                            onClick = {
                                importCodeOrUri(codeInput, hostOverride) { ok, msg ->
                                    if (ok) onDismiss()
                                    else statusError = msg
                                }
                            },
                            enabled = !busyState,
                            colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text(text = tr("pairActionBtn"), color = Color.White, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }

    // =========================================================================
    // TIMER MODAL & POWER HOLD-TO-CONFIRM MODAL
    // =========================================================================

    @Composable
    private fun TimerSheetModal(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel,
        onDismiss: () -> Unit
    ) {
        var minutes by remember { mutableFloatStateOf(30f) }

        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = tr("timer"),
                        color = palette.textPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "${minutes.roundToInt()} ${tr("minutes")}",
                        color = palette.warning,
                        fontSize = 26.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace
                    )
                    Slider(
                        value = minutes,
                        onValueChange = { minutes = it },
                        valueRange = 1f..180f
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        listOf(15, 30, 60, 120).forEach { preset ->
                            SmallDeckChip(Modifier.weight(1f), palette, "$preset ${tr("minutes")}") {
                                minutes = preset.toFloat()
                            }
                        }
                    }
                    Text(
                        text = tr("timerWarning"),
                        color = palette.textSecondary,
                        fontSize = 11.5.sp
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        OutlinedButton(
                            onClick = {
                                runRpc(profile, JSONObject().put("action", "timer.cancel"), tr("cancelTimer"))
                                onDismiss()
                            },
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text(text = tr("cancelTimer"), color = palette.danger, fontSize = 12.sp)
                        }
                        Button(
                            onClick = {
                                runRpc(
                                    profile,
                                    JSONObject().put("action", "timer.set").put("minutes", minutes.roundToInt()),
                                    tr("timer")
                                )
                                onDismiss()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text(text = tr("schedule"), color = Color.White, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun PowerHoldSheetModal(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel,
        onDismiss: () -> Unit
    ) {
        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    Text(
                        text = tr("powerTitle"),
                        color = palette.textPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = tr("holdHint"),
                        color = palette.textSecondary,
                        fontSize = 12.sp
                    )

                    HoldToConfirmPowerButton(
                        palette = palette,
                        title = tr("restartTitle"),
                        subtitle = tr("restartSub"),
                        barColor = palette.warning
                    ) {
                        runRpc(
                            profile,
                            JSONObject().put("action", "command").put("command", "restart"),
                            historyLabel = tr("restartTitle")
                        )
                        onDismiss()
                    }

                    HoldToConfirmPowerButton(
                        palette = palette,
                        title = tr("shutdownTitle"),
                        subtitle = tr("shutdownSub"),
                        barColor = palette.danger
                    ) {
                        runRpc(
                            profile,
                            JSONObject().put("action", "command").put("command", "shutdown"),
                            historyLabel = tr("shutdownTitle")
                        )
                        onDismiss()
                    }

                    TextButton(
                        onClick = onDismiss,
                        modifier = Modifier.align(Alignment.End)
                    ) {
                        Text(text = tr("cancel"), color = palette.textSecondary)
                    }
                }
            }
        }
    }

    @Composable
    private fun HoldToConfirmPowerButton(
        palette: RemoteThemePalette,
        title: String,
        subtitle: String,
        barColor: Color,
        onConfirmed: () -> Unit
    ) {
        var holding by remember { mutableStateOf(false) }
        var progress by remember { mutableFloatStateOf(0f) }

        LaunchedEffect(holding) {
            if (holding) {
                val start = System.currentTimeMillis()
                while (holding) {
                    val elapsed = System.currentTimeMillis() - start
                    progress = (elapsed / 1200f).coerceIn(0f, 1f)
                    if (progress >= 1f) {
                        holding = false
                        progress = 0f
                        onConfirmed()
                        break
                    }
                    delay(16L)
                }
            } else {
                progress = 0f
            }
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(58.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(palette.surface2)
                .border(1.dp, barColor.copy(alpha = 0.45f), RoundedCornerShape(16.dp))
                .pointerInput(Unit) {
                    detectTapGestures(
                        onPress = {
                            holding = true
                            tryAwaitRelease()
                            holding = false
                        }
                    )
                }
        ) {
            Box(
                modifier = Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(progress)
                    .background(barColor.copy(alpha = 0.35f))
            )
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = title,
                        color = palette.textPrimary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = subtitle,
                        color = palette.textSecondary,
                        fontSize = 11.sp
                    )
                }
                Text(
                    text = if (holding) "${(progress * 100).roundToInt()}%" else tr("holdBadge"),
                    color = barColor,
                    fontSize = 11.5.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
    }

    // =========================================================================
    // ONBOARDING, DEVICE EDITOR, IMPORT & RDP MODALS
    // =========================================================================

    @Composable
    private fun EmptyDeviceOnboardingCard(
        palette: RemoteThemePalette,
        onAddDevice: () -> Unit,
        onImportCode: () -> Unit
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier
                    .size(72.dp)
                    .clip(RoundedCornerShape(22.dp))
                    .background(palette.accent.copy(alpha = 0.15f))
            ) {
                Icon(
                    painter = painterResource(R.drawable.ic_devices_tab),
                    contentDescription = null,
                    tint = palette.accent,
                    modifier = Modifier.size(36.dp)
                )
            }
            Spacer(Modifier.height(18.dp))
            Text(
                text = tr("onboardingTitle"),
                color = palette.textPrimary,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = tr("onboardingSubtitle"),
                color = palette.textSecondary,
                fontSize = 13.5.sp,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(22.dp))
            Button(
                onClick = onAddDevice,
                colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = tr("addProfileTitle") }
            ) {
                Text(
                    text = tr("addProfileTitle"),
                    color = Color.White,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(vertical = 4.dp)
                )
            }
            Spacer(Modifier.height(10.dp))
            OutlinedButton(
                onClick = onImportCode,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = tr("importProfileTitle"),
                    color = palette.textPrimary,
                    fontSize = 14.sp
                )
            }
        }
    }

    @Composable
    private fun DeviceEditorModal(
        palette: RemoteThemePalette,
        editIndex: Int,
        onDismiss: () -> Unit
    ) {
        val existing = if (editIndex >= 0 && editIndex < profilesState.size) profilesState[editIndex] else null
        var name by remember { mutableStateOf(existing?.name ?: "") }
        var host by remember { mutableStateOf(existing?.host ?: "") }
        var port by remember { mutableStateOf(existing?.port ?: "8765") }
        var pin by remember { mutableStateOf(existing?.pin ?: "") }
        var showHost by remember { mutableStateOf(existing == null) }
        var showPin by remember { mutableStateOf(false) }
        var errorText by remember { mutableStateOf("") }

        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier
                        .padding(20.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(
                        text = tr(if (existing == null) "addProfileTitle" else "edit"),
                        color = palette.textPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )

                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text(tr("profileNameLabel")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = host,
                        onValueChange = { host = it },
                        label = { Text(tr("hostLabel")) },
                        placeholder = { Text(tr("hostHint")) },
                        singleLine = true,
                        visualTransformation = if (showHost) VisualTransformation.None else PasswordVisualTransformation(),
                        trailingIcon = {
                            if (host.isNotEmpty()) {
                                TextButton(onClick = { showHost = !showHost }) {
                                    Text(if (showHost) tr("hide") else tr("show"), fontSize = 11.sp)
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = port,
                        onValueChange = { port = it },
                        label = { Text(tr("portLabel")) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = pin,
                        onValueChange = { pin = it },
                        label = { Text("${tr("pinHint")} (PIN)") },
                        placeholder = { Text(tr("pinPlaceholder")) },
                        singleLine = true,
                        visualTransformation = if (showPin) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        trailingIcon = {
                            if (pin.isNotEmpty()) {
                                TextButton(onClick = { showPin = !showPin }) {
                                    Text(if (showPin) tr("hide") else tr("show"), fontSize = 11.sp)
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    )

                    if (errorText.isNotEmpty()) {
                        Text(text = errorText, color = palette.danger, fontSize = 12.sp)
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        if (existing != null) {
                            TextButton(
                                onClick = {
                                    val mutable = profilesState.toMutableList()
                                    mutable.removeAt(editIndex)
                                    profilesState = mutable
                                    selectedProfileIndex = selectedProfileIndex.coerceIn(0, (mutable.size - 1).coerceAtLeast(0))
                                    clients.remove(existing.id)
                                    statusesMap.remove(existing.id)
                                    persistProfilesToPrefs()
                                    onDismiss()
                                }
                            ) {
                                Text(text = tr("deleteProfileTitle"), color = palette.danger)
                            }
                        } else {
                            Spacer(Modifier.width(4.dp))
                        }

                        Row {
                            TextButton(onClick = onDismiss) {
                                Text(text = tr("cancel"), color = palette.textSecondary)
                            }
                            Spacer(Modifier.width(6.dp))
                            Button(
                                onClick = {
                                    val cleanHost = host.trim()
                                    val cleanPort = port.trim().ifEmpty { "8765" }
                                    try {
                                        RemoteClient(cleanHost, cleanPort, pin)
                                        if (!cleanHost.startsWith("http")) {
                                            val portNum = cleanPort.toInt()
                                            if (portNum !in 1..65535) throw Exception("invalidAddress")
                                        }
                                        if (pin.isEmpty()) throw Exception("pinRequired")
                                    } catch (e: Exception) {
                                        errorText = tr(e.message ?: "invalidAddress")
                                        return@Button
                                    }
                                    val model = DeviceProfileModel(
                                        id = existing?.id ?: UUID.randomUUID().toString(),
                                        name = name.trim().ifEmpty { tr("defaultProfileName") },
                                        host = cleanHost,
                                        port = cleanPort,
                                        pin = pin,
                                        mac = existing?.mac ?: ""
                                    )
                                    val mutable = profilesState.toMutableList()
                                    if (existing == null) {
                                        mutable.add(model)
                                        selectedProfileIndex = mutable.size - 1
                                    } else {
                                        mutable[editIndex] = model
                                        clients.remove(existing.id)
                                        statusesMap.remove(existing.id)
                                    }
                                    profilesState = mutable
                                    persistProfilesToPrefs()
                                    onDismiss()
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                                shape = RoundedCornerShape(12.dp),
                                modifier = Modifier.semantics { contentDescription = tr("saveProfileTitle") }
                            ) {
                                Text(
                                    text = tr("saveProfileTitle"),
                                    color = Color.White,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun ImportCodeModal(
        palette: RemoteThemePalette,
        initialCode: String,
        onDismiss: () -> Unit
    ) {
        var rawCode by remember { mutableStateOf(initialCode) }
        var errorMsg by remember { mutableStateOf("") }

        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = tr("importProfileTitle"),
                        color = palette.textPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = tr("importProfileMessage"),
                        color = palette.textSecondary,
                        fontSize = 12.sp
                    )
                    OutlinedTextField(
                        value = rawCode,
                        onValueChange = { rawCode = it },
                        placeholder = { Text(tr("importPlaceholder")) },
                        minLines = 3,
                        maxLines = 5,
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (errorMsg.isNotEmpty()) {
                        Text(text = errorMsg, color = palette.danger, fontSize = 12.sp)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(onClick = onDismiss) {
                            Text(text = tr("cancel"), color = palette.textSecondary)
                        }
                        Spacer(Modifier.width(8.dp))
                        Button(
                            onClick = {
                                importCodeOrUri(rawCode) { ok, msg ->
                                    if (ok) onDismiss()
                                    else errorMsg = msg
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text(text = tr("importProfileAction"), color = Color.White, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun RdpConfigModal(
        palette: RemoteThemePalette,
        profile: DeviceProfileModel,
        initialRdp: JSONObject,
        onDismiss: () -> Unit
    ) {
        var rdpHost by remember { mutableStateOf(initialRdp.optString("host", profile.host)) }
        var rdpPort by remember { mutableStateOf(initialRdp.optString("port", "3389")) }
        var rdpUser by remember { mutableStateOf(initialRdp.optString("username", "")) }
        var rdpGateway by remember { mutableStateOf(initialRdp.optString("gateway", "")) }
        var showRdpSensitive by remember { mutableStateOf(false) }
        var err by remember { mutableStateOf("") }

        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier
                        .padding(20.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(
                        text = "RDP (${profile.name})",
                        color = palette.textPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = tr("rdpSimple"),
                        color = palette.textSecondary,
                        fontSize = 12.sp
                    )
                    OutlinedTextField(
                        value = rdpHost,
                        onValueChange = { rdpHost = it },
                        label = { Text(tr("rdpAddress")) },
                        singleLine = true,
                        visualTransformation = if (showRdpSensitive) VisualTransformation.None else PasswordVisualTransformation(),
                        trailingIcon = {
                            if (rdpHost.isNotEmpty()) {
                                TextButton(onClick = { showRdpSensitive = !showRdpSensitive }) {
                                    Text(if (showRdpSensitive) tr("hide") else tr("show"), fontSize = 11.sp)
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = rdpPort,
                        onValueChange = { rdpPort = it },
                        label = { Text(tr("portLabel")) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = rdpUser,
                        onValueChange = { rdpUser = it },
                        label = { Text(tr("rdpUser")) },
                        singleLine = true,
                        visualTransformation = if (showRdpSensitive) VisualTransformation.None else PasswordVisualTransformation(),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = rdpGateway,
                        onValueChange = { rdpGateway = it },
                        label = { Text("RD Gateway (${tr("optional")})") },
                        singleLine = true,
                        visualTransformation = if (showRdpSensitive) VisualTransformation.None else PasswordVisualTransformation(),
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (err.isNotEmpty()) {
                        Text(text = err, color = palette.danger, fontSize = 12.sp)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        TextButton(onClick = {
                            prefs.edit().remove("rdp_${profile.id}").apply()
                            onDismiss()
                        }) {
                            Text(text = tr("usePcSettings"), color = palette.textSecondary, fontSize = 12.sp)
                        }
                        Button(
                            onClick = {
                                val portNum = rdpPort.trim().toIntOrNull() ?: 0
                                val addr = rdpHost.trim()
                                if (addr.isEmpty() || addr.contains("/") || addr.contains(" ") || portNum !in 1..65535) {
                                    err = tr("invalidAddress")
                                    return@Button
                                }
                                val saved = JSONObject()
                                    .put("host", addr)
                                    .put("port", portNum)
                                    .put("username", rdpUser.trim())
                                    .put("gateway", rdpGateway.trim())
                                prefs.edit().putString("rdp_${profile.id}", saved.toString()).apply()
                                onDismiss()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = palette.accent),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text(text = tr("saveProfileTitle"), color = Color.White, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun QuickDevicePickerModal(
        palette: RemoteThemePalette,
        onAddDevice: () -> Unit,
        onDismiss: () -> Unit
    ) {
        Dialog(onDismissRequest = onDismiss) {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = palette.surface1,
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = tr("profilesTitle"),
                        color = palette.textPrimary,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold
                    )
                    profilesState.forEachIndexed { idx, p ->
                        val selected = idx == selectedProfileIndex
                        Surface(
                            shape = RoundedCornerShape(14.dp),
                            color = if (selected) palette.accent.copy(alpha = 0.14f) else palette.surface2,
                            border = BorderStroke(1.dp, if (selected) palette.accent else palette.border),
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    selectedProfileIndex = idx
                                    persistProfilesToPrefs()
                                    onDismiss()
                                }
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = p.name,
                                    color = palette.textPrimary,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.weight(1f)
                                )
                                Text(
                                    text = if (selected) "✓ ${tr("selectedDeviceTitle")}" else tr("online"),
                                    color = palette.textSecondary,
                                    fontSize = 11.5.sp
                                )
                            }
                        }
                    }
                    TextButton(onClick = onAddDevice, modifier = Modifier.align(Alignment.End)) {
                        Text(text = "+ ${tr("addProfileTitle")}", color = palette.accent, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }

    private fun formatDuration(seconds: Long): String {
        val hours = seconds / 3600
        val d = tr("unitDay")
        val h = tr("unitHour")
        val m = tr("unitMinShort")
        return when {
            hours >= 24 -> "${hours / 24}$d ${hours % 24}$h"
            hours > 0 -> "${hours}$h ${(seconds % 3600) / 60}$m"
            else -> "${seconds / 60}$m"
        }
    }

    private fun formatSize(bytes: Long): String {
        return when {
            bytes >= 1048576 -> String.format(Locale.ROOT, "%.1f %s", bytes / 1048576.0, tr("unitMb"))
            bytes >= 1024 -> String.format(Locale.ROOT, "%.1f %s", bytes / 1024.0, tr("unitKb"))
            else -> "$bytes ${tr("unitByte")}"
        }
    }
}
