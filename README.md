# NOIR Store — Full Stack

## متطلبات التشغيل
- Python 3.8+ (مثبت افتراضياً على macOS/Linux)
- لا توجد مكتبات خارجية — stdlib فقط

## تشغيل المتجر

```bash
cd noir-store
python3 server.py
```

ثم افتح المتصفح على:

| الرابط | الوصف |
|--------|-------|
| http://localhost:8000 | المتجر الرئيسي |
| http://localhost:8000/admin | لوحة الإدارة |
| http://localhost:8000/api/products | API المنتجات |
| http://localhost:8000/api/stats | الإحصائيات |

## كلمة المرور
```
noir2026
```

## هيكل الملفات
```
noir-store/
├── server.py          ← الخادم الكامل (Python)
├── noir.db            ← قاعدة البيانات (تُنشأ تلقائياً)
├── uploads/           ← صور المنتجات المرفوعة
└── static/
    ├── index.html     ← المتجر الرئيسي
    └── admin.html     ← لوحة الإدارة
```

## API Endpoints

### المنتجات
- `GET  /api/products`              — كل المنتجات
- `GET  /api/products?category=بدل` — فلترة بالفئة
- `GET  /api/products/:id`          — منتج واحد
- `POST /api/products`              — إضافة منتج
- `PUT  /api/products/:id`          — تعديل منتج
- `DELETE /api/products/:id`        — حذف (soft delete)

### رفع الصور
- `POST /api/upload`  — multipart أو base64 JSON

### الطلبات
- `GET  /api/orders`       — كل الطلبات
- `POST /api/orders`       — طلب جديد
- `PUT  /api/orders/:id`   — تحديث الحالة

### متفرقات
- `GET  /api/stats`        — إحصائيات عامة
- `GET  /api/settings`     — الإعدادات
- `POST /api/settings`     — حفظ الإعدادات
- `POST /api/auth/login`   — تسجيل الدخول

## العملات
- الأسعار تُخزَّن بالدينار الأردني (JOD)
- تحويل تلقائي للجنيه المصري (EGP) بمعدل قابل للتعديل
- المعدل الافتراضي: 1 د.أ = 40 ج.م
