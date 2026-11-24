(() => {
  const find = id => document.getElementById(id);
  const backupCard = find('databaseBackups');
  const operations = find('operationPanel');
  const backupFeedback = find('backupFeedback');
  const operationFeedback = find('operationFeedback');
  const messages = {
    backup_failed: 'Não foi possível criar ou listar as cópias. Confira o espaço livre e o acesso à pasta de dados.',
    backup_invalid: 'A cópia não passou na verificação de integridade.',
    backup_not_found: 'A cópia selecionada não está disponível.',
    restored: 'A cópia do banco foi restaurada.',
    restore_failed: 'Falha na restauração. Escolha outra cópia ou cancele a restauração agendada.',
    monitor_busy: 'Aguarde a verificação atual terminar para tentar novamente.',
    retry_limit: 'Limite de tentativas manuais atingido.',
    failure_not_found: 'A falha já foi resolvida ou o produto saiu do monitoramento.',
    collected: 'A consulta foi concluída.',
    collection_failed: 'A consulta voltou a falhar. Confira as fontes no assistente de integrações.'
  };

  async function request(path, method = 'GET', body) {
    const response = await fetch(path, {
      method,
      ...(body && {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(messages[data.detail] || 'Não foi possível concluir a operação.');
    return data;
  }

  function date(value) {
    return value ? new Date(value).toLocaleString(document.documentElement.lang) : '—';
  }

  function action(label, callback) {
    const button = document.createElement('button');
    button.className = 'ghost';
    button.type = 'button';
    button.textContent = label;
    button.addEventListener('click', callback);
    return button;
  }

  function renderBackups(data) {
    find('cancelDatabaseRestore').hidden = !data.pending;
    backupFeedback.textContent = [
      messages[data.restore_result],
      data.pending && `Restauração agendada para a próxima abertura do MarketAI (${date(data.versions.find(version => version.id === data.pending)?.created_at)}).`,
      messages[data.error],
      `Até ${data.retention} cópias são mantidas na pasta de dados.`
    ].filter(Boolean).join(' ');
    const rows = data.versions.map(version => {
      const row = document.createElement('li');
      const size = (version.bytes / 1024 ** 2).toLocaleString(document.documentElement.lang, {
        maximumFractionDigits: 2
      });
      row.textContent = `${date(version.created_at)} · ${size} MB `;
      const restore = action('Restaurar', async () => {
        if (!confirm(`Restaurar a cópia de ${date(version.created_at)}? Ao reabrir o MarketAI, o banco atual será copiado antes da restauração.`)) return;
        await updateBackups(restore, '/restore', 'POST', {id: version.id});
      });
      restore.disabled = data.pending === version.id;
      row.append(restore);
      return row;
    });
    find('databaseBackupVersions').replaceChildren(...rows);
  }

  async function updateBackups(button, suffix = '', method = 'GET', body) {
    if (button) button.disabled = true;
    try {
      renderBackups(await request('/api/local/backups' + suffix, method, body));
    } catch (error) {
      backupFeedback.textContent = error.message;
    } finally {
      if (button) button.disabled = false;
    }
  }

  find('createDatabaseBackup').addEventListener('click', event => updateBackups(event.currentTarget, '', 'POST', {}));
  find('cancelDatabaseRestore').addEventListener('click', event => updateBackups(event.currentTarget, '/restore', 'DELETE'));

  let retrying = false;
  let refreshing = false;
  async function refreshOperations() {
    if (refreshing || retrying) return;
    refreshing = true;
    try {
      const data = await request('/api/local/monitor');
      find('lastCollection').textContent = date(data.last_collection);
      find('nextCollection').textContent = data.next_check ? date(data.next_check) : 'Após a verificação atual';
      find('operationActivity').textContent = [
        data.current_product || (data.running ? 'Verificando produtos' : 'Monitoramento em espera'),
        `${data.active_batches} lote(s) na fila ou em execução`,
        data.cycle_failed && 'O último ciclo foi interrompido'
      ].filter(Boolean).join(' · ');
      const rows = data.failures.map(failure => {
        const row = document.createElement('li');
        row.textContent = `${failure.product_name} · ${date(failure.failed_at)} · ${failure.attempts}/${data.retry_limit} tentativas manuais `;
        const retry = action('Tentar novamente', async () => {
          if (retrying) return;
          retrying = true;
          retry.disabled = true;
          operationFeedback.textContent = 'Repetindo a consulta…';
          try {
            const result = await request('/api/local/monitor/retry', 'POST', {watch_id: failure.id});
            operationFeedback.textContent = messages[result.result];
          } catch (error) {
            operationFeedback.textContent = error.message;
          } finally {
            retrying = false;
            refreshOperations();
          }
        });
        retry.disabled = data.running || failure.attempts >= data.retry_limit;
        row.append(retry);
        return row;
      });
      if (!rows.length) {
        const empty = document.createElement('li');
        empty.textContent = 'Nenhuma falha registrada.';
        rows.push(empty);
      }
      find('operationFailures').replaceChildren(...rows);
    } catch (error) {
      operationFeedback.textContent = error.message;
    } finally {
      refreshing = false;
    }
  }

  find('refreshOperations').addEventListener('click', refreshOperations);
  const source = find('integrationSource');
  const guides = {
    mercadolivre: 'Crie um aplicativo no portal de desenvolvedores do Mercado Livre e autorize o acesso. Cole o access token atual no campo Mercado Livre.',
    ebay: 'No portal eBay Developers, use um par de chaves de produção com acesso à Browse API. Preencha Client ID e Client Secret.',
    google_shopping: 'Abra o painel da SerpAPI, copie a API key e cole no campo SerpAPI.',
    vision: 'Crie uma chave do projeto na plataforma da OpenAI e confira o acesso ao modelo configurado.',
    bcb: 'O serviço público PTAX do Banco Central funciona sem credenciais.'
  };
  const diagnostics = {
    ok: 'Conexão bem-sucedida.',
    not_configured: 'Preencha e salve as credenciais desta fonte antes de testar.',
    auth_required: 'Credencial inválida, vencida ou sem permissão. Confira os dados e o acesso no portal da fonte.',
    rate_limited: 'Limite de consultas atingido. Confira a cota da sua conta ou aguarde a renovação.',
    model_unavailable: 'O modelo configurado está indisponível para este projeto. Confira o nome e as permissões.',
    network_error: 'Falha de comunicação. Confira a conexão e tente novamente.',
    fallback: 'O Banco Central está indisponível. O MarketAI usará a taxa de contingência.'
  };
  const integrationFeedback = find('integrationFeedback');
  function showGuide() {
    find('integrationGuide').textContent = guides[source.value];
    integrationFeedback.textContent = '';
  }
  source.addEventListener('change', showGuide);
  showGuide();
  find('testLocalIntegration').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = source.disabled = true;
    integrationFeedback.textContent = 'Testando a conexão…';
    try {
      const result = await request('/api/integrations/test?source=' + encodeURIComponent(source.value));
      integrationFeedback.textContent = diagnostics[result.status] || 'A fonte está indisponível. Tente novamente mais tarde.';
    } catch (error) {
      integrationFeedback.textContent = error.message;
    } finally {
      button.disabled = source.disabled = false;
    }
  });

  const tray = find('minimizeToTray');
  tray.addEventListener('change', async () => {
    tray.disabled = true;
    const feedback = find('trayFeedback');
    try {
      await request('/api/settings/preferences', 'POST', {minimize_to_tray: tray.checked});
      feedback.textContent = 'Preferência salva.';
    } catch (error) {
      tray.checked = !tray.checked;
      feedback.textContent = error.message;
    } finally {
      tray.disabled = false;
    }
  });

  async function refreshSettings() {
    if (backupCard.hidden) return;
    await Promise.all([updateBackups(), refreshOperations()]);
  }

  document.querySelector('[data-view=settings]').addEventListener('click', refreshSettings);
  document.addEventListener('marketai:accountready', async () => {
    try {
      const info = await request('/api/app/info');
      backupCard.hidden = operations.hidden = info.mode !== 'local';
      find('desktopTraySettings').hidden = !info.tray_available;
      tray.checked = Boolean(info.preferences?.minimize_to_tray);
      if (find('view-settings').classList.contains('active')) refreshSettings();
    } catch {
      // The account flow retains its existing connection status and retry behavior.
    }
  });
  setInterval(() => {
    if (!operations.hidden && find('view-settings').classList.contains('active')) refreshOperations();
  }, 5000);
})();
