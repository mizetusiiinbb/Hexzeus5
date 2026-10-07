# ZEUS Auto Deployer

این پروژه تمام قابلیت‌های قبلی Deployer را نگه می‌دارد و یک مسیر Cloudflare-native هم اضافه می‌کند.

## هدف
کاربر نهایی فقط **Cloudflare API Token** را وارد می‌کند. Deployer:

1. توکن را verify می‌کند.
2. اولین Cloudflare Account قابل دسترس را پیدا می‌کند.
3. یک D1 جدید می‌سازد و ID واقعی آن را نگه می‌دارد.
4. سورس واقعی ZEUS را مستقیم از GitHub دریافت می‌کند.
5. قبل از استقرار، سورس را با یک obfuscation/minification محافظه‌کارانه و semantics-preserving پردازش می‌کند؛ سپس artifact نهایی را روی Worker آپلود می‌کند. رشته‌ها، template literalها، regexها، importها و identifierها عمداً بازنویسی نمی‌شوند تا قابلیت‌های ZEUS و integrity checks خراب نشوند.
6. binding واقعی `DB` را وصل می‌کند.
7. `workers.dev` را فعال می‌کند.
8. URL نهایی پنل را برمی‌گرداند.
9. اگر مرحله deploy شکست بخورد، D1 ساخته‌شده در صورت امکان پاک می‌شود.

## Cloudflare-native
نسخه Python Worker با FastAPI/ASGI قابل اجرا روی Cloudflare Workers است. Cloudflare به‌صورت رسمی FastAPI و Python Workers را پشتیبانی می‌کند.

## توجه درباره GitHub
برای اینکه کاربر نهایی فقط Cloudflare Token بدهد، برنامه از GitHub عمومی ZEUS به‌صورت read-only سورس را می‌گیرد؛ GitHub Token لازم نیست. این با «Cloudflare Git Integration» که نیاز به اتصال GitHub حساب کاربر دارد متفاوت است.


## Build-time Obfuscation

هر Deploy قبل از Upload یک build step اجباری دارد. این مرحله:

- کامنت‌های غیرلازم و whitespace اضافی را حذف می‌کند.
- string/template/regex/import و identifierهای حساس را دستکاری نمی‌کند.
- anti-debug loop یا dead-code مخرب تزریق نمی‌کند.
- وجود `export default` و `env.DB` و نبود placeholder را بررسی می‌کند.
- فقط artifact نهاییِ پردازش‌شده را به Cloudflare Upload API می‌دهد.

این روش عمداً محافظه‌کارانه است؛ obfuscation تهاجمی روی کد ZEUS می‌تواند integrity/runtime آن را بشکند.
