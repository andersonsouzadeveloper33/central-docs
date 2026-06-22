Mostre o progresso do roadmap do **projeto em que você está trabalhando agora** (o diretório de trabalho atual) — não de um projeto fixo.

## Passo 1 — Localizar o ROADMAP.md do projeto atual

Procure por um arquivo `ROADMAP.md` na raiz do diretório de trabalho atual. Se não encontrar na raiz, procure também em `docs/ROADMAP.md` ou `.claude/ROADMAP.md`.

Se nenhum `ROADMAP.md` for encontrado, não invente conteúdo. Informe: "Este projeto ainda não tem um ROADMAP.md" e pergunte se o usuário quer criar um agora (use o fluxo do comando `/update-roadmap` para isso).

## Passo 2 — Calcular o progresso

Leia o arquivo inteiro e conte:
- Itens `- [x]` (concluídos)
- Itens `- [ ]` (pendentes)

## Passo 3 — Exibir o relatório

Use exatamente este formato:

```
**Progresso geral: X concluídos / Y total (Z%)**

**[Nome da Seção]** (N pendentes)
- item pendente 1
- item pendente 2

**[Próxima Seção]** (N pendentes)
- ...
```

Agrupe os itens pendentes pela seção em que aparecem no markdown original — não invente categorias novas.

Ao final, sugira os **3 próximos itens prioritários**, com base em:
- O que já foi concluído (dependências lógicas)
- A ordem natural em que os itens aparecem no roadmap
- Qualquer sinalização de prioridade já presente no arquivo

## Passo 4 — Atualizar o roadmap se necessário

Se, durante esta sessão, alguma tarefa do roadmap foi concluída no código mas ainda está marcada como `- [ ]`, atualize o `ROADMAP.md` trocando para `- [x]` **antes** de exibir o relatório. Só faça isso se tiver certeza de que a tarefa foi de fato concluída nesta conversa.

## Estilo

Seja direto e conciso. Não adicione texto de preenchimento antes ou depois do relatório.
