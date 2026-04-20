#!/usr/bin/env python3
"""
CalNav - Build script
Produce:
  release/CalNav-1.0.0-Portable.zip   -> copia ed esegui ovunque
  release/CalNav-1.0.0-Setup.exe      -> installer Windows (richiede Inno Setup)
  installer.iss                        -> script Inno Setup (ricompilabile manualmente)
"""

import sys
import subprocess
import shutil
import zipfile
import textwrap
from pathlib import Path

# Forza UTF-8 sul terminale Windows (cp1252 non regge i simboli box-drawing)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# -- Configurazione ------------------------------------------------------------
ROOT        = Path(__file__).parent.resolve()
APP_NAME    = "CalNav"
APP_VERSION = "1.0.0-alpha"
ICON_FILE   = ROOT / "logo_browser.ico"
DIST_DIR    = ROOT / "dist"
BUILD_DIR   = ROOT / "build"
RELEASE_DIR = ROOT / "release"

INNO_SETUP_PATHS = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 5\ISCC.exe"),
]


# -- Utility -------------------------------------------------------------------
def hline(char="-"):
    print(f"  {char * 53}")

def step(title: str):
    print()
    hline("-")
    print(f"  {title}")
    hline("-")

def log(msg: str):
    print(f"  {msg}")

def run(*args, **kwargs):
    result = subprocess.run(list(args), **kwargs)
    if result.returncode != 0:
        print(f"\n  ERRORE durante: {args[0]}")
        sys.exit(result.returncode)

def ensure_pkg(import_name: str, pip_name: str):
    # Per PyInstaller controlliamo tramite sottoprocesso (Python 3.14 compat)
    if import_name == "PyInstaller":
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
        )
        if r.returncode == 0:
            log(f"[OK] {pip_name} {r.stdout.decode().strip()} gia' installato")
            return
    else:
        try:
            __import__(import_name)
            log(f"[OK] {pip_name} gia' installato")
            return
        except ImportError:
            pass
    log(f"Installazione {pip_name}...")
    run(sys.executable, "-m", "pip", "install", pip_name, "-q")
    log(f"[OK] {pip_name} installato")


# -- Step 1 - Dipendenze -------------------------------------------------------
def ensure_deps():
    step("Verifica dipendenze build")
    ensure_pkg("PyInstaller", "pyinstaller")
    ensure_pkg("PIL",         "Pillow")


