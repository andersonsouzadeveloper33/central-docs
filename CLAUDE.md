# Zynor Docs — Contexto do Projeto

## O que é
App desktop de gestão de documentos (GED) para pequenas e médias empresas.
Stack: Python + pywebview (janela desktop) + HTML/CSS/JS (UI).

## Revisão técnica obrigatória
Ao final de qualquer desenvolvimento neste projeto — bug fix, feature ou melhoria —, antes de considerar a tarefa concluída, invocar o skill `revisao-tecnica`. Esse skill é **global** (fica em `~/.claude/skills/revisao-tecnica`, fora deste repositório) e atua como segunda camada de code review, segurança e qualidade sobre o que acabou de ser implementado.

## Arquitetura
- **`app_new.py`** — backend Python. Classe `Api` exposta ao JS via `window.pywebview.api.xxx()`
- **`ui/index.html`** — estrutura da UI (login/ativação/troca de senha, shell do app, Configurações, modais)
- **`ui/app.js`** — toda a lógica JS (estado, chamadas à API, renderização)
- **`ui/style.css`** — estilos
- **`app.py`** — versão antiga (Tkinter/CustomTkinter), mantida só como referência histórica. **Não é mais o entry point** — `build_cliente.ps1` e o `.iss` apontam para `app_new.py`. Já houve regressão real de build apontando pro arquivo errado; sempre confirmar isso ao tocar em build/instalador.
- **`build_cliente.ps1`** / **`installer/ZynorDocs.iss`** — geram o `.exe` (PyInstaller) e o instalador (Inno Setup)

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

## Sincronização automática de pasta local
- **Caso de uso**: cliente gera PDFs (ex.: orçamentos) numa ou mais pastas locais fixas do Windows e quer que eles entrem automaticamente no Zynor sem upload manual. Suporta múltiplas pastas monitoradas simultaneamente (ex.: "Orçamentos", "Projetos", "Contratos"), cada uma com seu próprio destino no Zynor.
- **Formato da config**: `{"watches": [{id, label, enabled, local_folder, remote_path, remote_name, processed}, ...]}` — lista de pastas monitoradas, não mais um único mapeamento. `_load_sync_config()` migra automaticamente o formato antigo (uma pasta só, sem `watches`) para uma lista de um item com `id: "migrated"`.
- **Config é por máquina, não por tenant**: salva em `~/Zynor Docs/{TENANT_ID}/.sync_watch.json` (`_load_sync_config`/`_save_sync_config` em `app_new.py`) — fica só no disco local, nunca vai pro Supabase. Cada computador tem sua própria lista de `watches`. Só precisa configurar na máquina que efetivamente roda o sistema que gera os arquivos; as demais não são afetadas.
- **Watcher único cobre todas as pastas**: existe uma só thread daemon (`_sync_watch_loop()`), que a cada ciclo de 5s itera sobre `cfg["watches"]` e processa cada uma habilitada — não sobe uma thread por pasta. Inicia em `login()`/`get_session()` se `any(w["enabled"] for w in watches)`. Antes de subir um arquivo, espera 2s e confere se mtime/size não mudaram (evita pegar PDF ainda sendo escrito).
- **Dedupe é por pasta**: cada item de `watches` tem seu próprio `processed` (`{nome_arquivo: "mtime:size"}`) — arquivos com o mesmo nome em pastas diferentes não conflitam entre si.
- **Upload**: `_sync_upload_local_file()` reusa a mesma lógica de `upload_file` (storage_path via `_make_storage_path`, insert em `files`, `_audit`), mas lendo direto do disco em vez de receber base64 do JS.
- **`set_sync_watches(watches)` substitui a lista inteira** (vinda da tela) em cada save, mas preserva o `processed` de cada `id` já existente — nunca reseta o dedupe de uma pasta que já estava configurada. Itens novos (sem `id` vindo do JS) recebem `uuid.uuid4()`.
- **UI**: aba "Sincronização automática" em Configurações (`paneSync` em `index.html`, `loadSyncTab`/`initSyncTab` em `app.js`) — só admin pode configurar (`get_permissions().is_admin`). Cada pasta é uma linha dinâmica (`_renderSyncWatchRow()`) com nome/label, escolha de pasta local via `select_local_folder()` (tkinter `askdirectory`), dropdown de pasta destino alimentado por `get_all_folders()`, checkbox de ativação e botão de remover. `+ Adicionar pasta` (`btnAddSyncWatch`) insere uma nova linha vazia; "Salvar" recolhe todas as linhas do DOM e chama `set_sync_watches()` de uma vez.

