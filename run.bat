@echo off
rem ================================================================
rem  AI_Paper_Translater v2.1 - Windows entry (self-bootstrapping)
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
set /p "_=Press Enter here after saving config\config.yaml: "

rem ---------- run pipeline for each file ----------
:ready
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "OKCNT=0"
set "FAILCNT=0"
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
echo    Keep this window open. Use "--offline" via CLI if you want local-only.
"%VPY%" -m paper_translate --open %1
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
