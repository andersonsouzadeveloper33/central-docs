# Zynor Docs — Contexto do Projeto

## O que é
App desktop de gestão de documentos (GED) para pequenas e médias empresas.
Stack: Python + pywebview (janela desktop) + HTML/CSS/JS (UI).

## Arquitetura
- **`app_new.py`** — backend Python. Classe `Api` exposta ao JS via `window.pywebview.api.xxx()`
- **`ui/index.html`** — estrutura da UI
- **`ui/app.js`** — toda a lógica JS (estado, chamadas à API, renderização)
- **`ui/style.css`** — estilos

## Infraestrutura
- **Banco**: Supabase (PostgreSQL via postgrest) — `sb.table(...).select(...).eq(...).execute()`
- **Storage**: Cloudflare R2 via boto3 (s3-compatible) — `_r2().copy_object / delete_object / upload_file`
- **Cache local**: `~/Zynor Docs/{TENANT_ID}/` — cópia local dos arquivos baixados
- **Multitenancy**: `TENANT_ID` global, todas as queries filtram por ele

## Tabelas principais
- `tenants` — empresa cliente, tem `plan_id` FK para `plans`
- `plans` — Starter / Business / Enterprise (feature flags: `has_groups`, `has_locks`, etc.)
- `users` — usuários do tenant
- `groups` — grupos com permissões (`can_view`, `can_create`, `can_edit`, `can_delete`, `is_admin`)
- `user_groups` — N:N usuários ↔ grupos
- `folders` — pastas (`storage_path`, `parent_path`, `tenant_id`)
- `files` — arquivos (`storage_path`, `parent_path`, `size`, `tenant_id`)
- `audit_log` — log de todas as ações
- `shared_files` — links temporários gerados

## Padrões importantes
- **Soft delete**: itens vão para `~/.trash.json`, filtrados de `get_children`/`get_root_folders`; só deletados do R2+DB no `empty_trash`
- **Navegação**: `state.navStack` armazena `{name, storage_path}` exatos do DB — não reconstruir paths por string
- **Rename no R2**: sempre chama `_storage_move(old_path, new_path)` após atualizar o DB
- **Favoritos**: `~/Zynor Docs/{TENANT_ID}/.favorites_{user_id}.json`
- **Lixeira**: `~/Zynor Docs/{TENANT_ID}/.trash.json`
- **Modal customizado**: `showConfirm()` — nunca usar `window.confirm()` nativo
- **`modalMode`**: guarda `"folder"` ou `"rename"` para evitar duplo disparo no modal
- **`upgrade_required`**: retorno padrão quando feature bloqueada pelo plano

## Modo offline (leitura cacheada + bloqueio de escrita)
- **Cache de leitura**: `_cached_query(key, fn, default)` em `app_new.py` executa `fn()` (chamada Supabase); se falhar, salva o resultado bem-sucedido em `~/Zynor Docs/{TENANT_ID}/.cache/` e retorna do cache na próxima falha. Aplicado em `get_root_folders`, `get_subfolders`, `get_children`, `get_permissions`, `get_tenant_info`, `get_session`.
- **Chave de cache → nome de arquivo**: `_cache_filename(key)` faz `sha256(key)` antes de usar como nome de arquivo, porque chaves contêm `storage_path` (que tem `/`) — gravar direto quebra silenciosamente (`except: pass` mascarava isso antes). Qualquer cache novo deve passar pelo mesmo helper, nunca usar a key crua como path.
- **Login offline**: ao logar online com sucesso, salva `{user, pw_hash}` em cache por `email+tenant`. Se a rede cair no login, compara o hash da senha digitada com o cache e libera acesso com a flag `offline: true`.
- **Flag global `OFFLINE`**: atualizada tanto pelas leituras cacheadas quanto por `check_connectivity()` (sonda TCP ativa na porta 443 do host Supabase, sem autenticar). Exposta ao JS via `is_offline()` e `check_connectivity()`.
- **Bloqueio de escrita**: toda função que grava no Supabase/R2 (criar, upload, renomear, excluir, esvaziar lixeira, compartilhar, lock, trocar senha, usuários/grupos) começa com `if (err := _require_online()): return err`. **Qualquer novo método de escrita deve repetir esse guard** — sem ele, a ação falha depois de já ter alterado algo local (storage local, lixeira) e fica inconsistente com o servidor.
- **Watcher de conectividade (JS)**: `startConnectivityWatcher()` em `app.js` chama `check_connectivity()` a cada 6s, atualiza o banner `#offlineBanner` e recarrega sidebar/pasta atual automaticamente quando volta a conexão. Chamado após `init()` e após login bem-sucedido.
- **Banner offline**: `#offlineBanner` faz parte do fluxo normal do layout (`.shell` é coluna, sidebar+main ficam dentro de `.shell-body`) — não usar `position: fixed` nele, isso já cobriu o topbar uma vez.
- **Fila de sincronização ainda não existe** — ver `ROADMAP.md` seção "Modo Offline". Hoje, offline = leitura do que já foi cacheado + escrita bloqueada, nada fica pendente para sincronizar depois.

## Planos (Starter / Business / Enterprise)
- Starter: 1 usuário, 50 GB, sem grupos/locks/admin
- Business: 10 usuários, 500 GB, tudo liberado
- Enterprise: 100 usuários, 1 TB, tudo + suporte prioritário
- Ver ROADMAP.md para o que ainda falta implementar no enforce de planos

## O que NÃO fazer
- Não usar `window.confirm()` — usar `showConfirm()`
- Não reconstruir `storage_path` por concatenação de strings — usar o valor exato do DB
- Não chamar `loadHomeDashboard()` dentro de `loadSidebar()` (já é chamado por `showHomeView`)
- Não fazer múltiplas chamadas paralelas ao Supabase na inicialização (causa WinError 10035)
- Não adicionar try/except em métodos que nunca falham — só em queries ao Supabase/R2
- Não usar uma string com `/` (ex.: `storage_path`) direto como nome de arquivo de cache — sempre hashear com `_cache_filename()`
- Não criar um método de escrita (grava no Supabase/R2) sem `_require_online()` no início — senão ele tenta, falha offline e pode deixar estado local/remoto inconsistente
- No JS, sempre checar `res.ok` antes de mostrar toast de sucesso — já existiu bug real onde `create_folder`/`create_file`/`upload_file` mostravam "sucesso" mesmo falhando, porque o `await` não checava o retorno
- Não usar `position: fixed` no `#offlineBanner` ou outro elemento de topo dentro de `#appShell` — o layout depende do `.shell` ser coluna (banner) + `.shell-body` (linha com sidebar/main)
