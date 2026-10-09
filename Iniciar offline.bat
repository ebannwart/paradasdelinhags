@echo off
setlocal
cd /d "%~dp0"
rem === CONFIGURACAO: preencha com a instalacao correta do Anaconda ===
rem Exemplo: set "ANACONDA_DIR=C:\Users\seu_usuario\anaconda3"
set "ANACONDA_DIR="
rem Use base, o nome de um ambiente, ou o caminho completo desse ambiente.
set "ANACONDA_ENV=base"
rem Com ANACONDA_DIR vazio, usa PYTHON_EXE se definido ou procura python/py.
if defined ANACONDA_DIR goto anaconda
if defined PYTHON_EXE goto personalizado
python -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if not errorlevel 1 goto python
py -3 -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if not errorlevel 1 goto py
echo Python 3.11 ou superior nao encontrado. Consulte INSTALACAO-OFFLINE.md.
pause
exit /b 1
:anaconda
if not exist "%ANACONDA_DIR%\Scripts\activate.bat" (
  echo Nao foi encontrado Scripts\activate.bat na pasta configurada.
  echo Confira ANACONDA_DIR neste arquivo.
  goto erro
)
call "%ANACONDA_DIR%\Scripts\activate.bat" "%ANACONDA_ENV%"
if errorlevel 1 (
  echo Falha ao ativar o ambiente Anaconda configurado.
  goto erro
)
if not defined CONDA_PREFIX (
  echo O Anaconda nao informou o ambiente ativo.
  goto erro
)
set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Python nao encontrado no ambiente Anaconda selecionado.
  goto erro
)
echo Ambiente Anaconda: "%CONDA_PREFIX%"
goto personalizado
:personalizado
"%PYTHON_EXE%" -S offline.py %*
goto fim
:python
python -S offline.py %*
goto fim
:py
py -3 -S offline.py %*
:fim
set "APP_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%APP_EXIT_CODE%"=="0" echo Falha ao executar. Confira as mensagens acima.
pause
exit /b %APP_EXIT_CODE%
:erro
pause
exit /b 1
