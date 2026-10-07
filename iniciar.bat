@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute a instalacao descrita no documento instalacao.md antes de iniciar.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo Falha ao ativar o ambiente virtual.
  pause
  exit /b 1
)
echo O navegador abrira automaticamente quando o servidor estiver pronto.
echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
".venv\Scripts\python.exe" iniciar.py
if errorlevel 1 echo Falha ao iniciar. Confira a mensagem acima e o documento instalacao.md.
pause
