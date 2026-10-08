# Instalação offline — sem pip na máquina de destino

Este pacote usa o **Python já instalado**. Não contém outro Python nem executáveis de terceiros. As dependências ficam na pasta `libs`, junto da aplicação. Não há download nem execução de pip durante a inicialização.

## Como usar

1. Baixe o arquivo **ParadasDeLinha-offline.zip** nos anexos da Release do GitHub. Os arquivos automáticos “Source code” não incluem `libs`.
2. Extraia **todo** o ZIP para uma pasta em que você possa gravar, por exemplo `Documentos\ParadasDeLinha`. Não execute dentro do ZIP.
3. Dê um duplo clique em **Diagnostico offline.bat**. Ele mostra a versão do Python e verifica as bibliotecas locais, a leitura de Excel e os gráficos, sem iniciar o servidor.
4. Dê um duplo clique em **Iniciar offline.bat**. O navegador abrirá quando a aplicação estiver pronta.
5. Mantenha a janela aberta durante o uso. Para encerrar, use Ctrl+C. Se o Windows perguntar se deseja encerrar o lote, confirme.

É necessário **Python 3.11 ou superior**. O pacote foi validado em Windows com Python 3.12 de 64 bits. A versão e a arquitetura da máquina de destino ainda não foram verificadas. As dependências incluídas são código Python, sem `.exe`, `.dll`, `.pyd` ou `.so`; o MarkupSafe usa sua implementação Python de fallback em vez da aceleração nativa opcional. O Python instalado continua usando sua própria biblioteca padrão.

As versões e licenças das dependências acompanham `DEPENDENCIAS-OFFLINE.txt` e as pastas `libs\*.dist-info`. O pacote não altera políticas do Windows nem configurações de segurança.

## Atalho no desktop

Clique com o botão direito em **Iniciar offline.bat** → **Mostrar mais opções** → **Enviar para → Área de trabalho (criar atalho)**. Crie um atalho, não mova o arquivo `.bat` para fora da aplicação.

## Escolher o Python ou ambiente virtual existente

O inicializador tenta `python` e depois `py -3`. Se necessário, edite `Iniciar offline.bat` e insira, antes de `if defined PYTHON_EXE`, uma linha como:

```bat
set "PYTHON_EXE=C:\caminho\do\python.exe"
```

Também pode apontar para o Python de um ambiente virtual criado nessa máquina. Não é necessário instalar dependências nele. Não copie um ambiente virtual de outro computador.

Para iniciar pelo PowerShell, estando na pasta extraída:

```powershell
python -S offline.py
```

Para diagnosticar:

```powershell
python -S offline.py --diagnostico
```

O parâmetro `-S` evita depender dos pacotes instalados no ambiente; `offline.py` inclui a pasta `libs` no caminho de importação. Se uma biblioteca for bloqueada pela política da máquina, o diagnóstico mostrará o erro; o pacote não remove esse bloqueio.

## Levar os dados atuais

Este ZIP inclui as planilhas do repositório, mas **não inclui o banco local, ofensores, metas ou a chave de sessão**. Para levar essas informações, baixe o backup pelo menu da aplicação de origem. Antes de iniciar no destino, coloque-o em `data\paradas.sqlite3` dentro da pasta extraída. Para uma restauração sobre uma instalação existente, encerre o servidor, guarde a pasta `data` anterior e restaure em uma nova pasta `data`, sem arquivos WAL/SHM antigos.

Sem backup, o sistema começa vazio. Importe as planilhas em **Arquivos e ajustes**.

## Problemas comuns

- **Pasta libs ausente:** baixe o anexo `ParadasDeLinha-offline.zip` da Release e extraia tudo.
- **Python não encontrado ou antigo:** indique o caminho do Python 3.11+ autorizado em `PYTHON_EXE`.
- **Acesso negado:** guarde a mensagem completa do diagnóstico para identificar o arquivo ou biblioteca afetado.
- **Porta ocupada:** a aplicação pode já estar aberta. Abra `http://127.0.0.1:5000`. Para escolher outra porta, adicione `set "PARADAS_PORT=5001"` no início do `.bat`.
- **Navegador não abriu:** confira a janela e abra manualmente `http://127.0.0.1:5000`.

## Recriar o pacote (somente na máquina de preparação)

Use o ambiente de desenvolvimento com as dependências instaladas e execute:

```powershell
.\.venv\Scripts\python.exe preparar_offline.py
```

O script gera uma pasta nova dentro de `dist` e um ZIP com a aplicação e as dependências. Não é necessário executá-lo no computador da empresa.