# -- Step 2 - Icona ------------------------------------------------------------
def create_icon():
    step("Preparazione icona")
    if not ICON_FILE.exists():
        log(f"[X] Icona non trovata: {ICON_FILE.name}")
        log("    Metti logo_browser.ico nella cartella del progetto e riprova.")
        sys.exit(1)

    from PIL import Image

    src = Image.open(str(ICON_FILE)).convert("RGBA")
    bbox = src.getbbox()
    content = src.crop(bbox)

    def make_size(img, size):
        margin = max(1, int(size * 0.06))
        inner  = size - margin * 2
        thumb  = img.resize((inner, inner), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(thumb, (margin, margin), thumb)
        return canvas

    sizes  = [16, 24, 32, 48, 64, 128, 256]
    frames = [make_size(content, s) for s in sizes]
    frames[-1].save(
        str(ICON_FILE),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[:-1],
    )
    log(f"[OK] Icona rigenerata: {ICON_FILE.name}  ({len(sizes)} risoluzioni)")


# -- Step 3 - PyInstaller ------------------------------------------------------
def build_exe():
    step("Build eseguibile (PyInstaller)")

    # Usa un distpath con timestamp per evitare il lock di Windows su _internal
    import time as _time
    fresh_dist = ROOT / f"dist_{int(_time.time())}"
    dest       = fresh_dist / APP_NAME

    # Pulisci il build dir precedente (non ha il lock)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name",        APP_NAME,
        "--windowed",
        "--noconfirm",
        "--icon",        str(ICON_FILE),
        "--distpath",    str(fresh_dist),
        "--workpath",    str(BUILD_DIR),
        "--add-data",    f"{ICON_FILE};.",

        # Solo i moduli effettivamente usati — i hook PyInstaller
        # includono automaticamente QtWebEngineProcess.exe e i .pak
        "--hidden-import", "PyQt6.QtWebEngineWidgets",
        "--hidden-import", "PyQt6.QtWebEngineCore",
        "--hidden-import", "PyQt6.QtWebChannel",
        "--hidden-import", "PyQt6.QtNetwork",
        "--hidden-import", "PyQt6.QtPrintSupport",
        "--hidden-import", "cryptography",
        "--hidden-import", "cryptography.fernet",
        "--hidden-import", "cryptography.hazmat.primitives.kdf.pbkdf2",

        # Escludi tutto quello che non serve a un browser
        "--exclude-module", "PyQt6.Qt3DCore",
        "--exclude-module", "PyQt6.Qt3DRender",
        "--exclude-module", "PyQt6.Qt3DAnimation",
        "--exclude-module", "PyQt6.Qt3DExtras",
        "--exclude-module", "PyQt6.QtMultimedia",
        "--exclude-module", "PyQt6.QtMultimediaWidgets",
        "--exclude-module", "PyQt6.QtQml",
        "--exclude-module", "PyQt6.QtQuick",
        "--exclude-module", "PyQt6.QtQuick3D",
        "--exclude-module", "PyQt6.QtQuickWidgets",
        "--exclude-module", "PyQt6.QtBluetooth",
        "--exclude-module", "PyQt6.QtNfc",
        "--exclude-module", "PyQt6.QtSensors",
        "--exclude-module", "PyQt6.QtSerialPort",
        "--exclude-module", "PyQt6.QtSpatialAudio",
        "--exclude-module", "PyQt6.QtTextToSpeech",
        "--exclude-module", "PyQt6.QtRemoteObjects",
        "--exclude-module", "PyQt6.QtDesigner",
        "--exclude-module", "PyQt6.QtHelp",
        "--exclude-module", "PyQt6.QtTest",
        "--exclude-module", "PyQt6.QtStateMachine",
        "--exclude-module", "PyQt6.QtPdf",
        "--exclude-module", "PyQt6.QtPdfWidgets",
        "--exclude-module", "PyQt6.QtSvg",
        "--exclude-module", "PyQt6.QtSvgWidgets",
        "--exclude-module", "PyQt6.QtSql",
        "--exclude-module", "PyQt6.QAxContainer",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "PIL",

        str(ROOT / "calnav.py"),
    ]

    log("Avvio PyInstaller - potrebbe richiedere qualche minuto...")
    run(*cmd, cwd=str(ROOT))

    _strip_unused_qt(dest / "_internal")

    # Sposta in dist/ (rimuovi eventuale vecchio con PowerShell per evitare lock)
    if DIST_DIR.exists():
        subprocess.run(
            ["powershell", "-Command",
             f"Remove-Item -Recurse -Force '{DIST_DIR}' -ErrorAction SilentlyContinue"],
            capture_output=True,
        )
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    try:
        fresh_dist.rename(DIST_DIR)
    except (OSError, FileExistsError):
        # Se il rename fallisce ancora, usa la cartella fresh_dist direttamente
        pass
    final_dist = DIST_DIR if (DIST_DIR / APP_NAME).exists() else fresh_dist
    log(f"[OK] Build: {final_dist.name}/{APP_NAME}/")


