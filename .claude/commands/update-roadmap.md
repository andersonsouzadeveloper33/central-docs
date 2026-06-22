Gerencie o `ROADMAP.md` do **projeto em que você está trabalhando agora** (diretório de trabalho atual). Cobre três situações: registrar uma tarefa já concluída, registrar uma tarefa futura, ou criar o ROADMAP.md do zero se ainda não existir.

## Passo 1 — Localizar o ROADMAP.md do projeto atual

Procure `ROADMAP.md` na raiz do diretório de trabalho atual (ou `docs/ROADMAP.md` / `.claude/ROADMAP.md`).

### Se não existir

Faça um reconhecimento rápido do projeto (estrutura de pastas, `package.json`/`pyproject.toml` ou equivalente, README se houver, `git log --oneline -15`) para entender o domínio e propor uma estrutura de seções coerente com o projeto — não um roadmap genérico.

Crie o arquivo com:
- Um título com o nome do projeto
- Seções relevantes ao domínio do projeto (adapte ao que você descobrir na exploração)
- A tarefa que motivou a criação, já posicionada na seção certa com o status correto (`[x]` ou `[ ]`)

Mostre o arquivo criado ao usuário e pergunte se a estrutura de seções faz sentido.

## Passo 2 — Determinar o status do item

- **Já concluída** ("acabei de fazer X", "implementei Y") → `- [x]`
- **Pendente / futura** ("precisamos fazer X depois", "isso é uma ideia") → `- [ ]`
- **Ambíguo** → pergunte. Não assuma.

## Passo 3 — Escolher a seção certa

Leia as seções existentes e escolha a que melhor corresponde ao tema da tarefa. Só crie uma seção nova se a tarefa não se encaixar em nenhuma existente — posicione-a perto de seções relacionadas, não necessariamente no fim do arquivo.

## Passo 4 — Escrever o item

```
- [ ] Descrição clara e específica da tarefa
```

A descrição deve ser específica o suficiente para alguém entender o que foi/será feito sem mais contexto — evite descrições vagas como "melhorar X".

## Passo 5 — Confirmar

Mostre a linha adicionada (ou o trecho da seção alterada) e confirme brevemente. Não é necessário pedir aprovação antes de editar — é uma operação de baixo risco — mas sempre mostre o que foi feito.

## Estilo

Seja direto. O fluxo ideal: usuário menciona a tarefa → você decide status e seção → edita → confirma em uma frase.
