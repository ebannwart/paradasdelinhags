@echo off
setlocal
cd /d "%~dp0"
rem Opcional: defina PYTHON_EXE com o caminho do python.exe autorizado.
if defined PYTHON_EXE goto personalizado
python -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if not errorlevel 1 goto python
py -3 -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if not errorlevel 1 goto py
echo Python 3.11 ou superior nao encontrado. Consulte INSTALACAO-OFFLINE.md.
pause
exit /b 1
:personalizado
"%PYTHON_EXE%" -S offline.py %*
goto fim
:python
python -S offline.py %*
goto fim
:py
py -3 -S offline.py %*
:fim
echo.
echo Mantenha esta janela aberta durante o uso. Ctrl+C encerra o servidor.
pause
