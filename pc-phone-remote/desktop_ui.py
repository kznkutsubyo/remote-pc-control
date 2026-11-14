import json


def desktop_html_bytes(admin_token: str = "") -> bytes:
    """Return the animated Obsidian Night + Frosted Glass Desktop Control Center HTML."""
    token_js = json.dumps(admin_token or "")
    html = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PC Phone Remote — Control Center</title>
<link rel="icon" type="image/png" href="/apple-touch-icon.png">
<style>
  :root {
    --bg: #08090d;
    --surface: rgba(20, 22, 34, 0.72);
    --surface-strong: rgba(26, 29, 44, 0.88);
    --surface-soft: rgba(255, 255, 255, 0.04);
    --border: rgba(255, 255, 255, 0.09);
    --border-glow: rgba(114, 137, 255, 0.42);
    --text: #f4f6fc;
    --text-muted: #98a1bd;
    --accent: #ff4d8d;
    --accent-2: #5eead4;
    --accent-3: #818cf8;
    --success: #34d399;
    --warning: #fbbf24;
    --danger: #fb7185;
    --shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    min-height: 100vh;
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Inter, sans-serif;
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }

  /* GPU-accelerated ambient aurora */
  .aurora-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    overflow: hidden;
    pointer-events: none;
    background: radial-gradient(circle at 20% 15%, rgba(129, 140, 248, 0.14), transparent 45%),
                radial-gradient(circle at 85% 80%, rgba(255, 77, 141, 0.12), transparent 45%),
                #08090d;
  }
  .blob {
    position: absolute;
    border-radius: 50%;
    filter: blur(85px);
    opacity: 0.45;
    will-change: transform;
  }
  .blob-1 {
    width: 440px; height: 440px;
    top: -120px; left: -90px;
    background: radial-gradient(circle, rgba(94, 234, 212, 0.5), rgba(59, 130, 246, 0.1));
    animation: driftA 18s ease-in-out infinite alternate;
  }
  .blob-2 {
    width: 520px; height: 520px;
    bottom: -160px; right: -120px;
    background: radial-gradient(circle, rgba(255, 77, 141, 0.48), rgba(168, 85, 247, 0.1));
    animation: driftB 22s ease-in-out infinite alternate;
  }
  .blob-3 {
    width: 340px; height: 340px;
    top: 38%; left: 52%;
    background: radial-gradient(circle, rgba(129, 140, 248, 0.32), transparent);
    animation: driftC 26s ease-in-out infinite alternate;
  }
  @keyframes driftA {
    from { transform: translate3d(0, 0, 0) scale(1); }
    to   { transform: translate3d(70px, 50px, 0) scale(1.12); }
  }
  @keyframes driftB {
    from { transform: translate3d(0, 0, 0) scale(1); }
    to   { transform: translate3d(-80px, -45px, 0) scale(1.15); }
  }
  @keyframes driftC {
    from { transform: translate3d(-30px, 20px, 0) scale(0.95); }
    to   { transform: translate3d(40px, -40px, 0) scale(1.08); }
  }

  .app-shell {
    position: relative;
    z-index: 1;
    max-width: 1120px;
    margin: 0 auto;
    padding: 20px 22px 34px;
    animation: shellEnter 0.45s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @keyframes shellEnter {
    from { opacity: 0; transform: translate3d(0, 14px, 0); }
    to   { opacity: 1; transform: translate3d(0, 0, 0); }
  }

  /* Top Header */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 18px;
    border-radius: 20px;
    background: var(--surface);
    backdrop-filter: blur(22px);
    -webkit-backdrop-filter: blur(22px);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    margin-bottom: 18px;
    flex-wrap: wrap;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .brand-logo {
    width: 46px;
    height: 46px;
    border-radius: 14px;
    object-fit: cover;
    box-shadow: 0 8px 24px rgba(255, 77, 141, 0.25);
    border: 1px solid rgba(255,255,255,0.14);
  }
  .brand-title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.02em;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .brand-sub {
    font-size: 12.5px;
    color: var(--text-muted);
    margin-top: 2px;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .status-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 13px;
    border-radius: 999px;
    background: rgba(52, 211, 153, 0.11);
    border: 1px solid rgba(52, 211, 153, 0.28);
    color: #a7f3d0;
    font-size: 12.5px;
    font-weight: 600;
  }
  .dot-live {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--success);
    box-shadow: 0 0 10px var(--success);
    animation: pulseDot 2s infinite;
  }
  @keyframes pulseDot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.8); }
  }

  .lang-switch {
    display: inline-flex;
    padding: 3px;
    border-radius: 12px;
    background: rgba(255,255,255,0.05);
    border: 1px solid var(--border);
  }
  .lang-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    padding: 6px 10px;
    border-radius: 9px;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .lang-btn.active {
    background: rgba(255,255,255,0.14);
    color: #fff;
  }

  /* Navigation Tabs */
  .nav-tabs {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 18px;
  }
  @media (max-width: 780px) {
    .nav-tabs { grid-template-columns: repeat(2, 1fr); }
  }
  .nav-tab {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    padding: 13px 14px;
    border-radius: 16px;
    background: var(--surface);
    backdrop-filter: blur(18px);
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 13.5px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s, background 0.2s, color 0.2s;
  }
  .nav-tab:hover {
    transform: translateY(-2px);
    color: var(--text);
    border-color: rgba(255,255,255,0.2);
  }
  .nav-tab.active {
    background: linear-gradient(135deg, rgba(255, 77, 141, 0.2), rgba(129, 140, 248, 0.22));
    border-color: rgba(255, 114, 174, 0.55);
    color: #fff;
    box-shadow: 0 10px 28px rgba(255, 77, 141, 0.16);
  }

  /* Tab Panels */
  .tab-panel {
    display: none;
    animation: tabSlide 0.32s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .tab-panel.active { display: block; }
  @keyframes tabSlide {
    from { opacity: 0; transform: translate3d(0, 10px, 0) scale(0.992); }
    to   { opacity: 1; transform: translate3d(0, 0, 0) scale(1); }
  }

  .grid-2 {
    display: grid;
    grid-template-columns: 1.08fr 0.92fr;
    gap: 18px;
  }
  @media (max-width: 860px) {
    .grid-2 { grid-template-columns: 1fr; }
  }
  .card {
    background: var(--surface);
    backdrop-filter: blur(22px);
    -webkit-backdrop-filter: blur(22px);
    border: 1px solid var(--border);
    border-radius: 22px;
    padding: 20px 22px;
    box-shadow: var(--shadow);
  }
  .card h2 {
    margin: 0 0 6px;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.015em;
  }
  .muted {
    color: var(--text-muted);
    font-size: 13px;
    line-height: 1.48;
  }

  /* QR Stage */
  .seg-pills {
    display: inline-flex;
    padding: 4px;
    background: rgba(255,255,255,0.05);
    border: 1px solid var(--border);
    border-radius: 14px;
    margin: 14px 0 12px;
    gap: 4px;
  }
  .seg-pill {
    border: none;
    background: transparent;
    color: var(--text-muted);
    padding: 8px 14px;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .seg-pill.active {
    background: linear-gradient(135deg, #ff4d8d, #818cf8);
    color: #fff;
    box-shadow: 0 6px 18px rgba(255, 77, 141, 0.28);
  }

  .ip-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 10px 0 16px;
  }
  .ip-pill {
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface-soft);
    color: var(--text-muted);
    font-size: 12.5px;
    font-family: ui-monospace, Consolas, monospace;
    cursor: pointer;
    transition: all 0.18s ease;
  }
  .ip-pill.active {
    background: rgba(94, 234, 212, 0.14);
    border-color: rgba(94, 234, 212, 0.5);
    color: #99f6e4;
  }

  .qr-showcase {
    display: flex;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  .qr-frame {
    position: relative;
    width: 232px;
    height: 232px;
    padding: 14px;
    border-radius: 22px;
    background: #ffffff;
    box-shadow: 0 18px 45px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255,255,255,0.2);
    overflow: hidden;
    flex-shrink: 0;
  }
  .qr-frame img {
    width: 100%;
    height: 100%;
    display: block;
    border-radius: 10px;
  }
  .qr-scanline {
    position: absolute;
    left: 10px; right: 10px;
    height: 3px;
    border-radius: 999px;
    background: linear-gradient(90deg, transparent, #ff4d8d, #5eead4, transparent);
    box-shadow: 0 0 12px rgba(255, 77, 141, 0.7);
    opacity: 0.75;
    animation: scanSweep 3.2s ease-in-out infinite;
    pointer-events: none;
  }
  @keyframes scanSweep {
    0%, 100% { top: 14px; opacity: 0.25; }
    50% { top: calc(100% - 17px); opacity: 0.85; }
  }

  .qr-meta {
    flex: 1;
    min-width: 220px;
  }
  .pin-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    border-radius: 12px;
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--border);
    font-family: ui-monospace, Consolas, monospace;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.14em;
    margin: 10px 0 12px;
  }

  /* Buttons & Inputs */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px 16px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.07);
    color: var(--text);
    font-size: 13.5px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.16s ease, background 0.18s, border-color 0.18s, box-shadow 0.18s;
  }
  .btn:hover { transform: translateY(-1px); background: rgba(255,255,255,0.12); border-color: rgba(255,255,255,0.22); }
  .btn:active { transform: translateY(0); }
  .btn-primary {
    background: linear-gradient(135deg, #ff4d8d, #818cf8);
    border-color: transparent;
    color: #fff;
    box-shadow: 0 10px 24px rgba(255, 77, 141, 0.26);
  }
  .btn-primary:hover {
    background: linear-gradient(135deg, #ff639c, #909bfa);
    box-shadow: 0 12px 28px rgba(255, 77, 141, 0.36);
  }
  .btn-success {
    background: rgba(52, 211, 153, 0.16);
    border-color: rgba(52, 211, 153, 0.45);
    color: #a7f3d0;
  }
  .btn-danger {
    background: rgba(251, 113, 133, 0.14);
    border-color: rgba(251, 113, 133, 0.42);
    color: #fecdd3;
  }
  .btn-row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }

  .field { margin-bottom: 14px; }
  .field label {
    display: block;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 6px;
  }
  .input, .textarea {
    width: 100%;
    padding: 10px 13px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: rgba(10, 12, 20, 0.72);
    color: var(--text);
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .input:focus, .textarea:focus {
    border-color: var(--accent-3);
    box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.18);
  }
  .input-group {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .grid-form-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  @media (max-width: 600px) { .grid-form-2 { grid-template-columns: 1fr; } }

  /* Live Radar + SVG Gauges */
  .radar-card {
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px 18px;
    border-radius: 18px;
    background: rgba(255,255,255,0.035);
    border: 1px solid var(--border);
    margin-bottom: 16px;
    transition: border-color 0.35s, background 0.35s;
  }
  .radar-card.connected {
    background: rgba(52, 211, 153, 0.11);
    border-color: rgba(52, 211, 153, 0.52);
  }
  .radar-rings {
    position: relative;
    width: 54px;
    height: 54px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .radar-ring {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 2px solid rgba(129, 140, 248, 0.5);
    animation: radarPulse 2.4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
  }
  .radar-ring.r2 { animation-delay: 1.2s; }
  .radar-card.connected .radar-ring { border-color: rgba(52, 211, 153, 0.72); }
  @keyframes radarPulse {
    0% { transform: scale(0.45); opacity: 0.9; }
    100% { transform: scale(1.25); opacity: 0; }
  }
  .radar-core {
    width: 18px; height: 18px;
    border-radius: 50%;
    background: var(--accent-3);
    box-shadow: 0 0 16px rgba(129, 140, 248, 0.8);
  }
  .radar-card.connected .radar-core {
    background: var(--success);
    box-shadow: 0 0 18px var(--success);
  }

  .gauges-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 14px;
  }
  .gauge-box {
    padding: 12px 10px;
    border-radius: 16px;
    background: rgba(255,255,255,0.035);
    border: 1px solid var(--border);
    text-align: center;
  }
  .gauge-svg { width: 76px; height: 76px; transform: rotate(-90deg); }
  .gauge-track { fill: none; stroke: rgba(255,255,255,0.08); stroke-width: 7; }
  .gauge-fill {
    fill: none;
    stroke-width: 7;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.55s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .gauge-val {
    font-size: 16px;
    font-weight: 700;
    margin-top: -50px;
    margin-bottom: 24px;
  }
  .gauge-lbl { font-size: 11.5px; color: var(--text-muted); font-weight: 600; }

  /* Switch Row */
  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 13px 15px;
    border-radius: 15px;
    background: rgba(255,255,255,0.035);
    border: 1px solid var(--border);
    margin-bottom: 11px;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }
  .badge-ok { background: rgba(52, 211, 153, 0.14); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.32); }
  .badge-warn { background: rgba(251, 191, 36, 0.14); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.32); }

  /* File list */
  .file-list {
    max-height: 280px;
    overflow-y: auto;
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .file-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px 13px;
    border-radius: 12px;
    background: rgba(255,255,255,0.035);
    border: 1px solid var(--border);
    font-size: 13px;
  }
  .file-size { color: var(--text-muted); font-size: 12px; font-family: ui-monospace, monospace; }

  /* Toast */
  .toast-wrap {
    position: fixed;
    top: 18px;
    right: 18px;
    z-index: 999;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .toast {
    padding: 11px 16px;
    border-radius: 14px;
    background: rgba(20, 23, 36, 0.94);
    backdrop-filter: blur(18px);
    border: 1px solid rgba(94, 234, 212, 0.45);
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
    animation: toastIn 0.28s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .toast.err { border-color: rgba(251, 113, 133, 0.65); }
  @keyframes toastIn {
    from { opacity: 0; transform: translate3d(18px, 0, 0); }
    to   { opacity: 1; transform: translate3d(0, 0, 0); }
  }
</style>
</head>
<body>
<div class="aurora-bg">
  <div class="blob blob-1"></div>
  <div class="blob blob-2"></div>
  <div class="blob blob-3"></div>
</div>
<div class="toast-wrap" id="toasts"></div>

<div class="app-shell">
  <header class="topbar">
    <div class="brand">
      <img class="brand-logo" src="/apple-touch-icon.png" alt="Logo" onerror="this.style.display='none'">
      <div>
        <div class="brand-title">
          <span>PC Phone Remote</span>
          <span class="badge badge-ok" id="osBadge">—</span>
        </div>
        <div class="brand-sub" id="hostSub">Подготовка рабочего пространства...</div>
      </div>
    </div>
    <div class="header-right">
      <div class="status-chip">
        <span class="dot-live"></span>
        <span id="serverStatusText">Сервер активен</span>
      </div>
      <div class="lang-switch">
        <button class="lang-btn" data-lang="ru" onclick="setLang('ru')">RU</button>
        <button class="lang-btn" data-lang="en" onclick="setLang('en')">EN</button>
        <button class="lang-btn" data-lang="uk" onclick="setLang('uk')">UK</button>
      </div>
    </div>
  </header>

  <nav class="nav-tabs">
    <button class="nav-tab active" data-tab="qr" onclick="switchTab('qr')">📱 <span data-i18n="tabQr">QR-подключение</span></button>
    <button class="nav-tab" data-tab="settings" onclick="switchTab('settings')">🛡️ <span data-i18n="tabSettings">Настройки и Безопасность</span></button>
    <button class="nav-tab" data-tab="unlock" onclick="switchTab('unlock')">🔓 <span data-i18n="tabUnlock">Вход с экрана блокировки</span></button>
    <button class="nav-tab" data-tab="files" onclick="switchTab('files')">📁 <span data-i18n="tabFiles">Файлы и Сервер</span></button>
  </nav>

  <!-- TAB 1: QR Pairing & Radar -->
  <section class="tab-panel active" id="tab-qr">
    <div class="grid-2">
      <div class="card">
        <h2 data-i18n="qrTitle">Подключение телефона по QR-коду</h2>
        <div class="muted" data-i18n="qrDesc">Откройте приложение на телефоне и нажмите «Сканировать QR» — компьютер и PIN добавятся мгновенно без ручного ввода IP.</div>

        <div class="seg-pills">
          <button class="seg-pill active" id="modeAndroidBtn" onclick="setQrMode('android')">🤖 Android (Камера в приложении)</button>
          <button class="seg-pill" id="modeIosBtn" onclick="setQrMode('ios')">🍏 iPhone / Web PWA</button>
        </div>

        <div class="muted" style="font-size:12px" data-i18n="selectIpHint">Локальный IP-адрес компьютера (выберите вашу Wi-Fi / LAN сеть):</div>
        <div class="ip-pills" id="ipPills"></div>

        <div class="qr-showcase">
          <div class="qr-frame">
            <img id="pairQrImg" alt="Pairing QR">
            <div class="qr-scanline"></div>
          </div>
          <div class="qr-meta">
            <div class="muted" id="qrCaption">Содержит имя ПК, локальный IP, порт и PIN-код для автоподключения.</div>
            <div class="pin-badge">
              <span style="font-size:12px;letter-spacing:0;color:var(--text-muted)">PIN:</span>
              <span id="qrPinText">••••</span>
            </div>
            <div class="btn-row">
              <button class="btn btn-primary" onclick="copyPairUri()">📋 <span data-i18n="copyLink">Копировать ссылку</span></button>
              <button class="btn" onclick="openPairWeb()">🌐 <span data-i18n="openPair">Страница /pair</span></button>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="radarTitle">Радар подключения и Телеметрия</h2>
        <div class="muted" data-i18n="radarDesc">Отслеживает сканирование QR и запросы от вашего смартфона в реальном времени.</div>

        <div class="radar-card" id="radarBox" style="margin-top:14px">
          <div class="radar-rings">
            <div class="radar-ring"></div>
            <div class="radar-ring r2"></div>
            <div class="radar-core"></div>
          </div>
          <div>
            <div style="font-weight:700;font-size:14.5px" id="radarTitleText">Ожидание подключения телефона...</div>
            <div class="muted" id="radarSubText" style="font-size:12.5px">Отсканируйте QR слева — статус обновится автоматически</div>
          </div>
        </div>

        <div class="gauges-row">
          <div class="gauge-box">
            <svg class="gauge-svg" viewBox="0 0 80 80">
              <circle class="gauge-track" cx="40" cy="40" r="32"/>
              <circle class="gauge-fill" id="cpuRing" cx="40" cy="40" r="32" stroke="#5eead4" stroke-dasharray="201.06" stroke-dashoffset="201.06"/>
            </svg>
            <div class="gauge-val" id="cpuVal">0%</div>
            <div class="gauge-lbl">CPU</div>
          </div>
          <div class="gauge-box">
            <svg class="gauge-svg" viewBox="0 0 80 80">
              <circle class="gauge-track" cx="40" cy="40" r="32"/>
              <circle class="gauge-fill" id="ramRing" cx="40" cy="40" r="32" stroke="#ff4d8d" stroke-dasharray="201.06" stroke-dashoffset="201.06"/>
            </svg>
            <div class="gauge-val" id="ramVal">0%</div>
            <div class="gauge-lbl" id="ramLbl">RAM</div>
          </div>
          <div class="gauge-box">
            <svg class="gauge-svg" viewBox="0 0 80 80">
              <circle class="gauge-track" cx="40" cy="40" r="32"/>
              <circle class="gauge-fill" id="diskRing" cx="40" cy="40" r="32" stroke="#818cf8" stroke-dasharray="201.06" stroke-dashoffset="201.06"/>
            </svg>
            <div class="gauge-val" id="diskVal">0%</div>
            <div class="gauge-lbl">Disk</div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 2: Settings & Security -->
  <section class="tab-panel" id="tab-settings">
    <div class="grid-2">
      <div class="card">
        <h2 data-i18n="secTitle">PIN-код, папка обмена и RDP</h2>
        <div class="muted" style="margin-bottom:14px" data-i18n="secDesc">Единый PIN используется для доступа телефона к ПК и для быстрого входа с экрана блокировки.</div>

        <div class="grid-form-2">
          <div class="field">
            <label data-i18n="pinLabel">Единый PIN-код</label>
            <div class="input-group">
              <input class="input" id="cfgPin" type="password" placeholder="1234">
              <button class="btn" type="button" onclick="togglePinEye()" title="Show/Hide">👁</button>
              <button class="btn" type="button" onclick="randomizePin()" title="Generate">🎲</button>
            </div>
          </div>
          <div class="field">
            <label data-i18n="portLabel">Порт HTTP-сервера</label>
            <input class="input" id="cfgPort" type="number" min="1024" max="65535" value="8765">
          </div>
        </div>

        <div class="field">
          <label data-i18n="shareDirLabel">Папка обмена файлами (Share Dir)</label>
          <div class="input-group">
            <input class="input" id="cfgShareDir" type="text">
            <button class="btn" type="button" onclick="openSharedFolder()">📂</button>
          </div>
        </div>

        <div class="grid-form-2">
          <div class="field">
            <label>RDP Host (необязательно)</label>
            <input class="input" id="cfgRdpHost" type="text" placeholder="Auto (LAN IP)">
          </div>
          <div class="field">
            <label>RDP Port / Username</label>
            <div class="input-group">
              <input class="input" id="cfgRdpPort" type="number" value="3389" style="max-width:95px">
              <input class="input" id="cfgRdpUser" type="text" placeholder="username">
            </div>
          </div>
        </div>

        <div class="field">
          <label>RDP Gateway (если используется)</label>
          <input class="input" id="cfgRdpGw" type="text" placeholder="rdp-gateway.example.com">
        </div>

        <button class="btn btn-primary" onclick="saveSettings()">💾 <span data-i18n="saveApply">Сохранить и применить</span></button>
      </div>

      <div class="card">
        <h2 data-i18n="sysTitle">Автозапуск и Сеть</h2>
        <div class="muted" style="margin-bottom:14px" data-i18n="sysDesc">Настройте фоновый запуск при включении ПК и правила брандмауэра в один клик.</div>

        <div class="toggle-row">
          <div>
            <div style="font-weight:700;font-size:14px" data-i18n="autostartTitle">Автозапуск при старте системы</div>
            <div class="muted" id="autostartMethodText" style="font-size:12px">—</div>
          </div>
          <button class="btn" id="autostartToggleBtn" onclick="toggleAutostart()">...</button>
        </div>

        <div class="toggle-row">
          <div>
            <div style="font-weight:700;font-size:14px" data-i18n="fwTitle">Правило Брандмауэра (TCP/UDP)</div>
            <div class="muted" id="fwStatusText" style="font-size:12px">Открывает порты управления и автообнаружения в локальной сети</div>
          </div>
          <button class="btn btn-success" onclick="openFirewall()">🛡️ <span data-i18n="openFwBtn">Открыть порты</span></button>
        </div>

        <div class="toggle-row">
          <div>
            <div style="font-weight:700;font-size:14px" data-i18n="macTitle">Wake-on-LAN MAC адрес</div>
            <div class="muted" id="macValueText" style="font-size:12.5px;font-family:ui-monospace,monospace">—</div>
          </div>
          <span class="badge badge-ok">WOL UDP 9</span>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 3: Lock Screen Unlock -->
  <section class="tab-panel" id="tab-unlock">
    <div class="grid-2">
      <div class="card">
        <h2 data-i18n="unlockTitle">Вход на ПК с экрана блокировки</h2>
        <div class="muted" style="margin-bottom:14px" data-i18n="unlockDesc">Позволяет разблокировать Windows или Linux прямо со смартфона через зашифрованный канал ECDH P-256 + AES-GCM.</div>

        <div class="toggle-row">
          <div>
            <div style="font-weight:700;font-size:14px" id="unlockModuleLabel">Провайдер входа</div>
            <div class="muted" id="unlockModuleSub" style="font-size:12px">—</div>
          </div>
          <span class="badge" id="unlockInstalledBadge">—</span>
        </div>

        <div class="toggle-row">
          <div>
            <div style="font-weight:700;font-size:14px" data-i18n="pipeStatusLabel">Служба разблокировки / Пароль</div>
            <div class="muted" id="unlockEnrolledSub" style="font-size:12px">—</div>
          </div>
          <span class="badge" id="unlockEnrolledBadge">—</span>
        </div>

        <div class="btn-row" id="windowsUnlockInstallRow">
          <button class="btn btn-primary" onclick="installUnlockProvider()">⚙️ <span data-i18n="installProviderBtn">Установить Credential Provider (UAC)</span></button>
          <button class="btn btn-danger" onclick="revokeEnroll()">🗑 <span data-i18n="revokeBtn">Отозвать привязку</span></button>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="enrollTitle">Привязка учётной записи по E2E QR</h2>
        <div class="muted" style="margin-bottom:12px" data-i18n="enrollDesc">Укажите пароль вашей учётной записи на ПК один раз — затем отсканируйте сгенерированный QR-код в разделе привязки телефона.</div>

        <div class="grid-form-2">
          <div class="field">
            <label>Домен (обычно .)</label>
            <input class="input" id="enrDomain" value=".">
          </div>
          <div class="field">
            <label>Имя пользователя Windows</label>
            <input class="input" id="enrUser" placeholder="Username">
          </div>
        </div>
        <div class="field">
          <label>Пароль учётной записи ПК</label>
          <input class="input" id="enrPass" type="password" placeholder="••••••••">
        </div>
        <button class="btn btn-primary" onclick="beginEnroll()">🔐 <span data-i18n="genEnrollQrBtn">Создать QR-код привязки</span></button>

        <div id="enrollQrResult" style="display:none;margin-top:16px;padding-top:14px;border-top:1px solid var(--border)">
          <div class="qr-showcase">
            <div class="qr-frame" style="width:186px;height:186px;padding:10px">
              <img id="enrollQrImg" alt="Enroll QR">
            </div>
            <div class="qr-meta">
              <div style="font-weight:700;color:var(--success);margin-bottom:6px">✅ QR привязки готов (120 сек)</div>
              <div class="muted" style="font-size:12.5px">На телефоне откройте <b>Разблокировать ПК → Привязать по QR</b> и наведите камеру.</div>
              <div class="btn-row">
                <button class="btn" onclick="copyEnrollUri()">📋 Копировать код</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 4: Files & Server -->
  <section class="tab-panel" id="tab-files">
    <div class="grid-2">
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
          <h2 data-i18n="filesTitle">Файлы обмена на ПК</h2>
          <button class="btn" onclick="openSharedFolder()">📂 <span data-i18n="openFolder">Открыть папку</span></button>
        </div>
        <div class="muted" id="shareDirSummary">—</div>
        <div class="file-list" id="filesList"></div>
      </div>

      <div class="card">
        <h2 data-i18n="noteTitle">Общая заметка и Сервер</h2>
        <div class="muted" style="margin-bottom:10px" data-i18n="noteDesc">Быстрый текстовый буфер, синхронизированный с телефоном.</div>
        <textarea class="textarea" id="sharedNoteBox" rows="5" placeholder="Текст заметки..."></textarea>
        <div class="btn-row">
          <button class="btn btn-primary" onclick="saveNote()">💾 <span data-i18n="saveNoteBtn">Сохранить заметку</span></button>
          <button class="btn btn-danger" onclick="restartServer()">🔄 <span data-i18n="restartBtn">Перезапустить сервер</span></button>
        </div>
        <div class="muted" id="uptimeText" style="margin-top:14px;font-size:12px">—</div>
      </div>
    </div>
  </section>
</div>

<script>
const ADMIN_TOKEN = """ + token_js + """;

const I18N = {
  ru: {
    tabQr: "QR-подключение",
    tabSettings: "Настройки и Безопасность",
    tabUnlock: "Вход с экрана блокировки",
    tabFiles: "Файлы и Сервер",
    qrTitle: "Подключение телефона по QR-коду",
    qrDesc: "Откройте приложение на телефоне и нажмите «Сканировать QR» — компьютер и PIN добавятся мгновенно без ручного ввода IP.",
    selectIpHint: "Локальный IP-адрес компьютера (выберите вашу Wi-Fi / LAN сеть):",
    copyLink: "Копировать ссылку",
    openPair: "Страница /pair",
    radarTitle: "Радар подключения и Телеметрия",
    radarDesc: "Отслеживает сканирование QR и запросы от вашего смартфона в реальном времени.",
    secTitle: "PIN-код, папка обмена и RDP",
    secDesc: "Единый PIN используется для доступа телефона к ПК и для быстрого входа с экрана блокировки.",
    pinLabel: "Единый PIN-код",
    portLabel: "Порт HTTP-сервера",
    shareDirLabel: "Папка обмена файлами (Share Dir)",
    saveApply: "Сохранить и применить",
    sysTitle: "Автозапуск и Сеть",
    sysDesc: "Настройте фоновый запуск при включении ПК и правила брандмауэра в один клик.",
    autostartTitle: "Автозапуск при старте системы",
    fwTitle: "Правило Брандмауэра (TCP/UDP)",
    openFwBtn: "Открыть порты",
    macTitle: "Wake-on-LAN MAC адрес",
    unlockTitle: "Вход на ПК с экрана блокировки",
    unlockDesc: "Позволяет разблокировать Windows или Linux прямо со смартфона через зашифрованный канал ECDH P-256 + AES-GCM.",
    pipeStatusLabel: "Служба разблокировки / Пароль",
    installProviderBtn: "Установить Credential Provider (UAC)",
    revokeBtn: "Отозвать привязку",
    enrollTitle: "Привязка учётной записи по E2E QR",
    enrollDesc: "Укажите пароль вашей учётной записи на ПК один раз — затем отсканируйте сгенерированный QR-код в приложении на телефоне.",
    genEnrollQrBtn: "Создать QR-код привязки",
    filesTitle: "Файлы обмена на ПК",
    openFolder: "Открыть папку",
    noteTitle: "Общая заметка и Сервер",
    noteDesc: "Быстрый текстовый буфер, синхронизированный с телефоном.",
    saveNoteBtn: "Сохранить заметку",
    restartBtn: "Перезапустить сервер",
    serverActive: "Сервер активен",
    waitingPhone: "Ожидание подключения телефона...",
    waitingSub: "Отсканируйте QR слева — статус обновится автоматически",
    phoneConnected: "Телефон на связи!"
  },
  en: {
    tabQr: "QR Pairing",
    tabSettings: "Settings & Security",
    tabUnlock: "Lock Screen Unlock",
    tabFiles: "Files & Server",
    qrTitle: "Connect Phone via QR Code",
    qrDesc: "Open the phone app and tap Scan QR — PC host, port and PIN import automatically.",
    selectIpHint: "PC Local IP Address (pick your Wi-Fi / LAN adapter):",
    copyLink: "Copy Link",
    openPair: "Open /pair",
    radarTitle: "Connection Radar & Telemetry",
    radarDesc: "Detects QR scans and live requests from your smartphone.",
    secTitle: "PIN, Shared Folder & RDP",
    secDesc: "Unified PIN protects HTTP access and phone lock-screen sign-in.",
    pinLabel: "Unified PIN",
    portLabel: "HTTP Server Port",
    shareDirLabel: "Shared Files Directory",
    saveApply: "Save & Apply",
    sysTitle: "Autostart & Firewall",
    sysDesc: "Manage background startup and local firewall ports with one click.",
    autostartTitle: "Start with System",
    fwTitle: "Firewall Rule (TCP/UDP)",
    openFwBtn: "Open Ports",
    macTitle: "Wake-on-LAN MAC Address",
    unlockTitle: "Lock Screen Sign-In",
    unlockDesc: "Unlock Windows or Linux remotely over E2E encrypted ECDH P-256 + AES-GCM.",
    pipeStatusLabel: "Unlock Service / Enrollment",
    installProviderBtn: "Install Credential Provider (UAC)",
    revokeBtn: "Revoke Enrollment",
    enrollTitle: "Enroll PC Account via E2E QR",
    enrollDesc: "Enter your PC account password once and scan the generated QR code in the phone app.",
    genEnrollQrBtn: "Generate Enrollment QR",
    filesTitle: "Shared PC Files",
    openFolder: "Open Folder",
    noteTitle: "Shared Note & Server",
    noteDesc: "Quick shared clipboard synced with your phone.",
    saveNoteBtn: "Save Note",
    restartBtn: "Restart Server",
    serverActive: "Server Online",
    waitingPhone: "Waiting for phone connection...",
    waitingSub: "Scan the QR code on the left — status updates live",
    phoneConnected: "Phone Connected!"
  },
  uk: {
    tabQr: "QR-підключення",
    tabSettings: "Налаштування та Безпека",
    tabUnlock: "Вхід з екрана блокування",
    tabFiles: "Файли та Сервер",
    qrTitle: "Підключення телефону по QR-коду",
    qrDesc: "Відкрийте додаток на телефоні та натисніть «Сканувати QR» — ПК і PIN додадуться миттєво.",
    selectIpHint: "Локальний IP комп'ютера (оберіть вашу Wi-Fi / LAN мережу):",
    copyLink: "Копіювати посилання",
    openPair: "Сторінка /pair",
    radarTitle: "Радар підключення та Телеметрія",
    radarDesc: "Відстежує сканування QR та запити зі смартфона в реальному часі.",
    secTitle: "PIN-код, папка обміну та RDP",
    secDesc: "Єдиний PIN використовується для доступу до ПК та входу з екрана блокування.",
    pinLabel: "Єдиний PIN-код",
    portLabel: "Порт HTTP-сервера",
    shareDirLabel: "Папка обміну файлами",
    saveApply: "Зберегти й застосувати",
    sysTitle: "Автозапуск та Мережа",
    sysDesc: "Фоновий запуск разом із системою та правила брандмауера в один клік.",
    autostartTitle: "Автозапуск при старті системи",
    fwTitle: "Правило Брандмауера (TCP/UDP)",
    openFwBtn: "Відкрити порти",
    macTitle: "Wake-on-LAN MAC адреса",
    unlockTitle: "Вхід на ПК з екрана блокування",
    unlockDesc: "Розблоковуйте Windows або Linux зі смартфона через шифрований канал ECDH P-256 + AES-GCM.",
    pipeStatusLabel: "Служба розблокування / Прив'язка",
    installProviderBtn: "Встановити Credential Provider (UAC)",
    revokeBtn: "Відкликати прив'язку",
    enrollTitle: "Прив'язка акаунта через E2E QR",
    enrollDesc: "Вкажіть пароль облікового запису один раз і відскануйте QR у додатку.",
    genEnrollQrBtn: "Створити QR прив'язки",
    filesTitle: "Файли обміну на ПК",
    openFolder: "Відкрити папку",
    noteTitle: "Спільна нотатка та Сервер",
    noteDesc: "Швидкий буфер обміну, синхронізований з телефоном.",
    saveNoteBtn: "Зберегти нотатку",
    restartBtn: "Перезапустити сервер",
    serverActive: "Сервер активний",
    waitingPhone: "Очікування підключення телефону...",
    waitingSub: "Відскануйте QR ліворуч — статус оновиться автоматично",
    phoneConnected: "Телефон на зв'язку!"
  }
};

let currentLang = localStorage.getItem('pc_desk_lang') || 'ru';
let qrMode = 'android';
let selectedIp = '';
let stateData = null;
let formHydrated = false;
let currentEnrollUri = '';

function t(k) {
  return (I18N[currentLang] && I18N[currentLang][k]) || I18N.ru[k] || k;
}

function setLang(l) {
  currentLang = l;
  localStorage.setItem('pc_desk_lang', l);
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.toggle('active', b.dataset.lang === l));
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    el.textContent = t(key);
  });
  document.getElementById('serverStatusText').textContent = t('serverActive');
  if (stateData) renderState(stateData, false);
}

