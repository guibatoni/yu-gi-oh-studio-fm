# Sistema de classes e cores — Studio FM v1.0.2

## Raridade do monstro

| Raridade | RGB | Uso |
| --- | --- | --- |
| Comum | `#CBD5E1` | Cinza claro; padrão ao importar carta sem classe |
| Incomum | `#FFFFFF` | Branco |
| Rara | `#FFD84D` | Amarelo |
| Épica | `#B57AFF` | Roxo |
| Lendária | `#F04F57` | Vermelho |
| Deus | `#123A79` | Azul-marinho |

## Categorias automáticas

Quando `tipo_id` estiver entre os tipos especiais abaixo, a cor e a classe visual **têm precedência** sobre a raridade salva:

| ID | Tipo | Classe visual | Cor |
| --- | --- | --- | --- |
| 20 | Magic | Mágica | `#48D995` verde |
| 21 | Trap | Trap | `#FF77C8` rosa |
| 23 | Equip | Equipamento | `#579DFF` azul |
| 24 | God | Deus | `#123A79` azul-marinho |

O tipo Ritual (22) permanece classificável por raridade até receber regra própria.

## Como usar

Selecione a carta, abra **Cartas → Raridade**, escolha uma classe e continue editando normalmente. **Salvar projeto** (`Ctrl+S`) grava todas as alterações pendentes de uma vez. Não existe pergunta de salvamento ao navegar entre cartas.

A cor e o nome da classe aparecem na prévia e na lista. Cartas Deus recebem fundo claro no nome da prévia e na linha da biblioteca para preservar a legibilidade. Tipos Magic, Trap, Equip e God bloqueiam o seletor porque possuem classes automáticas.

### Compatibilidade com projetos

- `raridade` é um novo campo de edição, persistido em `projeto.json` junto das edições já existentes.
- Projetos anteriores sem esse campo são tratados como `comum` até serem classificados, sem apagar o valor `cor_nome` legado.
- Alterar a raridade sincroniza o campo `cor_nome` legado para compatibilidade com versões antigas; a escolha atual de exibição é feita por `tipo_id` + `raridade`.
- A exportação gera `classes_cartas.json` com classe e RGB de cada carta, além das saídas anteriores.
- Não altera `fusoes.csv` nem os binários originais, não modifica o texto renderizado dentro do PS1. Essas cores são metadados do Studio.
