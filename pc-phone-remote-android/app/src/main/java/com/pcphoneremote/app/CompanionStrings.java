package com.pcphoneremote.app;

import java.util.HashMap;
import java.util.Map;

final class CompanionStrings {
    private static final Map<String, String[]> TEXT = new HashMap<>();
    private static final Map<String, String> LOCALIZED = new HashMap<>();
    private static final String[] KEYS = {"exchange","tabRemote","tabDevices","tabSettings","remoteLogin","timer","media","recent","sharedFiles","sharedText","sendFile","refresh","download","memory","uptime","online","done","edit","motionTitle","copyText"};
    static {
        put("exchange", "Transfer", "\u041e\u0431\u043c\u0435\u043d");
        put("idle", "Everything within reach", "\u0412\u0441\u0451 \u043f\u043e\u0434 \u0440\u0443\u043a\u043e\u0439");
        put("notChecked", "Refresh to connect", "\u041d\u0430\u0436\u043c\u0438 \u043e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0434\u043b\u044f \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f");
        put("online", "Connected", "\u041d\u0430 \u0441\u0432\u044f\u0437\u0438");
        put("sessionLocked", "Connected \u00b7 Windows locked", "\u041d\u0430 \u0441\u0432\u044f\u0437\u0438 \u00b7 Windows \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u0430");
        put("memory", "Memory", "\u041f\u0430\u043c\u044f\u0442\u044c");
        put("uptime", "Uptime", "\u0412\u0440\u0435\u043c\u044f \u0440\u0430\u0431\u043e\u0442\u044b");
        put("remoteLogin", "Windows sign-in", "\u0412\u0445\u043e\u0434 \u0432 Windows");
        put("timer", "Power timer", "\u0422\u0430\u0439\u043c\u0435\u0440");
        put("media", "Media & sound", "\u041c\u0443\u0437\u044b\u043a\u0430 \u0438 \u0437\u0432\u0443\u043a");
        put("recent", "Recent activity", "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f");
        put("previous", "Previous track", "\u041f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0438\u0439 \u0442\u0440\u0435\u043a");
        put("next", "Next track", "\u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0442\u0440\u0435\u043a");
        put("play_pause", "Play / pause", "\u0412\u043e\u0441\u043f\u0440\u043e\u0438\u0437\u0432\u0435\u0434\u0435\u043d\u0438\u0435 / \u043f\u0430\u0443\u0437\u0430");
        put("volume_up", "Volume up", "\u0413\u0440\u043e\u043c\u0447\u0435");
        put("volume_down", "Volume down", "\u0422\u0438\u0448\u0435");
        put("mute", "Toggle mute", "\u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c / \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0437\u0432\u0443\u043a");
        put("minutes", "min", "\u043c\u0438\u043d");
        put("timerWarning", "Windows forcibly closes apps when the timer expires. Save your work before scheduling. You can cancel the timer.", "Windows \u0437\u0430\u043a\u0440\u043e\u0435\u0442 \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u044b \u043f\u0440\u0438\u043d\u0443\u0434\u0438\u0442\u0435\u043b\u044c\u043d\u043e \u043f\u043e \u0442\u0430\u0439\u043c\u0435\u0440\u0443. \u0421\u043e\u0445\u0440\u0430\u043d\u0438 \u0440\u0430\u0431\u043e\u0442\u0443 \u043f\u0435\u0440\u0435\u0434 \u0437\u0430\u043f\u0443\u0441\u043a\u043e\u043c. \u0422\u0430\u0439\u043c\u0435\u0440 \u043c\u043e\u0436\u043d\u043e \u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c.");
        put("cancelTimer", "Cancel timer", "\u041e\u0442\u043c\u0435\u043d\u0438\u0442\u044c \u0442\u0430\u0439\u043c\u0435\u0440");
        put("schedule", "Schedule", "\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c");
        put("refresh", "Refresh", "\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c");
        put("rdpExplanation", "Open an RDP client for normal Windows sign-in. Requires a supported Windows edition (Pro / Enterprise), Remote Desktop enabled, and a reachable PC or RD Gateway. Enter your password in the RDP client. The PC's physical screen remains locked; this app's relay does not tunnel RDP.", "\u041e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f RDP-\u043a\u043b\u0438\u0435\u043d\u0442 \u0434\u043b\u044f \u043e\u0431\u044b\u0447\u043d\u043e\u0433\u043e \u0432\u0445\u043e\u0434\u0430 \u0432 Windows. \u041d\u0443\u0436\u043d\u044b \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u043c\u0430\u044f \u0440\u0435\u0434\u0430\u043a\u0446\u0438\u044f Windows (Pro / Enterprise), \u0432\u043a\u043b\u044e\u0447\u0451\u043d\u043d\u044b\u0439 \u0443\u0434\u0430\u043b\u0451\u043d\u043d\u044b\u0439 \u0440\u0430\u0431\u043e\u0447\u0438\u0439 \u0441\u0442\u043e\u043b \u0438 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0439 \u0430\u0434\u0440\u0435\u0441 \u041f\u041a \u0438\u043b\u0438 RD Gateway. \u041f\u0430\u0440\u043e\u043b\u044c \u0432\u0432\u043e\u0434\u0438\u0442\u0441\u044f \u0432 RDP-\u043a\u043b\u0438\u0435\u043d\u0442\u0435. \u0424\u0438\u0437\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u044d\u043a\u0440\u0430\u043d \u041f\u041a \u043e\u0441\u0442\u0430\u043d\u0435\u0442\u0441\u044f \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u043c; relay \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f RDP \u043d\u0435 \u043f\u0435\u0440\u0435\u0434\u0430\u0451\u0442.");
        put("rdpMissing", "On the PC, set rdp.host in config.json, and optionally port, username and gateway. Restart the server. Use an address reachable from your phone.", "\u041d\u0430 \u041f\u041a \u0437\u0430\u043f\u043e\u043b\u043d\u0438 rdp.host \u0432 config.json, \u043f\u0440\u0438 \u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e\u0441\u0442\u0438 port, username \u0438 gateway, \u0437\u0430\u0442\u0435\u043c \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u0442\u0438 \u0441\u0435\u0440\u0432\u0435\u0440. \u0423\u043a\u0430\u0436\u0438 \u0430\u0434\u0440\u0435\u0441, \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0439 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0443.");
        put("rdpInstall", "Install Windows App or a compatible RDP client on your phone.", "\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u0438 Windows App \u0438\u043b\u0438 \u0441\u043e\u0432\u043c\u0435\u0441\u0442\u0438\u043c\u044b\u0439 RDP-\u043a\u043b\u0438\u0435\u043d\u0442 \u043d\u0430 \u0442\u0435\u043b\u0435\u0444\u043e\u043d.");
        put("openStore", "Open store", "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043c\u0430\u0433\u0430\u0437\u0438\u043d");
        put("edit", "Edit device", "\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c");
        put("invalidAddress", "Check the address and port (1\u201365535).", "\u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0430\u0434\u0440\u0435\u0441 \u0438 \u043f\u043e\u0440\u0442 (1\u201365535).");
        put("pinRequired", "Enter the server PIN.", "\u0412\u0432\u0435\u0434\u0438 PIN \u0441\u0435\u0440\u0432\u0435\u0440\u0430.");
        put("sendFile", "Send file to PC", "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0444\u0430\u0439\u043b \u043d\u0430 \u041f\u041a");
        put("fileLimit", "Up to 8 MiB per file", "\u0414\u043e 8 \u041c\u0411 \u043d\u0430 \u0444\u0430\u0439\u043b");
        put("sharedFiles", "Shared files", "\u0424\u0430\u0439\u043b\u044b \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0430");
        put("filesHint", "Refresh to see files in the PC's shared folder.", "\u041e\u0431\u043d\u043e\u0432\u0438 \u0441\u043f\u0438\u0441\u043e\u043a \u0444\u0430\u0439\u043b\u043e\u0432 \u0438\u0437 \u043f\u0430\u043f\u043a\u0438 shared \u043d\u0430 \u041f\u041a.");
        put("emptyFiles", "No shared files yet", "\u0412 \u043f\u0430\u043f\u043a\u0435 \u043f\u043e\u043a\u0430 \u043f\u0443\u0441\u0442\u043e");
        put("download", "Save to phone", "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043d\u0430 \u0442\u0435\u043b\u0435\u0444\u043e\u043d");
        put("sharedText", "Shared text", "\u041e\u0431\u0449\u0438\u0439 \u0442\u0435\u043a\u0441\u0442");
        put("textHint", "Text, link or note\u2026", "\u0422\u0435\u043a\u0441\u0442, \u0441\u0441\u044b\u043b\u043a\u0430 \u0438\u043b\u0438 \u0437\u0430\u043c\u0435\u0442\u043a\u0430\u2026");
        put("receiveText", "Receive text from PC", "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0442\u0435\u043a\u0441\u0442 \u0441 \u041f\u041a");
        put("replaceDraft", "Replace the current draft with the note from your PC?", "\u0422\u0435\u043a\u0443\u0449\u0438\u0439 \u0442\u0435\u043a\u0441\u0442 \u0431\u0443\u0434\u0435\u0442 \u0437\u0430\u043c\u0435\u043d\u0451\u043d \u0437\u0430\u043c\u0435\u0442\u043a\u043e\u0439 \u0441 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0430.");
        put("copyText", "Copy text", "\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c");
        put("copied", "Text copied", "\u0422\u0435\u043a\u0441\u0442 \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d");
        put("motionTitle", "Animations", "\u0410\u043d\u0438\u043c\u0430\u0446\u0438\u0438");
        put("clearHistory", "Clear history", "\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0438\u0441\u0442\u043e\u0440\u0438\u044e");
        put("done", "Done", "\u0413\u043e\u0442\u043e\u0432\u043e");
        put("inProgress", "An operation is in progress", "\u0414\u043e\u0436\u0434\u0438\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u0438");
        put("noHistory", "Your recent actions will appear here", "\u0417\u0434\u0435\u0441\u044c \u043f\u043e\u044f\u0432\u044f\u0442\u0441\u044f \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u043d\u044b\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b");
        put("updateServer", "Update the PC server and relay to version 2.0.", "\u041e\u0431\u043d\u043e\u0432\u0438 \u0441\u0435\u0440\u0432\u0435\u0440 \u0438 relay \u0434\u043e \u0432\u0435\u0440\u0441\u0438\u0438 2.0.");
        put("rateLimited", "Too many attempts. Wait one minute.", "\u0421\u043b\u0438\u0448\u043a\u043e\u043c \u043c\u043d\u043e\u0433\u043e \u043f\u043e\u043f\u044b\u0442\u043e\u043a. \u041f\u043e\u0434\u043e\u0436\u0434\u0438 \u043c\u0438\u043d\u0443\u0442\u0443.");
        put("fileUnavailable", "Could not open the file.", "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0444\u0430\u0439\u043b.");
        put("controlsTitle", "Quick actions", "\u0411\u044b\u0441\u0442\u0440\u044b\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f");
        put("hostLabel", "PC address / relay URL", "\u0410\u0434\u0440\u0435\u0441 \u041f\u041a / relay URL");
        put("tabRemote", "Remote", "\u041f\u0443\u043b\u044c\u0442");
        put("tabDevices", "Devices", "\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430");
        put("tabSettings", "Settings", "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438");
        put("connectionOk", "PC connected", "\u041a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442");
    }
    private static void put(String key, String en, String ru) { TEXT.put(key, new String[]{en,ru}); }
    static {
        add("uk", "\u041e\u0431\u043c\u0456\u043d", "\u041f\u0443\u043b\u044c\u0442", "\u041f\u0440\u0438\u0441\u0442\u0440\u043e\u0457", "\u041d\u0430\u043b\u0430\u0448\u0442\u0443\u0432\u0430\u043d\u043d\u044f", "\u0412\u0445\u0456\u0434 \u0443 Windows", "\u0422\u0430\u0439\u043c\u0435\u0440", "\u041c\u0443\u0437\u0438\u043a\u0430 \u0442\u0430 \u0437\u0432\u0443\u043a", "\u041e\u0441\u0442\u0430\u043d\u043d\u0456 \u0434\u0456\u0457", "\u0421\u043f\u0456\u043b\u044c\u043d\u0456 \u0444\u0430\u0439\u043b\u0438", "\u0421\u043f\u0456\u043b\u044c\u043d\u0438\u0439 \u0442\u0435\u043a\u0441\u0442", "\u041d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438 \u0444\u0430\u0439\u043b \u043d\u0430 \u041f\u041a", "\u041e\u043d\u043e\u0432\u0438\u0442\u0438", "\u0417\u0431\u0435\u0440\u0435\u0433\u0442\u0438 \u043d\u0430 \u0442\u0435\u043b\u0435\u0444\u043e\u043d", "\u041f\u0430\u043c'\u044f\u0442\u044c", "\u0427\u0430\u0441 \u0440\u043e\u0431\u043e\u0442\u0438", "\u041d\u0430 \u0437\u0432'\u044f\u0437\u043a\u0443", "\u0413\u043e\u0442\u043e\u0432\u043e", "\u0420\u0435\u0434\u0430\u0433\u0443\u0432\u0430\u0442\u0438", "\u0410\u043d\u0456\u043c\u0430\u0446\u0456\u0457", "\u041a\u043e\u043f\u0456\u044e\u0432\u0430\u0442\u0438");
        add("sk", "Prenos", "Ovl\u00e1danie", "Zariadenia", "Nastavenia", "Prihl\u00e1senie do Windows", "\u010casova\u010d", "Hudba a zvuk", "Posledn\u00e9 akcie", "Zdie\u013ean\u00e9 s\u00fabory", "Zdie\u013ean\u00fd text", "Odosla\u0165 s\u00fabor do PC", "Obnovi\u0165", "Ulo\u017ei\u0165 do telef\u00f3nu", "Pam\u00e4\u0165", "\u010cas prev\u00e1dzky", "Pripojen\u00e9", "Hotovo", "Upravi\u0165", "Anim\u00e1cie", "Kop\u00edrova\u0165");
        add("cs", "P\u0159enos", "Ovl\u00e1d\u00e1n\u00ed", "Za\u0159\u00edzen\u00ed", "Nastaven\u00ed", "P\u0159ihl\u00e1\u0161en\u00ed do Windows", "\u010casova\u010d", "Hudba a zvuk", "Posledn\u00ed akce", "Sd\u00edlen\u00e9 soubory", "Sd\u00edlen\u00fd text", "Odeslat soubor do PC", "Obnovit", "Ulo\u017eit do telefonu", "Pam\u011b\u0165", "Doba provozu", "P\u0159ipojeno", "Hotovo", "Upravit", "Animace", "Kop\u00edrovat");
        add("ja", "\u8ee2\u9001", "\u30ea\u30e2\u30b3\u30f3", "\u30c7\u30d0\u30a4\u30b9", "\u8a2d\u5b9a", "Windows\u306b\u30b5\u30a4\u30f3\u30a4\u30f3", "\u30bf\u30a4\u30de\u30fc", "\u97f3\u697d\u3068\u97f3\u91cf", "\u6700\u8fd1\u306e\u64cd\u4f5c", "\u5171\u6709\u30d5\u30a1\u30a4\u30eb", "\u5171\u6709\u30c6\u30ad\u30b9\u30c8", "PC\u306b\u30d5\u30a1\u30a4\u30eb\u3092\u9001\u4fe1", "\u66f4\u65b0", "\u7aef\u672b\u306b\u4fdd\u5b58", "\u30e1\u30e2\u30ea", "\u7a3c\u50cd\u6642\u9593", "\u63a5\u7d9a\u6e08\u307f", "\u5b8c\u4e86", "\u7de8\u96c6", "\u30a2\u30cb\u30e1\u30fc\u30b7\u30e7\u30f3", "\u30b3\u30d4\u30fc");
        add("de", "\u00dcbertragen", "Fernbedienung", "Ger\u00e4te", "Einstellungen", "Windows-Anmeldung", "Timer", "Musik und Ton", "Letzte Aktionen", "Geteilte Dateien", "Geteilter Text", "Datei an PC senden", "Aktualisieren", "Auf Handy speichern", "Speicher", "Laufzeit", "Verbunden", "Fertig", "Bearbeiten", "Animationen", "Kopieren");
        add("es", "Transferir", "Control", "Dispositivos", "Ajustes", "Acceso a Windows", "Temporizador", "M\u00fasica y sonido", "Actividad reciente", "Archivos compartidos", "Texto compartido", "Enviar archivo al PC", "Actualizar", "Guardar en el tel\u00e9fono", "Memoria", "Tiempo activo", "Conectado", "Listo", "Editar", "Animaciones", "Copiar");
        add("fr", "Transfert", "T\u00e9l\u00e9commande", "Appareils", "R\u00e9glages", "Connexion Windows", "Minuterie", "Musique et son", "Actions r\u00e9centes", "Fichiers partag\u00e9s", "Texte partag\u00e9", "Envoyer au PC", "Actualiser", "Enregistrer sur le t\u00e9l\u00e9phone", "M\u00e9moire", "Dur\u00e9e d'activit\u00e9", "Connect\u00e9", "Termin\u00e9", "Modifier", "Animations", "Copier");
        add("pl", "Przesy\u0142anie", "Pilot", "Urz\u0105dzenia", "Ustawienia", "Logowanie Windows", "Timer", "Muzyka i d\u017awi\u0119k", "Ostatnie dzia\u0142ania", "Wsp\u00f3lne pliki", "Wsp\u00f3lny tekst", "Wy\u015blij plik do PC", "Od\u015bwie\u017c", "Zapisz w telefonie", "Pami\u0119\u0107", "Czas pracy", "Po\u0142\u0105czono", "Gotowe", "Edytuj", "Animacje", "Kopiuj");
    }
    private static void add(String language, String... values) {
        for (int i=0; i<KEYS.length; i++) LOCALIZED.put(language+":"+KEYS[i], values[i]);
    }
    static {
        put("paletteTitle","Colors","\u0426\u0432\u0435\u0442\u043e\u0432\u0430\u044f \u0441\u0445\u0435\u043c\u0430"); LOCALIZED.put("uk:paletteTitle","\u041a\u043e\u043b\u044c\u043e\u0440\u043e\u0432\u0430 \u0441\u0445\u0435\u043c\u0430");
        put("violet","Violet","\u0421\u0438\u0440\u0435\u043d\u044c"); LOCALIZED.put("uk:violet","\u0411\u0443\u0437\u043e\u043a");
        put("mint","Mint","\u041c\u044f\u0442\u0430"); LOCALIZED.put("uk:mint","\u041c'\u044f\u0442\u0430");
        put("ocean","Ocean","\u041e\u043a\u0435\u0430\u043d"); LOCALIZED.put("uk:ocean","\u041e\u043a\u0435\u0430\u043d");
        put("amber","Amber","\u042f\u043d\u0442\u0430\u0440\u044c"); LOCALIZED.put("uk:amber","\u0411\u0443\u0440\u0448\u0442\u0438\u043d");
        put("rose","Rose","\u0420\u043e\u0437\u0430"); LOCALIZED.put("uk:rose","\u0422\u0440\u043e\u044f\u043d\u0434\u0430");
        put("rdpSimple","Enter the PC address. Enable Remote Desktop on Windows first. Your password is entered in the RDP client.","\u0423\u043a\u0430\u0436\u0438 \u0430\u0434\u0440\u0435\u0441 \u041f\u041a. \u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043a\u043b\u044e\u0447\u0438 \u0443\u0434\u0430\u043b\u0451\u043d\u043d\u044b\u0439 \u0440\u0430\u0431\u043e\u0447\u0438\u0439 \u0441\u0442\u043e\u043b \u0432 Windows. \u041f\u0430\u0440\u043e\u043b\u044c \u0432\u0432\u043e\u0434\u0438\u0442\u0441\u044f \u0432 RDP-\u043a\u043b\u0438\u0435\u043d\u0442\u0435."); LOCALIZED.put("uk:rdpSimple","\u0412\u043a\u0430\u0436\u0438 \u0430\u0434\u0440\u0435\u0441\u0443 \u041f\u041a. \u0421\u043f\u043e\u0447\u0430\u0442\u043a\u0443 \u0443\u0432\u0456\u043c\u043a\u043d\u0438 \u0432\u0456\u0434\u0434\u0430\u043b\u0435\u043d\u0438\u0439 \u0440\u043e\u0431\u043e\u0447\u0438\u0439 \u0441\u0442\u0456\u043b \u0443 Windows. \u041f\u0430\u0440\u043e\u043b\u044c \u0432\u0432\u043e\u0434\u0438\u0442\u044c\u0441\u044f \u0432 RDP-\u043a\u043b\u0456\u0454\u043d\u0442\u0456.");
        put("rdpAddress","Windows PC address","\u0410\u0434\u0440\u0435\u0441 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0430 Windows"); LOCALIZED.put("uk:rdpAddress","\u0410\u0434\u0440\u0435\u0441\u0430 \u043a\u043e\u043c\u043f'\u044e\u0442\u0435\u0440\u0430 Windows");
        put("rdpUser","Windows username","\u0418\u043c\u044f \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f Windows"); LOCALIZED.put("uk:rdpUser","\u0406\u043c'\u044f \u043a\u043e\u0440\u0438\u0441\u0442\u0443\u0432\u0430\u0447\u0430 Windows");
        put("optional","Optional","\u041d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e"); LOCALIZED.put("uk:optional","\u041d\u0435\u043e\u0431\u043e\u0432'\u044f\u0437\u043a\u043e\u0432\u043e");
        put("usePcSettings","Use PC settings","\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0441 \u041f\u041a"); LOCALIZED.put("uk:usePcSettings","\u041d\u0430\u043b\u0430\u0448\u0442\u0443\u0432\u0430\u043d\u043d\u044f \u0437 \u041f\u041a");
    }
    static String get(String language, String key) {
        String localized=LOCALIZED.get(language+":"+key);
        if(localized!=null)return localized;
        if(!"en".equals(language)&&!"ru".equals(language)&&(key.equals("controlsTitle")||key.equals("hostLabel")||key.equals("connectionOk"))) return null;
        String[] text = TEXT.get(key);
        return text == null ? null : text["ru".equals(language) ? 1 : 0];
    }
}
