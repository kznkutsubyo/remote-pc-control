"""Full-featured mobile Progressive Web App (iOS Safari Add-to-Home-Screen & Mobile Browser App)."""
from __future__ import annotations

import json


def pwa_manifest_bytes() -> bytes:
    """Return Web App Manifest JSON for iOS / Android standalone Home Screen installation."""
    manifest = {
        "name": "PC Phone Remote Pro",
        "short_name": "PC Remote",
        "description": "Control your Windows or Linux PC from iPhone, iPad, or any browser.",
        "start_url": "/app",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0B0B10",
        "theme_color": "#0B0B10",
        "orientation": "portrait",
        "icons": [
            {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    return json.dumps(manifest, indent=2).encode("utf-8")


def pwa_service_worker_bytes() -> bytes:
    """Return minimal network-first Service Worker for standalone PWA installability."""
    sw = """self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
"""
    return sw.encode("utf-8")


def pwa_html_bytes(authenticated: bool, hostname: str = "My PC", os_name: str = "windows") -> bytes:
    """Render the self-contained iOS & mobile PWA interface served at `/app`."""
    auth_flag = "true" if authenticated else "false"
    html_doc = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="PC Remote">
  <meta name="theme-color" content="#0B0B10">
  <link rel="manifest" href="/manifest.json">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">
  <title>PC Phone Remote Pro</title>
  <style>
    :root {{
      --bg: #0B0B10;
      --s1: #15151C;
      --s2: #1E1E28;
      --border: #282836;
      --txt: #F4F4F8;
      --muted: #9898AA;
      --accent: #8B7CFF;
      --accent2: #38BDF8;
      --ok: #3DD68C;
      --warn: #F5B14C;
      --danger: #FF5C7C;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }}
    body.light {{
      --bg: #F5F5F8;
      --s1: #FFFFFF;
      --s2: #ECEEF4;
      --border: #E0E2EC;
      --txt: #16161D;
      --muted: #646674;
      --accent: #6353E8;
      --accent2: #0284C7;
      --ok: #10B981;
      --warn: #D97706;
      --danger: #E11D48;
    }}
    * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
    html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--txt); height: 100%; overscroll-behavior: none; }}
    .shell {{
      max-width: 520px; margin: 0 auto; min-height: 100vh;
      padding-top: env(safe-area-inset-top, 12px);
      padding-bottom: calc(84px + env(safe-area-inset-bottom, 12px));
      display: flex; flex-direction: column;
    }}
    .topbar {{ display: flex; align-items: center; gap: 8px; padding: 12px 16px 8px; }}
    .pill {{
      flex: 1; display: flex; align-items: center; gap: 10px; padding: 10px 14px;
      background: var(--s1); border: 1px solid var(--border); border-radius: 999px;
    }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--muted); flex-shrink: 0; }}
    .dot.ok {{ background: var(--ok); }}
    .dot.warn {{ background: var(--warn); }}
    .pill-title {{ font-size: 14px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .pill-sub {{ font-size: 11px; color: var(--muted); }}
    .circle-btn {{
      width: 42px; height: 42px; border-radius: 50%; border: 1px solid var(--border);
      background: var(--s1); color: var(--accent); font-size: 17px; font-weight: 700;
      display: grid; place-items: center; cursor: pointer; flex-shrink: 0;
    }}
    .banner-strip {{
      padding: 2px 20px 8px; font-size: 12px; color: var(--muted);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }}
    .content {{ flex: 1; padding: 6px 16px 16px; display: flex; flex-direction: column; gap: 14px; }}
    .card {{ background: var(--s1); border: 1px solid var(--border); border-radius: 22px; padding: 16px; }}
    .card-title {{ font-size: 15px; font-weight: 700; margin: 0 0 8px; }}
    .muted {{ font-size: 12px; color: var(--muted); line-height: 1.45; }}
    .row {{ display: flex; gap: 10px; align-items: center; }}
    .grid2 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .grid3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .btn {{
      border: 1px solid var(--border); border-radius: 14px; padding: 11px 12px;
      background: var(--s2); color: var(--txt); font: inherit; font-weight: 600;
      font-size: 13px; cursor: pointer; text-align: center;
    }}
    .btn.active-seg {{ background: rgba(139,124,255,0.22); border-color: var(--accent); color: #fff; }}
    .btn-primary {{
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #fff; border: none; font-weight: 700;
    }}
    .btn-warn {{ border-color: rgba(245,177,76,0.45); color: var(--warn); }}
    .btn-danger {{ border-color: rgba(255,92,124,0.5); color: var(--danger); }}
    .gauges {{ display: flex; justify-content: space-around; margin: 14px 0; }}
    .gauge {{ text-align: center; }}
    .ring {{
      width: 74px; height: 74px; border-radius: 50%; display: grid; place-items: center;
      font-family: ui-monospace, SFMono-Regular, monospace; font-size: 15px; font-weight: 700;
      background: radial-gradient(closest-side, var(--s1) 77%, transparent 78%),
                  conic-gradient(var(--c, var(--accent)) calc(var(--p, 0) * 1%), var(--s2) 0);
    }}
    .gauge-lbl {{ font-size: 11px; color: var(--muted); margin-top: 5px; }}
    .touchpad {{
      height: 176px; border-radius: 18px; background: var(--s2); border: 1px solid var(--border);
      display: grid; place-items: center; color: var(--muted); font-size: 12px;
      touch-action: none; user-select: none; -webkit-user-select: none;
    }}
    .screen-stage {{
      width: 100%; border-radius: 14px; overflow: hidden; background: #05060a;
      border: 1px solid var(--border); min-height: 120px; display: grid; place-items: center;
      position: relative;
    }}
    .screen-stage img {{ width: 100%; display: block; cursor: crosshair; touch-action: manipulation; }}
    .chip-scroll {{ display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }}
    .chip {{
      white-space: nowrap; border-radius: 14px; padding: 9px 13px;
      background: var(--s2); border: 1px solid var(--border); color: var(--txt);
      font-size: 12.5px; font-weight: 600; cursor: pointer; flex-shrink: 0;
    }}
    input[type="text"], input[type="password"], textarea {{
      width: 100%; border-radius: 14px; border: 1px solid var(--border);
      background: var(--s2); color: var(--txt); padding: 11px 14px; font: inherit; font-size: 14px;
    }}
    input[type="range"] {{ width: 100%; accent-color: var(--accent); }}
    .tip-card {{
      background: rgba(139,124,255,0.12); border: 1px solid rgba(139,124,255,0.38);
      border-radius: 18px; padding: 12px 14px; display: flex; gap: 10px; align-items: flex-start;
    }}
    .tip-close {{ background: none; border: none; color: var(--muted); font-size: 16px; cursor: pointer; padding: 0 4px; }}
    .bottom-nav {{
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 20;
      background: var(--s1); border-top: 1px solid var(--border);
      padding: 8px 10px calc(8px + env(safe-area-inset-bottom, 0px));
      display: flex; justify-content: space-around;
    }}
    .nav-btn {{
      flex: 1; border: none; background: transparent; color: var(--muted);
      padding: 6px 4px; border-radius: 12px; font: inherit; font-size: 11px; font-weight: 600;
      display: flex; flex-direction: column; align-items: center; gap: 3px; cursor: pointer;
    }}
    .nav-btn.active {{ color: var(--accent); background: rgba(139,124,255,0.12); }}
    .hidden {{ display: none !important; }}
    .login-wrap {{ max-width: 420px; margin: 40px auto; padding: 20px; }}
    .logo-img {{ width: 54px; height: 54px; border-radius: 14px; }}
    .modal-backdrop {{
      position: fixed; inset: 0; background: rgba(0,0,0,0.72); z-index: 50;
      display: grid; place-items: center; padding: 16px; overflow-y: auto;
    }}
    .modal {{ max-width: 440px; width: 100%; background: var(--s1); border: 1px solid var(--border); border-radius: 24px; padding: 18px; max-height: 86vh; overflow-y: auto; }}
    .file-row {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); }}
  </style>
</head>
<body>
  <div id="loginView" class="login-wrap hidden">
    <div class="card">
      <div class="row" style="margin-bottom:14px;">
        <img src="/icon-192.png" class="logo-img" alt="Logo">
        <div>
          <div style="font-size:19px;font-weight:800;">PC Phone Remote Pro</div>
          <div class="muted" id="loginSubtitle">Подключение к ПК: {hostname}</div>
        </div>
      </div>
      <div class="tip-card" style="margin-bottom:14px;">
        <div style="font-size:18px;">💡</div>
        <div class="muted" id="iosInstallTip">
          <b>iPhone / iPad:</b> Нажмите в Safari кнопку <b>«Поделиться»</b> → <b>«На экран Домой»</b>, или установите нативный <code>.ipa</code> из GitHub Releases.
        </div>
      </div>
      <label class="muted" id="pinPromptLbl">Введите единый PIN-код с компьютера:</label>
      <div style="height:8px;"></div>
      <input id="loginPin" type="password" inputmode="numeric" placeholder="PIN">
      <div style="height:12px;"></div>
      <button class="btn btn-primary" style="width:100%;" id="loginBtn" onclick="doLogin()">Подключиться</button>
      <div id="loginErr" class="muted" style="color:var(--danger);margin-top:8px;"></div>
    </div>
  </div>

  <div id="appShell" class="shell hidden">
    <div class="topbar">
      <div class="pill">
        <div class="dot" id="connDot"></div>
        <div style="min-width:0;">
          <div class="pill-title" id="pcNameLbl">{hostname}</div>
          <div class="pill-sub" id="connSubLbl">Обновите статус</div>
        </div>
      </div>
      <button class="circle-btn" onclick="refreshAll()" title="Refresh">↻</button>
      <button class="circle-btn" onclick="toggleTheme()" title="Theme" id="themeIconBtn">☾</button>
    </div>
    <div class="banner-strip" id="bannerStrip">Всё под рукой</div>

    <!-- TAB 0: REMOTE -->
    <div id="tab0" class="content">
      <div id="tip0" class="tip-card hidden">
        <div>💡</div>
        <div style="flex:1;" class="muted" id="tip0Txt"></div>
        <button class="tip-close" onclick="dismissTip('0')">×</button>
      </div>
      <div class="card">
        <div class="row" style="justify-content:space-between;">
          <span class="muted" id="sessionBadgeLbl">Статус сессии</span>
          <span class="muted" id="uptimeLbl" style="font-family:monospace;"></span>
        </div>
        <div class="gauges">
          <div class="gauge">
            <div class="ring" id="cpuRing" style="--p:0;--c:var(--accent);">--</div>
            <div class="gauge-lbl">CPU</div>
          </div>
          <div class="gauge">
            <div class="ring" id="ramRing" style="--p:0;--c:var(--ok);">--</div>
            <div class="gauge-lbl" id="lblRam">RAM</div>
          </div>
          <div class="gauge">
            <div class="ring" id="diskRing" style="--p:0;--c:var(--accent2);">--</div>
            <div class="gauge-lbl" id="lblDisk">Disk</div>
          </div>
        </div>
        <button class="btn btn-primary" style="width:100%;" onclick="openUnlockModal()" id="unlockCtaBtn">🔓 Разблокировать ПК / Войти</button>
      </div>

      <div class="grid2">
        <button class="btn" onclick="sendCmd('lock')" id="btnLock">🔒 Заблокировать</button>
        <button class="btn btn-warn" onclick="sendCmd('sleep')" id="btnSleep">🌙 Сон</button>
        <button class="btn" onclick="openTimerModal()" id="btnTimer">⏱ Таймер выкл.</button>
        <button class="btn btn-danger" onclick="openPowerModal()" id="btnPower">⏻ Питание</button>
      </div>

      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:8px;">
          <div class="card-title" style="margin:0;" id="lblMedia">Медиа и звук</div>
          <button class="btn" style="padding:6px 10px;font-size:12px;" onclick="openAudioMixerModal()">🎧 Микшер</button>
        </div>
        <div class="grid3" style="margin-bottom:8px;">
          <button class="btn" onclick="sendMedia('previous')">⏮</button>
          <button class="btn btn-primary" onclick="sendMedia('play_pause')">⏯</button>
          <button class="btn" onclick="sendMedia('next')">⏭</button>
        </div>
        <div class="grid3">
          <button class="btn" onclick="sendMedia('volume_down')">🔉 -</button>
          <button class="btn" onclick="sendMedia('mute')">🔇</button>
          <button class="btn" onclick="sendMedia('volume_up')">🔊 +</button>
        </div>
      </div>

      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:8px;">
          <div class="card-title" style="margin:0;">☀ Экран и яркость</div>
          <span class="muted" id="brightPctLbl">--%</span>
        </div>
        <div id="brightSliderWrap" style="margin-bottom:10px;">
          <input type="range" id="brightRange" min="0" max="100" value="80" oninput="document.getElementById('brightPctLbl').textContent=this.value+'%'" onchange="setBrightness(this.value)">
        </div>
        <button class="btn" style="width:100%;" onclick="rpc({{action:'display.off'}})">🌑 Выключить экран (без сна)</button>
      </div>
    </div>

    <!-- TAB 1: STUDIO PRO -->
    <div id="tab1" class="content hidden">
      <div id="tip1" class="tip-card hidden">
        <div>👆</div>
        <div style="flex:1;" class="muted" id="tip1Txt"></div>
        <button class="tip-close" onclick="dismissTip('1')">×</button>
      </div>

      <!-- Live Screen & Coordinate Tap -->
      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:8px;">
          <div class="card-title" style="margin:0;">🖥 Экран ПК и клик</div>
          <div class="row" style="gap:6px;">
            <button class="btn" style="padding:6px 10px;font-size:12px;" onclick="captureOnce()">📸 Снимок</button>
            <button class="btn btn-primary" style="padding:6px 10px;font-size:12px;" id="liveToggleBtn" onclick="toggleLiveStream()">▶ Live</button>
          </div>
        </div>
        <div class="chip-scroll" id="monitorPills" style="margin-bottom:8px;"></div>
        <div class="screen-stage" id="screenStage">
          <span class="muted" id="screenPlaceholder">Нажмите «📸 Снимок» или «▶ Live» для просмотра экрана</span>
          <img id="screenImg" class="hidden" alt="PC Screen" onclick="onScreenTap(event)">
        </div>
        <div class="grid3" style="margin-top:8px;">
          <button class="btn active-seg" id="tapBtnLeft" onclick="setTapBtn('left')">ЛКМ тап</button>
          <button class="btn" id="tapBtnRight" onclick="setTapBtn('right')">ПКМ тап</button>
          <button class="btn" id="tapBtnDouble" onclick="setTapBtn('double')">Двойной</button>
        </div>
      </div>

      <!-- Live Keyboard & Hotkeys -->
      <div class="card">
        <div class="card-title">⌨ Клавиатура и хоткеи</div>
        <div class="row" style="margin-bottom:10px;">
          <input type="text" id="liveTypeInput" placeholder="Текст сразу в окно ПК...">
          <button class="btn btn-primary" style="flex-shrink:0;" onclick="sendLiveText()">Ввод</button>
        </div>
        <div class="chip-scroll">
          <button class="chip" onclick="sendHotkey('alt_tab')">Alt+Tab</button>
          <button class="chip" onclick="sendHotkey('win_d')">Win+D</button>
          <button class="chip" onclick="sendHotkey('switch_lang')">Язык</button>
          <button class="chip" onclick="sendHotkey('ctrl_c')">Ctrl+C</button>
          <button class="chip" onclick="sendHotkey('ctrl_v')">Ctrl+V</button>
          <button class="chip" onclick="sendHotkey('alt_f4')">Alt+F4</button>
          <button class="chip" onclick="sendHotkey('ctrl_shift_esc')">Дисп. задач</button>
          <button class="chip" onclick="sendHotkey('enter')">Enter</button>
          <button class="chip" onclick="sendHotkey('esc')">Esc</button>
        </div>
      </div>

      <div class="card-title" id="lblScenes">Сценарии в 1 тап</div>
      <div class="chip-scroll">
        <button class="chip" onclick="runScene('movie')">🎬 Кино</button>
        <button class="chip" onclick="runScene('night')">🌙 Ночь</button>
        <button class="chip" onclick="runScene('work')">💼 Работа</button>
        <button class="chip" onclick="runScene('presentation')">📊 Слайд F5</button>
        <button class="chip" onclick="runScene('away')">🚶 Отошёл</button>
      </div>

      <div class="card">
        <div class="card-title" id="lblTouchpad">Беспроводной тачпад</div>
        <div class="touchpad" id="touchpadArea">Ведите пальцем для курсора · Тап = ЛКМ</div>
        <div class="grid2" style="margin-top:10px;">
          <button class="btn" onclick="tpClick('left')">ЛКМ</button>
          <button class="btn" onclick="tpClick('right')">ПКМ</button>
          <button class="btn" onclick="tpScroll(120)">Скролл ↑</button>
          <button class="btn" onclick="tpScroll(-120)">Скролл ↓</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Stream Deck</div>
        <div class="grid2">
          <button class="btn" onclick="runDeck('desktop')">🖥 Рабочий стол</button>
          <button class="btn" onclick="runDeck('task_manager')">📊 Диспетчер</button>
          <button class="btn" onclick="runDeck('screenshot')">📸 Скриншот</button>
          <button class="btn" onclick="runDeck('explorer')">📂 Файлы</button>
          <button class="btn" onclick="runDeck('browser')">🌐 Браузер</button>
          <button class="btn" onclick="runDeck('mute')">🔇 Мьют</button>
        </div>
        <div id="customDeckWrap" style="margin-top:10px;"></div>
      </div>

      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:8px;">
          <div class="card-title" style="margin:0;">⚙ Процессы ПК</div>
          <button class="btn" style="padding:6px 10px;font-size:12px;" onclick="loadProcesses()">↻</button>
        </div>
        <div id="procListWrap"><div class="muted">Нажмите ↻ для загрузки процессов</div></div>
      </div>
    </div>

    <!-- TAB 2: EXCHANGE -->
    <div id="tab2" class="content hidden">
      <div class="card">
        <div class="card-title" id="lblFiles">Обмен файлами (до 8 МБ)</div>
        <input type="file" id="fileInput" class="hidden" onchange="uploadSelectedFile()">
        <div class="grid2">
          <button class="btn btn-primary" onclick="document.getElementById('fileInput').click()" id="btnSendFile">📤 На ПК</button>
          <button class="btn" onclick="rpc({{action:'files.open_folder'}})" id="btnOpenFolder">📂 Папка ПК</button>
        </div>
        <div id="filesList" style="margin-top:10px;"></div>
      </div>

      <div class="card">
        <div class="card-title" id="lblNote">Буфер обмена и заметка</div>
        <textarea id="noteBox" rows="5" placeholder="Текст или ссылка..."></textarea>
        <div class="grid2" style="margin-top:10px;">
          <button class="btn btn-primary" onclick="pushPcClipboard()">📋 В буфер ПК</button>
          <button class="btn" onclick="pullPcClipboard()">📥 Из буфера ПК</button>
          <button class="btn" onclick="saveNote()">💾 Сохр. заметку</button>
          <button class="btn" onclick="loadNote()">📄 Загрузить заметку</button>
        </div>
      </div>
    </div>

    <!-- TAB 3: SETTINGS & GUIDE -->
    <div id="tab3" class="content hidden">
      <div class="card">
        <div class="card-title">📱 iPhone / iPad (iOS)</div>
        <div class="muted" id="iosGuideDetail">
          Добавьте эту страницу на «Экран Домой» через кнопку <b>Поделиться ↑ → На экран Домой</b> в Safari. Также в GitHub Releases доступен нативный <code>.ipa</code> для установки через Sideloadly / AltStore / TrollStore.
        </div>
      </div>
      <div class="card">
        <div class="card-title" id="lblLang">Язык / Language</div>
        <div class="grid3">
          <button class="btn" onclick="setLang('ru')">Русский</button>
          <button class="btn" onclick="setLang('uk')">Українська</button>
          <button class="btn" onclick="setLang('en')">English</button>
        </div>
        <div style="height:10px;"></div>
        <button class="btn" style="width:100%;" onclick="toggleTheme()">🌓 Сменить тему (Тёмная / Светлая)</button>
        <div style="height:8px;"></div>
        <button class="btn" style="width:100%;" onclick="resetOnboardingTips()">💡 Показать подсказки первого запуска</button>
      </div>
      <div class="card">
        <div class="card-title">Wake-on-LAN</div>
        <button class="btn btn-primary" style="width:100%;" onclick="sendWol()">⚡ Разбудить ПК (Magic Packet)</button>
      </div>
    </div>
  </div>

  <nav class="bottom-nav hidden" id="bottomNav">
    <button class="nav-btn active" onclick="switchTab(0)" id="nav0"><span>🎛</span><span id="nav0Lbl">Пульт</span></button>
    <button class="nav-btn" onclick="switchTab(1)" id="nav1"><span>✨</span><span id="nav1Lbl">Студия</span></button>
    <button class="nav-btn" onclick="switchTab(2)" id="nav2"><span>📁</span><span id="nav2Lbl">Обмен</span></button>
    <button class="nav-btn" onclick="switchTab(3)" id="nav3"><span>⚙</span><span id="nav3Lbl">Настройки</span></button>
  </nav>

  <div id="modalRoot" class="modal-backdrop hidden"></div>

  <script>
    let isAuthed = {auth_flag};
    let hostOs = "{os_name}";
    let activeTab = 0;
    let lastStatus = null;
    let activeMonitor = 0;
    let tapButtonMode = 'left';
    let liveStreamOn = false;
    let lang = localStorage.getItem('pcpr_lang') || 'ru';
    const TR = {{
      ru: {{ nav:['Пульт','Студия','Обмен','Настройки'], tip0:'Подсказка: управляйте яркостью, выключайте монитор без сна или откройте Микшер приложений.', tip1:'Подсказка: смотрите экран ПК, тапайте по картинке и печатайте текст сразу в активное окно.', connOk:'На связи', locked:'Сессия заблокирована', unlocked:'Сессия активна', connect:'Подключиться' }},
      uk: {{ nav:['Пульт','Студія','Обмін','Налаштування'], tip0:'Підказка: керуйте яскравістю, вимикайте екран без сну або відкрийте Мікшер програм.', tip1:'Підказка: дивіться екран ПК, натискайте по зображенню та вводьте текст у вікно.', connOk:'На звʼязку', locked:'Сесія заблокована', unlocked:'Сесія активна', connect:'Підключитися' }},
      en: {{ nav:['Remote','Studio','Transfer','Settings'], tip0:'Tip: Adjust brightness, turn off the display without sleep, or open the App Volume Mixer.', tip1:'Tip: View your PC screen, tap directly on the image, and type into the focused window.', connOk:'Connected', locked:'Session locked', unlocked:'Session active', connect:'Connect' }}
    }};

    if (localStorage.getItem('pcpr_theme') === 'light') document.body.classList.add('light');
    if ('serviceWorker' in navigator) {{ navigator.serviceWorker.register('/sw.js').catch(() => {{}}); }}

    function applyTranslations() {{
      const t = TR[lang] || TR.ru;
      for (let i = 0; i < 4; i++) document.getElementById('nav'+i+'Lbl').textContent = t.nav[i];
      document.getElementById('tip0Txt').textContent = t.tip0;
      document.getElementById('tip1Txt').textContent = t.tip1;
      document.getElementById('loginBtn').textContent = t.connect;
      ['0','1'].forEach(k => {{
        const el = document.getElementById('tip'+k);
        if (!localStorage.getItem('pcpr_tip_dismissed_'+k)) el.classList.remove('hidden');
        else el.classList.add('hidden');
      }});
    }}
    function setLang(l) {{ lang = l; localStorage.setItem('pcpr_lang', l); applyTranslations(); }}
    function dismissTip(k) {{ localStorage.setItem('pcpr_tip_dismissed_'+k, '1'); document.getElementById('tip'+k).classList.add('hidden'); }}
    function resetOnboardingTips() {{ ['0','1'].forEach(k => localStorage.removeItem('pcpr_tip_dismissed_'+k)); applyTranslations(); setBanner('Подсказки включены', 'var(--ok)'); }}

    function setBanner(msg, color) {{
      const el = document.getElementById('bannerStrip');
      el.textContent = msg;
      el.style.color = color || 'var(--muted)';
    }}

    function toggleTheme() {{
      document.body.classList.toggle('light');
      const isL = document.body.classList.contains('light');
      localStorage.setItem('pcpr_theme', isL ? 'light' : 'dark');
      document.getElementById('themeIconBtn').textContent = isL ? '☀' : '☾';
    }}

    function switchTab(idx) {{
      activeTab = idx;
      for (let i = 0; i < 4; i++) {{
        document.getElementById('tab'+i).classList.toggle('hidden', i !== idx);
        document.getElementById('nav'+i).classList.toggle('active', i === idx);
      }}
      if (idx !== 1 && liveStreamOn) toggleLiveStream(false);
      if (idx === 1) loadCustomDeck();
      if (idx === 2) {{ loadFiles(); loadNote(); }}
    }}

    async function doLogin() {{
      const pin = document.getElementById('loginPin').value.trim();
      const err = document.getElementById('loginErr');
      err.textContent = '';
      try {{
        const res = await fetch('/login', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
          body: 'pin=' + encodeURIComponent(pin)
        }});
        if (!res.ok) {{ err.textContent = 'Неверный PIN-код'; return; }}
        isAuthed = true;
        initAuthedView();
      }} catch (e) {{ err.textContent = 'Ошибка соединения с ПК'; }}
    }}

    async function rpc(payload) {{
      setBanner('Отправка...', 'var(--warn)');
      const res = await fetch('/api/v2', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      const data = await res.json();
      if (res.status === 401) {{ isAuthed = false; showLoginView(); throw new Error('Not authenticated'); }}
      if (!res.ok) {{ setBanner(data.message || 'Ошибка', 'var(--danger)'); throw new Error(data.message || 'RPC Error'); }}
      setBanner('Готово', 'var(--ok)');
      return data;
    }}

    async function refreshAll() {{
      try {{
        const st = await rpc({{ action: 'status' }});
        lastStatus = st;
        hostOs = st.os || hostOs;
        document.getElementById('pcNameLbl').textContent = st.hostname || 'My PC';
        document.getElementById('connDot').className = 'dot ' + (st.locked ? 'warn' : 'ok');
        const t = TR[lang] || TR.ru;
        document.getElementById('connSubLbl').textContent = t.connOk + ' · ' + (hostOs === 'linux' ? 'Linux' : 'Windows');
        document.getElementById('sessionBadgeLbl').textContent = st.locked ? ('🔒 ' + t.locked) : ('🔓 ' + t.unlocked);
        if (st.uptime) document.getElementById('uptimeLbl').textContent = '⏱ ' + Math.floor(st.uptime/3600) + 'ч';
        setRing('cpuRing', Math.round(st.cpu || 0));
        setRing('ramRing', Math.round(st.ram || 0));
        setRing('diskRing', st.battery != null ? Math.round(st.battery) : Math.round(st.disk || 0));
        document.getElementById('lblDisk').textContent = st.battery != null ? 'Battery' : 'Disk';
        refreshBrightness();
      }} catch (e) {{}}
    }}

    async function refreshBrightness() {{
      try {{
        const d = await rpc({{ action: 'display.status' }});
        document.getElementById('brightSliderWrap').style.display = d.supported ? 'block' : 'none';
        if (d.supported && d.brightness != null) {{
          document.getElementById('brightRange').value = d.brightness;
          document.getElementById('brightPctLbl').textContent = d.brightness + '%';
        }} else {{
          document.getElementById('brightPctLbl').textContent = 'DDC недоступен';
        }}
      }} catch (e) {{}}
    }}
    function setBrightness(val) {{ rpc({{ action: 'display.brightness', brightness: Number(val) }}); }}

    function setRing(id, pct) {{
      const el = document.getElementById(id);
      el.style.setProperty('--p', Math.max(0, Math.min(100, pct)));
      el.textContent = pct + '%';
    }}

    function sendCmd(command) {{ rpc({{ action: 'command', command }}).then(() => refreshAll()); }}
    function sendMedia(key) {{ rpc({{ action: 'media', key }}); }}
    function runScene(scene) {{ rpc({{ action: 'scenes.run', scene }}); }}
    function runDeck(macro) {{ rpc({{ action: 'deck.run', macro }}); }}
    function tpClick(button) {{ rpc({{ action: 'touchpad', mode: 'click', button }}); }}
    function tpScroll(delta) {{ rpc({{ action: 'touchpad', mode: 'scroll', delta }}); }}
    function sendHotkey(hotkey) {{ rpc({{ action: 'keyboard.hotkey', hotkey }}); }}
    function sendWol() {{ rpc({{ action: 'wol.wake', mac: lastStatus?.mac || '' }}); }}

    function setTapBtn(mode) {{
      tapButtonMode = mode;
      document.getElementById('tapBtnLeft').classList.toggle('active-seg', mode === 'left');
      document.getElementById('tapBtnRight').classList.toggle('active-seg', mode === 'right');
      document.getElementById('tapBtnDouble').classList.toggle('active-seg', mode === 'double');
    }}

    async function captureOnce() {{
      if (liveStreamOn) toggleLiveStream(false);
      const res = await rpc({{ action: 'screen.capture', monitor: activeMonitor, max_width: 960, quality: 60 }});
      const img = document.getElementById('screenImg');
      img.src = 'data:image/jpeg;base64,' + res.image_b64;
      img.classList.remove('hidden');
      document.getElementById('screenPlaceholder').classList.add('hidden');
      renderMonitorPills(res.monitors || []);
    }}

    function renderMonitorPills(monitors) {{
      const wrap = document.getElementById('monitorPills');
      if (!monitors.length) {{ wrap.innerHTML = ''; return; }}
      wrap.innerHTML = monitors.map(m =>
        `<button class="chip" style="${{m.id === activeMonitor ? 'border-color:var(--accent);color:var(--accent);' : ''}}" onclick="selectMonitor(${{m.id}})">${{m.name}} (${{m.width}}×${{m.height}})</button>`
      ).join('');
    }}

    function selectMonitor(id) {{
      activeMonitor = id;
      if (liveStreamOn) {{
        document.getElementById('screenImg').src = '/api/screen.mjpg?monitor=' + id + '&fps=3&t=' + Date.now();
      }} else {{
        captureOnce();
      }}
    }}

    function toggleLiveStream(forceState) {{
      liveStreamOn = (forceState !== undefined) ? forceState : !liveStreamOn;
      const btn = document.getElementById('liveToggleBtn');
      const img = document.getElementById('screenImg');
      btn.textContent = liveStreamOn ? '⏹ Стоп' : '▶ Live';
      if (liveStreamOn) {{
        img.src = '/api/screen.mjpg?monitor=' + activeMonitor + '&fps=3&t=' + Date.now();
        img.classList.remove('hidden');
        document.getElementById('screenPlaceholder').classList.add('hidden');
      }} else {{
        img.src = '';
      }}
    }}

    function onScreenTap(ev) {{
      const img = document.getElementById('screenImg');
      const rect = img.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const nx = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
      const ny = Math.max(0, Math.min(1, (ev.clientY - rect.top) / rect.height));
      rpc({{ action: 'screen.tap', nx, ny, monitor: activeMonitor, button: tapButtonMode }}).then(() => {{
        if (!liveStreamOn) setTimeout(() => captureOnce(), 250);
      }});
    }}

    async function sendLiveText() {{
      const inp = document.getElementById('liveTypeInput');
      const text = inp.value;
      if (!text) return;
      await rpc({{ action: 'keyboard.type', text }});
      inp.value = '';
    }}

    async function loadCustomDeck() {{
      try {{
        const res = await rpc({{ action: 'deck.custom_list' }});
        const wrap = document.getElementById('customDeckWrap');
        const list = res.buttons || [];
        if (!list.length) {{ wrap.innerHTML = ''; return; }}
        wrap.innerHTML = '<div class="muted" style="margin:6px 0;">Мои кнопки:</div><div class="grid2">' +
          list.map(b => `<button class="btn" onclick="rpc({{action:'deck.custom_run', id:'${{b.id}}'}})">${{b.icon}} ${{b.label}}</button>`).join('') +
          '</div>';
      }} catch (e) {{}}
    }}

    async function loadProcesses() {{
      try {{
        const res = await rpc({{ action: 'processes.list' }});
        const wrap = document.getElementById('procListWrap');
        const list = res.processes || [];
        if (!list.length) {{ wrap.innerHTML = '<div class="muted">Нет данных</div>'; return; }}
        wrap.innerHTML = list.map(p => `
          <div class="file-row">
            <div style="min-width:0;flex:1;">
              <div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;">${{p.name}}</div>
              <div class="muted">PID ${{p.pid}} · ${{Math.round(p.mem_mb)}} МБ</div>
            </div>
            <button class="btn btn-danger" style="padding:5px 10px;font-size:12px;" onclick="killProc(${{p.pid}}, '${{p.name.replace(/'/g, "\\\\'")}}')">✕</button>
          </div>`).join('');
      }} catch (e) {{}}
    }}

    async function killProc(pid, name) {{
      if (!confirm('Завершить процесс ' + name + ' (PID ' + pid + ')?')) return;
      await rpc({{ action: 'processes.kill', pid }});
      loadProcesses();
    }}

    async function openAudioMixerModal() {{
      const m = document.getElementById('modalRoot');
      m.innerHTML = `<div class="modal"><div class="card-title">🎧 Аудиовыходы и микшер</div><div class="muted">Загрузка...</div></div>`;
      m.classList.remove('hidden');
      try {{
        const st = await rpc({{ action: 'audio.list' }});
        const devs = (st.devices || []).map(d =>
          `<button class="btn ${{d.active ? 'btn-primary' : ''}}" style="width:100%;margin-bottom:6px;text-align:left;" onclick="switchAudioDev('${{d.id.replace(/'/g, "\\\\'")}}')">${{d.active ? '🔊 ' : '🔈 '}}${{d.name}}</button>`
        ).join('') || '<div class="muted">Устройства не найдены</div>';
        const apps = (st.sessions || []).map(s => `
          <div style="padding:8px 0;border-bottom:1px solid var(--border);">
            <div class="row" style="justify-content:space-between;margin-bottom:4px;">
              <span style="font-size:13px;font-weight:600;">${{s.name}}</span>
              <button class="btn" style="padding:4px 9px;font-size:12px;" onclick="toggleAppMute(${{s.pid}}, ${{!s.muted}})">${{s.muted ? '🔇' : '🔊'}} ${{s.volume}}%</button>
            </div>
            <input type="range" min="0" max="100" value="${{s.volume}}" onchange="setAppVol(${{s.pid}}, this.value)">
          </div>`).join('') || '<div class="muted">Нет активных аудиопотоков</div>';
        m.innerHTML = `<div class="modal"><div class="card-title">🎧 Устройства вывода</div>${{devs}}<div class="card-title" style="margin-top:12px;">Микшер программ</div>${{apps}}<div style="height:10px;"></div><button class="btn" style="width:100%;" onclick="closeModal()">Закрыть</button></div>`;
      }} catch (e) {{ m.innerHTML = `<div class="modal"><div class="muted">${{e.message}}</div><button class="btn" style="width:100%;margin-top:10px;" onclick="closeModal()">Закрыть</button></div>`; }}
    }}
    async function switchAudioDev(device_id) {{ await rpc({{ action: 'audio.set_output', device_id }}); openAudioMixerModal(); }}
    async function setAppVol(pid, vol) {{ await rpc({{ action: 'audio.set_app_volume', pid, volume: Number(vol) }}); }}
    async function toggleAppMute(pid, muted) {{ await rpc({{ action: 'audio.set_app_volume', pid, muted }}); openAudioMixerModal(); }}

    (function setupTouchpad() {{
      const area = document.getElementById('touchpadArea');
      let lx = 0, ly = 0, moved = false, pendingX = 0, pendingY = 0, scheduled = false;
      function flushMove() {{
        scheduled = false;
        const dx = Math.round(pendingX), dy = Math.round(pendingY);
        pendingX = 0; pendingY = 0;
        if (dx || dy) fetch('/api/v2', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{action:'touchpad', mode:'move', dx, dy}}) }});
      }}
      area.addEventListener('touchstart', (e) => {{ const t = e.touches[0]; lx = t.clientX; ly = t.clientY; moved = false; }}, {{ passive: false }});
      area.addEventListener('touchmove', (e) => {{
        e.preventDefault();
        const t = e.touches[0];
        const dx = (t.clientX - lx) * 1.4, dy = (t.clientY - ly) * 1.4;
        lx = t.clientX; ly = t.clientY;
        if (Math.abs(dx) > 1 || Math.abs(dy) > 1) moved = true;
        pendingX += dx; pendingY += dy;
        if (!scheduled) {{ scheduled = true; setTimeout(flushMove, 45); }}
      }}, {{ passive: false }});
      area.addEventListener('touchend', () => {{ if (!moved) tpClick('left'); }});
    }})();

    async function loadFiles() {{
      try {{
        const res = await rpc({{ action: 'files.list' }});
        const box = document.getElementById('filesList');
        if (!res.files || !res.files.length) {{ box.innerHTML = '<div class="muted">Нет файлов</div>'; return; }}
        box.innerHTML = res.files.map(f => `
          <div class="file-row">
            <div><div style="font-size:13px;font-weight:600;">${{f.name}}</div><div class="muted">${{Math.round(f.size/1024)}} КБ</div></div>
            <button class="btn" style="padding:6px 12px;" onclick="downloadFile('${{f.name.replace(/'/g, "\\\\'")}}')">⬇</button>
          </div>`).join('');
      }} catch (e) {{}}
    }}

    async function uploadSelectedFile() {{
      const inp = document.getElementById('fileInput');
      const f = inp.files[0];
      if (!f) return;
      if (f.size > 8 * 1024 * 1024) {{ alert('Максимум 8 МБ'); return; }}
      const buf = await f.arrayBuffer();
      let bin = '';
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      await rpc({{ action: 'files.put', name: f.name, data: btoa(bin) }});
      inp.value = '';
      loadFiles();
    }}

    async function downloadFile(name) {{
      const res = await rpc({{ action: 'files.get', name }});
      const bin = atob(res.data);
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([arr]));
      const a = document.createElement('a'); a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
    }}

    async function saveNote() {{ await rpc({{ action: 'note.set', text: document.getElementById('noteBox').value }}); }}
    async function loadNote() {{ const res = await rpc({{ action: 'note.get' }}); document.getElementById('noteBox').value = res.text || ''; }}
    async function pushPcClipboard() {{ await rpc({{ action: 'clipboard.set', text: document.getElementById('noteBox').value }}); }}
    async function pullPcClipboard() {{ const res = await rpc({{ action: 'clipboard.get' }}); document.getElementById('noteBox').value = res.text || ''; }}

    function closeModal() {{ document.getElementById('modalRoot').classList.add('hidden'); }}
    function openTimerModal() {{
      const m = document.getElementById('modalRoot');
      m.innerHTML = `<div class="modal"><div class="card-title">Таймер выключения</div>
        <div class="grid2" style="margin:12px 0;">
          <button class="btn" onclick="rpc({{action:'timer.set',minutes:15}});closeModal()">15 мин</button>
          <button class="btn" onclick="rpc({{action:'timer.set',minutes:30}});closeModal()">30 мин</button>
          <button class="btn" onclick="rpc({{action:'timer.set',minutes:60}});closeModal()">60 мин</button>
          <button class="btn btn-danger" onclick="rpc({{action:'timer.cancel'}});closeModal()">Отменить</button>
        </div><button class="btn" style="width:100%;" onclick="closeModal()">Закрыть</button></div>`;
      m.classList.remove('hidden');
    }}
    function openPowerModal() {{
      const m = document.getElementById('modalRoot');
      m.innerHTML = `<div class="modal"><div class="card-title">Управление питанием</div>
        <p class="muted">Подтвердите действие с компьютером:</p>
        <div class="grid2" style="margin:12px 0;">
          <button class="btn btn-warn" onclick="if(confirm('Перезагрузить ПК?')){{sendCmd('restart');closeModal();}}">🔄 Перезагрузка</button>
          <button class="btn btn-danger" onclick="if(confirm('Выключить ПК?')){{sendCmd('shutdown');closeModal();}}">⏻ Выключить</button>
        </div><button class="btn" style="width:100%;" onclick="closeModal()">Отмена</button></div>`;
      m.classList.remove('hidden');
    }}
    function openUnlockModal() {{
      if (hostOs === 'linux') {{ rpc({{ action: 'unlock.linux' }}).then(() => refreshAll()); return; }}
      const m = document.getElementById('modalRoot');
      m.innerHTML = `<div class="modal"><div class="card-title">Вход в Windows с iPhone</div>
        <p class="muted">Для разблокировки Windows по Face ID установите <code>PCPhoneRemote.ipa</code> из GitHub Releases через Sideloadly / AltStore.</p>
        <div style="height:10px;"></div>
        <button class="btn" style="width:100%;" onclick="closeModal()">Понятно</button></div>`;
      m.classList.remove('hidden');
    }}

    function showLoginView() {{
      document.getElementById('loginView').classList.remove('hidden');
      document.getElementById('appShell').classList.add('hidden');
      document.getElementById('bottomNav').classList.add('hidden');
    }}
    function initAuthedView() {{
      document.getElementById('loginView').classList.add('hidden');
      document.getElementById('appShell').classList.remove('hidden');
      document.getElementById('bottomNav').classList.remove('hidden');
      applyTranslations();
      refreshAll();
    }}

    if (isAuthed) initAuthedView(); else showLoginView();
  </script>
</body>
</html>"""
    return html_doc.encode("utf-8")
