# Manual de utilização — etiquetas de pastelaria

Esta ferramenta transforma a lista de produtos da sua Folha do Google num PDF pronto a imprimir (A4, 8 etiquetas por página, com marcas de corte). Edita a folha, carrega num botão, e cerca de 2 minutos depois o PDF aparece no Drive.

## 1. Preencher os dados

Abra a folha → separador **`real_data`**. Uma linha por produto. Colunas:

| Coluna | O que escrever | Exemplo |
|---|---|---|
| `name_fr` | Nome do produto em francês. Será impresso em **MAIÚSCULAS** automaticamente — pode escrever em minúsculas. | `cake au citron` |
| `description_pt` | Descrição curta em português. Será impressa em itálico, mais pequena. | `bolo de citrinos` |
| `gluten`, `milk`, `egg`, `peanut`, `soy` | Marque se o produto contém o alergénio. O ícone correspondente aparece na etiqueta. | ☑ ☑ ☑ ☐ ☐ |
| `price` | Número com **ponto** como separador decimal (`4.20`, não `4,20`). Será impresso como `4,20€`. | `4.20` |
| `active` | Marque para incluir esta linha no próximo PDF. Desmarque para manter a linha mas saltá-la. | ☑ |

Para adicionar um novo produto, basta escrever na próxima linha vazia — as regras das colunas aplicam-se automaticamente.

## 2. Quebras de linha

### Quebra forçada (recomendada para títulos)

Dentro de qualquer célula, prima **Alt + Enter** (no Mac: **Option + Enter**) para inserir uma quebra de linha.

```
GATEAU BASQUE       ← linha 1
À LA PART           ← linha 2 (forçada)
```

Funciona tanto em `name_fr` como em `description_pt`.

### Quebra automática

Os títulos demasiado compridos passam automaticamente para a linha seguinte. **Limite os títulos a 2 linhas no máximo** — para além disso (cerca de 27 caracteres sem quebra forçada), o título passa para 3 linhas e sobrepõe-se à descrição em baixo. Se o título for muito comprido, insira o seu próprio Alt+Enter num ponto que faça sentido.

| Comprimento | Comportamento |
|---|---|
| até ~14 caracteres | Uma linha |
| 15–26 caracteres | Passa para 2 linhas automaticamente |
| 27+ caracteres sem quebra forçada | Passa para 3 linhas → sobreposição visual (não imprimir) |

## 3. Gerar o PDF

1. Na folha, barra de menus → **🥖 Lully** → **Generate labels (PDF)**
2. O separador `release_history` recebe uma nova linha com estado `submitted`
3. Aguarde cerca de 2 minutos
4. A mesma linha passa a `success`, com um link do Drive em `pdf_drive_link`
5. Carregue no link → o seu PDF está lá, pronto a imprimir

A folha mantém um registo permanente de todos os PDFs que já gerou, com uma cópia CSV dos dados exactos que produziram cada um. Pode sempre voltar a imprimir uma versão antiga.

## 4. Impressão

Abra o PDF e imprima em **papel A4, escala 100 %** (sem "ajustar à página", sem margens adicionadas). As marcas nos cantos de cada etiqueta servem de guias de corte depois da impressão.

## 5. Se algo correr mal

Se a nova linha em `release_history` mostrar estado `failed`, veja a coluna `notes` para a mensagem de erro.

| `notes` mostra… | Causa provável | Solução |
|---|---|---|
| `Missing name_fr` | Uma linha activa não tem nome de produto | Preencha `name_fr` ou desmarque `active` nessa linha |
| `No active rows` | Nenhuma linha está marcada | Marque pelo menos uma checkbox `active` |
| `invalid_grant` / `Token expired` | A ligação ao Google expirou | Peça ao seu contacto técnico para renovar o token OAuth |
| `Tab 'real_data' is empty` | O separador foi esvaziado ou renomeado | Não renomeie `real_data`; mantenha pelo menos a linha de cabeçalho |

Se não reconhecer o erro, envie o texto de `notes` e o `request_id` ao seu contacto técnico.

## 6. Sugestões

- **Marque os alergénios com cuidado** — aparecem como pequenos ícones em que os clientes confiam. Uma marca esquecida significa que o cliente não consegue ver o alergénio à primeira vista.
- **Desmarque `active`** para produtos que não está a vender hoje, em vez de apagar a linha — assim mantém o catálogo completo pronto para a próxima vez.
- **Não apague linhas do `release_history`** — é o seu registo de auditoria de cada lote de etiquetas que já imprimiu.
- **Não renomeie os separadores** — `real_data`, `sample` e `release_history` são os nomes que o sistema procura.
