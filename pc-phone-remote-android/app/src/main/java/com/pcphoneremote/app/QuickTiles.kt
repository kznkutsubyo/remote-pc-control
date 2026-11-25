package com.pcphoneremote.app

import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import androidx.annotation.RequiresApi
import org.json.JSONObject

@RequiresApi(Build.VERSION_CODES.N)
class LockPcTileService : TileService() {
    override fun onStartListening() {
        super.onStartListening()
        qsTile?.let {
            val name = QuickCommandDispatcher.activeProfile(this)?.optString("name", "PC") ?: "PC"
            it.label = "Lock $name"
            it.state = Tile.STATE_INACTIVE
            it.updateTile()
        }
    }

    override fun onClick() {
        super.onClick()
        QuickCommandDispatcher.send(
            this,
            JSONObject().put("action", "command").put("command", "lock"),
            "Locked"
        )
    }
}

@RequiresApi(Build.VERSION_CODES.N)
class PlayPauseTileService : TileService() {
    override fun onStartListening() {
        super.onStartListening()
        qsTile?.let {
            it.label = "Play / Pause PC"
            it.state = Tile.STATE_INACTIVE
            it.updateTile()
        }
    }

    override fun onClick() {
        super.onClick()
        QuickCommandDispatcher.send(
            this,
            JSONObject().put("action", "media").put("key", "play_pause"),
            "Play / Pause"
        )
    }
}

@RequiresApi(Build.VERSION_CODES.N)
class ScreenOffTileService : TileService() {
    override fun onStartListening() {
        super.onStartListening()
        qsTile?.let {
            it.label = "Screen Off PC"
            it.state = Tile.STATE_INACTIVE
            it.updateTile()
        }
    }

    override fun onClick() {
        super.onClick()
        QuickCommandDispatcher.send(
            this,
            JSONObject().put("action", "display.off"),
            "Screen Off"
        )
    }
}
