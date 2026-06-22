Analise o repositório atual e gere um `CLAUDE.md` preciso e útil, que qualquer sessão futura do Claude Code possa usar para entrar no projeto sem precisar perguntar nada.

## Fase 0 — Verificar se já existe um CLAUDE.md

Verifique se já existe um `CLAUDE.md` na raiz do projeto.

**Se existir**, leia-o completamente e trate-o como a fonte da verdade sobre decisões humanas (proibições, convenções de equipe, decisões arquiteturais deliberadas). Seu papel é **enriquecer, não substituir** — preserve tudo que estiver lá, atualize o que o código contradizer, e acrescente o que estiver faltando.

**Se não existir**, gere do zero seguindo as fases abaixo.

## Fase 1 — Reconhecimento do repositório

Explore o projeto antes de escrever qualquer coisa:

1. **Estrutura geral**: arquivos e pastas na raiz, tipo de projeto
2. **Ponto de entrada**: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `requirements.txt`, `Makefile`, `Dockerfile`, ou equivalente
3. **Arquivos principais**: os 3-5 arquivos mais centrais do projeto
4. **Configuração**: `.env.example`, `config/`, `settings.py`, etc.
5. **README existente**: para capturar intenção e contexto do autor
6. **Histórico git**: `git log --oneline -20`
7. **Testes**: 1-2 arquivos para entender padrões

Não tente ler tudo — foque em entender a arquitetura.

## Fase 2 — Inferir as informações críticas

- **Stack**: linguagens, frameworks, bibliotecas principais
- **Arquitetura**: organização do código, módulos/camadas principais
- **Infraestrutura**: banco de dados, storage, filas, serviços externos
- **Padrões de código**: nomenclatura, tratamento de erros, padrão de retorno de API
- **Fluxo de dados**: como uma requisição típica flui pelo sistema
- **Convenções obrigatórias**: o que todo dev precisa saber antes de mexer no código
- **Armadilhas comuns**: o que já quebrou antes, o que parece óbvio mas está errado

Se algo for incerto, prefira omitir a inventar.

## Fase 3 — Escrever o CLAUDE.md

```markdown
# [Nome do Projeto] — Contexto do Projeto

## O que é
[1-2 frases]

## Stack
- **[Camada]**: [tecnologia] — [para que serve]

## Arquitetura
- **`arquivo_principal`** — [responsabilidade em 1 linha]
- **`pasta/`** — [o que contém]

## Infraestrutura
[Banco de dados, storage, serviços externos]

## Padrões importantes
- **[Nome do padrão]**: [como funciona e por que importa]

## [Seção específica do projeto]
[Ex: "Tabelas principais", "Fluxo de autenticação" — só se relevante]

## O que NÃO fazer
- Não [ação específica] — [razão]
```

### Princípios de escrita

- **Seja específico, não genérico.** "Usar `_r2().copy_object()` para mover arquivos no R2" é útil; "usar boas práticas" não é.
- **Documente o não-óbvio.** O `CLAUDE.md` deve capturar o *por quê*, não o *o quê* (o código já mostra isso).
- **A seção "O que NÃO fazer" é ouro.** Inclua pelo menos 3-5 proibições específicas com razões.
- **Tamanho ideal**: 100-300 linhas.

## Fase 4 — Salvar e confirmar

**Se estava enriquecendo um CLAUDE.md existente:**
- Salve direto, sem pedir confirmação
- Mostre um resumo do que foi adicionado/atualizado/preservado
- Pergunte se alguma alteração foi indesejada

**Se estava criando do zero:**
- Escreva em `CLAUDE.md` na raiz do projeto
- Mostre o conteúdo gerado
- Pergunte se falta algo
