// Public information pages (privacy, terms of use, how analysis works),
// the contact form, and the site footer. These are reachable WITHOUT signing
// in and from the footer of every screen. The text below describes what the
// platform really does today; if behaviour changes, update it here.
const Pages = (() => {
  const CONTENT = {
    privacy: {
      ar: {
        title: 'سياسة الخصوصية',
        updated: 'آخر تحديث: 4 نوفمبر 2026',
        sections: [
          { h: 'ماذا نحفظ؟', list: [
            'اسمك وبريدك الإلكتروني (للدخول فقط، لا نرسل لك رسائل).',
            'كلمة مرورك محفوظة بشكل مشفّر، ولا أحد يستطيع قراءتها.',
            'الملفات التي ترفعها، وسجل بما تم عليها (من رفع، ومن فتح، ومتى).',
          ]},
          { h: 'من يرى بياناتك؟', list: [
            'أنت، ومن تشاركهم القضية فقط.',
            'مسؤول النظام يدير الحسابات، لكنه لا يرى قضاياك إلا إذا أضفته.',
            'إذا طابق دليلٌ في قضيتك (ملف مطابق أو رقم هاتف أو بريد أو آيبان) دليلاً في قضية شخص آخر، يُبلَّغ كل منكما بوجود التطابق فقط، دون اسم القضية الأخرى أو صاحبها أو محتواها. ولا تُفتح القضية إلا إذا قبل مالكها طلب الوصول.',
            'الفريق الذي يشغّل الخادم يستطيع تقنياً الوصول للملفات المخزّنة.',
          ]},
          { h: 'الذكاء الاصطناعي', list: [
            'عند استخدام ميزاته، يُرسل جزء من نصوص الأدلة وصورها إلى خدمة ذكاء اصطناعي خارجية لتحليلها.',
            'لا ترفع أدلة لا يُسمح لك بمشاركتها مع جهة خارجية.',
          ]},
          { h: 'الحذف', list: [
            'الدليل المحذوف يختفي فوراً، ويُحذف ملفه نهائياً بعد 30 يوماً.',
            'تستطيع حذف حسابك من «حسابي».',
            'سجل العمليات لا يُحذف، لأنه الدليل على ما حدث.',
          ]},
          { h: 'تواصل معنا', list: ['لأي سؤال عن بياناتك استخدم صفحة «تواصل معنا».'] },
        ],
      },
      en: {
        title: 'Privacy Policy',
        updated: 'Last updated: 4 November 2026',
        sections: [
          { h: 'What we keep', list: [
            'Your name and e-mail (used only to sign in; we do not send you e-mails).',
            'Your password, stored encrypted so no one can read it.',
            'The files you upload, and a record of what happened to them (who uploaded, opened, and when).',
          ]},
          { h: 'Who can see your data', list: [
            'You, and only the people you share a case with.',
            'The administrator manages accounts but cannot see your cases unless you add them.',
            'If evidence in your case matches evidence in someone else\'s case (same file, phone number, e-mail or IBAN), each of you is told only that a match exists, never the other case\'s name, owner or content. The case opens only if its owner accepts an access request.',
            'The team that runs the server can technically reach the stored files.',
          ]},
          { h: 'AI features', list: [
            'When you use them, parts of the evidence text and images are sent to an outside AI service to be analysed.',
            'Do not upload evidence you are not allowed to share with an outside service.',
          ]},
          { h: 'Deleting', list: [
            'Deleted evidence disappears at once; its file is removed for good after 30 days.',
            'You can delete your account from "My account".',
            'The activity record is never deleted, because it is the proof of what happened.',
          ]},
          { h: 'Contact', list: ['For any question about your data, use the Contact page.'] },
        ],
      },
    },
    terms: {
      ar: {
        title: 'سياسة الاستخدام',
        updated: 'آخر تحديث: 4 نوفمبر 2026',
        sections: [
          { h: 'ما هي أثر؟', list: [
            'أداة تساعدك على تنظيم الأدلة الرقمية وإثبات أن أحداً لم يعدّلها.',
            'لا تغني عن الإجراءات القانونية ولا عن رأي الخبير.',
          ]},
          { h: 'استخدامك', list: [
            'استخدمها فقط لأدلة يحق لك التعامل معها، ولأغراض نظامية.',
            'حافظ على سرية كلمة مرورك.',
          ]},
          { h: 'الذكاء الاصطناعي', list: [
            'نتائجه اقتراحات قد تخطئ، وليست حكماً.',
            'تأكد بنفسك من أي نتيجة قبل الاعتماد عليها.',
          ]},
          { h: 'حدود النظام', list: [
            'ما تقوله رسالة أو مستند هو كلام كاتبه، وليس دليلاً على صحته.',
            'النظام يكشف أي تعديل بعد الرفع، لكنه لا يعرف ما حدث للملف قبل رفعه.',
            'احتفظ بنسخة من أدلتك المهمة.',
          ]},
        ],
      },
      en: {
        title: 'Terms of Use',
        updated: 'Last updated: 4 November 2026',
        sections: [
          { h: 'What Athar is', list: [
            'A tool that helps you organise digital evidence and prove nobody changed it.',
            'It does not replace legal procedure or an expert opinion.',
          ]},
          { h: 'Your use', list: [
            'Use it only for evidence you are allowed to handle, and for lawful purposes.',
            'Keep your password private.',
          ]},
          { h: 'AI features', list: [
            'AI results are suggestions that can be wrong, not a verdict.',
            'Check any result yourself before relying on it.',
          ]},
          { h: 'Limits', list: [
            'What a message or document says is what its writer claims, not proof it is true.',
            'The system detects any change after upload, but cannot know what happened to a file before.',
            'Keep a copy of important evidence.',
          ]},
        ],
      },
    },
    how: {
      ar: {
        title: 'كيف يعمل التحليل',
        updated: 'من رفع الدليل حتى التقرير.',
        steps: [
          { h: 'الرفع', p: 'ترفع الملف، ويأخذ النظام له «بصمة» فريدة. أي تغيير في الملف لاحقاً يغيّر البصمة.' },
          { h: 'القراءة', p: 'يقرأ النظام معلومات الصورة، ونص المستندات، ورسائل المحادثات.' },
          { h: 'التحقق', p: 'قبل أي تنزيل أو تحليل يقارن النظام البصمة، فإن تغيّر الملف يرفض العملية.' },
          { h: 'الربط', p: 'يبحث عن أدلة تشترك في شيء: نفس الملف، نفس الجهاز، نفس الرقم أو البريد، ويوضح السبب.' },
          { h: 'الذكاء الاصطناعي (اختياري)', p: 'يقترح ملخصات وروابط، وكل نتيجة عليه موسومة «تقدير آلي».' },
          { h: 'السجل والتقرير', p: 'كل عملية تُسجَّل بشكل لا يمكن تعديله دون اكتشافه، ويمكنك تصدير تقرير PDF.' },
        ],
        limits: [
          'نتائج الذكاء الاصطناعي قد تخطئ.',
          'غياب أي ملاحظة لا يعني أن الملف أصلي.',
          'قراءة النص من الصور تقريبية.',
        ],
      },
      en: {
        title: 'How analysis works',
        updated: 'From upload to report.',
        steps: [
          { h: 'Upload', p: 'You upload a file and the system takes a unique "fingerprint" of it. Any later change alters the fingerprint.' },
          { h: 'Read', p: 'The system reads photo details, document text and chat messages.' },
          { h: 'Check', p: 'Before any download or analysis it compares the fingerprint; if the file changed, it refuses.' },
          { h: 'Link', p: 'It finds evidence that shares something: the same file, device, number or e-mail, and shows why.' },
          { h: 'AI (optional)', p: 'It suggests summaries and links; every result is labelled "AI estimate".' },
          { h: 'Record and report', p: 'Every action is recorded so that any edit is detected, and you can export a PDF report.' },
        ],
        limits: [
          'AI results can be wrong.',
          'No warning does not mean a file is genuine.',
          'Reading text from images is approximate.',
        ],
      },
    },
  };

  function currentLang() { return I18n.getLang() === 'ar' ? 'ar' : 'en'; }

  function renderDoc(name) {
    const c = CONTENT[name][currentLang()];
    const wrap = document.createElement('div');
    wrap.className = 'doc-page';
    let body = '';
    if (c.sections) {
      body = c.sections.map((s) => `<section class="doc-section"><h2>${UI.escapeHtml(s.h)}</h2><ul>${s.list.map((li) => `<li>${UI.escapeHtml(li)}</li>`).join('')}</ul></section>`).join('');
    } else {
      body = `<ol class="doc-steps">${c.steps.map((s, i) => `<li><div class="doc-step-num">${i + 1}</div><div><h2>${UI.escapeHtml(s.h)}</h2><p>${UI.escapeHtml(s.p)}</p></div></li>`).join('')}</ol>
        <div class="card mt-4"><h3 style="display:flex; align-items:center; gap:8px;">${UI.icon('alertTriangle', '', 18)} <span>${I18n.t('howLimitsTitle')}</span></h3><ul>${c.limits.map((l) => `<li>${UI.escapeHtml(l)}</li>`).join('')}</ul></div>`;
    }
    wrap.innerHTML = `
      <div class="doc-nav">${navLinks(name)}</div>
      <div class="card doc-card">
        <h1>${UI.escapeHtml(c.title)}</h1>
        <p class="text-muted">${UI.escapeHtml(c.updated)}</p>
        ${body}
      </div>`;
    wireNav(wrap);
    return wrap;
  }

  function navLinks(active) {
    const items = [['privacy', 'privacyTitle'], ['terms', 'termsTitle'], ['how', 'howTitle'], ['contact', 'contactTitle']];
    return items.map(([k, label]) => `<button type="button" class="doc-nav-link ${k === active ? 'active' : ''}" data-page="${k}">${I18n.t(label)}</button>`).join('');
  }
  function wireNav(root) {
    root.querySelectorAll('[data-page]').forEach((b) => { b.onclick = () => go(b.dataset.page); });
  }

  // --- Contact form -----------------------------------------------------------------
  function renderContact() {
    const user = State.get().user;
    const wrap = document.createElement('div');
    wrap.className = 'doc-page';
    wrap.innerHTML = `
      <div class="doc-nav">${navLinks('contact')}</div>
      <div class="card doc-card">
        <h1 style="display:flex; align-items:center; gap:10px;">${UI.icon('mail', '', 26)} <span>${I18n.t('contactTitle')}</span></h1>
        <p class="text-muted">${I18n.t('contactIntro')}</p>
        <div id="contact-msg"></div>
        <form id="contact-form" novalidate>
          <div class="form-grid">
            <div class="field">
              <label for="ct-name">${I18n.t('contactName')}</label>
              <input id="ct-name" type="text" maxlength="120" autocomplete="name" value="${UI.escapeHtml(user ? (user.full_name || '') : '')}" />
            </div>
            <div class="field">
              <label for="ct-email">${I18n.t('contactEmail')}</label>
              <input id="ct-email" type="email" maxlength="200" autocomplete="email" dir="ltr" value="${UI.escapeHtml(user ? (user.email || user.username) : '')}" />
            </div>
          </div>
          <div class="field">
            <label for="ct-category">${I18n.t('contactCategory')}</label>
            <select id="ct-category">
              <option value="INQUIRY">${I18n.t('contactCatInquiry')}</option>
              <option value="TECHNICAL">${I18n.t('contactCatTechnical')}</option>
              <option value="SUGGESTION">${I18n.t('contactCatSuggestion')}</option>
              <option value="OTHER">${I18n.t('contactCatOther')}</option>
            </select>
          </div>
          <div class="field">
            <label for="ct-subject">${I18n.t('contactSubject')}</label>
            <input id="ct-subject" type="text" maxlength="200" />
          </div>
          <div class="field">
            <label for="ct-message">${I18n.t('contactMessage')}</label>
            <textarea id="ct-message" rows="6" maxlength="5000"></textarea>
            <div class="text-muted text-xs mt-1" id="ct-count">0 / 5000</div>
          </div>
          <div class="hp-field" aria-hidden="true"><label>Website <input id="ct-website" type="text" tabindex="-1" autocomplete="off" /></label></div>
          <div class="alert alert-warning" style="margin-block:8px;">${UI.icon('shieldAlert', '', 16)} <span>${I18n.t('contactNoEvidenceWarning')}</span></div>
          <button type="submit" class="btn btn-primary btn-neon" id="ct-send">${UI.icon('mail', '', 16)} <span>${I18n.t('contactSend')}</span></button>
        </form>
      </div>`;
    wireNav(wrap);
    const msgBox = wrap.querySelector('#contact-msg');
    const form = wrap.querySelector('#contact-form');
    const area = wrap.querySelector('#ct-message');
    area.addEventListener('input', () => { wrap.querySelector('#ct-count').textContent = `${area.value.length} / 5000`; });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const v = (id) => wrap.querySelector(id).value.trim();
      const data = {
        name: v('#ct-name'), email: v('#ct-email'), category: v('#ct-category'),
        subject: v('#ct-subject'), message: v('#ct-message'), website: v('#ct-website'),
      };
      const fail = (t) => { msgBox.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 16)} <span>${UI.escapeHtml(t)}</span></div>`; msgBox.scrollIntoView({ block: 'nearest' }); };
      msgBox.innerHTML = '';
      if (data.name.length < 2) return fail(I18n.t('contactErrName'));
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(data.email)) return fail(I18n.t('contactErrEmail'));
      if (data.subject.length < 3) return fail(I18n.t('contactErrSubject'));
      if (data.message.length < 10) return fail(I18n.t('contactErrMessage'));
      const btn = wrap.querySelector('#ct-send');
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span> <span>${I18n.t('contactSending')}</span>`;
      try {
        const res = await Api.sendContact(data);
        form.reset();
        wrap.querySelector('#ct-count').textContent = '0 / 5000';
        msgBox.innerHTML = `<div class="alert alert-success">${UI.icon('check', '', 16)} <div><strong>${I18n.t('contactSentTitle')}</strong><div class="text-sm">${res.emailed ? I18n.t('contactSentEmailed') : I18n.t('contactSentStored')}</div></div></div>`;
        msgBox.scrollIntoView({ block: 'nearest' });
      } catch (err) {
        fail(UI.errorMessage(err));
      }
      btn.disabled = false;
      btn.innerHTML = `${UI.icon('mail', '', 16)} <span>${I18n.t('contactSend')}</span>`;
    });
    return wrap;
  }

  function render(name) {
    if (name === 'contact') return renderContact();
    return renderDoc(name);
  }

  function go(name) {
    try { history.replaceState(null, '', '#/' + name); } catch (e) { /* ignore */ }
    State.set({ route: { name } });
    window.scrollTo(0, 0);
  }

  function footer() {
    const el = document.createElement('footer');
    el.className = 'site-footer';
    el.innerHTML = `
      <div class="footer-links">
        <button type="button" class="footer-link" data-page="privacy">${I18n.t('privacyTitle')}</button>
        <button type="button" class="footer-link" data-page="terms">${I18n.t('termsTitle')}</button>
        <button type="button" class="footer-link" data-page="how">${I18n.t('howTitle')}</button>
        <button type="button" class="footer-link" data-page="contact">${I18n.t('contactTitle')}</button>
      </div>
      <div class="footer-note">${I18n.t('footerNote')}</div>`;
    el.querySelectorAll('[data-page]').forEach((b) => { b.onclick = () => go(b.dataset.page); });
    return el;
  }

  const PUBLIC = ['privacy', 'terms', 'how', 'contact'];
  return { render, footer, go, PUBLIC };
})();
