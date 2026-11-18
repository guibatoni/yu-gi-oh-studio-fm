# Conversor PS1 de imagens (Pillow opcional)

## Implementação da primeira etapa segura

O conversor central é `fmstudio/ps1_image_optimizer.py`. O Studio
armazena a imagem de entrada em `assets/cartas/<id>.png`, sem manipular
o arquivo externo. O carregamento de PNG não depende de Pillow; a importação
de JPG, WEBP, BMP e TIFF exige Pillow e converte o arquivo em um PNG de
origem separado, preservando a imagem enviada.

O projeto mantém suas configurações de imagem no campo JSON
`ps1_image_optimizer`. Projetos antigos **sem o campo** mantêm o
comportamento legado ao gerar BIN/CUE, evitando mudança silenciosa de
imagens já aprovadas. Ao importar uma arte nova, o perfil Automático
é registrado como ativo. Desativar explicitamente o otimizador restaura
o redimensionamento e a busca de cor compatíveis com o conversor anterior.

## Formatos de destino

| Recurso | Resolução | Bytes por pixel | CLUT | Permissão de gravação |
| --- | ---: | ---: | ---: | --- |
| Arte original | 102×96 | 1 | 256 entradas de 16 bits | Pixels da arte apenas |
| Miniatura original | 40×32 | 1 | 64 entradas de 16 bits | Pixels da miniatura apenas |
| Cartas 723–740 | Como acima | 1 | Herdada do modelo PS1 | Apenas perfil nativo expandido, experimental |
| Cartas acima de 740 | Indefinido | — | — | Studio apenas |
| Ícones de descrição | 16×16 | 4 bits indexados | 16 entradas | Somente espaços exclusivos já validados pelo runtime |
| Retratos/texturas de cena | Dependente do recurso | — | — | Sem rotina de importação/patch nesta versão |

O bit 15 de RGB555 é um indicador especial do PS1 (STP), não é alpha PNG.
Ele e os valores brutos das CLUTs originais são preservados. Índice 0
com valor 0000 é interpretado como transparente no decoder de imagens
existente. PNGs com transparência são bloqueados se o índice zero da
CLUT real não corresponder a essa convenção.

## Filtros e modos

* **Automático:** LANCZOS para arte, BOX por área em reduções intensas de
  miniatura. Preserva proporção com padding transparente, sem recortar a arte.
* **Máxima fidelidade:** mantém as dimensões nativas; permite escolher o filtro.
* **Compatibilidade original:** a imagem ocupa a região de destino como no
  conversor legado, com busca euclidiana e sem dithering.
* **Personalizado:** brilho/contraste/saturação/gama/nitidez com limites moderados,
  redução opcional de ruído, filtro e dithering selecionáveis.

Floyd–Steinberg e Bayer 2×2, 4×4 ou 8×8 são aplicados na indexação RGB555
com intensidade 0–100%. O modo automático usa ordered dithering moderado
quando há gradientes suaves. A pontuação de fidelidade é **indicativa**,
baseada em RMSE RGB, e não é PSNR perceptual nem certificação de PS1.

## CLUTs

**Compatibilidade** sempre usa o CLUT original. **Seguro** e
**Automático** preservam a CLUT original nos registros reais do WA.
**Personalizada** só calcula cores novas se o chamador fornecer um recurso
com paleta própria e comprovadamente isolada (`private_clut=True`).
A implementação atual do disco **não passa essa autorização** para cartas,
incluindo as adicionadas: seus registros mantêm faixas/títulos que podem
depender da mesma paleta, portanto não é seguro trocar as entradas.

Assim a seleção de “Paleta personalizada” para uma carta registra um aviso
de bloqueio e mantém a CLUT original; não colore outras regiões do jogo.

## Uso e inspeção

1. Importe sua imagem no botão **Importar imagem** da aba Cartas.
2. Entre em **Comparar original | PS1 (CLUT real)**. Selecione o BIN/CUE
   de origem vinculado (hash do SLUS/WA conferido).
3. Compare pré-indexação e PS1 já quantizado. Escolha arte/miniatura,
   zoom 100%, 200%, 400% ou 800%, filtro, dithering e intensidade.
4. Salve a configuração do projeto, gere um novo BIN/CUE e confira o
   resultado in-game no ePSXe. O BIN/CUE original nunca é editado.
5. A releitura final de WA_MRG.MRG no exportador verifica igualdade total
   dos bytes gravados, incluindo as imagens indexadas.

A prévia usa os mesmos bytes e CLUT do exportador. A interface do PS1
pode introduzir fatores adicionais (VRAM, mistura de transparência,
efeitos e escala da tela), portanto a prévia **não comprova** exibição
no console ou emulador.

## Proteções

O Studio guarda backups da imagem anterior na pasta
`assets/cartas/backups` e do projeto em `backups`. Uma conversão
inválida não altera o BIN original. Os registros existentes do WA não
sofrem modificações em CLUT, tiras, faixas ou miniaturas de outras cartas.
Pillow é opcional para PNG; seu fallback mantém leitura PNG e redução
por área/linear, porém sem controles fotográficos avançados.

## Pendências de engenharia

Para liberar CLUTs próprias de cartas com segurança, será preciso mapear
o uso de **cada índice** em faixas, títulos e registros compartilhados e
testar a leitura da nova CLUT em ePSXe. Ainda faltam importadores
diretos de retratos, texturas de cena, outros formatos de textura PS1
e uma prova visual com BIN comercial/mod real. Nenhum deles foi tratado
como concluído ou “universal” apenas por existir o motor reutilizável.
