/*
 * آزمون موتور موج گفتار (VoiceWave) و speakBack.
 *
 * نکتهٔ مهم دربارهٔ روش: این آزمون منطق را «بازنویسی» نمی‌کند. کد موتور را
 * مستقیماً از خود index.html بیرون می‌کشد و در jsdom اجرا می‌کند، پس چیزی که
 * اینجا سبز می‌شود همان کدی است که در محصول اجرا می‌شود.
 *
 * اجرا:  node wave_engine.test.js
 * (نیازمند jsdom: از پوشهٔ والد  npm install jsdom)
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

let pass = 0, fail = 0;
const failures = [];
function check(name, cond, extra) {
  if (cond) { pass++; console.log('\u2705 ' + name); }
  else { fail++; failures.push(name); console.log('\u274c ' + name + (extra !== undefined ? ' -> ' + JSON.stringify(extra) : '')); }
}

function slice(startMarker, endMarker) {
  const a = html.indexOf(startMarker);
  const b = html.indexOf(endMarker, a < 0 ? 0 : a);
  if (a < 0 || b < 0 || b < a) throw new Error('slice failed: ' + startMarker);
  return html.slice(a, b);
}

// --- موتور + speakBack از خود فایل
const ENGINE = slice('const VoiceWave=(function(){', "const tabIds=['home'");

console.log('--- ۱) ساختار: موتور و سیم‌کشی در index.html ---');
check('موتور VoiceWave در index.html تعریف شده', ENGINE.includes('const VoiceWave=(function(){'));
check('API عمومی کامل است', ['setActive', 'startSpeech', 'boundary', 'attachStream', 'detachStream']
  .every(k => ENGINE.includes(k + (k === 'setActive' ? '(' : ',')) || ENGINE.includes('function ' + k + '(')));
check('createMediaStreamSource برای تحلیل واقعی استفاده می‌شود', ENGINE.includes('createMediaStreamSource'));
check('getByteFrequencyData برای دامنه استفاده می‌شود', ENGINE.includes('getByteFrequencyData'));
check('تحلیلگر به stream ورودی وصل می‌شود (همگام با صدای مدل)',
  html.includes('VoiceWave.attachStream(e.streams[0])'));
check('پاک‌سازی جلسهٔ زنده تعریف شده', html.includes('function stopRealtimeVoice()'));
check('در مسیر شکست هم تحلیلگر جدا می‌شود', html.includes('VoiceWave.detachStream();return false'));
check('کلاس js انیمیشن CSS را خاموش می‌کند',
  html.includes(".wave.speaking:not(.live):not(.js) i") && html.includes("w.classList.add('js')"));
check('برش بی‌قیدوشرط ۲۶۰۰ میلی‌ثانیه برداشته شده',
  !html.includes("setTimeout(()=>{setSpeaking(false);if(transcript)"));
check('fallback صرفاً-CSS برای حالت بدون JS نگه داشته شده',
  html.includes('@keyframes wave-fallback'));

console.log('--- ۲) اجرای واقعی موتور در jsdom ---');
const dom = new JSDOM('<!doctype html><html><body>' +
  '<div class="wave" id="voice-wave">' + '<i></i>'.repeat(14) + '</div>' +
  '<div class="transcript" id="transcript"></div></body></html>',
  { runScripts: 'outside-only' });
const w = dom.window;

let clock = 137;
Object.defineProperty(w.performance, 'now', { value: () => clock, configurable: true });
let rafQueue = [];
w.requestAnimationFrame = (fn) => { rafQueue.push(fn); return rafQueue.length; };
w.cancelAnimationFrame = () => { rafQueue = []; };
let rmOn = false;
w.matchMedia = (q) => ({ matches: rmOn && /reduced-motion/.test(q), media: q, addListener(){}, removeListener(){} });

let fakeLevel = 0;
w.AudioContext = function () {
  const node = { connect(){}, disconnect(){} };
  this.sampleRate = 48000; this.state = 'running';
  this.close = () => { this.state = 'closed'; };
  this.createMediaStreamSource = () => node;
  this.createAnalyser = () => ({
    fftSize: 1024, frequencyBinCount: 512, smoothingTimeConstant: 0,
    connect(){}, disconnect(){},
    getByteFrequencyData(arr){ for (let i = 0; i < arr.length; i++) arr[i] = fakeLevel; }
  });
};

function runFrames(n) { for (let i = 0; i < n; i++) { const q = rafQueue; rafQueue = []; q.forEach(f => f()); } }

w.eval(ENGINE + '\n;window.VoiceWave=VoiceWave;window.speakBack=speakBack;');
const VW = w.VoiceWave;
const waveEl = w.document.getElementById('voice-wave');
const bars = [...waveEl.querySelectorAll('i')];

check('موتور در jsdom ساخته شد', !!VW && typeof VW.startSpeech === 'function');

VW.startSpeech('سلام، امروز حالتان چطور است؟');
check('کلاس speaking افزوده شد', waveEl.classList.contains('speaking'));
check('کلاس js افزوده شد', waveEl.classList.contains('js'));
check('در مسیر TTS کلاس live نیست', !waveEl.classList.contains('live'));
runFrames(3);
const vals = bars.map(b => parseFloat(b.style.getPropertyValue('--s')));
check('هر ۱۴ میله مقدار گرفتند', vals.length === 14 && vals.every(Number.isFinite), vals);
const distinct = new Set(vals.map(v => v.toFixed(3)));
check('مقادیر میله‌ها متفاوت‌اند (موج رونده، نه هم‌فاز)', distinct.size >= 10, [...distinct]);
check('مقادیر در بازهٔ مجاز', vals.every(v => v >= 0.14 && v <= 1.0), [Math.min(...vals), Math.max(...vals)]);

const snaps = [];
for (let k = 0; k < 5; k++) { clock += 220; runFrames(2); snaps.push(parseFloat(bars[5].style.getPropertyValue('--s'))); }
check('موج در طول زمان تغییر می‌کند', new Set(snaps.map(v => v.toFixed(3))).size >= 4, snaps);

clock = 0; VW.startSpeech('آزمایش رویداد مرز کلمه در موتور موج سپندیار');
clock = 500; runFrames(1);
const b0 = parseFloat(bars[0].style.getPropertyValue('--s'));
VW.boundary(); clock = 520; runFrames(1);
const b1 = parseFloat(bars[0].style.getPropertyValue('--s'));
check('onboundary انرژی تزریق می‌کند', b0 !== b1, [b0, b1]);

console.log('--- ۳) مسیر صدای زنده: همگامی با دامنهٔ واقعی ---');
fakeLevel = 200;
check('attachStream موفق بود', VW.attachStream({ getTracks: () => [] }) === true);
check('کلاس live افزوده شد', waveEl.classList.contains('live'));
clock = 1000; runFrames(3);
const loud = bars.map(b => parseFloat(b.style.getPropertyValue('--s'))).reduce((a, b) => a + b, 0) / 14;
fakeLevel = 10; clock = 2000; runFrames(8);
const quiet = bars.map(b => parseFloat(b.style.getPropertyValue('--s'))).reduce((a, b) => a + b, 0) / 14;
check('صدای بلند میله‌ها را بلندتر می‌کند (همگامی واقعی با تن صوتی)',
  loud > quiet, [loud.toFixed(3), quiet.toFixed(3)]);
check('اختلاف دامنه معنادار است', loud - quiet > 0.15, (loud - quiet).toFixed(3));

VW.detachStream();
check('کلاس live برداشته شد', !waveEl.classList.contains('live'));
VW.setActive(false);
check('کلاس speaking برداشته شد', !waveEl.classList.contains('speaking'));

console.log('--- ۴) دسترسی‌پذیری: prefers-reduced-motion ---');
/*
  این بررسی عمداً «غیرتهی» ساخته شده است: اول ثابت می‌کنیم حلقه در حالت
  عادی واقعاً در حال اجراست و صف rAF پر است، بعد ترجیح را عوض می‌کنیم.
  اگر فقط صف را خالی می‌کردیم و بعد طولش را صفر می‌خواستیم، بررسی حتی
  وقتی نگهبان حذف شود هم سبز می‌ماند — یعنی چیزی را اثبات نمی‌کرد.
*/
rafQueue = []; rmOn = false;
VW.startSpeech('حالت عادی برای اثبات فعال بودن حلقه');
runFrames(2);
check('پیش‌زمینه: در حالت عادی حلقه فعال و صف rAF پر است', rafQueue.length === 1, rafQueue.length);
/*
  نکتهٔ صادقانه: بررسی «طول صف rAF صفر است» اینجا چیزی را اثبات نمی‌کرد.
  با آزمون تهی‌نبودن ثابت شد که حتی وقتی نگهبان reduced-motion کاملاً حذف
  می‌شود هم سبز می‌ماند، چون setActive تنها فراخوان loop() است و حذف
  نگهبان فقط staticOn را از کار می‌اندازد، نه زمان‌بندی قاب را. به‌جای
  نگه‌داشتن یک بررسیِ سبزِ بی‌معنا، نشانهٔ واقعی بررسی می‌شود: در حالت
  کاهش حرکت مقادیر میله‌ها باید «ثابت» بمانند و با گذشت زمان تغییر نکنند.
*/
rmOn = true;                      // کاربر کاهش حرکت را فعال می‌کند، حلقه هنوز گرم است
VW.startSpeech('حالت کاهش حرکت');
const rmSnap1 = bars.map(b => b.style.getPropertyValue('--s')).join(',');
clock += 3000; runFrames(4);
const rmSnap2 = bars.map(b => b.style.getPropertyValue('--s')).join(',');
check('در reduced-motion مقادیر میله‌ها با گذشت زمان تغییر نمی‌کنند (بدون انیمیشن)',
  rmSnap1 === rmSnap2, [rmSnap1.slice(0, 40), rmSnap2.slice(0, 40)]);
