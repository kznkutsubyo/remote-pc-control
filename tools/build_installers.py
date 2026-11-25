"""Build native standalone installers for PC Phone Remote:
- pc-phone-remote/PCPhoneRemote.exe (native Windows launcher & daemon wrapper)
- PCPhoneRemote-Setup.exe + release-dist/PCPhoneRemote-Setup.exe (dark animated WinForms installer)
- PCPhoneRemote-Linux-Installer.run + release-dist/PCPhoneRemote-Linux-Installer.run (self-extracting bash + tar.gz)
"""
from __future__ import annotations

import argparse
import base64
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PC_DIR = ROOT / "pc-phone-remote"
UNLOCK_DIR = ROOT / "windows-unlock"
ASSETS_DIR = PC_DIR / "assets"
DIST_DIR = ROOT / "release-dist"

INCLUDE_PC_EXTS = {".py", ".bat", ".vbs", ".ps1", ".html", ".md"}
INCLUDE_PC_NAMES = {"requirements.txt", "config.example.json"}


def find_csc_exe() -> str | None:
    candidates = [
        Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return shutil.which("csc.exe")


def ensure_assets() -> Path:
    sys.path.insert(0, str(PC_DIR))
    from brand_icon import ensure_brand_assets  # type: ignore

    assets = ensure_brand_assets()
    return assets["ico"]


def collect_pc_files(include_launcher_exe: bool = True) -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    for path in sorted(PC_DIR.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_file():
            continue
        if path.name == "config.json" or path.suffix == ".pyc":
            continue
        if path.suffix.lower() in INCLUDE_PC_EXTS or path.name in INCLUDE_PC_NAMES:
            items.append((path, f"pc-phone-remote/{path.name}"))
        elif include_launcher_exe and path.name == "PCPhoneRemote.exe":
            items.append((path, f"pc-phone-remote/{path.name}"))

    if ASSETS_DIR.exists():
        for path in sorted(ASSETS_DIR.iterdir(), key=lambda p: p.name.casefold()):
            if path.is_file():
                items.append((path, f"pc-phone-remote/assets/{path.name}"))
    return items


def collect_unlock_files() -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    if not UNLOCK_DIR.exists():
        return items
    for path in sorted(UNLOCK_DIR.iterdir(), key=lambda p: p.name.casefold()):
        if path.is_file() and (path.suffix.lower() in {".ps1", ".bat"} or path.name == "README.md"):
            items.append((path, f"windows-unlock/{path.name}"))
    build_dir = UNLOCK_DIR / "build"
    for dll_name in ("PhoneUnlockProvider.dll", "PhoneUnlockService.exe", "PhoneUnlockSelfTest.exe"):
        candidate = build_dir / dll_name
        if candidate.exists():
            items.append((candidate, f"windows-unlock/build/{dll_name}"))
    return items


LAUNCHER_CS = r'''
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace PCPhoneRemoteLauncher
{
    static class Program
    {
        [DllImport("kernel32.dll")]
        private static extern bool AttachConsole(int dwProcessId);

        [STAThread]
        static int Main(string[] args)
        {
            bool serverOnly = false;
            bool trayOnly = false;
            bool legacyTk = false;
            bool showHelp = false;

            foreach (string rawArg in args)
            {
                string arg = rawArg.Trim().ToLowerInvariant();
                if (arg == "--server" || arg == "-s") serverOnly = true;
                else if (arg == "--tray") trayOnly = true;
                else if (arg == "--legacy-tk") legacyTk = true;
                else if (arg == "--help" || arg == "-h" || arg == "/?") showHelp = true;
            }

            if (showHelp)
            {
                AttachConsole(-1);
                Console.WriteLine("PC Phone Remote Launcher");
                Console.WriteLine("Usage: PCPhoneRemote.exe [--server | --tray | --legacy-tk | --help]");
                return 0;
            }

            string appDir = ResolveAppDir();
            if (string.IsNullOrEmpty(appDir) || !File.Exists(Path.Combine(appDir, "app.py")))
            {
                if (!serverOnly)
                {
                    MessageBox.Show(
                        "Cannot locate app.py in application directory.",
                        "PC Phone Remote",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                }
                return 1;
            }

            if (trayOnly)
            {
                StartPythonHidden(appDir, Path.Combine(appDir, "server_tray.py"), "");
                return 0;
            }

            if (legacyTk)
            {
                StartPythonHidden(appDir, Path.Combine(appDir, "configure.py"), "--legacy-tk");
                return 0;
            }

            if (serverOnly)
            {
                if (IsServerHealthy(8765, 600))
                {
                    Thread.Sleep(1100);
                    if (IsServerHealthy(8765, 600)) return 0;
                }
                StartPythonHidden(appDir, Path.Combine(appDir, "app.py"), "--host 0.0.0.0 --port 8765");
                return 0;
            }

            if (!IsServerHealthy(8765, 500))
            {
                if (!StartPythonHidden(appDir, Path.Combine(appDir, "app.py"), "--host 0.0.0.0 --port 8765"))
                {
                    MessageBox.Show(
                        "Python 3 was not found on this PC.\nPlease install Python 3.10+ from python.org or re-run PCPhoneRemote-Setup.exe.",
                        "PC Phone Remote",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Warning
                    );
                    return 2;
                }
                for (int i = 0; i < 30; i++)
                {
                    if (IsServerHealthy(8765, 350)) break;
                    Thread.Sleep(200);
                }
            }

            OpenDesktopControlCenter("http://127.0.0.1:8765/desktop");
            return 0;
        }

        private static string ResolveAppDir()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            if (File.Exists(Path.Combine(baseDir, "app.py"))) return baseDir;
            string sub = Path.Combine(baseDir, "pc-phone-remote");
            if (File.Exists(Path.Combine(sub, "app.py"))) return sub;
            return baseDir;
        }

        private static bool IsServerHealthy(int port, int timeoutMs)
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(string.Format("http://127.0.0.1:{0}/health", port));
                req.Timeout = timeoutMs;
                req.ReadWriteTimeout = timeoutMs;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    return resp.StatusCode == HttpStatusCode.OK;
                }
            }
            catch
            {
                return false;
            }
        }

        private static bool IsRealExecutable(string path)
        {
            try
            {
                if (!File.Exists(path)) return false;
                if (path.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) >= 0) return false;
                FileInfo fi = new FileInfo(path);
                return fi.Length > 1024;
            }
            catch
            {
                return false;
            }
        }

        private static string FindPythonExecutable(out bool isPyLauncher)
        {
            isPyLauncher = false;
            string[] names = new string[] { "pythonw.exe", "python.exe", "pyw.exe", "py.exe" };
            string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] extraDirs = new string[]
            {
                Path.Combine(localApp, "Python", "bin"),
                Path.Combine(localApp, "Programs", "Python", "Python314"),
                Path.Combine(localApp, "Programs", "Python", "Python313"),
                Path.Combine(localApp, "Programs", "Python", "Python312"),
                Path.Combine(localApp, "Programs", "Python", "Python311"),
                Path.Combine(localApp, "Programs", "Python", "Python310")
            };

            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
            string[] pathDirs = pathEnv.Split(new char[] { ';' }, StringSplitOptions.RemoveEmptyEntries);

            foreach (string name in names)
            {
                foreach (string d in pathDirs)
                {
                    string candidate = Path.Combine(d.Trim(), name);
                    if (IsRealExecutable(candidate))
                    {
                        isPyLauncher = (name == "py.exe" || name == "pyw.exe");
                        return candidate;
                    }
                }
                foreach (string d in extraDirs)
                {
                    string candidate = Path.Combine(d, name);
                    if (IsRealExecutable(candidate))
                    {
                        isPyLauncher = (name == "py.exe" || name == "pyw.exe");
                        return candidate;
                    }
                }
            }

            foreach (string rootDir in new string[] {
                Path.Combine(localApp, "Python"),
                Path.Combine(localApp, "Programs", "Python"),
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles)
            })
            {
                if (!Directory.Exists(rootDir)) continue;
                try
                {
                    foreach (string dir in Directory.GetDirectories(rootDir, "Python*"))
                    {
                        foreach (string name in names)
                        {
                            string cand = Path.Combine(dir, name);
                            if (IsRealExecutable(cand))
                            {
                                isPyLauncher = (name == "py.exe" || name == "pyw.exe");
                                return cand;
                            }
                        }
                    }
                }
                catch { }
            }

            return null;
        }

        private static bool StartPythonHidden(string workDir, string scriptPath, string extraArgs)
        {
            bool isPyLauncher;
            string pyExe = FindPythonExecutable(out isPyLauncher);
            if (string.IsNullOrEmpty(pyExe)) return false;

            string prefix = isPyLauncher ? "-3 " : "";
            string args = string.Format("{0}\"{1}\"{2}", prefix, scriptPath, string.IsNullOrEmpty(extraArgs) ? "" : " " + extraArgs);
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pyExe;
            psi.Arguments = args;
            psi.WorkingDirectory = workDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;
            Process.Start(psi);
            return true;
        }

        private static void OpenDesktopControlCenter(string url)
        {
            string[] envKeys = new string[] { "ProgramFiles(x86)", "ProgramFiles", "LocalApplicationData" };
            string[] relPaths = new string[]
            {
                @"Microsoft\Edge\Application\msedge.exe",
                @"Google\Chrome\Application\chrome.exe",
                @"BraveSoftware\Brave-Browser\Application\brave.exe"
            };
            foreach (string key in envKeys)
            {
                string root = Environment.GetEnvironmentVariable(key);
                if (string.IsNullOrEmpty(root)) continue;
                foreach (string rel in relPaths)
                {
                    string exe = Path.Combine(root, rel);
                    if (File.Exists(exe))
                    {
                        try
                        {
                            ProcessStartInfo psi = new ProcessStartInfo();
                            psi.FileName = exe;
                            psi.Arguments = string.Format("--app=\"{0}\" --window-size=1140,830 --new-window", url);
                            psi.UseShellExecute = false;
                            Process.Start(psi);
                            return;
                        }
                        catch { }
                    }
                }
            }
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
    }
}
'''


SETUP_CS = r'''
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace PCPhoneRemoteSetup
{
    static class Native
    {
        [DllImport("kernel32.dll")]
        public static extern bool AttachConsole(int dwProcessId);

        [DllImport("Gdi32.dll")]
        public static extern IntPtr CreateRoundRectRgn(int left, int top, int right, int bottom, int w, int h);
    }

    public class BufferedPanel : Panel
    {
        public BufferedPanel()
        {
            this.DoubleBuffered = true;
            this.SetStyle(
                ControlStyles.AllPaintingInWmPaint |
                ControlStyles.UserPaint |
                ControlStyles.OptimizedDoubleBuffer |
                ControlStyles.ResizeRedraw,
                true
            );
            this.UpdateStyles();
        }
    }

    public static class Loc
    {
        private static readonly Dictionary<string, Dictionary<string, string>> Maps = BuildMaps();

        private static Dictionary<string, Dictionary<string, string>> BuildMaps()
        {
            Dictionary<string, Dictionary<string, string>> m = new Dictionary<string, Dictionary<string, string>>();

            Dictionary<string, string> ru = new Dictionary<string, string>();
            ru["subtitle"] = "Установщик ПК-сервера и Центра управления";
            ru["dirLabel"] = "Папка установки:";
            ru["browse"] = "Обзор...";
            ru["pinLabel"] = "Единый PIN-код подключения (для телефона и входа):";
            ru["chkShortcuts"] = "Создать ярлыки на Рабочем столе и в меню «Пуск»";
            ru["chkAutostart"] = "Запускать сервер в фоне при старте Windows";
            ru["chkFirewall"] = "Открыть порты в Брандмауэре Windows (TCP 8765, UDP 8766 · UAC)";
            ru["chkUnlock"] = "Установить вход с экрана блокировки (Credential Provider · UAC)";
            ru["installBtn"] = "Установить PC Phone Remote  →";
            ru["progressHeading"] = "Установка компонентов...";
            ru["progressInit"] = "Инициализация...";
            ru["doneBadge"] = "✅  Установка успешно завершена!";
            ru["doneInfo"] = "Теперь вы можете открыть анимированный Центр управления на ПК, отсканировать QR-код с телефона и управлять компьютером по Wi-Fi.";
            ru["launchBtn"] = "🚀  Запустить PC Phone Remote";
            ru["closeBtn"] = "Закрыть";
            ru["uninstallDone"] = "PC Phone Remote удалён с компьютера.";
            ru["installErr"] = "Ошибка установки: ";
            ru["stepStopping"] = "Остановка предыдущих фоновых процессов...";
            ru["stepCheckingPy"] = "Проверка среды Python 3...";
            ru["stepInstallPy"] = "Python 3 не найден — установка через winget...";
            ru["stepExtracting"] = "Распаковка компонентов приложения и иконок...";
            ru["stepPin"] = "Настройка единого PIN и конфигурации...";
            ru["stepDeps"] = "Установка Python-библиотек (qrcode, pillow, psutil)...";
            ru["stepShortcuts"] = "Создание ярлыков на Рабочем столе и в меню «Пуск»...";
            ru["stepAutostart"] = "Настройка автозапуска Windows...";
            ru["stepElevated"] = "Применение сетевых правил и системных компонентов (UAC)...";
            ru["stepDone"] = "Установка завершена!";
            m["ru"] = ru;

            Dictionary<string, string> en = new Dictionary<string, string>();
            en["subtitle"] = "PC Server & Animated Control Center Setup";
            en["dirLabel"] = "Install folder:";
            en["browse"] = "Browse...";
            en["pinLabel"] = "Unified connection PIN (for phone & sign-in):";
            en["chkShortcuts"] = "Create Desktop and Start Menu shortcuts";
            en["chkAutostart"] = "Start server in background on Windows startup";
            en["chkFirewall"] = "Open Windows Firewall ports (TCP 8765, UDP 8766 · UAC)";
            en["chkUnlock"] = "Install Lock Screen Unlock (Credential Provider · UAC)";
            en["installBtn"] = "Install PC Phone Remote  →";
            en["progressHeading"] = "Installing components...";
            en["progressInit"] = "Initializing...";
            en["doneBadge"] = "✅  Installation complete!";
            en["doneInfo"] = "You can now launch the PC Control Center, scan the QR code from your phone, and control this computer over Wi-Fi.";
            en["launchBtn"] = "🚀  Launch PC Phone Remote";
            en["closeBtn"] = "Close";
            en["uninstallDone"] = "PC Phone Remote has been removed from this computer.";
            en["installErr"] = "Installation error: ";
            en["stepStopping"] = "Stopping previous background processes...";
            en["stepCheckingPy"] = "Checking Python 3 environment...";
            en["stepInstallPy"] = "Python 3 not found — installing via winget...";
            en["stepExtracting"] = "Extracting application files and icons...";
            en["stepPin"] = "Configuring Unified PIN and settings...";
            en["stepDeps"] = "Installing Python packages (qrcode, pillow, psutil)...";
            en["stepShortcuts"] = "Creating Desktop & Start Menu shortcuts...";
            en["stepAutostart"] = "Configuring Windows startup entry...";
            en["stepElevated"] = "Applying firewall rules & system components (UAC)...";
            en["stepDone"] = "Installation finished!";
            m["en"] = en;

            Dictionary<string, string> uk = new Dictionary<string, string>();
            uk["subtitle"] = "Інсталятор ПК-сервера та Центру керування";
            uk["dirLabel"] = "Тека встановлення:";
            uk["browse"] = "Огляд...";
            uk["pinLabel"] = "Єдиний PIN-код підключення (для телефону та входу):";
            uk["chkShortcuts"] = "Створити ярлики на Робочому столі та в меню «Пуск»";
            uk["chkAutostart"] = "Запускати сервер у фоні при старті Windows";
            uk["chkFirewall"] = "Відкрити порти у Брандмауері Windows (TCP 8765, UDP 8766 · UAC)";
            uk["chkUnlock"] = "Встановити вхід з екрана блокування (Credential Provider · UAC)";
            uk["installBtn"] = "Встановити PC Phone Remote  →";
            uk["progressHeading"] = "Встановлення компонентів...";
            uk["progressInit"] = "Ініціалізація...";
            uk["doneBadge"] = "✅  Встановлення успішно завершено!";
            uk["doneInfo"] = "Тепер ви можете відкрити анімований Центр керування на ПК, відсканувати QR-код з телефону та керувати комп'ютером по Wi-Fi.";
            uk["launchBtn"] = "🚀  Запустити PC Phone Remote";
            uk["closeBtn"] = "Закрити";
            uk["uninstallDone"] = "PC Phone Remote видалено з комп'ютера.";
            uk["installErr"] = "Помилка встановлення: ";
            uk["stepStopping"] = "Зупинка попередніх фонових процесів...";
            uk["stepCheckingPy"] = "Перевірка середовища Python 3...";
            uk["stepInstallPy"] = "Python 3 не знайдено — встановлення через winget...";
            uk["stepExtracting"] = "Розпакування файлів програми та іконок...";
            uk["stepPin"] = "Налаштування єдиного PIN та конфігурації...";
            uk["stepDeps"] = "Встановлення бібліотек Python (qrcode, pillow, psutil)...";
            uk["stepShortcuts"] = "Створення ярликів на Робочому столі та в меню «Пуск»...";
            uk["stepAutostart"] = "Налаштування автозапуску Windows...";
            uk["stepElevated"] = "Застосування правил брандмауера та модулів (UAC)...";
            uk["stepDone"] = "Встановлення завершено!";
            m["uk"] = uk;

            return m;
        }

        public static string DetectDefaultLang()
        {
            try
            {
                string iso = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName.ToLowerInvariant();
                if (iso == "uk") return "uk";
                if (iso == "ru" || iso == "be" || iso == "kk") return "ru";
                return "en";
            }
            catch
            {
                return "en";
            }
        }

        public static string Normalize(string lang)
        {
            if (string.IsNullOrEmpty(lang)) return DetectDefaultLang();
            string low = lang.Trim().ToLowerInvariant();
            if (Maps.ContainsKey(low)) return low;
            return "en";
        }

        public static string Get(string lang, string key)
        {
            string code = Normalize(lang);
            Dictionary<string, string> dict = Maps[code];
            string val;
            if (dict.TryGetValue(key, out val)) return val;
            if (Maps["en"].TryGetValue(key, out val)) return val;
            return key;
        }
    }

    public class InstallOptions
    {
        public string InstallDir;
        public string Pin;
        public string Lang = "ru";
        public bool CreateShortcuts = true;
        public bool EnableAutostart = true;
        public bool OpenFirewall = true;
        public bool InstallUnlock = false;
        public bool RegisterUninstall = true;
    }

    public class InstallerEngine
    {
        public static string DefaultInstallDir()
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs", "PCPhoneRemote"
            );
        }

        public static string RandomPin()
        {
            Random rnd = new Random();
            return rnd.Next(100000, 999999).ToString();
        }

        private static bool IsRealExe(string path)
        {
            try
            {
                if (!File.Exists(path)) return false;
                if (path.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) >= 0) return false;
                return new FileInfo(path).Length > 1024;
            }
            catch
            {
                return false;
            }
        }

        public static string FindPython(out bool isPyLauncher)
        {
            isPyLauncher = false;
            string[] names = new string[] { "python.exe", "py.exe" };
            string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] extraDirs = new string[]
            {
                Path.Combine(localApp, "Python", "bin"),
                Path.Combine(localApp, "Programs", "Python", "Python314"),
                Path.Combine(localApp, "Programs", "Python", "Python313"),
                Path.Combine(localApp, "Programs", "Python", "Python312"),
                Path.Combine(localApp, "Programs", "Python", "Python311")
            };
            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
            foreach (string name in names)
            {
                foreach (string d in pathEnv.Split(new char[] { ';' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    string p = Path.Combine(d.Trim(), name);
                    if (IsRealExe(p))
                    {
                        isPyLauncher = (name == "py.exe" || name == "pyw.exe");
                        return p;
                    }
                }
                foreach (string d in extraDirs)
                {
                    string p = Path.Combine(d, name);
                    if (IsRealExe(p))
                    {
                        isPyLauncher = (name == "py.exe" || name == "pyw.exe");
                        return p;
                    }
                }
            }
            foreach (string rootDir in new string[] {
                Path.Combine(localApp, "Python"),
                Path.Combine(localApp, "Programs", "Python")
            })
            {
                if (!Directory.Exists(rootDir)) continue;
                try
                {
                    foreach (string d in Directory.GetDirectories(rootDir, "Python*"))
                    {
                        string p = Path.Combine(d, "python.exe");
                        if (IsRealExe(p)) return p;
                    }
                }
                catch { }
            }
            return null;
        }

        public static void Run(InstallOptions opts, Action<int, string> progress)
        {
            string lang = Loc.Normalize(opts.Lang);
            progress(8, Loc.Get(lang, "stepStopping"));
            StopRunningInstances();

            progress(18, Loc.Get(lang, "stepCheckingPy"));
            bool isPyLauncher;
            string pyExe = FindPython(out isPyLauncher);
            if (string.IsNullOrEmpty(pyExe))
            {
                progress(22, Loc.Get(lang, "stepInstallPy"));
                TryInstallPythonWinget();
                pyExe = FindPython(out isPyLauncher);
            }

            progress(34, Loc.Get(lang, "stepExtracting"));
            Directory.CreateDirectory(opts.InstallDir);
            ExtractEmbeddedPayload(opts.InstallDir);

            string pcDir = Path.Combine(opts.InstallDir, "pc-phone-remote");
            string launcherExe = Path.Combine(pcDir, "PCPhoneRemote.exe");
            Directory.CreateDirectory(Path.Combine(pcDir, "shared"));

            progress(55, Loc.Get(lang, "stepPin"));
            ConfigureUnifiedPin(pcDir, opts.Pin, pyExe, isPyLauncher);

            if (!string.IsNullOrEmpty(pyExe))
            {
                progress(68, Loc.Get(lang, "stepDeps"));
                InstallPythonDeps(pyExe, isPyLauncher);
            }

            if (opts.CreateShortcuts && File.Exists(launcherExe))
            {
                progress(80, Loc.Get(lang, "stepShortcuts"));
                CreateShortcuts(launcherExe, opts.InstallDir);
            }

            if (opts.EnableAutostart && File.Exists(launcherExe))
            {
                progress(88, Loc.Get(lang, "stepAutostart"));
                SetAutostart(launcherExe);
            }

            if (opts.RegisterUninstall)
            {
                RegisterAddRemovePrograms(opts.InstallDir, launcherExe);
            }

            if (opts.OpenFirewall || opts.InstallUnlock)
            {
                progress(94, Loc.Get(lang, "stepElevated"));
                ApplyElevatedSteps(opts.InstallDir, opts.OpenFirewall, opts.InstallUnlock);
            }

            progress(100, Loc.Get(lang, "stepDone"));
        }

        private static void StopRunningInstances()
        {
            try
            {
                RunQuiet("taskkill.exe", "/F /IM PCPhoneRemote.exe", 2000);
                RunQuiet("powershell.exe", "-NoProfile -WindowStyle Hidden -Command \"Get-CimInstance Win32_Process -Filter \\\"Name LIKE 'python%' AND CommandLine LIKE '%app.py%'\\\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }\"", 3500);
            }
            catch { }
        }

        private static void TryInstallPythonWinget()
        {
            try
            {
                RunQuiet("winget.exe", "install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements", 120000);
            }
            catch { }
        }

        private static void ExtractEmbeddedPayload(string targetDir)
        {
            Assembly asm = Assembly.GetExecutingAssembly();
            using (Stream stream = asm.GetManifestResourceStream("payload.zip"))
            {
                if (stream == null) throw new Exception("Embedded payload.zip not found.");
                using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        if (string.IsNullOrEmpty(entry.Name)) continue;
                        string rel = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                        string destPath = Path.GetFullPath(Path.Combine(targetDir, rel));
                        if (!destPath.StartsWith(Path.GetFullPath(targetDir), StringComparison.OrdinalIgnoreCase)) continue;
                        Directory.CreateDirectory(Path.GetDirectoryName(destPath));
                        using (Stream inStream = entry.Open())
                        using (FileStream outStream = new FileStream(destPath, FileMode.Create, FileAccess.Write))
                        {
                            inStream.CopyTo(outStream);
                        }
                    }
                }
            }
        }

        private static void ConfigureUnifiedPin(string pcDir, string pin, string pyExe, bool isPyLauncher)
        {
            string cfgPath = Path.Combine(pcDir, "config.json");
            string cleanPin = (pin ?? "").Trim().Replace("\\", "").Replace("\"", "");
            if (string.IsNullOrEmpty(cleanPin)) cleanPin = RandomPin();

            if (File.Exists(cfgPath))
            {
                string existing = File.ReadAllText(cfgPath, Encoding.UTF8);
                if (Regex.IsMatch(existing, "\"pin\"\\s*:\\s*\"[^\"]*\""))
                {
                    string updated = Regex.Replace(existing, "\"pin\"\\s*:\\s*\"[^\"]*\"", "\"pin\": \"" + cleanPin + "\"");
                    File.WriteAllText(cfgPath, updated, new UTF8Encoding(false));
                    return;
                }
                int brace = existing.IndexOf('{');
                if (brace >= 0)
                {
                    string patched = existing.Substring(0, brace + 1) + "\n  \"pin\": \"" + cleanPin + "\"," + existing.Substring(brace + 1);
                    File.WriteAllText(cfgPath, patched, new UTF8Encoding(false));
                    return;
                }
            }
            string json = "{\n  \"pin\": \"" + cleanPin + "\",\n  \"rdp\": {\n    \"host\": \"\",\n    \"port\": 3389,\n    \"username\": \"\",\n    \"gateway\": \"\"\n  }\n}\n";
            File.WriteAllText(cfgPath, json, new UTF8Encoding(false));
        }

        private static void InstallPythonDeps(string pyExe, bool isPyLauncher)
        {
            string prefix = isPyLauncher ? "-3 " : "";
            RunQuiet(pyExe, prefix + "-m pip install --disable-pip-version-check --quiet qrcode pillow psutil", 60000);
        }

        private static void CreateShortcuts(string launcherExe, string installDir)
        {
            string pcDir = Path.Combine(installDir, "pc-phone-remote");
            string icoPath = Path.Combine(pcDir, "assets", "app_icon.ico");
            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string startDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", "PC Phone Remote");
            Directory.CreateDirectory(startDir);

            bool updatedDesktopSubfolder = false;
            try
            {
                if (Directory.Exists(desktopDir))
                {
                    foreach (string subDir in Directory.GetDirectories(desktopDir))
                    {
                        string subMain = Path.Combine(subDir, "PC Phone Remote.lnk");
                        string subCfg = Path.Combine(subDir, "Configure PC Phone Remote.lnk");
                        if (File.Exists(subMain))
                        {
                            CreateShortcutFile(subMain, launcherExe, "", pcDir, icoPath, "PC Phone Remote Control Center");
                            updatedDesktopSubfolder = true;
                        }
                        if (File.Exists(subCfg))
                        {
                            CreateShortcutFile(subCfg, launcherExe, "", pcDir, icoPath, "PC Phone Remote Control Center");
                            updatedDesktopSubfolder = true;
                        }
                    }
                }
            }
            catch { }

            string rootMain = Path.Combine(desktopDir, "PC Phone Remote.lnk");
            string rootCfg = Path.Combine(desktopDir, "Configure PC Phone Remote.lnk");
            if (!updatedDesktopSubfolder || File.Exists(rootMain))
            {
                CreateShortcutFile(rootMain, launcherExe, "", pcDir, icoPath, "PC Phone Remote Control Center");
            }
            if (File.Exists(rootCfg))
            {
                CreateShortcutFile(rootCfg, launcherExe, "", pcDir, icoPath, "PC Phone Remote Control Center");
            }

            CreateShortcutFile(Path.Combine(startDir, "PC Phone Remote.lnk"), launcherExe, "", pcDir, icoPath, "PC Phone Remote Control Center");
            CreateShortcutFile(Path.Combine(startDir, "PC Phone Remote (Tray).lnk"), launcherExe, "--tray", pcDir, icoPath, "PC Phone Remote System Tray");
            string startCfg = Path.Combine(startDir, "Configure PC Phone Remote.lnk");
            if (File.Exists(startCfg))
            {
                CreateShortcutFile(startCfg, launcherExe, "", pcDir, icoPath, "PC Phone Remote Control Center");
            }
        }

        private static void CreateShortcutFile(string lnkPath, string target, string args, string workDir, string iconPath, string desc)
        {
            try
            {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                if (shellType == null) return;
                object shell = Activator.CreateInstance(shellType);
                object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { lnkPath });
                Type scType = shortcut.GetType();
                scType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
                scType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { args });
                scType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { workDir });
                if (File.Exists(iconPath))
                {
                    scType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { iconPath });
                }
                scType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { desc });
                scType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
            }
            catch { }
        }

        private static void SetAutostart(string launcherExe)
        {
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run"))
            {
                if (key != null)
                {
                    key.SetValue("PCPhoneRemote", "\"" + launcherExe + "\" --server", RegistryValueKind.String);
                }
            }
        }

        private static void RegisterAddRemovePrograms(string installDir, string launcherExe)
        {
            try
            {
                string setupCopy = Path.Combine(installDir, "PCPhoneRemote-Setup.exe");
                try
                {
                    File.Copy(Assembly.GetExecutingAssembly().Location, setupCopy, true);
                }
                catch { }
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PCPhoneRemote"))
                {
                    if (key != null)
                    {
                        key.SetValue("DisplayName", "PC Phone Remote");
                        key.SetValue("DisplayVersion", "2.3.1");
                        key.SetValue("Publisher", "PC Phone Remote");
                        key.SetValue("InstallLocation", installDir);
                        string ico = Path.Combine(installDir, "pc-phone-remote", "assets", "app_icon.ico");
                        key.SetValue("DisplayIcon", File.Exists(ico) ? ico : launcherExe);
                        key.SetValue("UninstallString", "\"" + setupCopy + "\" --uninstall --dir \"" + installDir + "\"");
                        key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                        key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                    }
                }
            }
            catch { }
        }

        private static void ApplyElevatedSteps(string installDir, bool firewall, bool unlockProvider)
        {
            StringBuilder sb = new StringBuilder();
            if (firewall)
            {
                sb.Append("netsh advfirewall firewall delete rule name='PC Phone Remote TCP' > $null 2>&1; ");
                sb.Append("netsh advfirewall firewall add rule name='PC Phone Remote TCP' dir=in action=allow protocol=TCP localport=8765 profile=any > $null 2>&1; ");
                sb.Append("netsh advfirewall firewall delete rule name='PC Phone Remote UDP' > $null 2>&1; ");
                sb.Append("netsh advfirewall firewall add rule name='PC Phone Remote UDP' dir=in action=allow protocol=UDP localport=8766 profile=any > $null 2>&1; ");
            }
            if (unlockProvider)
            {
                string ps1 = Path.Combine(installDir, "windows-unlock", "install-unlock.ps1");
                if (File.Exists(ps1))
                {
                    sb.Append("& '").Append(ps1.Replace("'", "''")).Append("'; ");
                }
            }
            if (sb.Length == 0) return;

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "powershell.exe";
                psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command \"" + sb.ToString().Replace("\"", "\\\"") + "\"";
                psi.Verb = "runas";
                psi.UseShellExecute = true;
                Process p = Process.Start(psi);
                if (p != null) p.WaitForExit(35000);
            }
            catch { }
        }

        public static void Uninstall(string installDir)
        {
            StopRunningInstances();
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true))
                {
                    if (key != null) key.DeleteValue("PCPhoneRemote", false);
                }
                Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PCPhoneRemote", false);
            }
            catch { }

            try
            {
                string desktopLnk = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "PC Phone Remote.lnk");
                if (File.Exists(desktopLnk)) File.Delete(desktopLnk);
                string startDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", "PC Phone Remote");
                if (Directory.Exists(startDir)) Directory.Delete(startDir, true);
            }
            catch { }

            if (!string.IsNullOrEmpty(installDir) && Directory.Exists(installDir))
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo("cmd.exe", string.Format("/c ping -n 2 127.0.0.1 >nul & rmdir /s /q \"{0}\"", installDir));
                    psi.CreateNoWindow = true;
                    psi.UseShellExecute = false;
                    Process.Start(psi);
                }
                catch { }
            }
        }

        private static void RunQuiet(string exe, string args, int timeoutMs)
        {
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = exe;
            psi.Arguments = args;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;
            Process p = Process.Start(psi);
            if (p != null) p.WaitForExit(timeoutMs);
        }
    }

    public class SetupForm : Form
    {
        private BufferedPanel pageConfig;
        private BufferedPanel pageProgress;
        private BufferedPanel pageDone;
        private BufferedPanel progressBarTrack;

        private Label lblD;
        private Button btnBrowse;
        private TextBox txtDir;
        private Label lblP;
        private TextBox txtPin;
        private CheckBox chkShortcuts;
        private CheckBox chkAutostart;
        private CheckBox chkFirewall;
        private CheckBox chkUnlock;
        private Button btnInstall;

        private Label lblHeading;
        private Label lblProgressStatus;
        private Label lblProgressPct;

        private Label lblDoneBadge;
        private Label lblDoneInfo;
        private Button btnLaunch;
        private Button btnFinish;

        private Button btnRu;
        private Button btnEn;
        private Button btnUk;

        private Image logoImg;
        private string activeLang = "ru";
        private int progressValue = 0;
        private float shimmerPos = 0f;
        private string installedDir = "";
        private Point dragStart;
        private bool dragging = false;

        public SetupForm(string initialLang)
        {
            this.activeLang = Loc.Normalize(initialLang);
            this.FormBorderStyle = FormBorderStyle.None;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.Size = new Size(780, 540);
            this.BackColor = Color.FromArgb(11, 11, 16);
            this.ForeColor = Color.FromArgb(244, 246, 252);
            this.Opacity = 0.0;
            this.DoubleBuffered = true;
            this.SetStyle(
                ControlStyles.AllPaintingInWmPaint |
                ControlStyles.UserPaint |
                ControlStyles.OptimizedDoubleBuffer |
                ControlStyles.ResizeRedraw,
                true
            );
            this.UpdateStyles();
            this.Region = Region.FromHrgn(Native.CreateRoundRectRgn(0, 0, Width, Height, 22, 22));

            try
            {
                using (Stream st = Assembly.GetExecutingAssembly().GetManifestResourceStream("logo.png"))
                {
                    if (st != null) logoImg = Image.FromStream(st);
                }
            }
            catch { }

            BuildHeaderButtons();
            BuildConfigPage();
            BuildProgressPage();
            BuildDonePage();
            ApplyLanguage();
            ShowPage(pageConfig);

            System.Windows.Forms.Timer fadeTimer = new System.Windows.Forms.Timer();
            fadeTimer.Interval = 16;
            fadeTimer.Tick += delegate
            {
                if (this.Opacity < 1.0)
                {
                    this.Opacity = Math.Min(1.0, this.Opacity + 0.12);
                }
                else
                {
                    fadeTimer.Stop();
                }
            };
            fadeTimer.Start();

            System.Windows.Forms.Timer progressTimer = new System.Windows.Forms.Timer();
            progressTimer.Interval = 24;
            progressTimer.Tick += delegate
            {
                if (pageProgress.Visible)
                {
                    shimmerPos += 0.03f;
                    if (shimmerPos > 1.4f) shimmerPos = -0.4f;
                    progressBarTrack.Invalidate();
                }
            };
            progressTimer.Start();
        }

        private string T(string key)
        {
            return Loc.Get(activeLang, key);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button == MouseButtons.Left && e.Y < 88)
            {
                dragging = true;
                dragStart = e.Location;
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            if (dragging)
            {
                this.Location = new Point(this.Left + e.X - dragStart.X, this.Top + e.Y - dragStart.Y);
            }
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            base.OnMouseUp(e);
            dragging = false;
        }

        protected override void OnPaintBackground(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (LinearGradientBrush lgb = new LinearGradientBrush(this.ClientRectangle,
                Color.FromArgb(14, 16, 26), Color.FromArgb(9, 10, 15), 45f))
            {
                g.FillRectangle(lgb, this.ClientRectangle);
            }
            using (GraphicsPath gp = new GraphicsPath())
            {
                gp.AddEllipse(-90, -90, 380, 320);
                using (PathGradientBrush pgb = new PathGradientBrush(gp))
                {
                    pgb.CenterColor = Color.FromArgb(34, 94, 234, 212);
                    pgb.SurroundColors = new Color[] { Color.Transparent };
                    g.FillPath(pgb, gp);
                }
            }
            using (GraphicsPath gp2 = new GraphicsPath())
            {
                gp2.AddEllipse(Width - 300, Height - 240, 380, 320);
                using (PathGradientBrush pgb2 = new PathGradientBrush(gp2))
                {
                    pgb2.CenterColor = Color.FromArgb(40, 255, 77, 141);
                    pgb2.SurroundColors = new Color[] { Color.Transparent };
                    g.FillPath(pgb2, gp2);
                }
            }
            using (Pen borderPen = new Pen(Color.FromArgb(42, 255, 255, 255), 1.5f))
            {
                g.DrawRectangle(borderPen, 0, 0, Width - 1, Height - 1);
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;

            if (logoImg != null)
            {
                Rectangle iconRect = new Rectangle(28, 20, 48, 48);
                using (GraphicsPath clipPath = new GraphicsPath())
                {
                    int r = 12;
                    clipPath.AddArc(iconRect.X, iconRect.Y, r * 2, r * 2, 180, 90);
                    clipPath.AddArc(iconRect.Right - r * 2, iconRect.Y, r * 2, r * 2, 270, 90);
                    clipPath.AddArc(iconRect.Right - r * 2, iconRect.Bottom - r * 2, r * 2, r * 2, 0, 90);
                    clipPath.AddArc(iconRect.X, iconRect.Bottom - r * 2, r * 2, r * 2, 90, 90);
                    clipPath.CloseFigure();
                    g.SetClip(clipPath);
                    g.DrawImage(logoImg, iconRect);
                    g.ResetClip();
                }
            }

            using (Font titleFont = new Font("Segoe UI", 16f, FontStyle.Bold))
            using (SolidBrush titleBrush = new SolidBrush(Color.White))
            {
                g.DrawString("PC Phone Remote", titleFont, titleBrush, 88f, 18f);
            }

            using (Font subFont = new Font("Segoe UI", 9.5f))
            using (SolidBrush subBrush = new SolidBrush(Color.FromArgb(165, 174, 202)))
            {
                g.DrawString(T("subtitle"), subFont, subBrush, 90f, 49f);
            }
        }

        private Button CreateLangButton(string code, string label, int x)
        {
            Button b = new Button();
            b.Text = label;
            b.SetBounds(x, 22, 42, 28);
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderSize = 1;
            b.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            b.Cursor = Cursors.Hand;
            b.Click += delegate { SetLanguage(code); };
            return b;
        }

        private void BuildHeaderButtons()
        {
            btnRu = CreateLangButton("ru", "RU", Width - 198);
            btnEn = CreateLangButton("en", "EN", Width - 151);
            btnUk = CreateLangButton("uk", "UK", Width - 104);

            Button btnClose = new Button();
            btnClose.Text = "✕";
            btnClose.SetBounds(Width - 48, 20, 32, 32);
            btnClose.FlatStyle = FlatStyle.Flat;
            btnClose.FlatAppearance.BorderSize = 0;
            btnClose.BackColor = Color.FromArgb(30, 32, 46);
            btnClose.ForeColor = Color.FromArgb(200, 205, 220);
            btnClose.Cursor = Cursors.Hand;
            btnClose.Click += delegate { this.Close(); };

            this.Controls.AddRange(new Control[] { btnRu, btnEn, btnUk, btnClose });
        }

        private void SetLanguage(string code)
        {
            activeLang = Loc.Normalize(code);
            ApplyLanguage();
            this.Invalidate(new Rectangle(84, 46, 460, 28), false);
        }

        private void ApplyLanguage()
        {
            UpdateLangPill(btnRu, activeLang == "ru");
            UpdateLangPill(btnEn, activeLang == "en");
            UpdateLangPill(btnUk, activeLang == "uk");

            lblD.Text = T("dirLabel");
            btnBrowse.Text = T("browse");
            lblP.Text = T("pinLabel");
            chkShortcuts.Text = T("chkShortcuts");
            chkAutostart.Text = T("chkAutostart");
            chkFirewall.Text = T("chkFirewall");
            chkUnlock.Text = T("chkUnlock");
            btnInstall.Text = T("installBtn");

            lblHeading.Text = T("progressHeading");
            if (progressValue == 0) lblProgressStatus.Text = T("progressInit");

            lblDoneBadge.Text = T("doneBadge");
            lblDoneInfo.Text = T("doneInfo");
            btnLaunch.Text = T("launchBtn");
            btnFinish.Text = T("closeBtn");
        }

        private void UpdateLangPill(Button b, bool isActive)
        {
            if (isActive)
            {
                b.BackColor = Color.FromArgb(255, 77, 141);
                b.ForeColor = Color.White;
                b.FlatAppearance.BorderColor = Color.FromArgb(255, 120, 170);
            }
            else
            {
                b.BackColor = Color.FromArgb(26, 29, 44);
                b.ForeColor = Color.FromArgb(165, 174, 200);
                b.FlatAppearance.BorderColor = Color.FromArgb(50, 56, 78);
            }
        }

        private BufferedPanel CreateCardPanel()
        {
            BufferedPanel card = new BufferedPanel();
            card.SetBounds(28, 96, Width - 56, Height - 124);
            card.BackColor = Color.FromArgb(20, 22, 34);
            card.Paint += delegate(object s, PaintEventArgs e)
            {
                using (Pen p = new Pen(Color.FromArgb(40, 255, 255, 255), 1))
                {
                    e.Graphics.DrawRectangle(p, 0, 0, card.Width - 1, card.Height - 1);
                }
            };
            this.Controls.Add(card);
            return card;
        }

        private void BuildConfigPage()
        {
            pageConfig = CreateCardPanel();

            lblD = new Label();
            lblD.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
            lblD.ForeColor = Color.FromArgb(190, 198, 220);
            lblD.SetBounds(24, 22, 380, 20);

            txtDir = new TextBox();
            txtDir.Text = InstallerEngine.DefaultInstallDir();
            txtDir.SetBounds(24, 46, 560, 28);
            txtDir.BackColor = Color.FromArgb(12, 13, 21);
            txtDir.ForeColor = Color.White;
            txtDir.BorderStyle = BorderStyle.FixedSingle;
            txtDir.Font = new Font("Segoe UI", 10f);

            btnBrowse = new Button();
            btnBrowse.SetBounds(594, 45, 102, 29);
            btnBrowse.FlatStyle = FlatStyle.Flat;
            btnBrowse.FlatAppearance.BorderColor = Color.FromArgb(65, 70, 95);
            btnBrowse.BackColor = Color.FromArgb(30, 33, 50);
            btnBrowse.ForeColor = Color.White;
            btnBrowse.Cursor = Cursors.Hand;
            btnBrowse.Click += delegate
            {
                using (FolderBrowserDialog fbd = new FolderBrowserDialog())
                {
                    fbd.SelectedPath = txtDir.Text;
                    if (fbd.ShowDialog() == DialogResult.OK)
                    {
                        txtDir.Text = Path.Combine(fbd.SelectedPath, "PCPhoneRemote");
                    }
                }
            };

            lblP = new Label();
            lblP.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
            lblP.ForeColor = Color.FromArgb(190, 198, 220);
            lblP.SetBounds(24, 88, 520, 20);

            txtPin = new TextBox();
            txtPin.Text = InstallerEngine.RandomPin();
            txtPin.SetBounds(24, 112, 220, 28);
            txtPin.BackColor = Color.FromArgb(12, 13, 21);
            txtPin.ForeColor = Color.FromArgb(94, 234, 212);
            txtPin.BorderStyle = BorderStyle.FixedSingle;
            txtPin.Font = new Font("Consolas", 12f, FontStyle.Bold);

            chkShortcuts = CreateOption(true, 24, 160);
            chkAutostart = CreateOption(true, 24, 192);
            chkFirewall = CreateOption(true, 24, 224);
            chkUnlock = CreateOption(false, 24, 256);

            btnInstall = new Button();
            btnInstall.SetBounds(24, 330, pageConfig.Width - 48, 48);
            btnInstall.FlatStyle = FlatStyle.Flat;
            btnInstall.FlatAppearance.BorderSize = 0;
            btnInstall.BackColor = Color.FromArgb(255, 77, 141);
            btnInstall.ForeColor = Color.White;
            btnInstall.Font = new Font("Segoe UI", 11.5f, FontStyle.Bold);
            btnInstall.Cursor = Cursors.Hand;
            btnInstall.Click += StartInstallClick;

            pageConfig.Controls.AddRange(new Control[] { lblD, txtDir, btnBrowse, lblP, txtPin, chkShortcuts, chkAutostart, chkFirewall, chkUnlock, btnInstall });
        }

        private CheckBox CreateOption(bool isChecked, int x, int y)
        {
            CheckBox cb = new CheckBox();
            cb.Checked = isChecked;
            cb.SetBounds(x, y, 668, 26);
            cb.Font = new Font("Segoe UI", 10f);
            cb.ForeColor = Color.FromArgb(228, 232, 245);
            return cb;
        }

        private void BuildProgressPage()
        {
            pageProgress = CreateCardPanel();

            lblHeading = new Label();
            lblHeading.Font = new Font("Segoe UI", 16f, FontStyle.Bold);
            lblHeading.ForeColor = Color.White;
            lblHeading.SetBounds(32, 48, 480, 34);

            lblProgressStatus = new Label();
            lblProgressStatus.Font = new Font("Segoe UI", 10.5f);
            lblProgressStatus.ForeColor = Color.FromArgb(165, 175, 200);
            lblProgressStatus.SetBounds(32, 100, 640, 26);

            progressBarTrack = new BufferedPanel();
            progressBarTrack.SetBounds(32, 146, pageProgress.Width - 64, 22);
            progressBarTrack.BackColor = Color.FromArgb(12, 14, 22);
            progressBarTrack.Paint += delegate(object s, PaintEventArgs e)
            {
                Graphics g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                int fillW = (int)((progressBarTrack.Width - 4) * (Math.Max(2, progressValue) / 100.0));
                Rectangle fillRect = new Rectangle(2, 2, Math.Max(8, fillW), progressBarTrack.Height - 4);
                using (LinearGradientBrush fill = new LinearGradientBrush(
                    fillRect, Color.FromArgb(94, 234, 212), Color.FromArgb(255, 77, 141), 0f))
                {
                    g.FillRectangle(fill, fillRect);
                }
                int sx = (int)(shimmerPos * Math.Max(40, fillW));
                if (fillW > 20)
                {
                    g.SetClip(fillRect);
                    Rectangle shimRect = new Rectangle(sx - 35, 2, 70, progressBarTrack.Height - 4);
                    using (LinearGradientBrush sb = new LinearGradientBrush(
                        shimRect, Color.FromArgb(0, 255, 255, 255), Color.FromArgb(95, 255, 255, 255), 0f))
                    {
                        g.FillRectangle(sb, shimRect);
                    }
                    g.ResetClip();
                }
            };

            lblProgressPct = new Label();
            lblProgressPct.Text = "0%";
            lblProgressPct.Font = new Font("Segoe UI", 11f, FontStyle.Bold);
            lblProgressPct.ForeColor = Color.FromArgb(94, 234, 212);
            lblProgressPct.SetBounds(32, 180, 120, 24);

            pageProgress.Controls.AddRange(new Control[] { lblHeading, lblProgressStatus, progressBarTrack, lblProgressPct });
        }

        private void BuildDonePage()
        {
            pageDone = CreateCardPanel();

            lblDoneBadge = new Label();
            lblDoneBadge.Font = new Font("Segoe UI", 17f, FontStyle.Bold);
            lblDoneBadge.ForeColor = Color.FromArgb(52, 211, 153);
            lblDoneBadge.SetBounds(32, 54, 640, 38);

            lblDoneInfo = new Label();
            lblDoneInfo.Font = new Font("Segoe UI", 10.5f);
            lblDoneInfo.ForeColor = Color.FromArgb(190, 198, 220);
            lblDoneInfo.SetBounds(32, 106, pageDone.Width - 64, 56);

            btnLaunch = new Button();
            btnLaunch.SetBounds(32, 200, 340, 50);
            btnLaunch.FlatStyle = FlatStyle.Flat;
            btnLaunch.FlatAppearance.BorderSize = 0;
            btnLaunch.BackColor = Color.FromArgb(255, 77, 141);
            btnLaunch.ForeColor = Color.White;
            btnLaunch.Font = new Font("Segoe UI", 11.5f, FontStyle.Bold);
            btnLaunch.Cursor = Cursors.Hand;
            btnLaunch.Click += delegate
            {
                string exe = Path.Combine(installedDir, "pc-phone-remote", "PCPhoneRemote.exe");
                if (File.Exists(exe))
                {
                    Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = Path.GetDirectoryName(exe) });
                }
                this.Close();
            };

            btnFinish = new Button();
            btnFinish.SetBounds(388, 200, 150, 50);
            btnFinish.FlatStyle = FlatStyle.Flat;
            btnFinish.FlatAppearance.BorderColor = Color.FromArgb(65, 70, 95);
            btnFinish.BackColor = Color.FromArgb(30, 33, 50);
            btnFinish.ForeColor = Color.White;
            btnFinish.Font = new Font("Segoe UI", 10.5f);
            btnFinish.Cursor = Cursors.Hand;
            btnFinish.Click += delegate { this.Close(); };

            pageDone.Controls.AddRange(new Control[] { lblDoneBadge, lblDoneInfo, btnLaunch, btnFinish });
        }

        private void ShowPage(Panel target)
        {
            pageConfig.Visible = (target == pageConfig);
            pageProgress.Visible = (target == pageProgress);
            pageDone.Visible = (target == pageDone);
        }

        private void StartInstallClick(object sender, EventArgs e)
        {
            InstallOptions opts = new InstallOptions();
            opts.InstallDir = txtDir.Text.Trim();
            if (string.IsNullOrEmpty(opts.InstallDir)) opts.InstallDir = InstallerEngine.DefaultInstallDir();
            installedDir = opts.InstallDir;
            opts.Pin = txtPin.Text.Trim();
            opts.Lang = activeLang;
            opts.CreateShortcuts = chkShortcuts.Checked;
            opts.EnableAutostart = chkAutostart.Checked;
            opts.OpenFirewall = chkFirewall.Checked;
            opts.InstallUnlock = chkUnlock.Checked;

            ShowPage(pageProgress);

            Thread worker = new Thread(delegate()
            {
                try
                {
                    InstallerEngine.Run(opts, delegate(int pct, string msg)
                    {
                        this.BeginInvoke((MethodInvoker)delegate
                        {
                            progressValue = pct;
                            lblProgressStatus.Text = msg;
                            lblProgressPct.Text = string.Format("{0}%", pct);
                            progressBarTrack.Invalidate();
                        });
                    });
                    this.BeginInvoke((MethodInvoker)delegate { ShowPage(pageDone); });
                }
                catch (Exception ex)
                {
                    this.BeginInvoke((MethodInvoker)delegate
                    {
                        MessageBox.Show(T("installErr") + ex.Message, "PC Phone Remote Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        ShowPage(pageConfig);
                    });
                }
            });
            worker.IsBackground = true;
            worker.Start();
        }
    }

    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            bool silent = false;
            bool uninstall = false;
            bool help = false;
            InstallOptions opts = new InstallOptions();
            opts.InstallDir = InstallerEngine.DefaultInstallDir();
            opts.Pin = "";
            opts.Lang = Loc.DetectDefaultLang();

            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i].Trim();
                string low = a.ToLowerInvariant();
                if (low == "--help" || low == "-h" || low == "/?") help = true;
                else if (low == "--silent" || low == "/s") silent = true;
                else if (low == "--uninstall") uninstall = true;
                else if (low == "--no-autostart") opts.EnableAutostart = false;
                else if (low == "--no-firewall") opts.OpenFirewall = false;
                else if (low == "--no-shortcuts") opts.CreateShortcuts = false;
                else if (low == "--no-reg") opts.RegisterUninstall = false;
                else if (low == "--with-unlock") opts.InstallUnlock = true;
                else if (low == "--dir" && i + 1 < args.Length) opts.InstallDir = args[++i];
                else if (low == "--pin" && i + 1 < args.Length) opts.Pin = args[++i];
                else if (low == "--lang" && i + 1 < args.Length) opts.Lang = Loc.Normalize(args[++i]);
            }

            if (help)
            {
                Native.AttachConsole(-1);
                Console.WriteLine("PC Phone Remote Setup Installer");
                Console.WriteLine("Usage: PCPhoneRemote-Setup.exe [--silent] [--lang ru|en|uk] [--dir <path>] [--pin <pin>] [--with-unlock] [--no-autostart] [--no-firewall] [--no-shortcuts] [--no-reg] [--uninstall]");
                return 0;
            }

            if (uninstall)
            {
                InstallerEngine.Uninstall(opts.InstallDir);
                if (!silent)
                {
                    MessageBox.Show(Loc.Get(opts.Lang, "uninstallDone"), "PC Phone Remote", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                return 0;
            }

            if (silent)
            {
                InstallerEngine.Run(opts, delegate(int pct, string msg) { });
                return 0;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm(opts.Lang));
            return 0;
        }
    }
}
'''


LINUX_RUN_HEADER = """#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${HOME}/.local/share/PCPhoneRemote"
PIN_ARG=""
SILENT=0
UNINSTALL=0
INSTALL_LANG=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir) INSTALL_DIR="${2:-$INSTALL_DIR}"; shift 2 ;;
    --pin) PIN_ARG="${2:-}"; shift 2 ;;
    --lang) INSTALL_LANG="${2:-}"; shift 2 ;;
    --silent) SILENT=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --help|-h)
      echo "PC Phone Remote Linux Installer"
      echo "Usage: $0 [--lang ru|en|uk] [--dir <path>] [--pin <pin>] [--silent] [--uninstall] [--help]"
      exit 0
      ;;
    *) shift ;;
  esac
done

if [ -z "$INSTALL_LANG" ]; then
  LOC="${LC_ALL:-${LANG:-en}}"
  case "$LOC" in
    ru*|be*|kk*) INSTALL_LANG="ru" ;;
    uk*) INSTALL_LANG="uk" ;;
    *) INSTALL_LANG="en" ;;
  esac
fi

case "$INSTALL_LANG" in
  ru)
    MSG_UNINST="Удаление PC Phone Remote..."
    MSG_DONE_UNINST="Готово."
    MSG_BANNER="        PC Phone Remote — Установщик Linux v2.3.1        "
    MSG_S1="Проверка Python 3 и системных зависимостей..."
    MSG_S2="Распаковка файлов в ${INSTALL_DIR}..."
    MSG_S3="Настройка виртуального окружения Python..."
    MSG_S4="Настройка единого PIN-кода..."
    MSG_PIN_PROMPT="Введите единый PIN (4-8 цифр)"
    MSG_S5="Создание ярлыка .desktop и автозапуска..."
    MSG_S6="Настройка правил брандмауэра (8765/tcp, 8766/udp)..."
    MSG_S7="Установка завершена!"
    MSG_READY="✅ PC Phone Remote готов к работе! Запуск: pc-phone-remote"
    ;;
  uk)
    MSG_UNINST="Видалення PC Phone Remote..."
    MSG_DONE_UNINST="Готово."
    MSG_BANNER="        PC Phone Remote — Інсталятор Linux v2.3.1        "
    MSG_S1="Перевірка Python 3 та системних компонентів..."
    MSG_S2="Розпакування файлів у ${INSTALL_DIR}..."
    MSG_S3="Налаштування віртуального середовища Python..."
    MSG_S4="Налаштування єдиного PIN-коду..."
    MSG_PIN_PROMPT="Введіть єдиний PIN (4-8 цифр)"
    MSG_S5="Створення ярлика .desktop та автозапуску..."
    MSG_S6="Налаштування правил брандмауера (8765/tcp, 8766/udp)..."
    MSG_S7="Встановлення завершено!"
    MSG_READY="✅ PC Phone Remote готовий! Запуск: pc-phone-remote"
    ;;
  *)
    MSG_UNINST="Uninstalling PC Phone Remote..."
    MSG_DONE_UNINST="Done."
    MSG_BANNER="        PC Phone Remote — Linux Installer v2.3.1             "
    MSG_S1="Checking Python 3 & desktop helpers..."
    MSG_S2="Extracting application archive to ${INSTALL_DIR}..."
    MSG_S3="Setting up isolated Python virtual environment..."
    MSG_S4="Configuring Unified PIN..."
    MSG_PIN_PROMPT="Enter Unified PIN (4-8 digits)"
    MSG_S5="Installing launcher, .desktop shortcut and user autostart..."
    MSG_S6="Configuring firewall rules (8765/tcp, 8766/udp)..."
    MSG_S7="Installation complete!"
    MSG_READY="✅ PC Phone Remote is ready! Run: pc-phone-remote"
    ;;
esac

CYAN='\\033[1;36m'
PINK='\\033[1;35m'
GREEN='\\033[1;32m'
DIM='\\033[2m'
NC='\\033[0m'

if [ "$UNINSTALL" -eq 1 ]; then
  echo -e "${CYAN}${MSG_UNINST}${NC}"
  systemctl --user disable --now pc-phone-remote.service >/dev/null 2>&1 || true
  rm -f "${HOME}/.config/systemd/user/pc-phone-remote.service"
  rm -f "${HOME}/.config/autostart/pc-phone-remote.desktop"
  rm -f "${HOME}/.local/share/applications/pc-phone-remote.desktop"
  rm -f "${HOME}/.local/bin/pc-phone-remote"
  rm -rf "$INSTALL_DIR"
  echo -e "${GREEN}${MSG_DONE_UNINST}${NC}"
  exit 0
fi

clear || true
echo -e "${PINK}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${PINK}║${MSG_BANNER}║${NC}"
echo -e "${PINK}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

step() {
  local pct="$1"
  local msg="$2"
  local filled=$((pct / 5))
  local empty=$((20 - filled))
  local bar
  bar=$(printf "%${filled}s" | tr ' ' '#')$(printf "%${empty}s" | tr ' ' '-')
  echo -e "${CYAN}[${bar}] ${pct}%${NC}  ${msg}"
}

step 10 "${MSG_S1}"
if ! command -v python3 >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm python python-pip
  else
    echo "Python 3 is required. Please install python3 and re-run."
    exit 1
  fi
fi

step 30 "${MSG_S2}"
mkdir -p "$INSTALL_DIR"
ARCHIVE_LINE=$(awk '/^__ARCHIVE_BELOW__$/{print NR + 1; exit 0;}' "$0")
tail -n+"$ARCHIVE_LINE" "$0" | base64 -d | tar -xzf - -C "$INSTALL_DIR"

PC_DIR="${INSTALL_DIR}/pc-phone-remote"
VENV_DIR="${INSTALL_DIR}/venv"

step 50 "${MSG_S3}"
if python3 -m venv "$VENV_DIR" >/dev/null 2>&1; then
  PY_BIN="${VENV_DIR}/bin/python"
else
  PY_BIN="$(command -v python3)"
fi
"$PY_BIN" -m pip install --disable-pip-version-check --quiet qrcode pillow psutil >/dev/null 2>&1 || true

step 65 "${MSG_S4}"
if [ -z "$PIN_ARG" ] && [ "$SILENT" -eq 0 ] && [ -t 0 ]; then
  DEFAULT_PIN=$("$PY_BIN" -c 'import secrets; print(secrets.randbelow(900000)+100000)')
  read -r -p "${MSG_PIN_PROMPT} [${DEFAULT_PIN}]: " INPUT_PIN || true
  PIN_ARG="${INPUT_PIN:-$DEFAULT_PIN}"
fi
if [ -z "$PIN_ARG" ]; then
  PIN_ARG=$("$PY_BIN" -c 'import secrets; print(secrets.randbelow(900000)+100000)')
fi

"$PY_BIN" - "${PC_DIR}/config.json" "$PIN_ARG" <<'PYCFG'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text("utf-8")) if p.exists() else {}
d["pin"] = sys.argv[2]
d.pop("allowed_pins", None)
d.setdefault("rdp", {"host": "", "port": 3389, "username": "", "gateway": ""})
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
PYCFG

step 80 "${MSG_S5}"
mkdir -p "${HOME}/.local/bin" "${HOME}/.local/share/applications" "${HOME}/.config/autostart" "${HOME}/.config/systemd/user"
cat > "${HOME}/.local/bin/pc-phone-remote" <<LAUNCH
#!/usr/bin/env bash
exec "${PY_BIN}" "${PC_DIR}/configure.py" "\\$@"
LAUNCH
chmod +x "${HOME}/.local/bin/pc-phone-remote"

cat > "${HOME}/.local/share/applications/pc-phone-remote.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PC Phone Remote
Comment=Control PC from your phone with QR pairing
Exec=${HOME}/.local/bin/pc-phone-remote
Path=${PC_DIR}
Icon=${PC_DIR}/assets/app_icon_512.png
Terminal=false
Categories=Utility;Network;
DESK

cp "${HOME}/.local/share/applications/pc-phone-remote.desktop" "${HOME}/.config/autostart/pc-phone-remote.desktop"

cat > "${HOME}/.config/systemd/user/pc-phone-remote.service" <<SVC
[Unit]
Description=PC Phone Remote Server
After=network-online.target graphical-session.target

[Service]
ExecStart=${PY_BIN} ${PC_DIR}/app.py --host 0.0.0.0 --port 8765
WorkingDirectory=${PC_DIR}
Restart=on-failure
RestartSec=4

[Install]
WantedBy=default.target
SVC

systemctl --user daemon-reload >/dev/null 2>&1 || true
systemctl --user enable --now pc-phone-remote.service >/dev/null 2>&1 || true

step 92 "${MSG_S6}"
if command -v ufw >/dev/null 2>&1; then
  sudo -n ufw allow 8765/tcp >/dev/null 2>&1 || true
  sudo -n ufw allow 8766/udp >/dev/null 2>&1 || true
elif command -v firewall-cmd >/dev/null 2>&1; then
  sudo -n firewall-cmd --permanent --add-port=8765/tcp >/dev/null 2>&1 || true
  sudo -n firewall-cmd --permanent --add-port=8766/udp >/dev/null 2>&1 || true
  sudo -n firewall-cmd --reload >/dev/null 2>&1 || true
fi

if ! curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
  nohup "$PY_BIN" "${PC_DIR}/app.py" --host 0.0.0.0 --port 8765 >/dev/null 2>&1 &
  sleep 1.2
fi

step 100 "${MSG_S7}"
echo -e "${GREEN}${MSG_READY}${NC}"
if [ "$SILENT" -eq 0 ] && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  "${HOME}/.local/bin/pc-phone-remote" >/dev/null 2>&1 &
fi
exit 0
__ARCHIVE_BELOW__
"""


def compile_cs(csc_exe: str, source: str, out_exe: Path, icon_path: Path, resources: list[tuple[Path, str]] | None = None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cs_path = Path(tmp) / "program.cs"
        cs_path.write_text(source, encoding="utf-8-sig")
        cmd = [
            csc_exe,
            "/nologo",
            "/target:winexe",
            "/optimize+",
            f"/win32icon:{icon_path}",
            f"/out:{out_exe}",
            "/r:System.dll",
            "/r:System.Drawing.dll",
            "/r:System.Windows.Forms.dll",
            "/r:System.IO.Compression.dll",
            "/r:System.IO.Compression.FileSystem.dll",
        ]
        for res_file, res_name in (resources or []):
            cmd.append(f"/resource:{res_file},{res_name}")
        cmd.append(str(cs_path))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"csc compilation failed ({out_exe.name}):\n{proc.stdout}\n{proc.stderr}")


def build_windows_installers(icon_path: Path) -> None:
    csc = find_csc_exe()
    if not csc:
        raise RuntimeError("C# compiler (csc.exe) not found in .NET Framework v4.0.30319")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    launcher_out = PC_DIR / "PCPhoneRemote.exe"
    print(f"Compiling {launcher_out}...")
    compile_cs(csc, LAUNCHER_CS, launcher_out, icon_path)

    with tempfile.TemporaryDirectory() as tmp:
        payload_zip = Path(tmp) / "payload.zip"
        with zipfile.ZipFile(payload_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for src, arcname in collect_pc_files(include_launcher_exe=True) + collect_unlock_files():
                zf.write(src, arcname)

        logo_png = ASSETS_DIR / "app_icon_512.png"
        setup_root_out = ROOT / "PCPhoneRemote-Setup.exe"
        print(f"Compiling {setup_root_out} (payload {payload_zip.stat().st_size // 1024} KB)...")
        compile_cs(
            csc,
            SETUP_CS,
            setup_root_out,
            icon_path,
            resources=[(payload_zip, "payload.zip"), (logo_png, "logo.png")],
        )
        shutil.copy2(setup_root_out, DIST_DIR / "PCPhoneRemote-Setup.exe")


def build_linux_installer() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for src, arcname in collect_pc_files(include_launcher_exe=False):
            info = tf.gettarinfo(str(src), arcname=arcname)
            if src.suffix in {".py", ".sh"}:
                info.mode = 0o755
            else:
                info.mode = 0o644
            with src.open("rb") as fh:
                tf.addfile(info, fh)

    b64_bytes = base64.b64encode(buf.getvalue())
    wrapped = b"\n".join(b64_bytes[i : i + 76] for i in range(0, len(b64_bytes), 76)) + b"\n"

    run_root_out = ROOT / "PCPhoneRemote-Linux-Installer.run"
    print(f"Building {run_root_out}...")
    with run_root_out.open("wb") as out:
        out.write(LINUX_RUN_HEADER.encode("utf-8"))
        out.write(wrapped)
    shutil.copy2(run_root_out, DIST_DIR / "PCPhoneRemote-Linux-Installer.run")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PC Phone Remote Windows & Linux installers")
    parser.add_argument("--windows-only", action="store_true")
    parser.add_argument("--linux-only", action="store_true")
    args = parser.parse_args()

    icon_path = ensure_assets()
    do_win = args.windows_only or (not args.linux_only and os.name == "nt")
    do_lin = args.linux_only or (not args.windows_only)

    if do_win:
        build_windows_installers(icon_path)
    if do_lin:
        build_linux_installer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