def _strip_unused_qt(internal: Path):
    """Rimuove tutto il superfluo Qt dalla cartella _internal."""
    if not internal.exists():
        return

    freed = 0

    def rm_file(p: Path):
        nonlocal freed
        if p.exists():
            freed += p.stat().st_size
            p.unlink()

    def rm_tree(p: Path):
        nonlocal freed
        if p.exists():
            freed += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            shutil.rmtree(p)

    qt6 = internal / "PyQt6" / "Qt6"
    if not qt6.exists():
        return

    # 1) File .debug.pak — risorse DevTools debug, inutili in release (~76 MB)
    for pak in (qt6 / "resources").glob("*.debug.*"):
        rm_file(pak)
    for pak in (qt6 / "resources").glob("*.debug"):
        rm_file(pak)

    # 2) Snapshot V8 debug (~2 MB)
    rm_file(qt6 / "resources" / "v8_context_snapshot.debug.bin")

    # 3) Locali WebEngine: tieni solo italiano + inglese (~47 MB su 53 locali)
    KEEP_LOCALES = {"it", "en-US", "en-GB", "en"}
    locales_dir = qt6 / "translations" / "qtwebengine_locales"
    if locales_dir.exists():
        for pak in locales_dir.glob("*.pak"):
            lang = pak.stem  # es. "it" o "en-US"
            if lang not in KEEP_LOCALES:
                rm_file(pak)

    # 4) Traduzioni Qt: tieni solo it + en (~25 MB sulle restanti)
    tr_dir = qt6 / "translations"
    KEEP_TR_SUFFIXES = ("_it", "_en", "qt_it", "qt_en", "qtbase_it", "qtbase_en")
    if tr_dir.exists():
        for f in tr_dir.glob("*.qm"):
            stem = f.stem
            if not any(stem == k or stem.endswith(k) for k in KEEP_TR_SUFFIXES):
                rm_file(f)

    # 5) Plugin Qt non necessari per un browser
    DROP_PLUGIN_DIRS = {
        "3dgeometryloaders", "3dinputdevices", "3drenderers", "3dsceneparsers",
        "assetimporters", "gamepads", "geoservices", "networkinformation",
        "position", "qmllint", "qmlls", "scxmldatamodel", "sensors",
        "serialport", "texttospeech", "virtualkeyboard", "webview",
        "audio", "mediaservice", "playlistformats", "video",
    }
    plugins_dir = qt6 / "plugins"
    if plugins_dir.exists():
        for d in plugins_dir.iterdir():
            if d.is_dir() and d.name in DROP_PLUGIN_DIRS:
                rm_tree(d)

    log(f"  Rimossi {freed / 1_048_576:.0f} MB di file Qt inutili (debug/locali/plugin)")


def _walk(path: Path):
    """os.walk compatibile con Path per versioni Python < 3.12."""
    import os
    return os.walk(str(path))


# -- Step 4 - Portable ZIP -----------------------------------------------------
def _find_built_app() -> Path:
    """Trova la cartella CalNav/ prodotta dal build — deve contenere CalNav.exe."""
    candidates = [DIST_DIR / APP_NAME] + [
        d / APP_NAME for d in sorted(ROOT.glob("dist_*"), reverse=True)
    ]
    for c in candidates:
        if c.exists() and (c / f"{APP_NAME}.exe").exists():
            return c
    raise FileNotFoundError("CalNav.exe non trovato. Esegui prima il build.")


def make_portable():
    step("Creazione versione Portable")
    RELEASE_DIR.mkdir(exist_ok=True)

    src      = _find_built_app()
    zip_path = RELEASE_DIR / f"{APP_NAME}-{APP_VERSION}-Portable.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in src.rglob("*"):
            if f.is_file():
                zf.write(f, Path(APP_NAME) / f.relative_to(src))

    mb = zip_path.stat().st_size / 1_048_576
    log(f"[OK] Portable ZIP: release/{zip_path.name}  ({mb:.0f} MB)")
    log("  -> Estrai e avvia CalNav.exe - nessuna installazione richiesta")