const rmVals = bars.map(b => parseFloat(b.style.getPropertyValue('--s')));
check('در reduced-motion میله‌ها حالت ایستا و مرئی گرفتند',
  rmVals.every(v => Number.isFinite(v) && v >= 0.5 && v <= 1.0), rmVals);
VW.setActive(false);

console.log('--- ۵) speakBack: همگامی با طول واقعی گفتار ---');
let spoken = null;
w.speechSynthesis = { cancel(){}, speak(u){ spoken = u; } };
w.SpeechSynthesisUtterance = function (t) { this.text = t; };
const timers = [];
w.setTimeout = (fn, ms) => { timers.push({ fn, at: clock + (ms || 0) }); return timers.length; };
w.clearTimeout = () => {};
function advance(ms) {
  clock += ms;
  timers.filter(t => !t.done && t.at <= clock).sort((x, y) => x.at - y.at).forEach(t => { t.done = true; t.fn(); });
}
const tr = w.document.getElementById('transcript');

const LONG = 'این یک پاسخ بلند است که بیش از دو ثانیه و ششصد میلی‌ثانیه طول می‌کشد تا خوانده شود و تمام شود.';
w.speakBack(LONG);
check('موج روشن شد', waveEl.classList.contains('speaking'));
check('speak صدا زده شد', !!spoken);
check('زبان fa-IR تنظیم شد', spoken && spoken.lang === 'fa-IR');
check('متن درست پاس داده شد', spoken && spoken.text === LONG);
check('onend و onerror هر دو ثبت شده‌اند',
  typeof spoken.onend === 'function' && typeof spoken.onerror === 'function');
