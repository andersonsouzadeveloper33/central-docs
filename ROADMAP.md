# Zynor Docs — Roadmap

## Infraestrutura de Planos
- [ ] Tabela `plans` com colunas de feature flags (`has_groups`, `has_locks`, `has_admin`, etc.)
- [ ] Coluna `plan_id` na tabela `tenants`
- [ ] Python: carregar plano do tenant junto com a sessão (`get_session`)
- [ ] Python: `get_permissions()` cruzar permissões do grupo com limites do plano
- [ ] Python: retornar `upgrade_required` em features bloqueadas pelo plano
- [ ] JS: tratar `upgrade_required` mostrando modal de upgrade de plano
- [ ] Modal "Plano atual" exibir nome real do plano (vindo do banco, não hardcoded)
- [ ] Validar limite de usuários por plano no `create_user`
- [ ] Validar limite de armazenamento por plano no `upload_file`

## Funcionalidades Enterprise — Roadmap

### Controle de versões
- [ ] Ao sobrescrever arquivo, salvar versão anterior (V1, V2, V3…)
- [ ] Tela de histórico de versões do arquivo
- [ ] Restaurar versão anterior

### Permissão por pasta
- [ ] Tabela `folder_permissions` (pasta + grupo + permissões)
- [ ] UI para admin configurar quem vê cada pasta
- [ ] `get_children` e `get_root_folders` filtrar pelo grupo do usuário por pasta

### OCR / Busca por conteúdo
- [ ] Indexação de texto em PDF e DOCX no upload
- [ ] Campo de busca global por conteúdo
- [ ] Resultados com trecho do documento onde o termo aparece

### Assinatura eletrônica
- [ ] Integração com provedor (ex: D4Sign, ClickSign ou nativo)
- [ ] Fluxo: enviar para assinatura → assinar → documento marcado como assinado
- [ ] Histórico de assinaturas por documento

### Acesso web / mobile
- [ ] Versão web (React ou similar) com mesma API Python via Supabase direto
- [ ] App mobile (React Native ou Flutter)
- [ ] Autenticação compartilhada com o desktop

## Modo Offline
- [x] Cache local de leitura (pastas/arquivos/permissões/tenant) com fallback quando a rede cai
- [x] Login offline usando hash da última sessão validada online
- [x] Banner de aviso "Sem conexão" na UI
- [x] Bloquear ações de escrita offline (criar, upload, renomear, excluir, lixeira, compartilhar, usuários/grupos, trocar senha) em vez de falhar silenciosamente
- [ ] Fila de sincronização: permitir criar/editar/excluir offline, guardando as alterações pendentes localmente
- [ ] Sincronização automática da fila ao detectar reconexão
- [ ] Resolução de conflitos (ex: item renomeado/apagado por outra sessão enquanto offline)
- [ ] Indicador de "alterações pendentes de sincronização" na UI

## Melhorias de Produto
- [ ] Fluxo de aprovação de documentos (enviar → aprovar → oficial)
- [ ] Relatórios: usuários mais ativos, arquivos mais acessados, compartilhamentos
- [ ] Auditoria exportável (CSV/PDF)
- [ ] Notificações por e-mail

## Concluído
- [x] Upload e download de arquivos com cache local
- [x] Estrutura de pastas com hierarquia livre
- [x] Renomear arquivos e pastas (persiste no R2)
- [x] Navegação por breadcrumb com navStack
- [x] Lixeira com soft delete, restauração e esvaziamento
- [x] Favoritos por usuário
- [x] Arquivos recentes
- [x] Compartilhamento por link temporário (presigned URL R2)
- [x] Re-compartilhar sem gerar novo link
- [x] Bloqueio de arquivos (lock/unlock)
- [x] Unlock forçado pelo admin
- [x] Auditoria completa (audit_log)
- [x] Notificações (sino com últimas ações)
- [x] Painel administrativo (usuários, grupos, permissões)
- [x] Grupos com permissões granulares (can_view, can_create, can_edit, can_delete)
- [x] Tela home com stats globais, recentes e favoritos
- [x] Menu de usuário no topbar (trocar senha, sair)
- [x] Barra de armazenamento real na sidebar
- [x] Modal "Plano atual" com dados reais do tenant
- [x] Diálogos de confirmação customizados (sem native confirm)
- [x] Dropdown de ações por linha (⋮)
- [x] Tabela `plans` criada no Supabase
- [x] Coluna `plan_id` adicionada na tabela `tenants`