function switchTab(name) {
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
}

function toast(msg, isErr = false) {
  const wrap = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast' + (isErr ? ' err' : '');
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 260); }, 3200);
}

async function apiPost(payload) {
  const res = await fetch('/api/local/admin', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Local-Admin': ADMIN_TOKEN
    },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || ('HTTP ' + res.status));
  }
  return data;
}

function buildActiveQrData() {
  if (!stateData) return '';
  const host = selectedIp || stateData.selected_host || '127.0.0.1';
  const port = stateData.port || 8765;
  const pin = stateData.pin || '';
  const name = encodeURIComponent(stateData.hostname || 'My PC');
  const mac = encodeURIComponent(stateData.mac || '');
  if (qrMode === 'ios') {
    return `http://${host}:${port}/app?name=${name}&host=${encodeURIComponent(host)}&port=${port}&pin=${encodeURIComponent(pin)}`;
  }
  return `pcphone://add?name=${name}&host=${encodeURIComponent(host)}&port=${port}&pin=${encodeURIComponent(pin)}${mac ? '&mac=' + mac : ''}`;
}

function updateQrImage() {
  const uri = buildActiveQrData();
  if (!uri) return;
  const img = document.getElementById('pairQrImg');
  const url = '/api/local/qr?data=' + encodeURIComponent(uri);
  if (img.dataset.srcUri !== uri) {
    img.dataset.srcUri = uri;
    img.src = url;
  }
}

