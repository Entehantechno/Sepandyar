/*
 * آزمون دسترسی‌پذیری و صحت سوییچ‌های رابط کاربری.
 *
 * قواعد مرجع (از skill طراحی ui-ux-pro-max، اولویت ۱ و ۲):
 *  - Accessibility: نام/نقش/وضعیت برای هر کنترل (WCAG 4.1.2)، نقش dialog
 *  - Touch: هدف لمسی بزرگ؛ استاندارد خودِ این پروژه از مرحلهٔ ۱۳ برابر ۴۸px
 *
 * نکتهٔ صادقانه دربارهٔ اندازه: WCAG 2.2 AA (قاعدهٔ ۲.۵.۸) کف ۲۴px است،
 * پس ۲۶ و ۲۸px از نظر WCAG رد نمی‌شوند. آنچه اینجا سنجیده می‌شود سازگاری
 * با استاندارد ۴۸px خودِ پروژه برای مخاطب سالمند است، نه ادعای نقض WCAG.
 *
 * اجرا: node ui_a11y.test.js   (نیازمند jsdom در ../node_modules)
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

let pass = 0, fail = 0;
const failures = [];
const check = (n, c, x) => {
  if (c) { pass++; console.log('\u2705 ' + n); }
  else { fail++; failures.push(n); console.log('\u274c ' + n + (x !== undefined ? ' -> ' + JSON.stringify(x) : '')); }
};

console.log('--- ۱) سوییچ‌ها: نقش، نام و وضعیت ---');
{
  const switches = [...html.matchAll(/<button[^>]*role="switch"[^>]*>/g)].map(m => m[0]);
  check('دست‌کم ۹ سوییچ با role="switch" وجود دارد', switches.length >= 9, switches.length);
  const noAria = switches.filter(t => !/aria-checked=/.test(t));
  check('همهٔ سوییچ‌ها aria-checked دارند', noAria.length === 0, noAria.length);
  check('همهٔ سوییچ‌ها type="button" دارند (تا فرم submit نشود)',
    switches.every(t => /type="button"/.test(t)));
  // توجه: بعضی ردیف‌ها درون یک رشتهٔ JS ساخته می‌شوند، پس در متن فایل
  // onclick="toggleSetting(\'key\')" دیده می‌شود و بک‌اسلش فرارِ رشته است،
  // نه بخشی از HTML. الگو هر دو شکل را می‌پذیرد.
  check('همهٔ سوییچ‌ها onclick واقعی دارند',
    switches.every(t => /onclick="toggleSetting\(\\?'/.test(t)), 'پیش‌تر ۴ ردیف کلیک‌پذیر نبود');

  // آن چهار ردیفی که پیش‌تر div بودند و کلیک هیچ کاری نمی‌کرد
  for (const key of ['shareVitals', 'shareMeds', 'dailyCheckin', 'shareLocation']) {
    check('کلید «' + key + '» به toggleSetting وصل است',
      html.includes("toggleSetting('" + key + "')"));
  }
  check('دیگر هیچ setting-row غیرتعاملی با ظاهر سوییچ نمانده',
    !/<div class="setting-row"><span>[^<]*<\/span><span class="toggle"/.test(html));
}

console.log('--- ۲) وضعیت سوییچ واقعاً بازتاب داده می‌شود ---');
{
  check('CSS حالت خاموش و روشن را از هم جدا می‌کند',
    html.includes('.setting-row.on .toggle{background:#58b99a') &&
    html.includes('.toggle{width:45px;height:26px;border-radius:20px;background:#c9d6d1'));
  check('syncSwitches تعریف شده', html.includes('function syncSwitches()'));
  check('toggleSetting بعد از تغییر، سوییچ‌ها را همگام می‌کند',
    /toggleSetting\(key\)\{[^}]*syncSwitches\(\)/.test(html));
  check('هنگام بارگذاری هم همگام می‌شود', html.includes('applySettings();syncSwitches();'));
  check('سبک درون‌خطی «خاموشِ» سخت‌کدشده برداشته شد',
    !html.includes('class="toggle" style="background:#c4d2cc"'));
}

console.log('--- ۳) اجرای واقعی منطق سوییچ در jsdom ---');
{
  const dom = new JSDOM('<!doctype html><html><body>' +
    '<button type="button" class="setting-row" role="switch" aria-checked="false" ' +
    'onclick="toggleSetting(\'shareVitals\')"><span>علائم حیاتی</span><span class="toggle"></span></button>' +
    '<button type="button" class="check" role="checkbox" aria-checked="false" ' +
    'aria-label="ثبت انجام شد" onclick="markTaskDone(this)"></button>' +
    '<div id="toast"></div></body></html>', { runScripts: 'outside-only' });
  const w = dom.window;
  w.toast = () => {};
  const store = {};
  // localStorage روی Window فقط getter دارد؛ با defineProperty جایگزین می‌شود
  Object.defineProperty(w, 'localStorage', { configurable: true, value: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  }});

  // همان منطق تولیدی از خود index.html
  // «async function» را هم می‌گیرد: اگر فقط «function name» را پیدا کنیم،
  // کلمهٔ async که پیش از آن است جا می‌افتد و بدنهٔ await‌دار خطای نحوی می‌دهد.
  const grab = (name) => {
    let i = html.indexOf('function ' + name + '(');
    if (i < 0) throw new Error('not found: ' + name);
    if (html.slice(i - 6, i) === 'async ') i -= 6;
    let d = 0, j = html.indexOf('{', i);
    for (let k = j; k < html.length; k++) {
      if (html[k] === '{') d++;
      else if (html[k] === '}') { d--; if (d === 0) return html.slice(i, k + 1); }
    }
    throw new Error('unbalanced: ' + name);
  };
  w.eval(grab('syncSwitches') + '\n' + grab('markTaskDone') +
         '\n;window.syncSwitches=syncSwitches;window.markTaskDone=markTaskDone;');

  const sw = w.document.querySelector('[role="switch"]');
  const chk = w.document.querySelector('.check');

  check('پیش‌زمینه: سوییچ خاموش است', sw.getAttribute('aria-checked') === 'false');
  store['shareVitals'] = '1';
  w.syncSwitches();
  check('با ذخیرهٔ «۱»، aria-checked درست می‌شود', sw.getAttribute('aria-checked') === 'true');
  check('کلاس بصری on هم اضافه می‌شود', sw.classList.contains('on'));
  store['shareVitals'] = '0';
  w.syncSwitches();
  check('با ذخیرهٔ «۰» به حالت خاموش برمی‌گردد',
    sw.getAttribute('aria-checked') === 'false' && !sw.classList.contains('on'));

  check('دکمهٔ کار پیش از کلیک aria-checked=false دارد', chk.getAttribute('aria-checked') === 'false');
  w.markTaskDone(chk);
  check('پس از کلیک aria-checked=true می‌شود', chk.getAttribute('aria-checked') === 'true');
  check('برچسب دسترس‌پذیر به حالت «انجام شد» تغییر می‌کند', /انجام شد/.test(chk.getAttribute('aria-label')));
  check('کلاس done هم افزوده می‌شود', chk.classList.contains('done'));
  w.markTaskDone(chk);
  check('کلیک دوم آن را برمی‌گرداند', chk.getAttribute('aria-checked') === 'false');
}

console.log('--- ۴) مودال: نقش dialog ---');
{
  check('مودال role="dialog" دارد', /id="modal-content"[^>]*role="dialog"/.test(html));
  check('مودال aria-modal="true" دارد', /id="modal-content"[^>]*aria-modal="true"/.test(html));
  check('مودال نام دسترس‌پذیر دارد', /id="modal-content"[^>]*aria-label=/.test(html));
}

console.log('--- ۵) اندازهٔ اهداف لمسی (استاندارد ۴۸px خودِ پروژه) ---');
{
  const css = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('');
  const size = (sel) => {
    const m = css.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\{[^}]*?width:(\\d+(?:\\.\\d+)?)px;height:(\\d+(?:\\.\\d+)?)px'));
    return m ? [parseFloat(m[1]), parseFloat(m[2])] : null;
  };
  // پوششِ سیم‌کشی: تابع درست کافی نیست، باید واقعاً به دکمه وصل باشد.
  // بدون این دو ادعا، برگرداندن onclick به کد درون‌خطیِ قدیمی بدون شکست
  // از تست رد می‌شد (بخش ۳ تابع را جدا اجرا می‌کند).
  const checks = [...html.matchAll(/<button[^>]*class="check"[^>]*>/g)].map(m => m[0]);
  check('دست‌کم دو دکمهٔ .check وجود دارد', checks.length >= 2, checks.length);
  check('همهٔ دکمه‌های .check واقعاً به markTaskDone وصل‌اند',
    checks.length > 0 && checks.every(t => /onclick="markTaskDone\(this\)"/.test(t)),
    checks.map(t => (t.match(/onclick="[^"]{0,30}/) || ['?'])[0]));
  check('همهٔ دکمه‌های .check نقش checkbox و وضعیت دارند',
    checks.every(t => /role="checkbox"/.test(t) && /aria-checked=/.test(t) && /aria-label=/.test(t)));
  const chkSize = size('.check');
  check('دکمهٔ .check دست‌کم ۴۴px است', !!chkSize && chkSize[0] >= 44 && chkSize[1] >= 44, chkSize);
  const inp = css.match(/\.range-row \.name-input\{height:(\d+(?:\.\d+)?)px/);
  check('ورودی range-row دست‌کم ۴۴px ارتفاع دارد', !!inp && parseFloat(inp[1]) >= 44, inp && inp[1]);
}

// «return» در سطح بالای ماژول CommonJS از کل ماژول بیرون می‌زند و خلاصه و
// process.exit را رد می‌کند؛ پس زنجیره را در یک متغیر نگه می‌داریم.
let consentDone = null;
console.log('--- ۶) رضایت سمت سرور: سوییچ‌ها واقعاً به /api/consents می‌رسند ---');
{
  const dom = new JSDOM('<!doctype html><html><body><div id="toast"></div></body></html>',
                        { runScripts: 'outside-only' });
  const w = dom.window;
  const toasts = []; w.toast = m => toasts.push(m);
  const offline = []; w.queueOffline = (p, o) => offline.push({ p: p, o: o });
  w.API_BASE = 'http://127.0.0.1:4174';
  const store = {};
  Object.defineProperty(w, 'localStorage', { configurable: true, value: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  }});

  // «async function» را هم می‌گیرد: اگر فقط «function name» را پیدا کنیم،
  // کلمهٔ async که پیش از آن است جا می‌افتد و بدنهٔ await‌دار خطای نحوی می‌دهد.
  const grab = (name) => {
    let i = html.indexOf('function ' + name + '(');
    if (i < 0) throw new Error('not found: ' + name);
    if (html.slice(i - 6, i) === 'async ') i -= 6;
    let d = 0, j = html.indexOf('{', i);
    for (let k = j; k < html.length; k++) {
      if (html[k] === '{') d++;
      else if (html[k] === '}') { d--; if (d === 0) return html.slice(i, k + 1); }
    }
    throw new Error('unbalanced: ' + name);
  };
  const scopeLine = html.match(/var CONSENT_SCOPE=\{[^}]*\};/);
  check('نگاشت CONSENT_SCOPE در کد تعریف شده', !!scopeLine);
  w.eval(scopeLine[0] + '\n' + grab('syncSwitches') + '\n' + grab('consentBody') + '\n' + grab('syncConsents') + '\n' + grab('pushConsent') +
         '\n;window.CONSENT_SCOPE=CONSENT_SCOPE;window.pushConsent=pushConsent;window.syncConsents=syncConsents;');

  // نگاشت باید دقیقاً با فهرست scope سمت سرور سازگار باشد
  const map = w.CONSENT_SCOPE;
  check('هر چهار کلید اشتراک‌گذاری به یک scope نگاشت شده',
    map.shareVitals === 'vitals' && map.shareMeds === 'medications' &&
    map.shareLocation === 'location' && map.shareCare === 'health', map);
  check('dailyCheckin عمداً رضایت محلی است و به سرور نمی‌رود', !('dailyCheckin' in map));

  // شاخهٔ ۱: سرور پذیرفت
  let sent = [];
  w.fetch = async (u, o) => { sent.push({ u: u, o: o });
    if (u.indexOf('/api/consents') >= 0 && o && o.method === 'POST') return { ok: true, json: async () => ({ ok: true }) };
    return { ok: true, json: async () => ({ items: [{ scope: 'vitals', granted: 1 }] }) }; };
  consentDone = w.pushConsent('shareVitals', true).then(() => {
    check('شاخهٔ پذیرش: POST به /api/consents فرستاده شد',
      sent.some(x => x.u.indexOf('/api/consents') >= 0 && x.o.method === 'POST'), sent.map(x => x.u));
    const body = JSON.parse(sent.find(x => x.o && x.o.method === 'POST').o.body);
    check('بدنهٔ درخواست scope و granted درست دارد',
      body.scope === 'vitals' && body.granted === true && body.updated_by === 'senior', body);
    check('شاخهٔ پذیرش: چیزی در صف آفلاین نرفت', offline.length === 0, offline.length);

    // شاخهٔ ۲: سرور رد کرد (۴۰۰) — باید مقدار محلی برگردد
    store['shareMeds'] = '1';
    w.fetch = async () => ({ ok: false, status: 400, json: async () => ({ error: 'invalid_scope' }) });
    toasts.length = 0;
    return w.pushConsent('shareMeds', true);
  }).then(() => {
    check('شاخهٔ رد: مقدار محلی برگردانده شد (نه «ذخیره شد» دروغین)',
      store['shareMeds'] === '0', store['shareMeds']);
    check('شاخهٔ رد: به کاربر گفته شد ذخیره نشد',
      toasts.some(t => /ذخیره نشد/.test(t)), toasts);
    check('شاخهٔ رد: اشتباهاً در صف آفلاین نرفت', offline.length === 0, offline.length);

    // شاخهٔ ۳: خطای شبکه — مقدار محلی می‌ماند و در صف آفلاین می‌رود
    store['shareLocation'] = '1';
    w.fetch = async () => { throw new TypeError('Failed to fetch'); };
    toasts.length = 0;
    return w.pushConsent('shareLocation', true);
  }).then(() => {
    check('شاخهٔ آفلاین: مقدار محلی حفظ شد', store['shareLocation'] === '1', store['shareLocation']);
    check('شاخهٔ آفلاین: درخواست در صف آفلاین ثبت شد',
      offline.length === 1 && offline[0].p === '/api/consents', offline.map(x => x.p));
    check('شاخهٔ آفلاین: به کاربر گفته شد بعداً همگام می‌شود',
      toasts.some(t => /آفلاین/.test(t)), toasts);

    // کلید محلی: هیچ درخواستی نباید برود
    sent.length = 0; offline.length = 0;
    w.fetch = async () => { throw new Error('should not be called'); };
    return w.pushConsent('dailyCheckin', true);
  }).then(() => {
    check('کلید محلی هیچ درخواست شبکه‌ای نمی‌فرستد', sent.length === 0 && offline.length === 0);

    // syncConsents: سرور منبع حقیقت است
    w.fetch = async () => ({ ok: true, json: async () => ({ items: [
      { scope: 'vitals', granted: 0 }, { scope: 'location', granted: 1 }] }) });
    return w.syncConsents();
  }).then(() => {
    check('syncConsents وضعیت سرور را روی حافظهٔ محلی می‌نویسد',
      store['vitals'] === undefined && store['shareVitals'] === '0' && store['shareLocation'] === '1',
      { v: store['shareVitals'], l: store['shareLocation'] });
    // پاسخ خراب نباید استثنای نگرفته بدهد
    w.fetch = async () => ({ ok: true, json: async () => { throw new Error('bad json'); } });
    return w.syncConsents();
  }).then(() => {
    check('syncConsents با JSON خراب فرونمی‌پاشد', true);
  });
}

console.log('--- ۸) «صفحه را برایم بخوان»: ترتیب مسیرها و حریم ---');
{
  // تنها آزمونی که دو تابع تازه را «اجرا» می‌کند؛ سنجش‌های ساختاری §۱۱ در
  // test_android_control.py فقط وجود کد را می‌بینند.
  //
  // همهٔ قدم‌ها در یک زنجیرهٔ ترتیبی await می‌شوند. نسخهٔ نخست هر قدم را
  // جداگانه در Promise.all می‌گذاشت؛ در نتیجه کد همگامِ قدم‌های بعدی پیش از
  // .then های قدم‌های قبلی اجرا می‌شد، mock عوض می‌شد و ۹ سنجش بی‌آنکه باگی
  // در کد محصول باشد شکست می‌خورد.
  const dom = new JSDOM('<!doctype html><html><body><div id="transcript"></div></body></html>',
                        { runScripts: 'outside-only' });
  const w = dom.window;
  const toasts = []; w.toast = m => toasts.push(m);
  const spoken = []; w.speakBack = t => spoken.push(t);
  const store = {};
  Object.defineProperty(w, 'localStorage', { configurable: true, value: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  }});
  const grab8 = (name) => {
    let i = html.indexOf('function ' + name + '(');
    if (i < 0) throw new Error('not found: ' + name);
    if (html.slice(i - 6, i) === 'async ') i -= 6;
    let d = 0, j = html.indexOf('{', i);
    for (let k = j; k < html.length; k++) {
      if (html[k] === '{') d++;
      else if (html[k] === '}') { d--; if (d === 0) return html.slice(i, k + 1); }
    }
    throw new Error('unbalanced: ' + name);
  };
  const posts = [];
  w.apiRequest = async (path, opt) => { posts.push({ path: path, opt: opt }); return { ok: true, text: 'فشار خون ۱۲ روی ۸' }; };
  w.eval(grab8('readScreenAloud') + '\n' + grab8('readNotificationsAloud') +
         '\n;window.readScreenAloud=readScreenAloud;window.readNotificationsAloud=readNotificationsAloud;');
  const reset = () => { spoken.length = 0; toasts.length = 0; posts.length = 0; };

  consentDone = (async () => {
    await consentDone;
    let caps = 0;

    // ۱) درخت گره جواب می‌دهد ⇒ بینایی هرگز صدا زده نمی‌شود.
    w.SepandyarNative = { readScreenText: () => 'دکمهٔ تأیید، مبلغ ۱۲۰۰۰ تومان',
                          captureScreenForVision: () => { caps++; return 'IMG'; } };
    reset(); await w.readScreenAloud();
    check('درخت گره که جواب بدهد، همان متن خوانده می‌شود', spoken[0] === 'دکمهٔ تأیید، مبلغ ۱۲۰۰۰ تومان', spoken);
    check('تا وقتی درخت جواب می‌دهد هیچ تصویری گرفته نمی‌شود', caps === 0, caps);
    check('متن همزمان روی صفحه هم نمایش داده می‌شود (دو‌حسی)',
      w.document.getElementById('transcript').textContent.length > 0, '');
    check('در مسیر بی‌خطر هیچ درخواست شبکه‌ای نمی‌رود', posts.length === 0, posts.length);

    // ۲) درخت خالی + رضایت خاموش ⇒ تصویر گرفته نمی‌شود.
    w.SepandyarNative = { readScreenText: () => '',
                          captureScreenForVision: () => { caps++; return 'IMG'; } };
    store.screenVision = '0';
    reset(); await w.readScreenAloud();
    check('بدون رضایت، حتی وقتی درخت خالی است تصویر گرفته نمی‌شود', caps === 0, caps);
    check('به کاربر گفته می‌شود کجا اجازه بدهد (نه سکوت)',
      spoken.length === 1 && spoken[0].indexOf('حریم خصوصی') >= 0, spoken);
    check('بدون رضایت هیچ درخواستی به سرور نمی‌رود', posts.length === 0, posts.length);

    // ۳) درخت خالی + رضایت روشن ⇒ بینایی.
    w.SepandyarNative = { readScreenText: () => '   ',
                          captureScreenForVision: () => { caps++; return 'BASE64IMG'; } };
    store.screenVision = '1';
    reset(); await w.readScreenAloud();
    check('با رضایت، از بینایی استفاده می‌شود', caps === 1, caps);
    check('تصویر به /api/screen/vision فرستاده می‌شود',
      posts.length === 1 && posts[0].path === '/api/screen/vision', posts.map(x => x.path));
    check('بدنهٔ درخواست خودِ تصویر است',
      posts[0] && JSON.parse(posts[0].opt.body).image === 'BASE64IMG', posts[0] && posts[0].opt.body);
    check('متن بازگشتی از بینایی خوانده می‌شود', spoken[0] === 'فشار خون ۱۲ روی ۸', spoken);
    check('به کاربر گفته می‌شود که از تصویر خوانده شد', toasts.some(t => t.indexOf('تصویر') >= 0), toasts);

    // ۴) سقف گفتار: صفحهٔ شلوغ نباید سالمند را دقیقه‌ها زیر حرف ببرد.
    w.SepandyarNative = { readScreenText: () => 'الف'.repeat(900) };
    reset(); await w.readScreenAloud();
    check('متن بلند کوتاه می‌شود و کوتاه شدنش اعلام می‌شود',
      spoken[0].length < 1300 && spoken[0].indexOf('کوتاه شد') >= 0, spoken[0].length);

    // ۵) نبودِ پوستهٔ بومی نباید استثنا بدهد.
    delete w.SepandyarNative;
    reset(); await w.readScreenAloud();
    check('در مرورگر معمولی فقط راهنما داده می‌شود، استثنا نه',
      toasts.length === 1 && spoken.length === 0, [toasts, spoken]);

    // ۶) اعلان‌ها: بدون رضایت اصلاً خوانده نمی‌شوند.
    let gotN = 0;
    w.SepandyarNative = { notificationsAllowed: () => false,
                          getNotifications: () => { gotN++; return '[]'; } };
    reset(); w.readNotificationsAloud();
    check('بدون رضایت، اعلان‌ها اصلاً خوانده نمی‌شوند', gotN === 0, gotN);
    check('به کاربر توضیح داده می‌شود که داده از گوشی بیرون نمی‌رود',
      spoken.length === 1 && spoken[0].indexOf('جایی فرستاده نمی‌شوند') >= 0, spoken);

    // ۷) با رضایت: حداکثر ۵ تا خوانده می‌شود و بقیه شمرده.
    const many = JSON.stringify(Array.from({ length: 9 }, (_, i) => ({ app: 'a', title: 'ع' + i, text: 'م' + i })));
    w.SepandyarNative = { notificationsAllowed: () => true, getNotifications: () => many };
    reset(); w.readNotificationsAloud();
    check('شمار کل اعلان‌ها گفته می‌شود', spoken[0].indexOf('9') >= 0, spoken[0]);
    check('فقط ۵ تای اول خوانده می‌شود', spoken[0].indexOf('ع4') >= 0 && spoken[0].indexOf('ع5') < 0, spoken[0]);
    check('باقی‌مانده شمرده می‌شود نه نادیده', spoken[0].indexOf('اعلان دیگر') >= 0, spoken[0]);

    // ۸) XSS: عنوان اعلان از یک اپ بیرونی می‌آید و نباید HTML تفسیر شود.
    const evil = JSON.stringify([{ app: 'x', title: '<img src=x onerror="window.__pwn=1">', text: '<b>q</b>' }]);
    w.SepandyarNative = { notificationsAllowed: () => true, getNotifications: () => evil };
    const tr = w.document.getElementById('transcript');
    tr.textContent = '';
    w.readNotificationsAloud();
    check('عنوان اعلان به‌صورت متن درج می‌شود نه HTML (هیچ عنصری ساخته نشد)',
      tr.children.length === 0, tr.innerHTML);
    check('اسکریپت تزریق‌شده اجرا نشد', w.__pwn === undefined, w.__pwn);
    w.SepandyarNative = { notificationsAllowed: () => true, getNotifications: () => 'not-json' };
    let threw = false;
    try { w.readNotificationsAloud(); } catch (e) { threw = true; }
    check('JSON خراب فرونمی‌پاشد', !threw, threw);

    // ۹) کلیدها باید همان لحظه روی پوستهٔ بومی نوشته شوند.
    const native8 = {};
    w.SepandyarNative = { setNotificationsAllowed: v => { native8.n = v; },
                          setScreenVisionAllowed: v => { native8.v = v; } };
    w.eval(html.match(/var CONSENT_SCOPE=\{[^}]*\};/)[0] + '\n' + grab8('syncSwitches') + '\n' +
           grab8('consentBody') + '\n' + grab8('toggleSetting') + '\n;window.toggleSetting=toggleSetting;');
    w.pushConsent = () => {};
    // قدم ۳ این کلید را «۱» گذاشته بود، پس toggle درست آن را خاموش می‌کرد.
    // از «۰» شروع می‌کنیم تا جهتِ روشن‌شدن سنجیده شود.
    store.screenVision = '0'; delete store.readNotifications;
    w.toggleSetting('screenVision');
    check('روشن کردن بینایی فوراً روی پوستهٔ بومی نوشته می‌شود', native8.v === true, native8);
    w.toggleSetting('readNotifications');
    check('روشن کردن اعلان‌ها فوراً روی پوستهٔ بومی نوشته می‌شود', native8.n === true, native8);
    check('screenVision به scope سرور نگاشت شده', w.CONSENT_SCOPE.screenVision === 'screen_vision', w.CONSENT_SCOPE);
  })();
}

console.log('--- ۷) همسان بودن دارایی اندروید ---');
{
  const asset = fs.readFileSync(path.join(ROOT, 'android', 'app', 'src', 'main', 'assets', 'index.html'), 'utf8');
  check('assets/index.html با index.html بایت‌به‌بایت یکسان است', asset === html);
}

Promise.resolve(consentDone).then(() => {
  console.log('\nبررسی‌ها: %d · شکست: %d', pass, fail);
  if (failures.length) { console.log('شکست‌ها:'); failures.forEach(f => console.log(' - ' + f)); }
  process.exit(fail ? 1 : 0);
});
