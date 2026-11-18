# Conversor PS1 de imagens (Pillow opcional)

## Conversão de imagens

O conversor central é `fmstudio/ps1_image_optimizer.py`. O Studio
armazena a imagem de entrada em `assets/cartas/<id>.png`, sem manipular
o arquivo externo. O carregamento de PNG não depende de Pillow; a importação
de JPG, WEBP, BMP e TIFF exige Pillow e converte o arquivo em um PNG de
origem separado, preservando a imagem enviada.

O projeto mantém suas configurações de imagem no campo JSON
`ps1_image_optimizer`. Projetos antigos sem esse campo usam o perfil
Automático no layout verificado do Original Drop x15. Em outras bases
continuam no modo legado. Ao importar uma arte nova, o Studio ativa o
perfil Automático se ainda não houver uma configuração salva. O perfil
Compatibilidade original restaura a conversão que usa a paleta de origem.

## Formatos de destino

| Recurso | Resolução | Bytes por pixel | CLUT | Permissão de gravação |
| --- | ---: | ---: | ---: | --- |
| Arte original | 102×96 | 1 | 256 entradas de 16 bits | Pixels e paleta local no Drop x15 |
| Miniatura original | 40×32 | 1 | 64 entradas de 16 bits | Pixels e paleta local nas duas cópias verificadas |
| Cartas 723–740 | Como acima | 1 | Criada a partir do PNG | Perfil nativo expandido do Drop x15 |
| Cartas acima de 740 | Indefinido | — | — | Studio apenas |
| Ícones de descrição | 16×16 | 4 bits indexados | 16 entradas | Somente espaços exclusivos já validados pelo runtime |
| Retratos/texturas de cena | Dependente do recurso | — | — | Sem rotina de importação/patch nesta versão |

Em uma paleta adaptativa, a entrada zero recebe o valor 0000 para
transparência e as cores opacas usam RGB555 com STP desligado. O Studio
preserva os valores brutos nas paletas originais. Se a entrada zero da
paleta escolhida for opaca, as bordas do enquadramento tomam essa cor.
Uma imagem que usa transparência real precisa de um índice transparente.

## Filtros e modos

* **Automático:** LANCZOS para arte, BOX por área em reduções intensas de
  miniatura. **Preencher (recorte central)** mantém a proporção e ocupa toda
  a área de destino. **Imagem inteira** preserva o enquadramento completo
  com margens quando a proporção do PNG é diferente.
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

No Original Drop x15, a arte tem uma paleta local de 256 entradas no
offset `0x2640` do registro. O título ocupa o intervalo de `0x2840` a
`0x2AE0` e usa uma paleta própria de 4 bits no renderizador. A miniatura
de `0x580` bytes inclui pixels e paleta no setor individual e dentro do
registro de arte a partir de `0x2AE0`. As 722 cópias coincidem no disco
de referência. [Mapa do formato e rotinas de vídeo](https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/blob/36d499c13522402a83c5b4772714f66046f80357/notes/research/Unchiga_Symbols/findings.md#L335)

**Automático**, **Seguro** e **Paleta personalizada** calculam as cores
do PNG quando a assinatura do executável e a cópia da miniatura confirmam
o layout. O Studio aplica a mesma miniatura nos dois locais. **CLUT
original** conserva a paleta de origem. Se o layout divergir, o Studio
também conserva as paletas e mantém a escrita nos locais já suportados.

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

O Studio guarda backups da imagem anterior na pasta `assets/cartas/backups`
e do projeto em `backups`. Uma conversão inválida preserva o BIN original.
A escrita de uma arte ocupa os registros daquele ID. A numeração, o título
e as cartas vizinhas podem ser conferidos no arquivo final. Sem Pillow, o
Studio lê PNG, reduz por área ou interpolação linear e gera a paleta por
divisão de intervalos de cor RGB555. Os filtros e ajustes fotográficos
exigem Pillow.
