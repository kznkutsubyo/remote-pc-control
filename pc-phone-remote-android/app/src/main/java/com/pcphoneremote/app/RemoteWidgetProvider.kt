package com.pcphoneremote.app

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.widget.RemoteViews
import org.json.JSONObject

class RemoteWidgetProvider : AppWidgetProvider() {
    companion object {
        private const val ACTION_LOCK = "com.pcphoneremote.app.WIDGET_LOCK"
        private const val ACTION_PLAY = "com.pcphoneremote.app.WIDGET_PLAY_PAUSE"
        private const val ACTION_MUTE = "com.pcphoneremote.app.WIDGET_MUTE"
        private const val ACTION_SCREEN_OFF = "com.pcphoneremote.app.WIDGET_SCREEN_OFF"

        fun updateAllWidgets(context: Context) {
            val mgr = AppWidgetManager.getInstance(context)
            val ids = mgr.getAppWidgetIds(ComponentName(context, RemoteWidgetProvider::class.java))
            if (ids != null && ids.isNotEmpty()) {
                for (id in ids) updateWidget(context, mgr, id)
            }
        }

        private fun pendingBroadcast(context: Context, action: String, reqCode: Int): PendingIntent {
            val intent = Intent(context, RemoteWidgetProvider::class.java).setAction(action)
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0
            return PendingIntent.getBroadcast(context, reqCode, intent, flags)
        }

        private fun pendingOpenApp(context: Context): PendingIntent {
            val intent = Intent(context, MainActivity::class.java)
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0
            return PendingIntent.getActivity(context, 100, intent, flags)
        }

        fun updateWidget(context: Context, mgr: AppWidgetManager, widgetId: Int) {
            val views = RemoteViews(context.packageName, R.layout.widget_remote)
            val pcName = QuickCommandDispatcher.activeProfile(context)?.optString("name", "PC Phone Remote") ?: "PC Phone Remote"
            views.setTextViewText(R.id.widgetTitle, pcName)
            views.setOnClickPendingIntent(R.id.widgetTitle, pendingOpenApp(context))
            views.setOnClickPendingIntent(R.id.widgetBtnLock, pendingBroadcast(context, ACTION_LOCK, 1))
            views.setOnClickPendingIntent(R.id.widgetBtnPlay, pendingBroadcast(context, ACTION_PLAY, 2))
            views.setOnClickPendingIntent(R.id.widgetBtnMute, pendingBroadcast(context, ACTION_MUTE, 3))
            views.setOnClickPendingIntent(R.id.widgetBtnScreenOff, pendingBroadcast(context, ACTION_SCREEN_OFF, 4))
            mgr.updateAppWidget(widgetId, views)
        }
    }

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (id in appWidgetIds) updateWidget(context, appWidgetManager, id)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            ACTION_LOCK -> QuickCommandDispatcher.send(context, JSONObject().put("action", "command").put("command", "lock"), "Locked")
            ACTION_PLAY -> QuickCommandDispatcher.send(context, JSONObject().put("action", "media").put("key", "play_pause"), "Play / Pause")
            ACTION_MUTE -> QuickCommandDispatcher.send(context, JSONObject().put("action", "media").put("key", "mute"), "Mute")
            ACTION_SCREEN_OFF -> QuickCommandDispatcher.send(context, JSONObject().put("action", "display.off"), "Screen Off")
        }
    }
}
