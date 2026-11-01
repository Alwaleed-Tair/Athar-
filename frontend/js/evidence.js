const Evidence = (() => {
  const IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp', '.heic', '.heif'];

  function isImageFilename(filename) {
    const lower = (filename || '').toLowerCase();
    return IMAGE_EXTENSIONS.some((ext) => lower.endsWith(ext));
  }

  const CATEGORY_CODES = [
    'PHYSICAL_EVIDENCE',
    'TESTIMONY',
    'TECHNICAL_REPORT',
    'CORRESPONDENCE',
    'OFFICIAL_DOCUMENT',
    'OTHER',
  ];

  function categoryLabel(code) {
    const key = 'category' + code
      .toLowerCase()
      .split('_')
      .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
      .join('');
    return I18n.t(key);
  }

  function categoryOptionsHtml(selected) {
    return CATEGORY_CODES.map(
      (c) => `<option value="${c}" ${c === selected ? 'selected' : ''}>${categoryLabel(c)}</option>`
    ).join('');
  }

  const displayName = (it) => it.title || it.filename;

  async function renderTab(caseId) {
    const wrap = document.createElement('div');

    const uploadCard = document.createElement('div');
    uploadCard.className = 'card';
    uploadCard.innerHTML = `
      <h3 style="display:flex; align-items:center; gap:8px;">
        ${UI.icon('file', '', 20)}
        <span>${I18n.t('uploadEvidence')}</span>
      </h3>
      <div id="upload-error"></div>
      <div class="form-grid">
        <div class="field">
          <label for="upload-title">${I18n.t('evTitle')} <span class="text-muted text-xs">(${I18n.t('optional')})</span></label>
          <input id="upload-title" type="text" maxlength="200" placeholder="${I18n.t('evTitlePlaceholder')}" />
        </div>
        <div class="field">
          <label for="upload-category">${I18n.t('category')}</label>
          <select id="upload-category">${categoryOptionsHtml('OTHER')}</select>
        </div>
      </div>
      <div class="field">
        <label for="upload-desc">${I18n.t('evDescription')} <span class="text-muted text-xs">(${I18n.t('optional')})</span></label>
        <textarea id="upload-desc" rows="2" maxlength="2000" placeholder="${I18n.t('evDescriptionPlaceholder')}"></textarea>
      </div>
      <div class="dropzone" id="dropzone" tabindex="0" role="button" aria-label="${I18n.t('dropHint')}">
        <div style="color:var(--color-primary); margin-bottom:8px; display:flex; justify-content:center;">
          ${UI.icon('folder', '', 36)}
        </div>
        <div id="dropzone-text" style="font-weight:500;">${I18n.t('dropHint')}</div>
        <div class="text-muted text-xs mt-1">${I18n.t('uploadFormatsHint')}</div>
        <input type="file" id="file-input" style="display:none" />
      </div>
    `;
    wrap.appendChild(uploadCard);

    const listCard = document.createElement('div');
    listCard.className = 'card mt-4';
    wrap.appendChild(listCard);

    async function reloadList() {
      listCard.innerHTML = UI.spinner();
      let items;
      try {
        items = await Api.listEvidence(caseId);
      } catch (e) {
        listCard.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div>`;
        return;
      }
      if (items.length === 0) {
        listCard.innerHTML = `<div class="empty-state"><div style="color:var(--color-cyan); display:flex; justify-content:center; margin-bottom:8px;">${UI.icon('file', '', 40)}</div><h3>${I18n.t('noEvidenceTitle')}</h3><p>${I18n.t('noEvidenceBody')}</p></div>`;
        return;
      }
      const tableWrap = document.createElement('div');
      tableWrap.className = 'table-wrap';
      const table = document.createElement('table');
      table.className = 'responsive-table';
      table.innerHTML = `
        <thead><tr>
          <th>${I18n.t('filename')}</th>
          <th>${I18n.t('category')}</th>
          <th>${I18n.t('size')}</th>
          <th>${I18n.t('exifStatus')}</th>
          <th>${I18n.t('uploadedAt')}</th>
          <th><span class="sr-only">${I18n.t('actions')}</span></th>
        </tr></thead>
        <tbody></tbody>
      `;
      const tbody = table.querySelector('tbody');
      items.forEach((it) => {
        const tr = document.createElement('tr');
        tr.className = 'clickable';
        const chat = it.message_count ? `<span class="badge ok" title="${I18n.t('convBadgeTitle')}">${UI.icon('message', '', 12)} ${it.message_count}</span>` : '';
        tr.innerHTML = `
          <td data-label="${I18n.t('filename')}">
            <div class="ev-name">${UI.escapeHtml(displayName(it))} ${chat}</div>
            ${it.title ? `<div class="text-muted text-xs" dir="auto">${UI.escapeHtml(it.filename)}</div>` : ''}
            ${it.description ? `<div class="text-muted text-xs ev-desc" dir="auto">${UI.escapeHtml(it.description)}</div>` : ''}
          </td>
          <td data-label="${I18n.t('category')}"><span class="badge">${categoryLabel(it.category)}</span></td>
          <td data-label="${I18n.t('size')}"><bdi dir="ltr">${UI.formatBytes(it.size_bytes)}</bdi></td>
          <td data-label="${I18n.t('exifStatus')}"><span class="badge ${it.exif_status === 'SUCCESS' ? 'ok' : it.exif_status === 'FAILED' ? 'bad' : ''}">${I18n.t('exif_' + it.exif_status)}</span></td>
          <td data-label="${I18n.t('uploadedAt')}" class="text-muted text-sm">${UI.dateHtml(it.uploaded_at)}<div class="text-xs">${UI.escapeHtml(it.uploader_name || '')}</div></td>
          <td class="row-actions"></td>
        `;
        const actions = tr.querySelector('.row-actions');
        const mk = (iconName, label, cls, fn) => {
          const b = document.createElement('button');
          b.type = 'button';
          b.className = `btn btn-sm btn-icon ${cls || ''}`;
          b.title = label;
          b.setAttribute('aria-label', label);
          b.innerHTML = UI.icon(iconName, '', 15);
          b.onclick = (e) => { e.stopPropagation(); fn(); };
          actions.appendChild(b);
        };
        mk('eye', I18n.t('view'), '', () => openInspectModal(it.id, reloadList));
        if (it.can_manage) {
          mk('edit', I18n.t('edit'), '', () => openInspectModal(it.id, reloadList, { focusEdit: true }));
          mk('trash', I18n.t('delete'), 'btn-danger-ghost', () => confirmDelete(it, reloadList));
        }
        tr.onclick = () => openInspectModal(it.id, reloadList);
        tbody.appendChild(tr);
      });
      tableWrap.appendChild(table);
      listCard.innerHTML = '';
      listCard.appendChild(tableWrap);
    }

    const dropzone = uploadCard.querySelector('#dropzone');
    const fileInput = uploadCard.querySelector('#file-input');
    const dzText = uploadCard.querySelector('#dropzone-text');
    const errorBox = uploadCard.querySelector('#upload-error');
    const categorySelect = uploadCard.querySelector('#upload-category');
    const titleInput = uploadCard.querySelector('#upload-title');
    const descInput = uploadCard.querySelector('#upload-desc');

    async function doUpload(file) {
      if (!file) return;
      errorBox.innerHTML = '';
      dropzone.classList.add('busy');
      dzText.innerHTML = `<span class="spinner"></span> ${I18n.t('uploading')} <bdi dir="ltr">${UI.escapeHtml(file.name)}</bdi>`;
      try {
        const res = await Api.uploadEvidence(caseId, file, categorySelect.value, titleInput.value.trim(), descInput.value.trim());
        Notifications.refresh();
        titleInput.value = '';
        descInput.value = '';
        UI.toast(res.conversation
          ? I18n.t('uploadDoneChat', { count: res.conversation.message_count })
          : I18n.t('uploadDone'));
        await reloadList();
      } catch (err) {
        errorBox.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 16)} <span>${UI.escapeHtml(UI.errorMessage(err))}</span></div>`;
      }
      dropzone.classList.remove('busy');
      dzText.textContent = I18n.t('dropHint');
      fileInput.value = '';
    }

    dropzone.onclick = () => fileInput.click();
    dropzone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
    fileInput.addEventListener('change', () => doUpload(fileInput.files[0]));
    ['dragover', 'dragenter'].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add('dragover'); })
    );
    ['dragleave', 'drop'].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove('dragover'); })
    );
    dropzone.addEventListener('drop', (e) => {
      const file = e.dataTransfer.files[0];
      doUpload(file);
    });

    await reloadList();
    return wrap;
  }

  // Confirmation + retention explanation before deleting evidence.
  async function confirmDelete(item, onDone) {
    const ok = await UI.confirmDialog({
      title: I18n.t('evDeleteTitle'),
      message: I18n.t('evDeleteConfirm', { name: `<strong dir="auto">${UI.escapeHtml(displayName(item))}</strong>` }),
      note: I18n.t('evDeleteNote'),
      confirmLabel: I18n.t('evDeleteBtn'),
    });
    if (!ok) return false;
    try {
      await Api.deleteEvidence(item.id);
      Notifications.refresh();
      UI.toast(I18n.t('evDeleted'));
      if (onDone) await onDone();
      return true;
    } catch (e) {
      UI.toast(UI.errorMessage(e), 'error');
      return false;
    }
  }

  async function openInspectModal(evidenceId, onChange, { focusEdit = false } = {}) {
    const content = document.createElement('div');
    content.innerHTML = UI.spinner();
    const { close } = UI.openModal(content, { onClose: () => { if (changed && onChange) onChange(); } });
    let changed = false;

    let ev;
    try {
      ev = await Api.getEvidence(evidenceId);
    } catch (e) {
      content.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div><div class="mt-3"><button class="btn" id="ev-close-err">${I18n.t('close')}</button></div>`;
      content.querySelector('#ev-close-err').onclick = close;
      return;
    }

    const exifEntries = Object.entries(ev.exif || {});
    const exifHtml = exifEntries.length
      ? `<div class="table-wrap"><table><tbody>${exifEntries
          .map(([k, v]) => `<tr><td class="text-muted">${UI.escapeHtml(k)}</td><td dir="auto">${UI.escapeHtml(v)}</td></tr>`)
          .join('')}</tbody></table></div>`
      : `<p class="text-muted text-sm">${I18n.t('noExifData')}</p>`;

    const custodyHtml = (ev.custody_log || []).length
      ? `<div class="chain-list">${ev.custody_log
          .map(
            (c) => `<div class="chain-item">
                <div class="text-sm" dir="auto">${UI.escapeHtml(c.message)}</div>
                <div class="text-muted text-xs">${UI.dateHtml(c.ts)}</div>
              </div>`
          )
          .join('')}</div>`
      : `<p class="text-muted text-sm">${I18n.t('chainEmpty')}</p>`;

    const hasCached = !!ev.cached_analysis;
    const analyzeLabel = hasCached ? I18n.t('reRunAiAnalysis') : I18n.t('runAiAnalysis');

    const isImage = isImageFilename(ev.filename);
    const hasCachedAuth = !!ev.cached_authenticity;
    const authLabel = hasCachedAuth ? I18n.t('reRunAuthCheck') : I18n.t('runAuthCheck');
    const authSectionHtml = isImage
      ? `
        <h4 class="mt-4">${I18n.t('authCheckTitle')}</h4>
        <p class="text-muted text-xs">${I18n.t('authCheckCaveat')}</p>
        <button class="btn btn-sm" id="ev-auth-check">${authLabel}</button>
        <div id="ev-auth-result" class="mt-3">
          ${hasCachedAuth ? renderAuthenticityResult(ev.cached_authenticity, ev.cached_authenticity_at) : ''}
        </div>
      `
      : '';

    const detailsHtml = ev.can_manage
      ? `
        <form id="ev-edit-form" novalidate>
          <div class="field">
            <label for="ev-title">${I18n.t('evTitle')}</label>
            <input id="ev-title" type="text" maxlength="200" value="${UI.escapeHtml(ev.title || '')}" placeholder="${UI.escapeHtml(ev.filename)}" />
          </div>
          <div class="field">
            <label for="ev-desc">${I18n.t('evDescription')}</label>
            <textarea id="ev-desc" rows="3" maxlength="2000">${UI.escapeHtml(ev.description || '')}</textarea>
          </div>
          <div class="field">
            <label for="ev-category">${I18n.t('category')}</label>
            <select id="ev-category">${categoryOptionsHtml(ev.category)}</select>
          </div>
          <div id="ev-edit-msg"></div>
          <button type="submit" class="btn btn-primary btn-sm" id="ev-edit-save">${UI.icon('check', '', 14)} <span>${I18n.t('save')}</span></button>
          <p class="text-muted text-xs mt-2">${I18n.t('evEditNote')}</p>
        </form>`
      : `
        <div class="field"><label>${I18n.t('evTitle')}</label><div dir="auto">${UI.escapeHtml(ev.title || '—')}</div></div>
        <div class="field"><label>${I18n.t('evDescription')}</label><div dir="auto" style="white-space:pre-wrap">${UI.escapeHtml(ev.description || '—')}</div></div>
        <div class="field"><label>${I18n.t('category')}</label><div>${categoryLabel(ev.category)}</div></div>
        <p class="text-muted text-xs">${I18n.t('evReadOnlyNote')}</p>`;

    content.innerHTML = `
      <div class="modal-header">
        <h3 dir="auto" style="word-break:break-word;">${UI.escapeHtml(displayName(ev))}</h3>
        <button class="btn btn-sm" id="ev-close" aria-label="${I18n.t('close')}">${UI.icon('x', '', 14)}</button>
      </div>
      ${ev.title ? `<div class="text-muted text-sm" dir="auto">${UI.escapeHtml(ev.filename)}</div>` : ''}

      <div class="mt-3">${detailsHtml}</div>

      <div class="field mt-3">
        <label>${I18n.t('sha256')}</label>
        <div class="mono" style="word-break:break-all" dir="ltr">${ev.sha256}</div>
      </div>
      <div class="flex gap-3 text-sm text-muted mt-2" style="flex-wrap:wrap;">
        <div>${I18n.t('size')}: <bdi dir="ltr">${UI.formatBytes(ev.size_bytes)}</bdi></div>
        <div>${I18n.t('uploadedAt')}: ${UI.dateHtml(ev.uploaded_at)}</div>
        <div>${I18n.t('uploadedBy')}: ${UI.escapeHtml(ev.uploader_name || '')}</div>
        ${ev.updated_at ? `<div>${I18n.t('evUpdatedAt')}: ${UI.dateHtml(ev.updated_at)}</div>` : ''}
      </div>

      <div class="integrity-box mt-3">
        <div class="flex gap-2" style="align-items:center; flex-wrap:wrap;">
          <button class="btn btn-sm" id="ev-verify">${UI.icon('shieldCheck', '', 14)} <span>${I18n.t('evVerifyIntegrity')}</span></button>
          <span class="text-muted text-xs">${I18n.t('evVerifyHint')}</span>
        </div>
        <div id="ev-verify-result" class="mt-2" aria-live="polite"></div>
      </div>

      <h4 class="mt-4">${I18n.t('exifMetadata')}</h4>
      ${exifHtml}

      <div class="mt-4 flex gap-2" style="flex-wrap:wrap;">
        <button class="btn btn-primary btn-sm" id="ev-download">${UI.icon('download', '', 14)} <span>${I18n.t('download')}</span></button>
        <button class="btn btn-sm" id="ev-analyze">${UI.icon('cpu', '', 14)} <span>${analyzeLabel}</span></button>
        ${ev.can_manage ? `<button class="btn btn-danger btn-sm" id="ev-delete" style="margin-inline-start:auto;">${UI.icon('trash', '', 14)} <span>${I18n.t('delete')}</span></button>` : ''}
      </div>
      <div id="ev-analysis-result" class="mt-3">
        ${hasCached ? renderAnalysisResult(ev.cached_analysis, ev.cached_analysis_at) : ''}
      </div>
      ${authSectionHtml}

      ${ev.conversation ? `<h4 class="mt-4" style="display:flex; align-items:center; gap:8px;">${UI.icon('message', '', 18)} <span>${I18n.t('convTitle')}</span></h4><div id="ev-conversation"></div>` : ''}

      <h4 class="mt-4">${I18n.t('custodyLog')}</h4>
      ${custodyHtml}
    `;

    content.querySelector('#ev-close').onclick = close;

    content.querySelector('#ev-download').onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await Api.downloadEvidence(ev.id, ev.filename);
      } catch (err) {
        UI.toast(UI.errorMessage(err), 'error');
      }
      btn.disabled = false;
    };

    // --- integrity ---------------------------------------------------------
    const verifyBtn = content.querySelector('#ev-verify');
    const verifyBox = content.querySelector('#ev-verify-result');
    verifyBtn.onclick = async () => {
      verifyBtn.disabled = true;
      verifyBox.innerHTML = UI.spinner(I18n.t('verifying'));
      try {
        const r = await Api.verifyEvidenceIntegrity(ev.id);
        if (r.intact) {
          verifyBox.innerHTML = `<div class="alert alert-success">${UI.icon('shieldCheck', '', 16)} <span>${I18n.t('evIntegrityOk')}</span></div>`;
        } else {
          verifyBox.innerHTML = `<div class="alert alert-danger">${UI.icon('shieldAlert', '', 16)} <div><strong>${r.result === 'MISSING' ? I18n.t('evIntegrityMissing') : I18n.t('evIntegrityBad')}</strong>
            <div class="mono text-xs mt-1" dir="ltr" style="word-break:break-all">${I18n.t('evExpected')}: ${UI.escapeHtml(r.expected_sha256)}<br>${I18n.t('evActual')}: ${UI.escapeHtml(r.actual_sha256 || '—')}</div></div></div>`;
        }
      } catch (e) {
        verifyBox.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div>`;
      }
      verifyBtn.disabled = false;
    };

    // --- edit --------------------------------------------------------------
    const form = content.querySelector('#ev-edit-form');
    if (form) {
      const msg = content.querySelector('#ev-edit-msg');
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const save = content.querySelector('#ev-edit-save');
        const title = content.querySelector('#ev-title').value.trim();
        if (title.length > 200) { msg.innerHTML = `<div class="alert alert-danger">${I18n.t('evTitleTooLong')}</div>`; return; }
        save.disabled = true;
        msg.innerHTML = '';
        try {
          const r = await Api.updateEvidence(ev.id, {
            title,
            description: content.querySelector('#ev-desc').value.trim(),
            category: content.querySelector('#ev-category').value,
          });
          changed = changed || r.changed.length > 0;
          msg.innerHTML = `<div class="alert alert-success">${UI.icon('check', '', 16)} <span>${r.changed.length ? I18n.t('evSaved') : I18n.t('evNoChanges')}</span></div>`;
          if (r.changed.length) UI.toast(I18n.t('evSaved'));
        } catch (err) {
          msg.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(err))}</div>`;
        }
        save.disabled = false;
      });
      if (focusEdit) setTimeout(() => content.querySelector('#ev-title').focus(), 50);
    }

    // --- delete ------------------------------------------------------------
    const delBtn = content.querySelector('#ev-delete');
    if (delBtn) {
      delBtn.onclick = async () => {
        const done = await confirmDelete(ev, null);
        if (done) { changed = true; close(); }
      };
    }

    // --- AI analysis ---------------------------------------------------------
    const analyzeBtn = content.querySelector('#ev-analyze');
    const resultBox = content.querySelector('#ev-analysis-result');
    analyzeBtn.onclick = async () => {
      analyzeBtn.disabled = true;
      resultBox.innerHTML = UI.spinner(I18n.t('analyzing'));
      try {
        const res = await Api.analyzeEvidence(ev.id);
        resultBox.innerHTML = renderAnalysisResult(res);
      } catch (e) {
        resultBox.innerHTML = `<div class="alert alert-danger">${UI.icon('shieldAlert', '', 16)} <span>${UI.escapeHtml(UI.errorMessage(e))}</span></div>`;
      }
      analyzeBtn.disabled = false;
      analyzeBtn.querySelector('span').textContent = I18n.t('reRunAiAnalysis');
    };

    if (isImage) {
      const authBtn = content.querySelector('#ev-auth-check');
      const authResultBox = content.querySelector('#ev-auth-result');
      authBtn.onclick = async () => {
        authBtn.disabled = true;
        authResultBox.innerHTML = UI.spinner(I18n.t('analyzing'));
        try {
          const res = await Api.checkEvidenceAuthenticity(ev.id);
          authResultBox.innerHTML = renderAuthenticityResult(res);
        } catch (e) {
          authResultBox.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div>`;
        }
        authBtn.disabled = false;
        authBtn.textContent = I18n.t('reRunAuthCheck');
      };
    }

    // --- conversation --------------------------------------------------------
    const convBox = content.querySelector('#ev-conversation');
    if (convBox) {
      Conversation.render(convBox, ev.id, {
        onOpenEvidence: (id) => { close(); openInspectModal(id, onChange); },
      });
    }
  }

  function renderAnalysisResult(res, analyzedAt) {
    if (res.status === 'DISABLED') {
      return `<div class="alert alert-warning">${I18n.t('aiDisabled')}</div>`;
    }
    if (res.status === 'FAILED') {
      return `<div class="alert alert-danger">${UI.escapeHtml((I18n.getLang() === 'ar' ? res.message_ar : res.message_en) || I18n.t('genericError'))}</div>`;
    }
    const correlations = res.correlations || [];
    const corrHtml = correlations.length
      ? `<ul>${correlations
          .map((c) => `<li><strong>${UI.escapeHtml(c.evidence_filename)}</strong> — ${UI.escapeHtml(c.explanation)}</li>`)
          .join('')}</ul>`
      : `<p class="text-muted text-sm">${I18n.t('aiNone')}</p>`;
    const savedNote = analyzedAt
      ? `<div class="text-muted text-xs mt-1">${I18n.t('lastAnalyzedAt')}: ${UI.dateHtml(analyzedAt)}</div>`
      : '';
    return `
      <div class="ai-tag">${UI.icon('alertTriangle', '', 14)} <span>${I18n.t('aiAutomatedEstimate')}</span></div>
      <p><strong>${I18n.t('aiSummary')}:</strong> ${UI.escapeHtml(res.summary || '')}</p>
      <p><strong>${I18n.t('aiCorrelations')}:</strong></p>
      ${corrHtml}
      ${savedNote}
    `;
  }

  function renderAuthenticityResult(res, checkedAt) {
    if (res.status === 'NOT_APPLICABLE') {
      return `<p class="text-muted text-sm">${I18n.t('authCheckNotApplicable')}</p>`;
    }

    const exif = res.exif_indicators || {};
    const exifLines = [];
    if (exif.editing_software_detected) {
      exifLines.push(
        `<li class="text-danger">${I18n.t('authExifSoftwareDetected')}: ${UI.escapeHtml(exif.software_field || '')}</li>`
      );
    } else {
      exifLines.push(`<li class="text-success">${I18n.t('authExifNoSoftware')}</li>`);
    }
    if (exif.missing_camera_metadata) {
      exifLines.push(`<li class="text-muted">${I18n.t('authExifMissingCamera')}</li>`);
    }
    const exifHtml = `<ul class="text-sm">${exifLines.join('')}</ul>`;

    let aiHtml = '';
    if (res.ai_status === 'DISABLED') {
      aiHtml = `<div class="alert alert-warning mt-2">${I18n.t('aiDisabled')}</div>`;
    } else if (res.ai_status === 'FAILED') {
      aiHtml = `<div class="alert alert-danger mt-2">${UI.escapeHtml(res.ai_message || I18n.t('genericError'))}</div>`;
    } else if (res.ai_assessment) {
      const labelKey = {
        REAL: 'authLabelReal',
        FAKE: 'authLabelFake',
        UNSURE: 'authLabelUnsure',
      }[res.ai_assessment.label] || 'authLabelUnsure';
      const badgeClass = res.ai_assessment.label === 'FAKE' ? 'bad' : res.ai_assessment.label === 'REAL' ? 'ok' : 'warn';
      aiHtml = `
        <div class="mt-2"><span class="badge ${badgeClass}">${I18n.t(labelKey)}</span></div>
        <p class="text-sm mt-1">${UI.escapeHtml(res.ai_assessment.explanation || '')}</p>
      `;
    }

    const savedNote = checkedAt
      ? `<div class="text-muted text-xs mt-2">${I18n.t('lastAnalyzedAt')}: ${UI.dateHtml(checkedAt)}</div>`
      : '';

    return `
      <div class="ai-tag">${UI.icon('alertTriangle', '', 14)} <span>${I18n.t('authCheckCaveat')}</span></div>
      <h5 class="mt-2 text-sm">${I18n.t('authExifTitle')}</h5>
      ${exifHtml}
      <h5 class="mt-2 text-sm">${I18n.t('authAiTitle')}</h5>
      ${aiHtml}
      ${savedNote}
    `;
  }

  return { renderTab, openInspectModal };
})();
