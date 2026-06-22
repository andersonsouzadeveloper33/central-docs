Explique ao usuário como funciona o fluxo de desenvolvimento com Claude Code **no projeto atual** (detecte o nome do projeto pelo diretório de trabalho, pelo `package.json`/`pyproject.toml`, ou pelo título no `CLAUDE.md`/`README.md` — não use um nome fixo). Use formatação clara e seja direto.

Antes de responder, verifique rapidamente o que existe no projeto atual:
- Existe `CLAUDE.md` na raiz?
- Existe `ROADMAP.md` na raiz?
- O que há em `.claude/commands/` deste projeto?

Monte a explicação adaptada ao que encontrar, seguindo esta estrutura:

---

## Como funciona o desenvolvimento com Claude Code em [Nome do Projeto]

**1. CLAUDE.md — contexto automático** (se existir)
O arquivo `CLAUDE.md` na raiz do projeto é carregado automaticamente pelo Claude Code em toda sessão dentro desta pasta. Resuma as seções que ele contém (stack, arquitetura, padrões, o que não fazer, etc., conforme o conteúdo real do arquivo).

Isso significa que você nunca precisa re-explicar o projeto a cada sessão.

Se **não existir**, diga isso e sugira rodar `/criarskilclaude` para gerar um.

**2. /view-roadmap — ver progresso** (se existir ROADMAP.md)
Digite `/view-roadmap` para ver:
- Quantas tarefas já foram concluídas vs. pendentes
- Lista de pendências agrupadas por área
- Sugestão dos próximos 3 passos prioritários

Esse comando é genérico — mostra sempre o roadmap do projeto em que você está trabalhando.

**3. /update-roadmap — registrar tarefas**
Use para marcar uma tarefa como concluída, anotar algo para fazer depois, ou criar o `ROADMAP.md` do zero se o projeto ainda não tiver um.

**4. /criarskilclaude — gerar ou atualizar o CLAUDE.md**
Analisa o repositório e cria (ou enriquece, se já existir) o `CLAUDE.md` com stack, arquitetura, padrões e convenções. Quando já existe um arquivo, ele preserva o conteúdo e só atualiza o que estiver desatualizado.

**5. Outros comandos customizados deste projeto**
Liste aqui qualquer outro arquivo encontrado em `.claude/commands/` além dos três acima, com uma linha explicando o que cada um faz (leia o início do arquivo para resumir).

**Fluxo recomendado por sessão**
```
1. Abra o projeto
2. Trabalhe normalmente — se houver CLAUDE.md, Claude já tem o contexto
3. Opcional: /view-roadmap para ver o progresso
4. Ao terminar uma tarefa: /update-roadmap para registrar
```

**Arquivos importantes**
- `CLAUDE.md` — contexto permanente do projeto (se existir)
- `ROADMAP.md` — tarefas pendentes e concluídas (se existir)
- `.claude/commands/` — comandos customizados deste projeto

---

Esses três comandos (`view-roadmap`, `update-roadmap`, `criarskilclaude`) são genéricos e funcionam em qualquer projeto onde a pasta `.claude/commands/` for copiada — eles detectam o contexto pelo diretório de trabalho atual, sem nome de projeto fixo.
