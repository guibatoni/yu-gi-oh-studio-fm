# Metodologia, fontes e limites

## Origem de cada dado

- `SLUS_014.11`, offsets `0x801D4244` e `0x801D5332`: cartas/nível/tipo/estrelas, ver `fmstudio/tables.py`.
- `SLUS_014.11`, bancos `0x801B0000`, `0x801C0000`, `0x801D0000`: menus, diálogos, descrições e nomes. Ponteiros em `0x801C0000` e `0x801D5800` e mapa de glifos em `0x801D9000`.
- `DATA/WA_MRG.MRG`, setor `(ID-1)*7+722`: arte principal da carta, paleta e faixas.
- `DATA/WA_MRG.MRG`, setor `ID-1`: miniatura da carta e paleta.
- `DATA/WA_MRG.MRG`, blocos `0xF35000` e `0xF55000`: retratos.
- `DATA/WA_MRG.MRG`, setor `0x21D5`: quadros de cenas da campanha, com paleta própria por registro.
- `DATA/WA_MRG.MRG` em `0xB63000`: tabelas de fusão, equipamentos e rituais.
- `DATA/WA_MRG.MRG` em `0xE99800` e `0xFB9800`: pools de duelistas e senhas.

Referências detalhadas:

- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/tools/pc/text_listing.py
- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/tools/pc/extract_images.py
- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/tools/pc/fm_editor/README.md
- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/notes/pc-build.md
- https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/master/LICENSE

## Verificação antes da extração

O programa compara os 722 registros numéricos do executável com o catálogo importado. Também compara hashes do SLUS e WA quando registrados. Uma mistura de imagens de discos distintos é recusada. O nome do arquivo não é prova suficiente de compatibilidade.

## Fidelidade e limitações

1. A extração de banco de texto é linear: para comandos condicionais e desvio, marca a referência em vez de supor a frase exibida. Retém os comandos em formato textual para posterior análise.
2. A codificação Shift-JIS do jogo pode incluir glifos e pictogramas próprios. A tabela do executável é utilizada quando possível; códigos desconhecidos ficam marcados.
3. A representação de cenas e faixas é uma imagem técnica e pode não coincidir com o desenho final montado pelo GPU do PS1.
4. Os porcentuais de pools são teóricos (peso/2048) e não uma promessa de drop in-game.
5. Um arquivo PNG gerado não é prova de que o conteúdo é visualmente correto; validar as artes após a extração.
6. As tabelas de fusão, equipamentos e rituais **não são modificadas** na extração.
7. O pacote não contém materiais pertencentes à Konami.

Código Python próprio escrito para este editor com referência à documentação pública. O código relacionado do PC port está sob licença MIT ©2026 Unchiga e colaboradores; texto da licença na página acima. Se incorporar ou distribuir futuramente material original das ferramentas, preserve obrigatoriamente os respectivos avisos de licença.