# -- Step 5 - Inno Setup -------------------------------------------------------
def make_installer():
    step("Creazione installer Windows")
    RELEASE_DIR.mkdir(exist_ok=True)

    iss_path = ROOT / "installer.iss"
    iss_path.write_text(textwrap.dedent(f"""\
        ; CalNav Browser - Inno Setup script
        ; Compilare con: iscc installer.iss

        [Setup]
        AppName={APP_NAME}
        AppVersion={APP_VERSION}
        AppVerName={APP_NAME} {APP_VERSION}
        AppPublisher=CalNav Browser
        AppPublisherURL=https://github.com/Jorkhan-coder/CalNav-Browser
        AppSupportURL=https://github.com/Jorkhan-coder/CalNav-Browser/issues
        AppUpdatesURL=https://github.com/Jorkhan-coder/CalNav-Browser/releases

        ; Installazione in Programmi con privilegi amministratore
        DefaultDirName={{autopf}}\\{APP_NAME}
        DefaultGroupName={APP_NAME}
        PrivilegesRequired=admin
        ArchitecturesInstallIn64BitMode=x64compatible

        ; Registrazione Pannello di Controllo -> Programmi e funzionalita'
        UninstallDisplayName={APP_NAME} Browser
        UninstallDisplayIcon={{app}}\\{APP_NAME}.exe
        AppId={{8F3A2C1D-4B7E-4F9A-B2D6-1E5C3A8F7D2B}}

        ; Output
        OutputDir=release
        OutputBaseFilename={APP_NAME}-{APP_VERSION}-Setup
        SetupIconFile=logo_browser.ico

        ; Compressione massima
        Compression=lzma2/ultra64
        SolidCompression=yes
        WizardStyle=modern

        [Languages]
        Name: "italian"; MessagesFile: "compiler:Languages\\Italian.isl"
        Name: "english"; MessagesFile: "compiler:Default.isl"

        [Tasks]
        Name: "desktopicon"; Description: "Crea icona sul Desktop"; \\
            GroupDescription: "Icone aggiuntive:"; Flags: checked
        Name: "startmenu";   Description: "Aggiungi al Menu Start"; \\
            GroupDescription: "Icone aggiuntive:"; Flags: checked

        [Files]
        Source: "dist\\{APP_NAME}\\*"; DestDir: "{{app}}"; \\
            Flags: ignoreversion recursesubdirs createallsubdirs

        [Icons]
        Name: "{{group}}\\{APP_NAME}"; \\
            Filename: "{{app}}\\{APP_NAME}.exe"; \\
            Tasks: startmenu
        Name: "{{group}}\\Disinstalla {APP_NAME}"; \\
            Filename: "{{uninstallexe}}"; \\
            Tasks: startmenu
        Name: "{{commondesktop}}\\{APP_NAME}"; \\
            Filename: "{{app}}\\{APP_NAME}.exe"; \\
            Tasks: desktopicon

        [Run]
        Filename: "{{app}}\\{APP_NAME}.exe"; \\
            Description: "Avvia {APP_NAME} adesso"; \\
            Flags: nowait postinstall skipifsilent

        [UninstallDelete]
        Type: filesandordirs; Name: "{{app}}"
    """), encoding="utf-8")
    log("[OK] Script Inno Setup: installer.iss")

    # Cerca ISCC.exe
    iscc = next((p for p in INNO_SETUP_PATHS if p.exists()), None)
    if not iscc:
        log("")
        log("[!]  Inno Setup non trovato. Creo installer PowerShell alternativo...")
        _make_powershell_installer()
        return

    log(f"Compilazione con {iscc.name}...")
    result = subprocess.run([str(iscc), str(iss_path)], cwd=str(ROOT))
    if result.returncode == 0:
        out = RELEASE_DIR / f"{APP_NAME}-{APP_VERSION}-Setup.exe"
        mb  = out.stat().st_size / 1_048_576
        log(f"[OK] Installer: release/{out.name}  ({mb:.0f} MB)")
    else:
        log("[X] Compilazione installer fallita - vedi errori sopra.")