function setQrMode(mode) {
  qrMode = mode;
  document.getElementById('modeAndroidBtn').classList.toggle('active', mode === 'android');
  document.getElementById('modeIosBtn').classList.toggle('active', mode === 'ios');
  document.getElementById('qrCaption').textContent = mode === 'android'
    ? 'Содержит имя ПК, локальный IP, порт, MAC и PIN-код для автоподключения в Android-приложении.'
    : 'Откройте стандартной камерой iPhone — запустит веб-пульт iOS PWA с авто-входом по PIN.';
  updateQrImage();
}

function selectIp(ip) {
  selectedIp = ip;
  document.querySelectorAll('.ip-pill').forEach(p => p.classList.toggle('active', p.dataset.ip === ip));
  updateQrImage();
}

function setGauge(ringId, valId, pct) {
  const c = 201.06;
  const clamped = Math.max(0, Math.min(100, Number(pct) || 0));
  document.getElementById(ringId).style.strokeDashoffset = (c - (clamped / 100) * c).toFixed(2);
  document.getElementById(valId).textContent = Math.round(clamped) + '%';
}

function renderState(d, hydrateForms) {
  stateData = d;
  document.getElementById('osBadge').textContent = (d.os || 'pc').toUpperCase();
  document.getElementById('hostSub').textContent = `${d.hostname || 'PC'} · :${d.port || 8765} · ${(d.selected_host || '127.0.0.1')}`;
  document.getElementById('qrPinText').textContent = d.pin ? d.pin : 'не задан';

  if (!selectedIp || !(d.ips || []).includes(selectedIp)) {
    selectedIp = d.selected_host || (d.ips && d.ips[0]) || '127.0.0.1';
  }
  const pillsWrap = document.getElementById('ipPills');
  pillsWrap.innerHTML = '';
  (d.ips || [selectedIp]).forEach(ip => {
    const btn = document.createElement('button');
    btn.className = 'ip-pill' + (ip === selectedIp ? ' active' : '');
    btn.dataset.ip = ip;
    btn.textContent = ip;
    btn.onclick = () => selectIp(ip);
    pillsWrap.appendChild(btn);
  });
  updateQrImage();

  // Radar
  const lc = d.last_client_seen;
  const radarBox = document.getElementById('radarBox');
  if (lc && lc.ago_sec !== undefined && lc.ago_sec < 15) {
    radarBox.classList.add('connected');
    document.getElementById('radarTitleText').textContent = `${t('phoneConnected')} (${lc.ip})`;
    document.getElementById('radarSubText').textContent = `Последний запрос ${lc.path || '/'} · ${lc.ago_sec.toFixed(1)} сек назад`;
  } else {
    radarBox.classList.remove('connected');
    document.getElementById('radarTitleText').textContent = t('waitingPhone');
    document.getElementById('radarSubText').textContent = lc && lc.ip
      ? `Последний клиент: ${lc.ip} (${Math.round(lc.ago_sec)} сек назад)`
      : t('waitingSub');
  }

  // Telemetry gauges
  const tel = d.telemetry || {};
  setGauge('cpuRing', 'cpuVal', tel.cpu_percent);
  setGauge('ramRing', 'ramVal', tel.memory_percent);
  setGauge('diskRing', 'diskVal', tel.disk_percent);
  if (tel.memory_total_gb) {
    document.getElementById('ramLbl').textContent = `RAM (${tel.memory_used_gb}/${tel.memory_total_gb}G)`;
  }

  // Settings form hydration once
  if (hydrateForms && !formHydrated) {
    formHydrated = true;
    document.getElementById('cfgPin').value = d.pin || '';
    document.getElementById('cfgPort').value = d.port || 8765;
    document.getElementById('cfgShareDir').value = d.share_dir || '';
    document.getElementById('cfgRdpHost').value = d.rdp_host || '';
    document.getElementById('cfgRdpPort').value = d.rdp_port || 3389;
    document.getElementById('cfgRdpUser').value = d.rdp_username || '';
    document.getElementById('cfgRdpGw').value = d.rdp_gateway || '';
    document.getElementById('sharedNoteBox').value = d.note || '';
    if (d.rdp_username) document.getElementById('enrUser').value = d.rdp_username;
  }

  // Autostart & Network
  const autoBtn = document.getElementById('autostartToggleBtn');
  autoBtn.textContent = d.autostart_enabled ? '✅ Включён (Выкл)' : 'Выключен (Включить)';
  autoBtn.className = 'btn ' + (d.autostart_enabled ? 'btn-success' : 'btn-primary');
  document.getElementById('autostartMethodText').textContent = d.autostart_method || 'Task Scheduler / systemd';
  document.getElementById('macValueText').textContent = d.mac || 'Не найден';

  // Unlock tab
  const instBadge = document.getElementById('unlockInstalledBadge');
  instBadge.textContent = d.unlock_provider_installed ? 'Установлен' : 'Не установлен';
  instBadge.className = 'badge ' + (d.unlock_provider_installed ? 'badge-ok' : 'badge-warn');
  document.getElementById('unlockModuleSub').textContent = d.unlock_provider_details || (d.os === 'linux' ? 'Native logind / PAM' : 'PhoneUnlockProvider.dll');

  const enrBadge = document.getElementById('unlockEnrolledBadge');
  enrBadge.textContent = d.unlock_enrolled ? 'Привязан' : (d.pipe_running ? 'Служба готова' : 'Ожидает настройки');
  enrBadge.className = 'badge ' + (d.unlock_enrolled ? 'badge-ok' : 'badge-warn');
  document.getElementById('unlockEnrolledSub').textContent = d.os === 'windows'
    ? (d.pipe_running ? 'Named Pipe PhoneUnlockService активен' : 'Служба PhoneUnlockService не запущена')
    : 'Нативный DBus / loginctl / polkit';
  document.getElementById('windowsUnlockInstallRow').style.display = d.os === 'linux' ? 'none' : 'flex';

  // Files & Uptime
  document.getElementById('shareDirSummary').textContent = d.share_dir || '';
  const filesWrap = document.getElementById('filesList');
  filesWrap.innerHTML = '';
  if (!d.files || !d.files.length) {
    filesWrap.innerHTML = '<div class="muted" style="padding:12px 4px">Папка пока пуста — отправляйте файлы с телефона или с ПК.</div>';
  } else {
    d.files.slice(0, 40).forEach(f => {
      const row = document.createElement('div');
      row.className = 'file-item';
      const kb = f.size >= 1048576 ? (f.size / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(f.size / 1024)) + ' KB';
      row.innerHTML = `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(f.name)}</span><span class="file-size">${kb}</span>`;
      filesWrap.appendChild(row);
    });
  }
  const up = d.server_uptime_sec || 0;
  const mins = Math.floor(up / 60);
  const secs = Math.floor(up % 60);
  document.getElementById('uptimeText').textContent = `Время работы сервера: ${mins}м ${secs}с · Python HTTP :${d.port || 8765}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

async function pollState(hydrate = false) {
  try {
    const res = await fetch('/api/local/admin', { headers: { 'X-Local-Admin': ADMIN_TOKEN } });
    if (!res.ok) return;
    const d = await res.json();
    renderState(d, hydrate);
  } catch (e) {}
}

function copyPairUri() {
  const uri = buildActiveQrData();
  if (!uri) return;
  navigator.clipboard.writeText(uri).then(() => toast('Ссылка скопирована в буфер обмена')).catch(() => toast(uri));
}

function openPairWeb() {
  const host = selectedIp || (stateData && stateData.selected_host) || '127.0.0.1';
  const port = (stateData && stateData.port) || 8765;
  window.open(`http://${host}:${port}/pair`, '_blank');
}