## Licenciamento e ativação
- **Sem `tenant_id` configurado → tela de ativação**, não tela de login. Em `app_new.py`, `TENANT_ID` é carregado de `%APPDATA%\ZynorDocs\config.json`; se o arquivo não existe (instalação nova), `TENANT_ID` fica `""`.
- **`Api.license_activate(code)`** valida o código na tabela `licenses`, resolve o `tenant_id`, atualiza `TENANT_ID` em memória e grava `config.json` em `%APPDATA%\ZynorDocs\`. É o único jeito de vincular a instalação a um tenant — não existe mais baking de `tenant_id` no build.
- No JS, `init()` (`app.js`) decide a tela: `!session.tenant_id` → `showActivation()`; tem `tenant_id` mas sem `user.id` → `showLogin()`; senão entra direto no app. `applySidebarLogo()` é chamado assim que existe `tenant_id` (mesmo antes do login), porque a logo já pode ser mostrada na tela de login.
- **Build é genérico**: `build_cliente.ps1` não recebe mais `-TenantId`/`-TenantName` e não grava `config.json` no pacote. O `.iss` não copia `config.json` para `{userappdata}` — quem grava esse arquivo é sempre o `license_activate()` em runtime. Um único instalador serve para todos os clientes.

## Telas de autenticação (ativação / login / troca de senha)
- Layout split-screen: painel de marca à esquerda (`.login-brand-panel`, gradiente azul + blobs decorativos + lista de features) e formulário à direita (`.login-form-panel`). Abaixo de 760px o painel de marca some (`@media (max-width: 760px)`) porque a janela mínima do app é 900×600 e não pode sobrar espaço espremido.
- A logo do tenant (quando existe) substitui o ícone genérico nessas telas via `_applyLogoTo()` em `app.js`, chamado em sidebar **e** login **e** troca de senha pela mesma `applySidebarLogo()`. A tela de ativação fica sempre com a marca genérica Zynor (ainda não há tenant nesse ponto).
- **Troca de senha tem dois fluxos na mesma tela** (`#changePwScreen`): obrigatório (primeiro acesso, `must_change_password`) e voluntário (menu do usuário → "Trocar senha"). O botão `#changePwCancelBtn` só pode aparecer no fluxo voluntário — escondê-lo explicitamente sempre que abrir a tela pelo fluxo obrigatório, senão o usuário consegue pular a troca de senha exigida.

## Configurações (Usuários / Grupos / Empresa / Sincronização)
- Página com abas (`#settingsView` → `.settings-tab` + `.settings-pane`) em `index.html`, lógica em `app.js` (`loadSettingsView`, `switchSettingsTab`, `initSettingsModals`). Só renderiza conteúdo se `get_permissions().is_admin` — senão mostra `#settingsRestricted`.
- **Usuários/Grupos**: CRUD completo via `get_users/create_user/update_user/delete_user` e `get_groups/create_group/update_group/delete_group` em `app_new.py` — todos com `_require_online()` e `_audit()`. Usuário não pode excluir a própria conta (botão fica `disabled` comparando com `state.user.id`).
- **Empresa**: upload/remoção de logo (`upload_tenant_logo`, `remove_tenant_logo`) e nome do tenant (`update_tenant_name`). Logo é salva no R2 em `{TENANT_ID}/_branding/logo{ext}` e servida via URL pré-assinada (`get_tenant_logo_url`, 1h de validade) — nunca fica em cache local nem é embutida no build.
- **Trim automático de logo** (`_trim_logo_whitespace` em `app_new.py`): toda logo enviada passa por recorte da margem vazia antes de subir pro R2, porque clientes tendem a exportar PNG quadrado grande (ex.: 2400×2400) com a marca pequena no centro — sem isso, o `object-fit: contain` do CSS escala a imagem inteira (incluindo a margem) e a logo fica minúscula na tela. **Se a imagem tem transparência real, o recorte usa só o canal alfa** (binarizado com tolerância de ruído ≤10), nunca o diff de RGB inteiro — pixels totalmente transparentes costumam ter RGB ruidoso/lixo, e comparar todos os 4 canais faz o `bbox` cobrir a imagem inteira (bug real já visto: trim "funcionava" no teste sintético mas não recortava nada na logo real do cliente).
- **CSS de logo com proporção desconhecida**: usar box fixo (`width` + `height` definidos, não `max-width`/`max-height` com `width:auto`) + `object-fit: contain`. Com `max-width`/`max-height`, uma logo muito larga e fina é limitada pela largura antes de aproveitar a altura disponível e fica visualmente pequena mesmo com o "tamanho máximo" generoso.

