# Paradas de Linha

Aplicação local em Python e Flask para analisar lançamentos de parada e classificar ofensores. Interface em português, gráficos Plotly servidos localmente, SQLite e importação de Excel. Não depende de conexão com a internet depois de instalada.

## Iniciar no Windows

**Pacote sem pip na máquina de destino:** baixe `ParadasDeLinha-offline.zip` nos [anexos da Release offline](https://github.com/ebannwart/paradasdelinhags/releases/tag/v1.0.1-offline) e siga [INSTALACAO-OFFLINE.md](INSTALACAO-OFFLINE.md). Usa o Python 3.11+ já instalado e inclui as dependências em `libs`. Os ZIPs automáticos de código-fonte não incluem essas bibliotecas.

Para transferir a aplicação para outro computador, siga o [guia de instalação](instalacao.md), com comandos para criar o ambiente virtual, instalar bibliotecas, restaurar o backup e criar o inicializador `.bat` no desktop.

Nesta instalação, o ambiente `.venv` já está preparado. Abra `iniciar.bat`; o navegador abrirá automaticamente em **http://127.0.0.1:5000**. Mantenha a janela aberta durante o uso; Ctrl+C encerra o servidor.

Para uma instalação nova, use Python 3.11 ou superior:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

O servidor Waitress escuta apenas em `127.0.0.1`. Não há autenticação para acesso remoto. Para mudar a porta, defina `PARADAS_PORT` antes de iniciar.

## Fluxo de uso

1. Em **Arquivos e ajustes**, marque as planilhas da pasta ou envie outros `.xlsx`. A importação acontece em segundo plano e mostra resultados por arquivo.
2. Em **Visão geral**, selecione anos, meses, equipamentos, ofensores e demais filtros. Clique em **Aplicar filtros**. Sem seleção em um campo significa todos. Use Ctrl para selecionar vários valores.
3. O Pareto em destaque permite escolher tempo total ou quantidade de paradas (eventos), além de mostrar ou ocultar os valores sobre as barras. O heatmap permite agrupar as colunas por mês ou por ano, ordenadas cronologicamente, e ordena os ofensores de forma decrescente pelo último período com dados nas fontes do recorte. A medida pode ser tempo ou quantidade. A quantidade anual conta eventos distintos, sem somar contagens mensais que poderiam repetir um evento. Todos os filtros aplicados são respeitados, inclusive meses selecionados no agrupamento anual. Clique nas barras ou células para consultar os lançamentos. A evolução, a composição e o gráfico por equipamento complementam a análise. O percentual acumulado por quantidade usa a soma das contagens por ofensor; um evento com vários ofensores participa de cada categoria.
4. Em **Lançamentos**, busque palavras no motivo/observação. Todas as palavras são exigidas, ignorando acentos e caixa. Classifique pela lista de cada linha ou selecione vários registros e aplique um ofensor em lote. A seleção da página e a seleção de todos os resultados são explícitas.
5. Crie ofensores no catálogo ou na própria tela de lançamentos. Cada registro tem um ofensor principal. Remova a classificação selecionando **Não classificado**. Equipamentos do cadastro são referências, não restrições.
6. Use **Corrigir tipo** para ajustar a detecção de preventiva/reparo geral ou voltar à detecção automática.
7. Exporte o recorte como CSV com separador `;`, codificação UTF-8 e fonte de cada linha. Baixe uma cópia completa do banco pelo link no menu lateral.

## Regras dos dados

- Cabeçalhos são reconhecidos pelo nome, com/sem `(PE)`, acentos e quebras de linha. `Equipamento` e `Equipto (PE)` são equivalentes. As colunas de teste são ignoradas. O cabeçalho deve estar nas primeiras 20 linhas de cada aba.
- Fonte, aba e número de linha são preservados. Linhas com equipamento/data/minutos inválidos são rejeitadas e reportadas. Importação sem registros válidos não substitui a anterior.
- Um arquivo de mesmo nome substitui suas próprias referências. Registros com conteúdo igual mantêm ofensor e ajuste de tipo. Se o conteúdo do registro mudou, é um novo lançamento e precisa de classificação. Arquivos com conteúdo idêntico e mesmo nome não são reprocessados.
- Lançamentos exatamente iguais em equipamento, datas, minutos, responsável original, motivo, observação, equipe e turno contam uma vez, mesmo em arquivos distintos. A posição da linha não faz parte da identidade. Duas linhas realmente distintas com todos esses campos iguais também serão consolidadas; confira o contador de duplicatas se isso ocorrer.
- Registros antigos sem fonte vigente são mantidos internamente para preservar classificações em reimportações, mas não entram nas análises.
- Um evento agrupa lançamentos do mesmo equipamento em ordem cronológica. Usa o maior fim da sequência e tolerância padrão de **1 minuto**, incluindo intervalo zero e sobreposição. Horários são arredondados ao segundo para tratar imprecisões do Excel (por exemplo, `59.999`). Motivos diferentes não interrompem o evento.
- Sobreposições são sinalizadas, mas os minutos do Excel não são alterados. Somar esses minutos pode contar tempos sobrepostos. O detalhe mostra tanto a soma informada quanto o intervalo decorrido.
- O evento é calculado usando todas as fontes importadas. Os filtros escolhem lançamentos; contar eventos usa os eventos distintos presentes nesse recorte. O detalhe exibe o evento completo, incluindo linhas fora do filtro atual.
- Os filtros e os meses dos gráficos usam a **data de início**. Uma parada que atravessa o mês não é rateada. O tempo principal é o valor de **Tempo Parada Calculada**, em minutos, não a diferença das datas.
- A frequência de um ofensor é a quantidade de eventos distintos com esse ofensor. Um evento pode ter vários ofensores; frequências por categoria ou mês não são aditivas.
- O responsável original é preservado. Mecânica, Elétrica, Operação, Externa, Programação e Setup são normalizados quando reconhecidos; categorias desconhecidas ficam com o texto original.
- `MP`, `preventiva`, `manutenção preventiva`, `RG`, `reparo geral` e `reforma geral`, em motivo/observação, sugerem o tipo. São regras textuais, sujeitas a falsos positivos; a correção manual prevalece. O responsável permanece independente.
- Meses sem registros nas fontes do recorte ficam como lacunas, nunca como zero presumido. Quando a fonte contém registros naquele mês mas nenhum passa nos demais filtros, o valor é zero. **Presença de registros não comprova cobertura integral do mês.** A visão geral não infere dias trabalhados. A rota KPI usa a convenção de calendário 24×7 descrita abaixo.

## KPI manutenção

A rota **`/kpi-manutencao`**, disponível no menu lateral, apresenta cinco pares de gráficos: histórico anual à esquerda e meses do ano mais recente das fontes selecionadas à direita. Escolha uma linha por vez. As metas são gravadas no SQLite por linha e indicador, aparecem nos dois gráficos e fazem parte do backup. IMC/DGFM usam %, MTBF usa horas e MTTR usa minutos. Metas zero são válidas; campo vazio remove a meta. DGFM e MTBF têm meta mínima; IMC, MTTR e eventos de falha têm meta máxima. A meta de eventos usa eventos/mês.

Modalidades, mutuamente exclusivas:

| Código | Composição |
|---|---|
| ME | Manutenção elétrica |
| MM | Manutenção mecânica |
| Preventiva | Manutenção preventiva + reparo geral, com prioridade sobre o responsável original |
| OP | Operação |
| ST | Setup |
| PP | Programação sem preventivas/reparo geral |
| EX | Todas as demais paradas |

As modalidades também estão nos filtros, lançamentos, composição da visão geral e CSV. O responsável original é preservado. O ajuste manual do tipo continua prevalecendo. A detecção de preventiva considera também o nome do responsável, inclusive `ZHST MANUTENÇÃO PREVENTIVA`.

**Base aprovada: tempo calendário 24×7**, incluindo fins de semana e feriados. Use T em minutos, C = ME + MM, P = Preventiva e N = eventos distintos com minutos de ME/MM:

- IMC = `[C / T] × 100`: percentual de tempo parado em ME + MM. Quanto menor, melhor.
- DGFM = `[1 − (C + P) / T] × 100`.
- MTBF = `(T − C) / N / 60`, em horas. Nesta convenção, a base desconta apenas corretivas, incluindo OP/ST/PP/EX/Preventiva no tempo sem falha corretiva. Não equivale às horas efetivas de produção.
- MTTR = `C / N`, em minutos de parada por evento corretivo. Não distingue espera de reparo e trabalho efetivo da equipe.

Eventos de falha: no anual, eventos distintos do ano divididos pelos meses com lançamentos da linha; no mensal, eventos distintos do mês. Meses com dados e zero falhas entram no divisor; meses sem dados ficam indisponíveis. Meses parciais contam como um mês sem extrapolação. O divisor é visível no hover e na memória de cálculo. Eventos que atravessam meses aparecem em cada mês, mas uma vez no ano, portanto a média anual pode diferir da média das barras mensais.

ME e MM em um mesmo evento contam uma falha. N = 0 torna MTBF/MTTR indisponíveis, sem inventar zero ou infinito. As metas não alteram o cálculo.

A cobertura usa o início do primeiro dia e o fim do último dia encontrados nas datas de início de cada fonte, unindo intervalos sobrepostos sem duplicar o calendário. Por exemplo, a fonte de 2026 até 30/09 tem janeiro a setembro; outubro a dezembro ficam sem resultado. O mês final parcial considera só os dias abrangidos pela fonte. Essa é uma hipótese de cobertura, explicitada na tela; a existência de registros não prova que a fonte esteja completa.

Meses sem lançamentos da linha não recebem disponibilidade presumida de 100%. O anual considera os meses com dados e marca o período como parcial quando o calendário não cobre o ano inteiro. Anos são recalculados pelos numeradores, denominadores e eventos distintos, nunca pela média simples dos meses.

Na rota KPI, minutos de lançamentos que atravessam períodos são rateados proporcionalmente ao intervalo entre início e fim, preservando como total o tempo calculado do Excel. Trechos fora da cobertura das fontes não entram e são informados na tela. Um evento entre meses pode aparecer em ambos, mas é contado uma vez no ano. A visão geral mantém a regra anterior de atribuição pela data de início; por isso seus totais por período podem diferir dos KPIs nas fronteiras.

Sobreposições não são corrigidas automaticamente. Percentuais com paradas consideradas maiores que T ficam indisponíveis. Início igual ao fim com minutos positivos é sinalizado e atribuído ao período do início. A memória de cálculo apresenta calendário, minutos das sete modalidades, eventos e observações por período.

## Persistência e cópia de segurança

O banco fica em `data/paradas.sqlite3`; a chave de sessão em `data/.secret`. Ambos estão fora do Git. Os arquivos Excel originais não são alterados. Uma cópia baixada em **Baixar cópia de segurança** inclui fontes importadas, ofensores, classificações e tolerância.

Para restaurar, encerre o servidor, guarde uma cópia da pasta `data` atual e substitua o banco pelo arquivo de backup, com o nome `paradas.sqlite3`. Não misture um banco restaurado com arquivos `-wal`/`-shm` de outro banco: preserve esses arquivos com a cópia antiga e restaure em uma pasta `data` limpa. Reinicie o servidor. A interface não oferece restauração automática nesta versão.

## Validação

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testes cobrem importação/reimportação, variantes de cabeçalho, duplicação, agrupamento, sobreposição, classificação, filtros, exportação e backup. Dados de teste são temporários.

## Estrutura

- `app.py`: servidor, API local, importação em segundo plano e exportações.
- `database.py`: esquema SQLite e normalização.
- `importer.py`: leitura das planilhas e agrupamento de eventos.
- `analytics.py`: filtros e agregações.
- `templates/index.html`, `static/`: interface e gráficos.

Limites iniciais: arquivos `.xlsx`, 100 MB por envio, uma importação/reagrupamento por vez, uso pessoal local. Não há sincronização com o GitHub, classificação por IA ou login multiusuário nesta versão.

No KPI manutencao, clique nas barras ou nos rotulos de mes/ano do IMC para consultar abaixo dele as 10 maiores paradas corretivas (ME + MM), agrupadas por evento e ordenadas pelos minutos rateados dentro do periodo e das fontes selecionadas. A lista inclui descricoes e acesso ao evento completo.
