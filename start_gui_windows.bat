@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" transcribe_betagaki_gui.py
  goto done
)
if defined CONDA_PREFIX (
  if exist "%CONDA_PREFIX%\python.exe" (
    "%CONDA_PREFIX%\python.exe" transcribe_betagaki_gui.py
    goto done
  )
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3 transcribe_betagaki_gui.py
) else (
  python transcribe_betagaki_gui.py
)
:done
if errorlevel 1 (
  echo Startup failed. See README.md and install requirements in the selected Python environment.
  pause
  exit /b 1
)
endlocal