## Build, ícone e instalador (Windows)
- **`_icon_path()`** em `app_new.py` resolve `icon.ico` tanto rodando via `.py` quanto via `.exe` (PyInstaller/`_MEIPASS`), igual ao `_resource()` do `app.py` antigo. É passado para `webview.start(icon=...)`, que no backend Windows (winforms/EdgeChromium) seta `Form.Icon` nativamente — não precisa do hack via `ctypes`/`WM_SETICON` que o app antigo usava.
- **`_fix_taskbar_identity()`**: roda no início de `open_window()` e chama `SetCurrentProcessExplicitAppUserModelID` no Windows. Sem isso, rodando via `python app_new.py` (não congelado), a taskbar mostra o ícone do `python.exe` em vez do ícone do app, porque o AppUserModelID do processo por padrão é o do interpretador.
- **`installer/ZynorDocs.iss`**: os atalhos (`[Icons]`) declaram `AppUserModelID: "ZynorDocs.App"` — precisa bater exatamente com a string usada em `_fix_taskbar_identity()`, senão um atalho fixado (pin) antes da primeira execução pode herdar o ícone errado.
- **`build_cliente.ps1` precisa empacotar `ui/` e `icon.ico`** via `--add-data` — sem isso o `.exe` simplesmente não tem a interface (já houve regressão real do script ainda apontando pro `app.py` antigo e sem empacotar `ui/`, gerando um build "fantasma" da versão errada).
- **Scripts `.ps1` com acento devem ser salvos como UTF-8 com BOM.** Windows PowerShell 5.1 interpreta `.ps1` sem BOM usando o codepage ANSI do sistema, não UTF-8 — acentos (é, ã, ô) corrompem bytes multibyte e podem quebrar o parser com erro de "cadeia sem terminador" em uma linha que parece perfeitamente válida. Pra resalvar com BOM: `[System.IO.File]::WriteAllText(path, (Get-Content -Raw -Encoding UTF8 path), [System.Text.Encoding]::UTF8)`.
- Fluxo de build: `.\build_cliente.ps1` (sem parâmetros) → `dist\ZynorDocs.exe` → `installer_output\ZynorDocs_Setup.exe`. Não precisa de `-TenantId`/`-TenantName` (ver seção "Licenciamento e ativação").

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
- Não tratar a config de sincronização automática (`.sync_watch.json`) como dado de tenant — ela é por máquina (arquivo local), nunca deve ir pro Supabase nem ser lida como se fosse compartilhada entre usuários do mesmo tenant
- Não apontar `build_cliente.ps1`/`.spec` para `app.py` — o entry point atual é `app_new.py`; já houve regressão real onde o build compilava a versão Tkinter antiga sem ninguém notar até instalar
- Não gravar `tenant_id` no build/instalador (nem em `config.json` versionado, nem via parâmetro do script) — o instalador é genérico, o vínculo com o tenant é feito em runtime por `license_activate()`
- Não salvar `.ps1` com acentos em UTF-8 sem BOM — quebra o parser do Windows PowerShell 5.1 com um erro que aponta para uma linha aparentemente válida
- Não recortar margem vazia/transparente de imagem comparando os 4 canais RGBA inteiros — usar só o canal alfa quando a imagem tem transparência real (RGB de pixel transparente costuma ser ruidoso e faz o `bbox` não recortar nada)
- Não dimensionar `<img>` de logo com `max-width`/`max-height` + `width:auto`/`height:auto` quando a proporção da imagem é desconhecida — usar `width`+`height` fixos com `object-fit: contain`, senão uma logo muito larga/fina aparece bem menor que o esperado
- Não fazer `return` antecipado num loader antes de chamar a função que renderiza o estado vazio (ex.: pular `loadHomeGrid(folders)` quando `folders` está vazio) — já causou bug real onde a lista de pastas ficava em branco sem nenhum empty state
- Não deixar a tela de troca de senha mostrar o botão "Cancelar" no fluxo obrigatório de primeiro acesso (`must_change_password`) — só no fluxo voluntário (menu do usuário), senão dá pra pular a troca exigida
- Não considerar um bug fix ou feature concluído sem antes rodar o skill global `revisao-tecnica`