function togglePinEye() {
  const el = document.getElementById('cfgPin');
  el.type = el.type === 'password' ? 'text' : 'password';
}

function randomizePin() {
  const digits = Math.floor(100000 + Math.random() * 900000);
  const el = document.getElementById('cfgPin');
  el.value = String(digits);
  el.type = 'text';
  toast('Сгенерирован новый PIN — нажмите «Сохранить и применить»');
}

async function saveSettings() {
  try {
    await apiPost({
      action: 'save_config',
      pin: document.getElementById('cfgPin').value.trim(),
      port: Number(document.getElementById('cfgPort').value) || 8765,
      share_dir: document.getElementById('cfgShareDir').value.trim(),
      rdp_host: document.getElementById('cfgRdpHost').value.trim(),
      rdp_port: Number(document.getElementById('cfgRdpPort').value) || 3389,
      rdp_username: document.getElementById('cfgRdpUser').value.trim(),
      rdp_gateway: document.getElementById('cfgRdpGw').value.trim()
    });
    toast('✅ Настройки сохранены и применены');
    pollState(false);
  } catch (e) { toast('❌ ' + e.message, true); }
}

async function toggleAutostart() {
  try {
    const target = !(stateData && stateData.autostart_enabled);
    const res = await apiPost({ action: 'set_autostart', enabled: target });
    toast(res.message || (target ? '✅ Автозапуск включён' : 'Автозапуск отключён'));
    pollState(false);
  } catch (e) { toast('❌ ' + e.message, true); }
}

