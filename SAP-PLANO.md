# Realização do plano de manutenção — SAP PM

Acesse `/plano-manutencao` pelo menu **Realização do plano**.

## Fontes

- **IP18:** cadastro mestre de planos e itens, características e filtros.
- **IW39:** ordens, status de execução e horários usados no cálculo de duração.
- **IP24:** ocorrências programadas, inclusive sem ordem.
- **IH06:** descrições dos locais de instalação.

Em **Selecionar arquivos SAP**, escolha o arquivo correspondente a cada fonte na lista da pasta `data`, ou informe seu caminho completo. O nome do arquivo é livre; os cabeçalhos identificam as colunas, independentemente da posição. Cabeçalhos repetidos utilizam a primeira ocorrência. Use tabelas comuns em `.xlsx`. A IW49N não participa dos cálculos nem da seleção de fontes.

Os caminhos escolhidos ficam salvos no SQLite. Uma fonte em branco conserva os dados anteriormente importados. A leitura substitui apenas as fontes selecionadas e preserva grupos e regras. Falhas de leitura ou registros conflitantes interrompem a gravação do lote.

## Cálculos e vínculos

Ordens são vinculadas por item e plano. Na ausência do item na ordem, o vínculo pelo plano exige um único item no mestre. Ordens fora do cadastro IP18 não entram no indicador.

O período considera a data planejada da IP24 quando vinculada; nos demais casos, usa o início básico da IW39. Não são geradas ocorrências retroativamente a partir do ciclo atual da IP18. Itens sem programação datada aparecem separadamente e não entram no índice.

Executado significa confirmação final CNF/CONF ou status de usuário configurado. Status negativos configurados e marca de eliminação prevalecem. As demais ocorrências são não executadas, inclusive sem ordem. Para usar EXCT, configure-o em **Regra de execução da IW39** (ou restaure o banco com a regra já salva).

O índice por quantidade é executadas / previstas × 100, contado por item, ordem e data. Representa o estado da exportação, não comprova execução dentro do prazo.

**H duração** é a diferença absoluta entre `Fim-base (hora)` e `Hora fim`, convertendo `24:00:00` para `00:00:00`. Soma-se uma vez por ordem dentro de cada recorte. H executadas e não executadas usam essa mesma duração, separada por status. Não é mão de obra nem tempo calculado entre datas. Horários ausentes ou inválidos não viram zero. O índice por horas é H executadas / H previstas × 100; sem denominador positivo, fica indisponível.

## Filtros, agrupamentos e consultas

Componentes abaixo de `G-CSN-79-001-010-XXX` são consolidados nesse nível. Locais superiores cadastrados também estão disponíveis; selecionar um pai inclui seus descendentes. A tabela distingue planos cadastrados diretamente em um local superior.

O último período fica salvo no navegador e é restaurado ao reabrir a página. O botão Limpar conserva as datas e remove os demais filtros. Para mudar o período, edite os campos De e Até.

Há filtros de período, ativos, grupo, tipo de ordem, tipo de atividade, centro de trabalho, ABC e texto. Atividade e centro permitem múltiplas seleções. **Todos os Ativos** ignora seleção e busca de ativos e grupo no seu card, mantendo período e demais filtros; clicar nele aplica esse recorte às tabelas e ao gráfico.

Salve um grupo pela seleção de ativos. Em **Gerenciar agrupamentos**, edite nome e composição, ordene os cards, oculte ou exiba e exclua grupos. As preferências persistem no banco. Todos os Ativos permanece fixo no início.

O gráfico mensal alterna entre quantidade de ordens e H Total no eixo secundário; o índice das barras acompanha a opção escolhida.

As tabelas de ativos e planos permitem ordenar pelas colunas. Clicar em um ativo restringe a tabela de planos àquela linha; clicar em um plano abre suas ordens e detalhes. Outro clique recolhe. A consulta respeita o período e os filtros aplicados.

**Exportar Excel** gera duas abas: resumo dos planos com características e ordens/ocorrências com plano e item associados. Respeita filtros, seleção na tabela de ativos e ordenação dos planos. Não exporta apenas a página de registros, nem inclui itens sem data no resumo.

## Transferência e backup

O banco `data/paradas.sqlite3` guarda os dados SAP, regras, agrupamentos e caminhos escolhidos. Para levar o estado atual a outro computador, use o backup da aplicação e siga `INSTALACAO-OFFLINE.md`. Os caminhos antigos precisam ser revisados no destino. As exportações SAP não acompanham o ZIP público.

Testes: `python -m unittest discover -s tests`.
