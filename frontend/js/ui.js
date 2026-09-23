const UI = (() => {
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  }

  // Modals are built fresh on every open call (never cached/reused), per spec.
  function openModal(contentEl, { onClose } = {}) {
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.appendChild(contentEl);
    backdrop.appendChild(modal);

    function close() {
      backdrop.remove();
      if (onClose) onClose();
    }
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) close();
    });
    document.body.appendChild(backdrop);
    return { close, modal };
  }

  return { escapeHtml, formatBytes, openModal };
})();