async function openFirewall() {
  try {
    const res = await apiPost({ action: 'open_firewall', port: (stateData && stateData.port) || 8765 });
    toast(res.message || '🛡 Порты открыты в брандмауэре');
  } catch (e) { toast('❌ ' + e.message, true); }
}

async function installUnlockProvider() {
  try {
    toast('Запуск установки Credential Provider (подтвердите UAC)...');
    const res = await apiPost({ action: 'install_unlock_provider' });
    toast(res.message || '✅ Установка запущена');
    setTimeout(() => pollState(false), 1800);
  } catch (e) { toast('❌ ' + e.message, true); }
}

async function beginEnroll() {
  const password = document.getElementById('enrPass').value;
  if (!password) { toast('Введите пароль учётной записи ПК', true); return; }
  try {
    const res = await apiPost({
      action: 'enroll_begin',
      domain: document.getElementById('enrDomain').value.trim() || '.',
      username: document.getElementById('enrUser').value.trim(),
      password: password,
      host: selectedIp || (stateData && stateData.selected_host) || ''
    });
    currentEnrollUri = res.qr_uri || '';
    document.getElementById('enrollQrImg').src = '/api/local/qr?data=' + encodeURIComponent(currentEnrollUri);
    document.getElementById('enrollQrResult').style.display = 'block';
    document.getElementById('enrPass').value = '';
    toast('🔐 QR-код привязки сформирован');
    pollState(false);
  } catch (e) { toast('❌ ' + e.message, true); }
}

function copyEnrollUri() {
  if (!currentEnrollUri) return;
  navigator.clipboard.writeText(currentEnrollUri).then(() => toast('Код привязки скопирован'));
}

async function revokeEnroll() {
  try {
    await apiPost({ action: 'enroll_revoke' });
    toast('Привязка отозвана');
    pollState(false);
  } catch (e) { toast('❌ ' + e.message, true); }
}

async function openSharedFolder() {
  try {
    await apiPost({ action: 'open_shared_folder' });
  } catch (e) { toast('❌ ' + e.message, true); }
}

async function saveNote() {
  try {
    await apiPost({ action: 'note_set', text: document.getElementById('sharedNoteBox').value });
    toast('📝 Заметка синхронизирована');
  } catch (e) { toast('❌ ' + e.message, true); }
}

async function restartServer() {
  try {
    await apiPost({ action: 'restart_server' });
    toast('🔄 Сервер перезапускается...');
    setTimeout(() => pollState(false), 2000);
  } catch (e) { toast('❌ ' + e.message, true); }
}

setLang(currentLang);
pollState(true);
setInterval(() => pollState(false), 1500);
</script>
</body>
</html>
"""
    return html.encode("utf-8")
