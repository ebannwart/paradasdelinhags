# Paradas de Linha

Aplicação local em Python e Flask para analisar lançamentos de parada e classificar ofensores. Interface em português, gráficos Plotly servidos localmente, SQLite e importação de Excel. Não depende de conexão com a internet depois de instalada.

## Iniciar no Windows

**Pacote sem pip na máquina de destino:** baixe `ParadasDeLinha-offline.zip` nos [anexos da Release offline](https://github.com/ebannwart/paradasdelinhags/releases/tag/v1.3.0-offline) e siga [INSTALACAO-OFFLINE.md](INSTALACAO-OFFLINE.md). Usa o Python 3.11+ já instalado e inclui as dependências em `libs`. Os ZIPs automáticos de código-fonte não incluem essas bibliotecas.

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

### Configurações e pasta Importacao

Use **Configurações** (`/configuracoes`) para administrar as fontes e ajustes da aplicação. A antiga entrada “Arquivos e ajustes” foi substituída por esta rota. A pasta `Importacao` reúne as planilhas anuais de paradas, o ZPMX e as exportações IH06/IP18/IP24/IW39/IW49N. Na primeira configuração, os arquivos reconhecidos são sugeridos e salvos. Os caminhos são mantidos no perfil local de cada usuário, inclusive quando os arquivos estão temporariamente ausentes. Os dados de gestão ficam no SQLite operacional e no backup. Reiniciar a aplicação não restaura os valores iniciais.

- **Paradas de linha:** lista dos arquivos `.xlsx`, atualização dos dados, tolerância de agrupamento e metas dos KPIs por linha.
- **Análises de falha:** endereço do ZPMX, atualização das análises e quantidade de ocorrências por página.
- **Plano preventivo:** endereços das cinco exportações SAP, atualização das fontes, regras de status IW39 e manutenção dos agrupamentos de ativos. A IW49N é uma fonte auxiliar armazenada; o indicador de execução continua baseado na IW39.

Salve os caminhos antes de atualizar. Os botões de atualização usam os últimos endereços salvos. Substituir o conteúdo de um arquivo no mesmo endereço permite reimportá-lo sem configurar novamente. Retirar um caminho da configuração não exclui os dados já importados. Arquivos de paradas devem ter nomes diferentes, pois cada nome identifica a fonte substituída na reimportação. Campos SAP vazios preservam os dados anteriores daquela transação. Os filtros das análises permanecem nas respectivas rotas; os ajustes estruturais ficam em Configurações.

1. Em **Configurações**, salve os caminhos e use **Atualizar paradas**. A importação acontece em segundo plano e mostra resultados por arquivo.
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

## Acompanhamento mensal de análises de falha

A rota **`/analises-de-falha`** acompanha ocorrências, investigações e ações do ZPMX. Defina o endereço do ZPMX em **Configurações → Análises de falha** e use **Atualizar análises** para ler a exportação Unicode SAP em `.xls`/`.txt` do último endereço salvo. Aceita os relatórios resumido e expandido em duas linhas por registro. Não lê arquivos binários Excel nessa rota.

Selecione linha, mês da ocorrência, status da análise e situação da ação. A linha é extraída do local de instalação, com o nome da unidade operacional exibido ao lado. O mês corresponde à **data da parada**, não à conclusão da investigação. Abra a ocorrência para consultar sintomas, causas, cinco porquês e todas as ações. O status original é preservado: “Falha analisada” não presume que existam medidas abertas, e análise concluída não implica que as ações estejam encerradas.

Os filtros **Centro de trabalho** e **Perda de produção** usam, respectivamente, `Cent. Trab. Resp.` e a marcação `Perda de Produção` do ZPMX. “Não marcada” significa campo presente e vazio, sem inferir perda pela duração. Campos não disponíveis na versão aparecem como não informados. A tabela mostra a data de `Dta. parada processo` e o tempo de `Dur. parada processo`, preservando separadamente a data e duração de produção no registro. A unidade de duração ainda não foi confirmada. Clique em qualquer cabeçalho para alternar a ordenação crescente/decrescente de todo o recorte, antes da paginação. Tempos são ordenados numericamente e valores ausentes ficam no final. A exportação respeita os novos filtros e a ordenação. Importar novamente uma base antiga gera uma nova versão com esses campos, sem alterar o histórico anterior.

**Pendências anteriores** reúne notas anteriores ao mês selecionado com investigação em andamento ou ações não encerradas, respeitando os demais filtros. As abas **Concluídas** e **Todas** consideram todos os meses da importação, com o seletor de mês desabilitado e os demais filtros aplicados. Concluídas exige status de análise concluída e nenhuma ação não encerrada; notas concluídas sem ações registradas também aparecem. Os indicadores superiores representam a aba selecionada (no Registro mensal, representam o mês). O filtro de ação seleciona notas com ao menos uma ação correspondente, restringe os indicadores de ações e a exportação CSV; o detalhe continua mostrando todas as ações da nota.

Cada conteúdo importado gera uma versão imutável no SQLite. Reimportar o mesmo conteúdo seleciona a versão já existente. O seletor de histórico permite comparar as bases. Vencimentos são avaliados na data atual de São Paulo, inclusive ao consultar uma versão antiga: a versão conserva o status importado, mas não representa uma fotografia histórica dos atrasos. Uma ação aberta vence no dia seguinte ao prazo. Conclusões após o prazo não entram como pendências.

Notas repetidas contam uma única vez. Ações são comparadas pelos seus dados completos, preservando ações distintas com numeração reutilizada e sinalizando ambiguidades. A duração mantém a unidade do relatório, ainda não confirmada. Exportações inválidas não substituem versões anteriores. Textos truncados na origem não são reconstruídos.

Em **Registro mensal**, selecione uma linha e mês e salve decisões, responsáveis e prazos da reunião. As anotações persistem por linha/mês e não alteram os status SAP. Histórico e registros fazem parte do banco e do backup existente. Esta primeira versão usa importação manual e não sincroniza alterações de volta ao SAP.

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

## Realização do plano de manutenção (SAP PM)

Acesse **Realização do plano** no menu. A rota usa IP18 como mestre, IW39 para execução e duração, IP24 para programação e IH06 para nomes de locais. Consulte [SAP-PLANO.md](SAP-PLANO.md) para regras, filtros, agrupamentos e exportação Excel.

O ZIP offline desta versão inclui esse módulo e suas dependências. O pacote inclui as fontes da pasta Importacao. O banco local, a chave de sessão e as preferências pessoais não são incluídos. Para preservar configurações e dados, transfira o backup SQLite por um meio interno autorizado; ao mudar de computador, revise os caminhos em **Configurações**.

### Centro de Serviços e escalas dos KPIs

O card **CS — Centro de Serviços** consolida LCI1, LIN1, LCT1G, LPR1, LSL1 e LBT2. O calendário de cada período corresponde a seis linhas em regime 24×7. Os minutos e eventos são somados e os KPIs recalculados a partir dos totais; não se usa média dos índices individuais. As metas do CS podem ser salvas em Configurações. A memória de cálculo sinaliza períodos sem lançamentos de alguma linha. Para cada indicador, os gráficos anual e mensal usam a mesma escala vertical, incluindo a meta.

### Plano de ação dos ofensores

Em `/ofensores?aba=acoes`, selecione um ofensor para ver automaticamente as análises e suas ações. O cruzamento usa a linha produtiva mapeada e a interseção dos intervalos completos das paradas, incluindo ambas as extremidades. O fim SAP é calculado pelo início mais a duração de processo em horas decimais. Qualquer sobreposição, mesmo de um minuto, ou coincidência entre início e fim gera vínculo. Sem duração SAP, compara-se apenas o instante de início. Não há margem adicional para intervalos separados. Não basta ocorrer no mesmo dia. Paradas que atravessam a meia-noite também são consideradas. O formulário mostra os lançamentos correspondentes para conferência. Se houver lançamentos coincidentes de diferentes ofensores, a análise pode aparecer em ambos; uma nota aparece apenas uma vez por ofensor.

O vínculo automático é recalculado a cada consulta, acompanhando importações, classificações e regras de locais. Sem horário ou sem linha correspondente não há associação automática. A importação ZPMX versão 3 preserva o campo Hora parada processo; versões antigas precisam de reimportação para incorporar horários. Vínculos manuais anteriores são preservados e identificados. Ações vêm da última importação SAP, com responsável, prazo e status. Notas históricas de vínculos manuais são sinalizadas e excluídas do resumo atual.

Use **Editar locais e linhas** (também em Configurações) para relacionar locais SAP ou prefixos às linhas. A regra mais específica prevalece, respeitando segmentos separados por hífen. Regras persistem no SQLite e no backup, inclusive listas vazias; novas importações não as sobrescrevem.


### Banco compartilhado e preferências locais

Em **Configurações → Banco de dados e configurações locais**, informe o caminho absoluto do arquivo SQLite (por exemplo, um caminho UNC da pasta de rede). A opção **Criar cópia inicial** usa o backup consistente do SQLite e recusa sobrescrever destinos existentes. Ela preserva os dados de gestão e remove da cópia os caminhos legados de importação. Os outros usuários escolhem **Conectar a banco existente**. A seleção é validada e só entra em vigor após encerrar e iniciar novamente a aplicação; requisições e importações em andamento continuam usando o banco anterior. Faça a primeira cópia sem novas alterações pelos usuários até a conclusão da mudança: alterações posteriores na origem não são sincronizadas com a cópia.

- Banco operacional compartilhado: registros importados, classificação de paradas, ofensores, histórico SAP, medidas e status importados, reuniões mensais, metas, regras de gestão, agrupamentos e mapeamentos de locais/linhas.
- Perfil local do usuário Windows (`%LOCALAPPDATA%/GovernancaGDM`): `database.json` com o caminho escolhido, `preferences.sqlite3` com fontes de importação e tamanho de página, e `.secret` da sessão. Estado visual do menu permanece no navegador. Esses arquivos locais não integram o backup operacional.
- Na primeira abertura da instalação antiga, seus caminhos são migrados para o perfil local. As próximas alterações de caminhos não escrevem no banco operacional. Configurações legadas podem continuar na base original por compatibilidade, mas não são utilizadas após a migração local; a cópia inicial não as inclui.
- Todos precisam usar esta versão, ter acesso de leitura/gravação ao arquivo e à pasta, e configurar os caminhos de importação válidos no próprio computador. Não há contas ou permissões internas por usuário: quem tem acesso ao arquivo pode alterar os dados. A aplicação continua ouvindo apenas em `127.0.0.1`.
- O banco usa journal **DELETE**, não WAL, com espera de até 60 segundos por bloqueios. As gravações são serializadas; a última edição gravada prevalece. Locks de importação da interface são locais ao processo: coordene importações com um responsável, evitando atualizações concorrentes das mesmas fontes. Feche versões antigas antes da mudança de modo.
- SQLite em pasta de rede depende da confiabilidade de bloqueios e sincronização do compartilhamento. Não use OneDrive/Dropbox/pastas sincronizadas para o arquivo em uso. Não houve teste no compartilhamento real do usuário. Para concorrência intensa ou maior confiabilidade, use um servidor que acesse SQLite localmente, ou PostgreSQL. Referências: https://www.sqlite.org/useovernet.html e https://www.sqlite.org/wal.html.
- Se o banco configurado estiver ausente ou inválido na inicialização, a aplicação falha explicitamente: não cria um banco vazio nem retorna silenciosamente ao anterior. Restaure o acesso à rede; para recuperar a configuração, feche a aplicação e corrija o campo `path` de `database.json` (ou remova esse arquivo para voltar ao banco local padrão). Mantenha backups periódicos usando a opção de backup da aplicação.


### Múltiplas configurações do Plano Manter

Em **Configurações → Configurações do Plano Manter**, crie uma configuração com nome próprio, selecione-a e informe suas fontes IP18, IW39, IP24, IH06 e IW49N. Salve os caminhos e use **Atualizar plano preventivo**. Uma configuração nova inicia vazia; campos de fonte vazios preservam apenas o que já foi importado naquela mesma configuração.

Na tela **Plano Manter**, o seletor **Origem dos dados do Plano Manter** alterna a configuração consultada. Relatórios, detalhes, exportações, regras de execução e agrupamentos são isolados por configuração; códigos SAP iguais podem coexistir em origens diferentes. A seleção via parâmetro `profile` acompanha as requisições, inclusive a importação em segundo plano, evitando mudança de destino durante a operação. O cadastro de configurações e seus dados pertencem ao banco operacional compartilhado. Os caminhos dos arquivos continuam locais por usuário e por configuração.

A migração preserva os dados anteriores como **Plano atual**, inclusive regras, grupos e suas posições. É possível renomear essa configuração. Importar uma origem não apaga nem substitui as demais. A migração do esquema exige que todos os usuários atualizem a aplicação antes de reabrir o banco compartilhado; versões antigas não devem continuar gravando nele.