advance(2700);
check('رفع باگ: موج بعد از ۲.۶ ثانیه هنوز روشن است (هنوز در حال صحبت)',
  waveEl.classList.contains('speaking'));
spoken.onend();
check('با onend واقعی موج خاموش شد', !waveEl.classList.contains('speaking'));
check('متن آماده بازنشانی شد', /درخواست بعدی/.test(tr.textContent), tr.textContent);
const before = tr.textContent;
spoken.onend();
check('onend تکراری بی‌اثر است', tr.textContent === before);

spoken = null;
w.speakBack('موتور تی‌تی‌اس خراب است و هرگز پایان را اعلام نمی‌کند');
check('موج روشن است', waveEl.classList.contains('speaking'));
advance(100000);
check('نگهبان، موجِ گیرکرده را خاموش می‌کند', !waveEl.classList.contains('speaking'));

spoken = null;
w.speakBack('آزمایش خطا');
spoken.onerror();
check('با onerror موج خاموش شد', !waveEl.classList.contains('speaking'));

console.log('--- ۶) باگ نسلِ گفتار: قطع پاسخ قبلی نباید موج پاسخ جاری را خاموش کند ---');
/*
  باگ واقعی که اینجا قفل می‌شود: speechSynthesis.cancel() رویداد onend
  گفتار قبلی را شلیک می‌کند و finish قدیمی setSpeaking(false) را اجرا
  می‌کرد. چون cancel بعد از setSpeaking(true) صدا زده می‌شد، هر بار پاسخ
  جدیدی پاسخ قبلی را قطع می‌کرد، موج برای کل پاسخ جدید خاموش می‌ماند.
*/
{
  let spoken2 = null; const queue = [];
  w.speechSynthesis = {
    get speaking(){ return queue.length > 0; },
    get pending(){ return false; },
    /*
      slice() ضروری است: «const q = queue» فقط یک ارجاع است، پس
      «queue.length = 0» همان آرایه را خالی می‌کرد و forEach روی آرایهٔ
      خالی اجرا می‌شد — یعنی onend هرگز شلیک نمی‌شد و آزمونِ همین باگ
      تهی می‌ماند. با آزمون تهی‌نبودن کشف شد.
    */
    cancel(){ const q = queue.slice(); queue.length = 0; q.forEach(u => { if (u.onend) u.onend(); }); },
    speak(u){ spoken2 = u; queue.push(u); }
  };
  const timers2 = [];
  w.setTimeout = (fn, ms) => { timers2.push({ fn, at: clock + (ms || 0) }); return timers2.length; };
  w.clearTimeout = (id) => { if (timers2[id - 1]) timers2[id - 1].done = true; };
  function advance2(ms) {
    const target = clock + ms;
    for (;;) {
      const n = timers2.filter(t => !t.done && t.at <= target).sort((a, b) => a.at - b.at)[0];
      if (!n) break;
      clock = n.at; n.done = true; n.fn();
    }
    clock = Math.max(clock, target);
  }
  w.speakBack('باشه');
  check('پاسخ ۱ موج را روشن کرد', waveEl.classList.contains('speaking'));
  clock += 500;
  w.speakBack('این یک پاسخ بلند است که باید چندین ثانیه طول بکشد تا خوانده شود و تازه بعد از آن تمام شود');
  check('رفع باگ: پس از قطع پاسخ قبلی، موج پاسخ جدید روشن می‌ماند',
    waveEl.classList.contains('speaking'));
  advance2(2650);
  check('نگهبانِ منسوخِ پاسخ ۱ موج پاسخ جاری را خاموش نمی‌کند',
    waveEl.classList.contains('speaking'));
  spoken2.onend();
  check('پایان واقعی، موج را خاموش می‌کند', !waveEl.classList.contains('speaking'));

  clock += 5000;
  w.speakBack('پاسخ سوم');
  clock += 200;
  w.speakBack('پاسخ چهارم');
  check('onend منسوخ، متن وضعیت را بازنشانی نمی‌کند',
    /در حال پاسخ/.test(tr.textContent), tr.textContent);
  advance2(300000);
  check('نگهبانِ پاسخ جاری در نهایت موج را خاموش می‌کند', !waveEl.classList.contains('speaking'));
}

console.log('--- ۷) همسان بودن دارایی اندروید ---');
const asset = fs.readFileSync(path.join(ROOT, 'android', 'app', 'src', 'main', 'assets', 'index.html'), 'utf8');
check('android/app/src/main/assets/index.html با index.html بایت‌به‌بایت یکسان است', asset === html);

console.log('\nبررسی‌ها: %d · شکست: %d', pass, fail);
if (failures.length) { console.log('شکست‌ها:'); failures.forEach(f => console.log(' - ' + f)); }
process.exit(fail ? 1 : 0);
