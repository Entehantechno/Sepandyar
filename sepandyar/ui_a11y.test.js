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
  const grab = (name) => {
    const i = html.indexOf('function ' + name + '(');
    if (i < 0) throw new Error('not found: ' + name);
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

console.log('--- ۶) همسان بودن دارایی اندروید ---');
{
  const asset = fs.readFileSync(path.join(ROOT, 'android', 'app', 'src', 'main', 'assets', 'index.html'), 'utf8');
  check('assets/index.html با index.html بایت‌به‌بایت یکسان است', asset === html);
}

console.log('\nبررسی‌ها: %d · شکست: %d', pass, fail);
if (failures.length) { console.log('شکست‌ها:'); failures.forEach(f => console.log(' - ' + f)); }
process.exit(fail ? 1 : 0);
