@echo off
setlocal
rem Altere o caminho abaixo se instalar em outra pasta.
set "APP_DIR=C:\ParadasDeLinha"
if not exist "%APP_DIR%\iniciar.bat" (
  echo Aplicacao nao encontrada em "%APP_DIR%".
  echo Ajuste APP_DIR neste arquivo. Consulte instalacao.md.
  pause
  exit /b 1
)
call "%APP_DIR%\iniciar.bat"
