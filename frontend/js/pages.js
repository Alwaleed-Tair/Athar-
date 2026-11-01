// Public information pages (privacy, terms of use, how analysis works),
// the contact form, and the site footer. These are reachable WITHOUT signing
// in and from the footer of every screen. The text below describes what the
// platform really does today; if behaviour changes, update it here.
const Pages = (() => {
  const CONTENT = {
    privacy: {
      en: {
        title: 'Privacy Policy',
        updated: 'Last updated: 1 November 2026',
        sections: [
          { h: '1. What data ATHAR collects', list: [
            'Account data: your name, e-mail address (used to sign in and to verify the account) and a salted PBKDF2 hash of your password. The password itself is never stored.',
            'Case and evidence data that you enter or upload: case details, evidence files, their SHA-256 hashes, titles and descriptions, EXIF metadata, text extracted from documents, and messages parsed from chat exports.',
            'The audit log (chain of custody): who did what and when - sign-ins, failed sign-ins, uploads, views, downloads, edits, deletions, analyses and report exports - together with file names and hashes. It does not store IP addresses.',
            'Messages you send through the contact form (name, e-mail, subject, message).',
            'In your browser: a sign-in token, your language/theme choice and a list of notifications you have already seen, kept in local storage. ATHAR does not use advertising or tracking cookies.',
          ]},
          { h: '2. How evidence and files are stored and processed', list: [
            'Uploaded files are stored on the server that hosts ATHAR, exactly as received. The application does not encrypt files at rest; protection relies on access control, on the hosting provider\'s infrastructure security and on the encryption of the connection (HTTPS) where the host provides it.',
            'ATHAR reads files only to compute their SHA-256, extract metadata/text and parse conversations. Processing never modifies the original file: the hash is re-checked before downloads and analyses, and again after AI processing.',
          ]},
          { h: '3. Who can access your data', list: [
            'Only members of a case can open that case and its evidence. Every request is checked on the server. A case you are not a member of looks exactly as if it does not exist.',
            'The case owner (its creator) can share the case with another verified user by typing that person\'s exact e-mail address. They can remove members again. Search, similarity and cross-case alerts only ever use cases you are a member of.',
            'Platform administrators manage accounts (create users, activate accounts, reset passwords) and read contact-form messages. Being an administrator does NOT give access to other users\' cases or evidence; an administrator sees a case only if its owner added them as a member, and that is recorded in the case\'s audit log.',
            'Technical exception: the people who operate the server and database (the hosting provider and the operator of this deployment) can technically reach stored files and the database. Use ATHAR only if you trust the operator of the deployment you are using.',
          ]},
          { h: '4. Third-party services', list: [
            'AI provider: when AI features are enabled and they run (when you trigger them, automatically on the case Overview screen the first time it is opened, and on the Evidence map screen each time it is opened), extracted text, chat messages (a sample for long chats), image descriptions, image content (for authenticity triage and descriptions), file names, hashes, EXIF details and case names are sent to the configured AI provider (DeepSeek by default) for processing. If no AI key is configured, nothing is sent and the features are disabled.',
            'E-mail provider: when e-mail is configured, your e-mail address and the verification link are sent through the operator\'s SMTP provider.',
            'Do not upload evidence you are not allowed to process with such providers.',
          ]},
          { h: '5. Retention and deletion', list: [
            'Deleting evidence removes it immediately from lists, search, maps, reports and AI inputs, and removes the text, parsed messages and AI results derived from it. The stored file and its hash are kept for 30 days (the default retention period, set by the operator) so mistakes can be recovered and custody can be proven, then the file is permanently deleted.',
            'The audit log is append-only and is never edited or deleted, because its purpose is to prove what happened. It will therefore still show that an item existed and was deleted, with its name and hash.',
            'Deleting a case archives it (hides it from everyone); its evidence and audit log are kept under the same rules.',
            'There is no self-service account deletion yet. To ask for access to, correction of or deletion of your personal data, use the Contact page; requests are handled by the operator, subject to the audit-log rule above.',
          ]},
          { h: '6. Security measures', list: [
            'Passwords are hashed with salted PBKDF2-SHA256; sign-in attempts are rate-limited; accounts must verify their e-mail before use; changing a password ends all other sessions.',
            'Uploads are checked for blocked executable types, mismatched content and size limits. File content shown on screen is always treated as plain text.',
            'No system is perfectly secure. If you believe your account or data is affected, contact the operator immediately.',
          ]},
        ],
      },
      ar: {
        title: 'سياسة الخصوصية',
        updated: 'آخر تحديث: 1 نوفمبر 2026',
        sections: [
          { h: '١. البيانات التي تجمعها أثر', list: [
            'بيانات الحساب: اسمك وبريدك الإلكتروني (لتسجيل الدخول وتفعيل الحساب) ونسخة مشفّرة (PBKDF2 مع ملح عشوائي) من كلمة المرور. كلمة المرور نفسها لا تُحفظ أبداً.',
            'بيانات القضايا والأدلة التي تُدخلها أو ترفعها: تفاصيل القضية وملفات الأدلة وبصمات SHA-256 والعناوين والأوصاف وبيانات EXIF والنصوص المستخرجة من المستندات والرسائل المحلَّلة من ملفات المحادثات.',
            'سجل التدقيق (سلسلة العهدة): من فعل ماذا ومتى - تسجيل الدخول ومحاولاته الفاشلة والرفع والاطلاع والتنزيل والتعديل والحذف والتحليل وتصدير التقارير - مع أسماء الملفات وبصماتها. لا يُسجَّل عنوان IP.',
            'الرسائل التي ترسلها عبر نموذج التواصل (الاسم والبريد والعنوان والرسالة).',
            'في متصفحك: رمز تسجيل الدخول واختيارك للغة والمظهر وقائمة التنبيهات التي شاهدتها، محفوظة في التخزين المحلي. لا تستخدم أثر ملفات تعريف ارتباط للإعلانات أو التتبع.',
          ]},
          { h: '٢. كيف تُخزَّن الأدلة وتُعالَج', list: [
            'تُخزَّن الملفات المرفوعة كما استُلمت على الخادم الذي يستضيف أثر. التطبيق لا يشفّر الملفات أثناء التخزين؛ الحماية تعتمد على ضوابط الوصول وأمن بنية الاستضافة وتشفير الاتصال (HTTPS) حيث توفره الاستضافة.',
            'تقرأ أثر الملفات فقط لحساب بصمة SHA-256 واستخراج البيانات الوصفية والنصوص وتحليل المحادثات. المعالجة لا تعدّل الملف الأصلي أبداً: تُفحص البصمة قبل التنزيل والتحليل، وتُفحص مرة أخرى بعد معالجة الذكاء الاصطناعي.',
          ]},
          { h: '٣. من يستطيع الوصول إلى بياناتك', list: [
            'أعضاء القضية فقط يستطيعون فتحها والاطلاع على أدلتها. كل طلب يُفحص في الخادم، والقضية التي لست عضواً فيها تبدو تماماً كأنها غير موجودة.',
            'مالك القضية (منشئها) يستطيع مشاركتها مع مستخدم موثَّق بكتابة بريده الإلكتروني بدقة، ويستطيع إزالة الأعضاء. البحث والتشابه وتنبيهات القضايا المتقاطعة تستخدم دائماً القضايا التي أنت عضو فيها فقط.',
            'مسؤولو المنصة يديرون الحسابات (إنشاء المستخدمين وتفعيل الحسابات وإعادة تعيين كلمات المرور) ويقرؤون رسائل نموذج التواصل. صفة المسؤول لا تمنح الاطلاع على قضايا المستخدمين الآخرين وأدلتهم؛ المسؤول يرى القضية فقط إذا أضافه مالكها عضواً، ويُسجَّل ذلك في سجل تدقيق القضية.',
            'استثناء تقني: من يشغّلون الخادم وقاعدة البيانات (مزوّد الاستضافة ومشغّل هذه النسخة) يستطيعون تقنياً الوصول إلى الملفات المخزّنة وقاعدة البيانات. استخدم أثر فقط إذا كنت تثق بمشغّل النسخة التي تستخدمها.',
          ]},
          { h: '٤. خدمات الأطراف الثالثة', list: [
            'مزوّد الذكاء الاصطناعي: عند تفعيل ميزات الذكاء الاصطناعي وتشغيلها (عند تشغيلها منك، أو تلقائياً في شاشة النظرة العامة عند أول فتح لها، وفي شاشة خريطة الأدلة عند كل فتح لها)، تُرسَل النصوص المستخرجة ورسائل المحادثات (عينة منها للمحادثات الطويلة) ووصف الصور ومحتوى الصور (لفحص الأصالة والوصف) وأسماء الملفات والبصمات وتفاصيل EXIF وأسماء القضايا إلى مزوّد الذكاء الاصطناعي المضبوط (DeepSeek افتراضياً) لمعالجتها. إذا لم يُضبط مفتاح الذكاء الاصطناعي فلا يُرسل شيء وتبقى الميزات معطّلة.',
            'مزوّد البريد: عند ضبط البريد الإلكتروني يُرسَل بريدك ورابط التفعيل عبر خادم SMTP الخاص بالمشغّل.',
            'لا ترفع أدلة غير مسموح لك بمعالجتها لدى هذه الجهات.',
          ]},
          { h: '٥. الاحتفاظ بالبيانات وحذفها', list: [
            'حذف الدليل يزيله فوراً من القوائم والبحث والخرائط والتقارير ومدخلات الذكاء الاصطناعي، ويحذف النص والرسائل المحلَّلة ونتائج الذكاء الاصطناعي المشتقة منه. أما الملف المخزّن وبصمته فيُحتفظ بهما 30 يوماً (مدة الاحتفاظ الافتراضية التي يحددها المشغّل) لإمكان التراجع عن الأخطاء وإثبات العهدة، ثم يُحذف الملف نهائياً.',
            'سجل التدقيق للإضافة فقط ولا يُعدَّل أو يُحذف، لأن غرضه إثبات ما حدث. لذلك سيبقى يُظهر أن العنصر وُجد ثم حُذف مع اسمه وبصمته.',
            'حذف القضية يؤرشفها (يخفيها عن الجميع)، وتبقى أدلتها وسجلها بنفس القواعد.',
            'لا يوجد حتى الآن حذف ذاتي للحساب. لطلب الاطلاع على بياناتك الشخصية أو تصحيحها أو حذفها استخدم صفحة التواصل؛ يعالج المشغّل الطلبات مع مراعاة قاعدة سجل التدقيق أعلاه.',
          ]},
          { h: '٦. إجراءات الأمان', list: [
            'تُشفَّر كلمات المرور بـ PBKDF2-SHA256 مع ملح، وتُقيَّد محاولات الدخول، ويجب تفعيل البريد قبل استخدام الحساب، وتغيير كلمة المرور ينهي كل الجلسات الأخرى.',
            'تُفحص الملفات المرفوعة لمنع الأنواع التنفيذية وعدم تطابق المحتوى والحجم المفرط. وأي محتوى ملف يُعرض على الشاشة يُعامل دائماً كنص عادي.',
            'لا يوجد نظام آمن تماماً. إذا اعتقدت أن حسابك أو بياناتك تأثرت فتواصل مع المشغّل فوراً.',
          ]},
        ],
      },
    },
    terms: {
      en: {
        title: 'Terms of Use',
        updated: 'Last updated: 1 November 2026',
        sections: [
          { h: '1. Purpose', list: [
            'ATHAR helps authorised investigators, lawyers and forensic examiners register digital evidence, keep a tamper-evident record of who handled it, extract metadata and text, read chat exports, and find links between items.',
            'It is a decision-support tool. It does not replace legal procedure, a certified forensic laboratory, or professional judgement.',
          ]},
          { h: '2. Who may use it and how', list: [
            'Use ATHAR only for evidence you are lawfully entitled to hold and process, and only for lawful investigative, legal or educational purposes.',
            'Do not upload malware, attempt to access other users\' data, probe or overload the service, or use it to harass or unlawfully surveil anyone.',
            'You are responsible for keeping your password confidential and for everything done under your account. Report suspected misuse to the operator.',
          ]},
          { h: '3. AI-assisted analysis', list: [
            'AI features (case summaries, correlations, conversation summaries, authenticity triage and image descriptions) are produced by a third-party language/vision model. They are automated estimates that help you look in the right place.',
            'They are not a legal finding, not proof, and not an expert opinion. They can be wrong, incomplete or biased, and may miss relationships or invent connections. Authenticity triage is a rough, low-confidence hint and is not a reliable deepfake detector.',
            'Always verify AI output against the original evidence before relying on it, quoting it, or presenting it to others. ATHAR labels AI content as an estimate in the interface and in reports.',
            'What a document or chat says is a claim made by its author. ATHAR shows it as written and does not verify that it is true.',
          ]},
          { h: '4. Accuracy limits', list: [
            'Hash checks, EXIF extraction and text/conversation parsing are deterministic, but depend on the file: scanned documents and images contain no extractable text (there is no OCR); EXIF can be absent or forged; chat timestamps carry no time zone and some formats have an ambiguous day/month order.',
            'The chain-of-custody log is tamper-evident: it reveals edits to existing records and removed records. It cannot by itself prove who held a file before it was uploaded, and an operator with full database access could in principle rebuild the whole log.',
          ]},
          { h: '5. Availability and changes', list: [
            'The service is provided "as is", without a guarantee of availability or of any particular result. Features may change. Back up evidence you cannot afford to lose.',
          ]},
          { h: '6. Contact', list: ['Questions about these terms: use the Contact page.'] },
        ],
      },
      ar: {
        title: 'سياسة الاستخدام',
        updated: 'آخر تحديث: 1 نوفمبر 2026',
        sections: [
          { h: '١. الغرض', list: [
            'تساعد أثر المحققين والمحامين وخبراء الأدلة الرقمية المصرّح لهم على تسجيل الأدلة الرقمية، والاحتفاظ بسجل يكشف أي تلاعب لمن تداولها، واستخراج البيانات الوصفية والنصوص، وقراءة ملفات المحادثات، وإيجاد الروابط بين العناصر.',
            'هي أداة مساندة للقرار، ولا تحل محل الإجراءات القانونية أو المختبر الجنائي المعتمد أو الحكم المهني.',
          ]},
          { h: '٢. من يستخدمها وكيف', list: [
            'استخدم أثر فقط لأدلة يحق لك قانوناً حيازتها ومعالجتها، ولأغراض تحقيقية أو قانونية أو تعليمية مشروعة فقط.',
            'لا ترفع برمجيات خبيثة، ولا تحاول الوصول إلى بيانات مستخدمين آخرين، ولا تختبر الخدمة أو تثقلها، ولا تستخدمها لمضايقة أحد أو مراقبته بصورة غير مشروعة.',
            'أنت مسؤول عن سرية كلمة مرورك وعن كل ما يتم عبر حسابك. بلّغ المشغّل عن أي اشتباه بإساءة الاستخدام.',
          ]},
          { h: '٣. التحليل المدعوم بالذكاء الاصطناعي', list: [
            'ميزات الذكاء الاصطناعي (ملخصات القضايا والارتباطات وملخصات المحادثات وفرز الأصالة ووصف الصور) يولّدها نموذج لغوي/بصري من طرف ثالث. هي تقديرات آلية تساعدك على معرفة أين تنظر.',
            'هي ليست حكماً قانونياً ولا إثباتاً ولا رأي خبير. قد تكون خاطئة أو ناقصة أو متحيزة، وقد تفوّت علاقات أو تختلق روابط. وفرز الأصالة مجرد مؤشر تقريبي منخفض الثقة وليس كاشفاً موثوقاً للتزييف العميق.',
            'تحقق دائماً من مخرجات الذكاء الاصطناعي بالرجوع إلى الدليل الأصلي قبل الاعتماد عليها أو الاستشهاد بها أو عرضها على الآخرين. وتوسم أثر محتوى الذكاء الاصطناعي بأنه تقدير في الواجهة وفي التقارير.',
            'ما يقوله المستند أو المحادثة هو ادعاء صاحبه. تعرضه أثر كما كُتب ولا تتحقق من صحته.',
          ]},
          { h: '٤. حدود الدقة', list: [
            'فحوص البصمة واستخراج EXIF وتحليل النصوص والمحادثات حتمية، لكنها تعتمد على الملف: المستندات الممسوحة ضوئياً والصور لا تحتوي نصاً قابلاً للاستخراج (لا يوجد OCR)؛ وقد يغيب EXIF أو يُزوَّر؛ وأوقات المحادثات بلا منطقة زمنية، وبعض الصيغ يكون ترتيب اليوم/الشهر فيها غامضاً.',
            'سجل سلسلة العهدة يكشف التلاعب: يُظهر تعديل السجلات الموجودة وحذف السجلات. لكنه لا يثبت بذاته من حاز الملف قبل رفعه، ويمكن نظرياً لمشغّل يملك صلاحية كاملة على قاعدة البيانات إعادة بناء السجل بأكمله.',
          ]},
          { h: '٥. التوفر والتغييرات', list: [
            'تُقدَّم الخدمة «كما هي» دون ضمان للتوفر أو لنتيجة معينة. قد تتغير الميزات. احتفظ بنسخة احتياطية من الأدلة التي لا تحتمل فقدانها.',
          ]},
          { h: '٦. التواصل', list: ['للاستفسار عن هذه الشروط استخدم صفحة التواصل.'] },
        ],
      },
    },
    how: {
      en: {
        title: 'How analysis works',
        updated: 'From upload to report - what happens to your evidence at each step.',
        steps: [
          { h: 'Upload and registration', p: 'The file is streamed to storage while its SHA-256 hash is computed at the same time. The name is cleaned, executable types are refused, the content must match its extension, and the size is limited. The hash and an "uploaded" event are written to the chain of custody. The original is never changed afterwards.' },
          { h: 'Extraction (deterministic)', p: 'Images: EXIF metadata (camera, capture time, software). Text files, PDF and Word: full text. Chat exports (WhatsApp text, Telegram/Instagram JSON, CSV, and chats inside PDF/Word): each message is parsed into sender, time and text, with its exact source position (line, page or row). Scanned pages and screenshots have no extractable text - ATHAR has no OCR - so they are only described by the optional AI vision step.' },
          { h: 'Integrity checks', p: 'Before a file is downloaded or analysed ATHAR re-computes its SHA-256 and compares it with the value recorded at upload. If they differ the action is refused and the mismatch is logged. For AI analysis the hash is checked before and after, and both values are recorded.' },
          { h: 'Linking evidence (deterministic, explainable)', p: 'Items are linked when they share an identical hash, the same camera model, the same phone number / e-mail / IBAN / URL, the same chat participant, or similar wording (a lexical TF-IDF score - shared distinctive words, not meaning). Every link shows its exact reason. Only cases you are a member of are ever compared.' },
          { h: 'AI-assisted analysis (optional, labelled)', p: 'If an AI key is configured, extracted text, chat samples and image descriptions are sent to the AI provider to produce summaries, correlations and a rough authenticity triage. The evidence is passed as inert data, with instructions kept separate, and the model is told to ignore any instructions found inside evidence. Chat summaries must cite message numbers; points without a source are dropped. All AI output is marked as an automated estimate that needs human review.' },
          { h: 'Results and reports', p: 'The case page shows the facts and the estimates separately. The PDF report (Arabic or English) lists case details, every evidence item with its recorded and re-computed hash, extracted metadata, relationships, conversations, previously generated AI notes in a clearly marked amber section, the chain of custody and the method and its limits. Exporting a report never creates new AI conclusions.' },
          { h: 'Chain of custody', p: 'Every important action appends a record whose hash covers the previous record, so changing or removing an old record breaks the chain from that point. "Run verification" recomputes it and tells you the first broken record.' },
        ],
        limits: [
          'AI output can be wrong; treat it as a lead, not a conclusion.',
          'A clean EXIF or clean check does not prove a file is genuine.',
          'Chat times have no time zone; some formats have ambiguous day/month order (the viewer says when it assumed one).',
          'Lexical similarity does not understand synonyms or meaning.',
        ],
      },
      ar: {
        title: 'كيف يعمل التحليل',
        updated: 'من الرفع حتى التقرير - ما الذي يحدث لأدلتك في كل خطوة.',
        steps: [
          { h: 'الرفع والتسجيل', p: 'يُنقل الملف إلى التخزين وتُحسب بصمته SHA-256 في الوقت نفسه. يُنظَّف الاسم، وتُرفض الأنواع التنفيذية، ويجب أن يطابق المحتوى امتداد الملف، وتُقيَّد الحجم. تُكتب البصمة وحدث «رفع» في سلسلة العهدة. ولا يتغير الأصل بعد ذلك أبداً.' },
          { h: 'الاستخراج (حتمي)', p: 'الصور: بيانات EXIF (الكاميرا ووقت الالتقاط والبرنامج). الملفات النصية وPDF وWord: النص الكامل. ملفات المحادثات (نص واتساب وJSON لتيليجرام وإنستغرام وCSV والمحادثات داخل PDF/Word): تُحلَّل كل رسالة إلى مرسل ووقت ونص، مع موضعها الدقيق في المصدر (سطر أو صفحة أو صف). الصفحات الممسوحة ولقطات الشاشة لا نص قابلاً للاستخراج فيها - لا يوجد OCR في أثر - لذا تُوصف فقط عبر خطوة الرؤية بالذكاء الاصطناعي الاختيارية.' },
          { h: 'فحوص السلامة', p: 'قبل تنزيل أي ملف أو تحليله تعيد أثر حساب SHA-256 وتقارنه بالقيمة المسجلة عند الرفع. إذا اختلفتا يُرفض الإجراء ويُسجَّل عدم التطابق. وفي تحليل الذكاء الاصطناعي تُفحص البصمة قبله وبعده وتُسجَّل القيمتان.' },
          { h: 'ربط الأدلة (حتمي وقابل للتفسير)', p: 'تُربط العناصر عندما تشترك في بصمة متطابقة أو طراز كاميرا واحد أو رقم هاتف/بريد/IBAN/رابط واحد أو طرف محادثة واحد أو صياغة متشابهة (درجة TF-IDF لفظية - كلمات مميزة مشتركة وليس المعنى). كل رابط يعرض سببه الدقيق. ولا تُقارَن إلا القضايا التي أنت عضو فيها.' },
          { h: 'التحليل بالذكاء الاصطناعي (اختياري وموسوم)', p: 'إذا ضُبط مفتاح الذكاء الاصطناعي تُرسل النصوص المستخرجة وعينات المحادثات ووصف الصور إلى المزوّد لإنتاج ملخصات وارتباطات وفرز تقريبي للأصالة. تُمرَّر الأدلة كبيانات خاملة منفصلة عن التعليمات، ويُطلب من النموذج تجاهل أي تعليمات توجد داخل الأدلة. وملخصات المحادثات يجب أن تذكر أرقام الرسائل، وتُحذف أي نقطة بلا مصدر. وكل مخرجات الذكاء الاصطناعي موسومة بأنها تقدير آلي يحتاج مراجعة بشرية.' },
          { h: 'النتائج والتقارير', p: 'تعرض صفحة القضية الحقائق والتقديرات منفصلةً. ويتضمن تقرير PDF (عربي أو إنجليزي) بيانات القضية وكل دليل مع بصمته المسجلة والمحسوبة حديثاً، والبيانات الوصفية المستخرجة، والعلاقات، والمحادثات، وملاحظات الذكاء الاصطناعي المولَّدة سابقاً في قسم كهرماني واضح، وسلسلة العهدة، والمنهجية وحدودها. تصدير التقرير لا يولّد استنتاجات ذكاء اصطناعي جديدة.' },
          { h: 'سلسلة العهدة', p: 'كل إجراء مهم يضيف سجلاً تغطي بصمته السجل السابق، فأي تعديل أو حذف لسجل قديم يكسر السلسلة من تلك النقطة. زر «تشغيل التحقق» يعيد حسابها ويخبرك بأول سجل مكسور.' },
        ],
        limits: [
          'مخرجات الذكاء الاصطناعي قد تكون خاطئة؛ تعامل معها كخيط للبحث وليس كاستنتاج.',
          'خلو EXIF أو نجاح الفحص لا يثبت أن الملف أصلي.',
          'أوقات المحادثات بلا منطقة زمنية، وبعض الصيغ ترتيب اليوم/الشهر فيها غامض (يوضح العارض متى افترض ترتيباً).',
          'التشابه اللفظي لا يفهم المرادفات ولا المعنى.',
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
