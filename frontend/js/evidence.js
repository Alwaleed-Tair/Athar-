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

  async function renderTab(caseId) {
    const wrap = document.createElement('div');

    const uploadCard = document.createElement('div');
    uploadCard.className = 'card';
    uploadCard.innerHTML = `
      <h3>${I18n.t('uploadEvidence')}</h3>
      <div id="upload-error"></div>
      <div class="field">
        <label>${I18n.t('category')}</label>
        <select id="upload-category">${categoryOptionsHtml('OTHER')}</select>
      </div>
      <div class="dropzone" id="dropzone">
        <div id="dropzone-text">${I18n.t('dropHint')}</div>
        <input type="file" id="file-input" style="display:none" />
      </div>
    `;
    wrap.appendChild(uploadCard);

    const listCard = document.createElement('div');
    listCard.className = 'card mt-4';
    wrap.appendChild(listCard);

    async function reloadList() {
      listCard.innerHTML = `<p class="text-muted">…</p>`;
      let items;
      try {
        items = await Api.listEvidence(caseId);
      } catch (e) {
        listCard.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
        return;
      }
      if (items.length === 0) {
        listCard.innerHTML = `<div class="empty-state"><h3>${I18n.t('noEvidenceTitle')}</h3><p>${I18n.t('noEvidenceBody')}</p></div>`;
        return;
      }
      const tableWrap = document.createElement('div');
      tableWrap.className = 'table-wrap';
      const table = document.createElement('table');
      table.innerHTML = `
        <thead><tr>
          <th>${I18n.t('filename')}</th>
          <th>${I18n.t('category')}</th>
          <th>${I18n.t('size')}</th>
          <th>${I18n.t('exifStatus')}</th>
          <th>${I18n.t('uploadedAt')}</th>
        </tr></thead>
        <tbody></tbody>
      `;
      const tbody = table.querySelector('tbody');
      items.forEach((it) => {
        const tr = document.createElement('tr');
        tr.className = 'clickable';
        tr.innerHTML = `
          <td>${UI.escapeHtml(it.filename)}</td>
          <td><span class="badge">${categoryLabel(it.category)}</span></td>
          <td>${UI.formatBytes(it.size_bytes)}</td>
          <td><span class="badge ${it.exif_status === 'SUCCESS' ? 'ok' : it.exif_status === 'FAILED' ? 'bad' : ''}">${I18n.t('exif_' + it.exif_status)}</span></td>
          <td class="text-muted text-sm">${UI.escapeHtml(it.uploaded_at)}</td>
        `;
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

    async function doUpload(file) {
      if (!file) return;
      errorBox.innerHTML = '';
      dzText.textContent = I18n.t('uploading');
      try {
        await Api.uploadEvidence(caseId, file, categorySelect.value);
        Notifications.refresh();
        dzText.textContent = I18n.t('dropHint');
        await reloadList();
      } catch (err) {
        dzText.textContent = I18n.t('dropHint');
        errorBox.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(err.message)}</div>`;
      }
    }

    dropzone.onclick = () => fileInput.click();
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

  async function openInspectModal(evidenceId) {
    const content = document.createElement('div');
    content.innerHTML = `<p class="text-muted">…</p>`;
    const { close } = UI.openModal(content);

    let ev;
    try {
      ev = await Api.getEvidence(evidenceId);
    } catch (e) {
      content.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
      return;
    }

    const exifEntries = Object.entries(ev.exif || {});
    const exifHtml = exifEntries.length
      ? `<table><tbody>${exifEntries
          .map(([k, v]) => `<tr><td class="text-muted">${UI.escapeHtml(k)}</td><td>${UI.escapeHtml(v)}</td></tr>`)
          .join('')}</tbody></table>`
      : `<p class="text-muted text-sm">${I18n.t('noExifData')}</p>`;

    const custodyHtml = (ev.custody_log || []).length
      ? `<div class="chain-list">${ev.custody_log
          .map(
            (c) => `<div class="chain-item">
                <div class="text-sm">${UI.escapeHtml(c.message)}</div>
                <div class="text-muted text-xs">${UI.escapeHtml(c.ts)}</div>
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

    content.innerHTML = `
      <div class="modal-header">
        <h3>${UI.escapeHtml(ev.filename)}</h3>
        <button class="btn btn-sm" id="ev-close">${I18n.t('close')}</button>
      </div>
      <div class="field">
        <label>${I18n.t('category')}</label>
        <div class="flex gap-2">
          <select id="ev-category" style="flex:1">${categoryOptionsHtml(ev.category)}</select>
          <button class="btn btn-sm" id="ev-category-save">${I18n.t('save')}</button>
        </div>
      </div>
      <div class="field">
        <label>${I18n.t('sha256')}</label>
        <div class="mono" style="word-break:break-all">${ev.sha256}</div>
      </div>
      <div class="flex gap-3 text-sm text-muted mt-3">
        <div>${I18n.t('size')}: ${UI.formatBytes(ev.size_bytes)}</div>
        <div>${I18n.t('uploadedAt')}: ${UI.escapeHtml(ev.uploaded_at)}</div>
      </div>

      <h4 class="mt-4">${I18n.t('exifMetadata')}</h4>
      ${exifHtml}

      <div class="mt-4 flex gap-2">
        <button class="btn btn-primary btn-sm" id="ev-download">${I18n.t('download')}</button>
        <button class="btn btn-sm" id="ev-analyze">${analyzeLabel}</button>
      </div>
      <div id="ev-analysis-result" class="mt-3">
        ${hasCached ? renderAnalysisResult(ev.cached_analysis, ev.cached_analysis_at) : ''}
      </div>
      ${authSectionHtml}

      <h4 class="mt-4">${I18n.t('custodyLog')}</h4>
      ${custodyHtml}
    `;

    content.querySelector('#ev-close').onclick = close;
    content.querySelector('#ev-download').onclick = () => Api.downloadEvidence(ev.id, ev.filename);

    const categorySelect = content.querySelector('#ev-category');
    const categorySaveBtn = content.querySelector('#ev-category-save');
    categorySaveBtn.onclick = async () => {
      categorySaveBtn.disabled = true;
      try {
        await Api.setEvidenceCategory(ev.id, categorySelect.value);
        categorySaveBtn.textContent = I18n.t('saved');
        setTimeout(() => {
          categorySaveBtn.textContent = I18n.t('save');
          categorySaveBtn.disabled = false;
        }, 1200);
      } catch (e) {
        categorySaveBtn.disabled = false;
      }
    };

    const analyzeBtn = content.querySelector('#ev-analyze');
    const resultBox = content.querySelector('#ev-analysis-result');
    analyzeBtn.onclick = async () => {
      analyzeBtn.disabled = true;
      analyzeBtn.textContent = I18n.t('analyzing');
      try {
        const res = await Api.analyzeEvidence(ev.id);
        resultBox.innerHTML = renderAnalysisResult(res);
      } catch (e) {
        resultBox.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
      }
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = I18n.t('reRunAiAnalysis');
    };

    if (isImage) {
      const authBtn = content.querySelector('#ev-auth-check');
      const authResultBox = content.querySelector('#ev-auth-result');
      authBtn.onclick = async () => {
        authBtn.disabled = true;
        authBtn.textContent = I18n.t('analyzing');
        try {
          const res = await Api.checkEvidenceAuthenticity(ev.id);
          authResultBox.innerHTML = renderAuthenticityResult(res);
        } catch (e) {
          authResultBox.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
        }
        authBtn.disabled = false;
        authBtn.textContent = I18n.t('reRunAuthCheck');
      };
    }
  }

  function renderAnalysisResult(res, analyzedAt) {
    if (res.status === 'DISABLED') {
      return `<div class="alert alert-warning">${I18n.t('aiDisabled')}</div>`;
    }
    if (res.status === 'FAILED') {
      return `<div class="alert alert-danger">${UI.escapeHtml(res.message_en || I18n.t('genericError'))}</div>`;
    }
    const correlations = res.correlations || [];
    const corrHtml = correlations.length
      ? `<ul>${correlations
          .map((c) => `<li><strong>${UI.escapeHtml(c.evidence_filename)}</strong> — ${UI.escapeHtml(c.explanation)}</li>`)
          .join('')}</ul>`
      : `<p class="text-muted text-sm">${I18n.t('aiNone')}</p>`;
    const savedNote = analyzedAt
      ? `<div class="text-muted text-xs mt-1">${I18n.t('lastAnalyzedAt')}: ${UI.escapeHtml(analyzedAt)}</div>`
      : '';
    return `
      <div class="ai-tag">⚠ ${I18n.t('aiAutomatedEstimate')}</div>
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
      ? `<div class="text-muted text-xs mt-2">${I18n.t('lastAnalyzedAt')}: ${UI.escapeHtml(checkedAt)}</div>`
      : '';

    return `
      <div class="ai-tag">⚠ ${I18n.t('authCheckCaveat')}</div>
      <h5 class="mt-2 text-sm">${I18n.t('authExifTitle')}</h5>
      ${exifHtml}
      <h5 class="mt-2 text-sm">${I18n.t('authAiTitle')}</h5>
      ${aiHtml}
      ${savedNote}
    `;
  }

  return { renderTab, openInspectModal };
})();