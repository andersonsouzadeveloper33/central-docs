# Zynor Docs — Roadmap

## Infraestrutura de Planos
- [ ] 00001 - Tabela `plans` com colunas de feature flags (`has_groups`, `has_locks`, `has_admin`, etc.)
- [ ] 00002 - Coluna `plan_id` na tabela `tenants`
- [ ] 00003 - Python: carregar plano do tenant junto com a sessão (`get_session`)
- [ ] 00004 - Python: `get_permissions()` cruzar permissões do grupo com limites do plano
- [ ] 00005 - Python: retornar `upgrade_required` em features bloqueadas pelo plano
- [ ] 00006 - JS: tratar `upgrade_required` mostrando modal de upgrade de plano
- [ ] 00007 - Modal "Plano atual" exibir nome real do plano (vindo do banco, não hardcoded)
- [ ] 00008 - Validar limite de usuários por plano no `create_user`
- [ ] 00009 - Validar limite de armazenamento por plano no `upload_file`

## Funcionalidades Enterprise — Roadmap

### Controle de versões
- [ ] 00010 - Ao sobrescrever arquivo, salvar versão anterior (V1, V2, V3…)
- [ ] 00011 - Tela de histórico de versões do arquivo
- [ ] 00012 - Restaurar versão anterior

### Permissão por pasta
- [ ] 00013 - Tabela `folder_permissions` (pasta + grupo + permissões)
- [ ] 00014 - UI para admin configurar quem vê cada pasta
- [ ] 00015 - `get_children` e `get_root_folders` filtrar pelo grupo do usuário por pasta

### OCR / Busca por conteúdo
- [ ] 00016 - Indexação de texto em PDF e DOCX no upload
- [ ] 00017 - Campo de busca global por conteúdo
- [ ] 00018 - Resultados com trecho do documento onde o termo aparece

### Assinatura eletrônica
- [ ] 00019 - Integração com provedor (ex: D4Sign, ClickSign ou nativo)
- [ ] 00020 - Fluxo: enviar para assinatura → assinar → documento marcado como assinado
- [ ] 00021 - Histórico de assinaturas por documento

### Acesso web / mobile
- [ ] 00022 - Versão web (React ou similar) com mesma API Python via Supabase direto
- [ ] 00023 - App mobile (React Native ou Flutter)
- [ ] 00024 - Autenticação compartilhada com o desktop

## Modo Offline
- [x] 00025 - Cache local de leitura (pastas/arquivos/permissões/tenant) com fallback quando a rede cai
- [x] 00026 - Login offline usando hash da última sessão validada online
- [x] 00027 - Banner de aviso "Sem conexão" na UI
- [x] 00028 - Bloquear ações de escrita offline (criar, upload, renomear, excluir, lixeira, compartilhar, usuários/grupos, trocar senha) em vez de falhar silenciosamente
- [ ] 00029 - Fila de sincronização: permitir criar/editar/excluir offline, guardando as alterações pendentes localmente
- [ ] 00030 - Sincronização automática da fila ao detectar reconexão
- [ ] 00031 - Resolução de conflitos (ex: item renomeado/apagado por outra sessão enquanto offline)
- [ ] 00032 - Indicador de "alterações pendentes de sincronização" na UI

## Auto-atualização
- [ ] 00060 - Manifesto de versão (JSON no R2 ou tabela `app_versions` no Supabase) com `{version, url, sha256}`
- [ ] 00061 - App verifica versão no startup e baixa o instalador em background para pasta temp
- [ ] 00062 - Verificar hash do instalador baixado antes de aplicar (evitar instalar binário corrompido/adulterado)
- [ ] 00063 - Instalar silenciosamente (`/VERYSILENT`) no próximo fechamento do app ou via botão "Reiniciar para atualizar"

## Melhorias de Produto
- [ ] 00033 - Fluxo de aprovação de documentos (enviar → aprovar → oficial)
- [ ] 00034 - Relatórios: usuários mais ativos, arquivos mais acessados, compartilhamentos
- [ ] 00035 - Auditoria exportável (CSV/PDF)
- [ ] 00036 - Notificações por e-mail

## Concluído
- [x] 00037 - Upload e download de arquivos com cache local
- [x] 00038 - Estrutura de pastas com hierarquia livre
- [x] 00039 - Renomear arquivos e pastas (persiste no R2)
- [x] 00040 - Navegação por breadcrumb com navStack
- [x] 00041 - Lixeira com soft delete, restauração e esvaziamento
- [x] 00042 - Favoritos por usuário
- [x] 00043 - Arquivos recentes
- [x] 00044 - Compartilhamento por link temporário (presigned URL R2)
- [x] 00045 - Re-compartilhar sem gerar novo link
- [x] 00046 - Bloqueio de arquivos (lock/unlock)
- [x] 00047 - Unlock forçado pelo admin
- [x] 00048 - Auditoria completa (audit_log)
- [x] 00049 - Notificações (sino com últimas ações)
- [x] 00050 - Painel administrativo (usuários, grupos, permissões)
- [x] 00051 - Grupos com permissões granulares (can_view, can_create, can_edit, can_delete)
- [x] 00052 - Tela home com stats globais, recentes e favoritos
- [x] 00053 - Menu de usuário no topbar (trocar senha, sair)
- [x] 00054 - Barra de armazenamento real na sidebar
- [x] 00055 - Modal "Plano atual" com dados reais do tenant
- [x] 00056 - Diálogos de confirmação customizados (sem native confirm)
- [x] 00057 - Dropdown de ações por linha (⋮)
- [x] 00058 - Tabela `plans` criada no Supabase
- [x] 00059 - Coluna `plan_id` adicionada na tabela `tenants`
