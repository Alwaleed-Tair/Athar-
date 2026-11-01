# التشغيل والاختبار محلياً (Windows)

## 1) تنزيل المشروع
```bash
git clone --branch claude/amazing-mccarthy-ivh0hk https://github.com/Alwaleed-Tair/Athar-.git
cd Athar-
```

## 2) التثبيت
```bash
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
```

## 3) الإعداد (ملف backend\.env)
```bash
copy .env.example backend\.env
```
عدّل في `backend\.env` السطور التالية فقط للتجربة المحلية:
```
ATHAR_ADMIN_PASSWORD=Adm1n!Local#2026
ATHAR_MAIL_CONSOLE=1
```
`ATHAR_MAIL_CONSOLE=1` يطبع روابط التفعيل واستعادة كلمة المرور في نافذة الأوامر بدل إرسالها بالبريد.
(اختياري: `ATHAR_AI_KEY` لتجربة الذكاء الاصطناعي.)

## 4) التشغيل
```bash
python run.py
```
افتح http://localhost:8000 (الدخول: admin + كلمة المرور أعلاه).

## 5) الاختبارات الآلية
```bash
pip install pytest httpx
cd backend
python -m pytest tests
```

## 6) قائمة الاختبار اليدوي
- [ ] تسجيل حساب جديد ← يظهر «تحقق من بريدك» ← انسخ الرابط من نافذة الأوامر ← يُفعَّل الحساب ← الدخول.
- [ ] «نسيت كلمة المرور» ← رابط من نافذة الأوامر ← كلمة جديدة ← الدخول بها.
- [ ] حسابي: تعديل الاسم واسم المستخدم، تغيير كلمة المرور.
- [ ] إنشاء قضية، رفع صورة (EXIF) ومستند PDF/Word ومحادثة واتساب .txt.
- [ ] فتح المحادثة: الرسائل، البحث داخلها، الإحصاءات.
- [ ] تعديل دليل ثم حذفه (مع التأكيد) والتأكد من اختفائه من القائمة والبحث والخريطة.
- [ ] «التحقق من سلامة الملف» ثم تعديل الملف يدوياً داخل backend\storage\evidence والتحقق مرة أخرى (يجب أن يظهر عدم تطابق).
- [ ] خريطة الأدلة، تبويب البحث (كلمات + الأدلة المرتبطة).
- [ ] التقرير القانوني PDF بالعربية والإنجليزية.
- [ ] حسابان: لا يرى أحدهما قضية الآخر؛ مشاركة قضية بالبريد.
- [ ] الصفحات: الخصوصية، الاستخدام، كيف يعمل التحليل، التواصل (وفي حساب admin: رسائل التواصل في شاشة المستخدمين).
- [ ] الجوال: افتح الموقع من هاتفك على نفس الشبكة عبر http://عنوان-جهازك:8000 (شغّل بـ `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` من مجلد backend).
- [ ] حذف حساب تجريبي.

## 7) النشر على Render (بعد تأكيدك)
راجع `render.yaml` وقسم النشر في README. الإعدادات الإلزامية: قرص دائم، `ATHAR_STORAGE_DIR`, `ATHAR_JWT_SECRET`, `ATHAR_ADMIN_PASSWORD`, `ATHAR_PUBLIC_URL`.
