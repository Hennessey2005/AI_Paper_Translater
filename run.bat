@echo off
rem ================================================================
rem  PDF:Paper Decoding Flow v2.1 - Windows entry (self-bootstrapping)
rem  Use 1: drop one or more PDF files onto this .bat icon
rem  Use 2: run it, then drag a PDF path into the prompt + Enter
rem  First run: auto-creates venv, installs deps, guides API key.
rem  Result : output\<paper title>\  (Explorer opens when done)
rem  NOTE   : messages kept in ASCII to avoid console codepage issues
rem ================================================================
setlocal EnableExtensions
cd /d "%~dp0"
set "MINERU_MODEL_SOURCE=modelscope"
set "PIP_NO_INPUT=1"

rem ---------- collect input files (dropped args first, prompt fallback) ----------
set "ARGS=%*"
if defined ARGS goto :setup

set "PDFS="
set /p "PDFS=Drag PDF into this window (or paste full path), then Enter: "
if not defined PDFS goto :empty
set "PDFS=%PDFS:"=%"
if not exist "%PDFS%" goto :notfound
set "ARGS="%PDFS%""

rem ---------- environment fingerprint: size+mtime of pyproject.toml ----------
:setup
set "VPY=.venv\Scripts\python.exe"
set "MARKER=.venv\.setup_ok"

set "PH="
for %%F in (pyproject.toml) do set "PH=%%~zF_%%~tF"

set "SAVED="
if exist "%MARKER%" for /f "usebackq delims=" %%S in ("%MARKER%") do if not defined SAVED set "SAVED=%%S"

if exist "%VPY%" if "%SAVED%"=="%PH%" goto :config
goto :bootstrap

:bootstrap
rem ---------- find Python 3.10+ (py launcher, then python, then winget) ----------
set "BOOTPY="
where py >nul 2>&1 && set "BOOTPY=py -3"
if not defined BOOTPY ( where python >nul 2>&1 && set "BOOTPY=python" )
if defined BOOTPY goto :make_venv

where winget >nul 2>&1 || goto :no_python
echo [setup] Python not found. Trying one-time install via winget...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "BOOTPY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined BOOTPY goto :make_venv
( where py >nul 2>&1 && set "BOOTPY=py -3" )
if defined BOOTPY goto :make_venv
echo [setup] Python was installed, but this window cannot see it yet.
echo         Close this window, then run run.bat again.
pause
exit /b 1

:no_python
echo [setup] Python 3.10+ not found and winget is unavailable.
echo         Install Python from https://www.python.org/downloads/
echo         (tick "Add python.exe to PATH"), then run run.bat again.
pause
exit /b 1

:make_venv
if exist "%VPY%" goto :install
echo [setup] creating virtualenv (.venv) ...
%BOOTPY% -m venv .venv
if not exist "%VPY%" (
    echo [setup] venv creation failed. Check the message above, then run again.
    pause
    exit /b 1
)

:install
echo [setup] installing dependencies - first run may take several minutes.
echo         Re-running this file resumes an interrupted install.
"%VPY%" -m pip install -e .
if errorlevel 1 (
    echo [setup] pip install failed. Fix the error above, then run run.bat again.
    pause
    exit /b 1
)
> "%MARKER%" echo %PH%
echo [setup] environment ready.

rem ---------- first-run API key guidance ----------
:config
if exist config\config.yaml goto :ready
echo.
echo [setup] creating config\config.yaml from template. Notepad will open.
copy /y config\config.example.yaml config\config.yaml >nul
start "" notepad config\config.yaml
echo   - fill api_key / base_url for your OpenAI-compatible provider
echo     (default: SiliconFlow; VLM=Qwen3-VL, LLM=DeepSeek), save and close Notepad.
echo   - STRONGLY RECOMMENDED: fill api.zhipu_api_key for free mode
echo     (Zhipu GLM-4.6V/4.7-Flash, zero cost; get key at open.bigmodel.cn)
echo   - optional local mode: install Ollama + import a translation model
echo     (GGUF recommended: gemma3-4b-it Q4_K_M, ~2.8GB VRAM; see README)
set /p "_=Press Enter here after saving config\config.yaml: "

rem ---------- run pipeline for each file ----------
:ready
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "OKCNT=0"
set "FAILCNT=0"

rem ---------- 模式选择（平级四选一） ----------
set "MODEFLAG="
echo.
echo Select mode:
echo   1^) default  ^(recommended^)  - SiliconFlow 云端
echo   2^) free                    - 智谱 GLM-4.6V/4.7-Flash 免费云
echo   3^) local                   - Ollama 本地翻译（本地 GPU）
echo   4^) minimum                 - 纯解析（不调任何 API）
set /p "MODE=Input 1-4 (Enter=1): "
if /i "%MODE%"=="2" set "MODEFLAG=--mode free"
if /i "%MODE%"=="3" set "MODEFLAG=--mode local"
if /i "%MODE%"=="4" set "MODEFLAG=--mode minimum"

rem free 需要智谱 key
if "%MODEFLAG%"=="--mode free" (
  set "ZP=NO"
  for /f "usebackq delims=" %%K in (`"%VPY%" -c "import yaml;c=yaml.safe_load(open('config/config.yaml',encoding='utf-8')) or {};a=(c.get('api') or {});k=(a.get('zhipu_api_key') or '');print('HAS' if str(k).strip() else 'NO')"`) do set "ZP=%%K"
  if not "%ZP%"=="HAS" (
    echo [mode] free 需要 api.zhipu_api_key，请在 config.yaml 填写后重试。
    pause
    exit /b 1
  )
)

rem local 需要 Ollama 可达且已 pull 模型
if "%MODEFLAG%"=="--mode local" (
  "%VPY%" -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
  if errorlevel 1 (
    echo [mode] local 需要本机运行 Ollama 且已导入翻译模型（推荐 gemma4b，显存约 2.8GB）。
    echo        先启动: ollama serve  并导入模型后重试（导入方法见 README）。
    pause
    exit /b 1
  )
)

for %%F in (%ARGS%) do call :run_one %%F

echo.
if "%FAILCNT%"=="0" (
    echo ======== DONE. %OKCNT% ok. Results in output\ under paper title, Explorer opened. ========
) else (
    echo ======== Finished: %OKCNT% ok, %FAILCNT% failed. See error messages above. ========
)
pause
exit /b %FAILCNT%

:run_one
echo.
echo ======== Processing: %~1 ========
echo    First parse of a paper downloads MinerU models once and takes ~10 min.
echo    Keep this window open. CLI 可用 --mode minimum(纯解析)/local(Ollama) 等。
"%VPY%" -m paper_translate %MODEFLAG% --open %1
if not errorlevel 1 goto :run_ok
rem no paren-block here: file names may contain ")" and break block parsing
echo [run] FAILED: %~1
set /a FAILCNT+=1
goto :eof
:run_ok
set /a OKCNT+=1
goto :eof

:empty
echo No input path.
pause
exit /b 1

:notfound
echo File not found: %PDFS%
pause
exit /b 1
