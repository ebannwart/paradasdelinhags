# Instalação — Paradas de Linha

Guia para instalar a aplicação em outro computador com **Windows**, criar seu ambiente virtual e iniciar pelo desktop com um duplo clique.

## 1. Instalar Python

Instale **Python 3.11 ou superior** usando o instalador oficial disponível em [python.org](https://www.python.org/downloads/windows/). Habilite a opção de adicionar o Python ao PATH, quando apresentada. Abra uma nova janela do **PowerShell** e execute:

```powershell
py -3 --version
```

Deve aparecer Python 3.11 ou superior. Se `py` não for reconhecido, tente `python --version`; nesse caso, use `python` no lugar de `py -3` no comando de criação do ambiente da etapa 4.

Internet é necessária para instalar Python e bibliotecas. Depois, a aplicação e os gráficos funcionam localmente, sem internet.

## 2. Copiar os arquivos da aplicação

Crie **C:\ParadasDeLinha** na máquina nova e copie para essa pasta:

- Todos os arquivos `.py` da raiz desta aplicação, incluindo `app.py`, `iniciar.py`, `analytics.py`, `maintenance.py`, `database.py`, `modalities.py` e `importer.py`.
- As pastas **static** e **templates**, completas.
- `requirements.txt`, `iniciar.bat`, `Paradas de Linha.bat`, `instalacao.md` e `README.md`.
- As planilhas `.xlsx` que deseja disponibilizar para importação.

Use um pendrive, pasta compartilhada ou ZIP. Confira que existe **C:\ParadasDeLinha\app.py**. Copie os arquivos locais desta versão; um clone do GitHub só serve se as alterações já tiverem sido enviadas ao repositório.

**Não copie `.venv`**: o ambiente virtual deve ser recriado na máquina nova. Não precisa copiar `__pycache__`, `.git`, logs ou imagens de prévia.

## 3. Transferir dados, ofensores e metas

Se deseja continuar com os dados atuais, baixe um **backup** pelo menu lateral da aplicação de origem. O arquivo SQLite contém os registros importados, ofensores, classificações, metas e configurações.

Antes de abrir o sistema na máquina nova:

1. Crie a pasta **C:\ParadasDeLinha\data**.
2. Copie o backup para ela.
3. Renomeie o arquivo para **paradas.sqlite3**.

O caminho final deve ser **C:\ParadasDeLinha\data\paradas.sqlite3**. Use o backup gerado pela aplicação, evitando copiar apenas o banco enquanto o servidor estiver em execução: alterações podem estar no arquivo auxiliar WAL.

Se o destino já tiver dados, encerre seu servidor e guarde a pasta `data` anterior antes de restaurar. Restaure em uma pasta `data` nova, sem arquivos `paradas.sqlite3-wal` ou `paradas.sqlite3-shm` de outro banco.

Para começar do zero, pule a restauração. O sistema criará um banco vazio; importe as planilhas em **Arquivos e ajustes**. Importar somente as planilhas não recupera ofensores nem metas. Não precisa transferir `.secret`: ele será criado automaticamente.

## 4. Criar o ambiente virtual e instalar as bibliotecas

No **PowerShell da máquina de destino**, copie e cole todo este bloco:

```powershell
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'C:\ParadasDeLinha'
if (-not (Test-Path -LiteralPath '.\app.py')) { throw 'app.py nao encontrado.' }

py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente virtual.' }

& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Falha ao atualizar o pip.' }

& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as bibliotecas.' }

& '.\.venv\Scripts\python.exe' -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Existem dependencias inconsistentes.' }

& '.\.venv\Scripts\python.exe' -c "import flask, openpyxl, waitress, plotly; print('Bibliotecas instaladas com sucesso.')"
if ($LASTEXITCODE -ne 0) { throw 'Falha ao verificar as bibliotecas.' }
```

O arquivo `requirements.txt` instala **Flask, openpyxl, waitress e plotly**, com as respectivas dependências. SQLite e os outros módulos da biblioteca padrão já acompanham o Python.

Esses comandos usam diretamente o Python do ambiente virtual, sem exigir ativação manual no PowerShell ou alteração da política de execução de scripts.

## 5. Criar o .bat na Área de Trabalho

Ainda no PowerShell, copie e cole:

```powershell
Set-Location -LiteralPath 'C:\ParadasDeLinha'
$pastaAplicacao = (Get-Location).Path
$areaTrabalho = [Environment]::GetFolderPath('Desktop')
$arquivoDesktop = Join-Path $areaTrabalho 'Paradas de Linha.bat'
$conteudoBat = Get-Content -LiteralPath '.\Paradas de Linha.bat' -Raw
$conteudoBat = $conteudoBat.Replace('set "APP_DIR=C:\ParadasDeLinha"', ('set "APP_DIR=' + $pastaAplicacao + '"'))
Set-Content -LiteralPath $arquivoDesktop -Value $conteudoBat -Encoding OEM
Write-Host "Inicializador criado em: $arquivoDesktop"
```

Se escolheu outra pasta, altere o `Set-Location` dos dois blocos. Prefira um caminho simples, como `C:\ParadasDeLinha`. O comando identifica a Área de Trabalho configurada, inclusive quando está no OneDrive. Caso já exista um `Paradas de Linha.bat` no desktop, esse comando o substitui.

Também pode copiar manualmente **Paradas de Linha.bat** para o desktop. Se necessário, edite a linha `set "APP_DIR=C:\ParadasDeLinha"` com o caminho escolhido.

**Mantenha `iniciar.bat` na pasta da aplicação.** O arquivo do desktop chama esse inicializador, que ativa `.venv\Scripts\activate.bat` e executa `.venv\Scripts\python.exe iniciar.py`. O programa `iniciar.py` inicia `app.py` e abre o navegador quando o servidor responde.

## 6. Usar diariamente

1. Dê um duplo clique em **Paradas de Linha.bat** na Área de Trabalho.
2. Aguarde o navegador. Se ele não abrir, acesse [http://127.0.0.1:5000](http://127.0.0.1:5000).
3. Mantenha a janela do servidor aberta; pode minimizá-la.
4. Para encerrar, pressione **Ctrl+C** nessa janela. Se o Windows perguntar se deseja encerrar o arquivo em lotes, confirme. Fechar somente a aba do navegador não encerra o servidor.

Não precisa reinstalar as bibliotecas nem recriar o ambiente a cada uso. Para iniciar pelo PowerShell:

```powershell
Set-Location -LiteralPath 'C:\ParadasDeLinha'
& '.\iniciar.bat'
```

O endereço `127.0.0.1` funciona somente no próprio computador. As máquinas terão bancos independentes; não há sincronização automática.

## 7. Conferir a instalação

Abra **Visão geral** e **KPI manutenção**, selecione uma linha e confira os gráficos. Se restaurou o backup, confira também ofensores e metas. Se começou do zero, importe uma planilha em **Arquivos e ajustes**.

## Problemas comuns

| Problema | Solução |
| --- | --- |
| `py` não reconhecido | Reabra o PowerShell após instalar Python. Tente `python --version` e use `python -m venv .venv`, ou repare a instalação do Python. |
| Ambiente virtual não encontrado | Execute a etapa 4 na pasta correta. Não use a `.venv` copiada de outra máquina. |
| `ModuleNotFoundError` | Execute novamente `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`. |
| Aplicação não encontrada | Corrija `APP_DIR` no `.bat` do desktop ou refaça a etapa 5. |
| Porta 5000 em uso / erro 10048 | O sistema pode já estar aberto: tente o endereço no navegador e feche a segunda janela. Se outra aplicação usa essa porta, veja abaixo. |
| Navegador não abre | Confira a janela do servidor e abra o endereço manualmente. |
| Banco vazio | Confira o nome e a localização de `data\paradas.sqlite3`, ou importe as planilhas. |
| Falha no pip | Confira internet e acesso ao PyPI. Em rede corporativa, consulte o suporte sobre proxy. |

Para usar outra porta, inclua esta linha no `.bat` do desktop, **antes** da linha `call`:

```bat
set "PARADAS_PORT=5001"
```

O navegador automático usará essa porta; o endereço manual será **http://127.0.0.1:5001**.

Para atualizar futuramente, faça backup, encerre o servidor, substitua os arquivos de código e execute novamente a instalação de `requirements.txt`. Preserve `data` e o ambiente virtual local.