# -- PowerShell installer (fallback senza Inno Setup) -------------------------
def _make_powershell_installer():
    """Genera Install-CalNav.bat + installer.ps1 che non richiedono Inno Setup."""
    try:
        src = _find_built_app()
    except FileNotFoundError:
        log("[X] CalNav.exe non trovato — esegui prima il build.")
        return

    RELEASE_DIR.mkdir(exist_ok=True)

    ps1 = RELEASE_DIR / f"{APP_NAME}-{APP_VERSION}-Installer.ps1"
    bat = RELEASE_DIR / f"Installa-{APP_NAME}.bat"

    ps1.write_text(textwrap.dedent(f"""\
        # CalNav Browser {APP_VERSION} - Installer PowerShell
        # Esegui con: powershell -ExecutionPolicy Bypass -File "{ps1.name}"
        param(
            [string]$InstallDir = "$env:LOCALAPPDATA\\{APP_NAME}"
        )
        $ErrorActionPreference = "Stop"

        $src = Join-Path $PSScriptRoot ".."
        # Cerca la cartella CalNav/ accanto allo script (o in dist/)
        $appFolder = $null
        foreach ($candidate in @(
            (Join-Path $src "dist\\{APP_NAME}"),
            (Join-Path $src "{APP_NAME}")
        )) {{
            if (Test-Path (Join-Path $candidate "{APP_NAME}.exe")) {{
                $appFolder = $candidate; break
            }}
        }}
        if (-not $appFolder) {{
            # Cerca in dist_*/
            $appFolder = Get-ChildItem $src -Directory -Filter "dist_*" |
                Sort-Object Name -Descending |
                ForEach-Object {{ Join-Path $_.FullName "{APP_NAME}" }} |
                Where-Object {{ Test-Path (Join-Path $_ "{APP_NAME}.exe") }} |
                Select-Object -First 1
        }}
        if (-not $appFolder) {{
            Write-Host "ERRORE: CalNav.exe non trovato. Esegui prima build.py." -ForegroundColor Red
            exit 1
        }}

        Write-Host "Installazione in: $InstallDir" -ForegroundColor Cyan
        if (Test-Path $InstallDir) {{
            Remove-Item $InstallDir -Recurse -Force
        }}
        Copy-Item $appFolder $InstallDir -Recurse

        # Collegamento Desktop
        $shell   = New-Object -ComObject WScript.Shell
        $lnk     = $shell.CreateShortcut("$env:USERPROFILE\\Desktop\\{APP_NAME}.lnk")
        $lnk.TargetPath       = "$InstallDir\\{APP_NAME}.exe"
        $lnk.WorkingDirectory = $InstallDir
        $lnk.IconLocation     = "$InstallDir\\{APP_NAME}.exe"
        $lnk.Description      = "{APP_NAME} Browser"
        $lnk.Save()

        # Collegamento Menu Start
        $startDir = "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs"
        $lnk2     = $shell.CreateShortcut("$startDir\\{APP_NAME}.lnk")
        $lnk2.TargetPath       = "$InstallDir\\{APP_NAME}.exe"
        $lnk2.WorkingDirectory = $InstallDir
        $lnk2.IconLocation     = "$InstallDir\\{APP_NAME}.exe"
        $lnk2.Save()

        Write-Host "[OK] {APP_NAME} installato con successo!" -ForegroundColor Green
        Write-Host "  -> Trovi l'icona sul Desktop e nel Menu Start."
        Start-Process "$InstallDir\\{APP_NAME}.exe"
    """), encoding="utf-8")

    bat.write_text(
        f"@echo off\r\n"
        f"powershell -ExecutionPolicy Bypass -File \"%~dp0{ps1.name}\"\r\n"
        f"pause\r\n",
        encoding="utf-8",
    )

    log(f"[OK] Installer PowerShell: release/{bat.name}")
    log(f"     Esegui  release\\{bat.name}  per installare CalNav")
    log(f"     Oppure: powershell -ExecutionPolicy Bypass -File release\\{ps1.name}")


# -- Main ----------------------------------------------------------------------
def main():
    hline("=")
    print(f"  CalNav {APP_VERSION} - Build")
    hline("=")

    ensure_deps()
    create_icon()
    build_exe()
    make_portable()
    make_installer()

    print()
    hline("=")
    print(f"  Fatto!  Output in: release/")
    hline("=")
    print()


if __name__ == "__main__":
    main()
