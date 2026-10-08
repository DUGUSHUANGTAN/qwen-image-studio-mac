// qwen image studio — the page. Talks to web/server.py; renders go through
// the ComfyUI set under Paths — nothing is sent anywhere.
"use strict";

const $ = (id) => document.getElementById(id);

// ── language ────────────────────────────────────────────────────────────
// html[data-lang] is set before first paint; the 中/EN button flips and remembers it.
const I18N = {
  en: {
    langBtn: "中", themeTitle: "Switch light / dark",
    newSession: "+ New", rename: "✎ Rename", renameTitle: "Rename session",
    delete: "Delete", deleting: "Delete",
    gallery: "Gallery", paths: "⚙ Paths", close: "Close",
    docs: "Docs", docsTitle: "Docs",
    resetPill: "↻ Reset", resetTitle2: "Clear references and restore the defaults",
    resetTitle: "Reset everything?",
    resetMsg: "The prompt, every setting and every reference image are cleared; the preview returns to the default empty size frame. Takes stay.",
    connecting: "connecting…", idle: "idle", queuedStatus: "queued", rendering: "rendering", reconnecting: "reconnecting…",
    model: "Model", comfyBad: "not connected", notSet: "not set",
    mode: "Mode", modeHint: "set by reference images", modeT2I: "Text → image", modeEdit: "Edit", modeEditN: "Edit · ${n} image${s}",
    prompt: "Prompt", chars: "${n} chars", promptPlaceholder: "A neon shop sign that reads QWEN",
    promptHint: "Type @ to name a reference image; it becomes <image1>, <image2>… in the order of the list.",
    aspectRatio: "Aspect ratio", ratioChosen: "chosen", ratioAuto: "auto · ${source}",
    srcLastImage: "follows the first image", srcDefault: "default 1:1",
    ratioAutoLabel: "Auto", width: "Width", height: "Height", auto: "auto",
    whHint: "Multiples of 32. With a ratio chosen, editing one side re-derives the other from it; clearing either side returns both to the ratio's own size. On Auto both are free.",
    sizeWarn: "Edits look best near the reference's own scale — the official recipe here is about ${w}×${h}. Much larger or smaller canvases go soft.",
    steps: "Steps", seed: "Seed", randomSeed: "Random seed",
    transparentBg: "Transparent background",
    transparentHint: "Asks for an alpha channel; the take is always saved as PNG.",
    generate: "Generate", addToQueue: "Add to queue",
    gridOk: "ok", gridBad: "not a multiple",
    noTake: "No take yet", useAsRef: "Use as reference", reuseSettings: "Reuse settings", open: "Open",
    frameEmpty: "Generate to see a take here",
    stageNames: { load: "Load", denoise: "Denoise", decode: "Decode", save: "Save" },
    nSteps: "${n} steps", stepN: "step ${i}/${n}", starting: "Starting",
    takes: "Takes", noTakes: "No takes in this session yet.",
    takeMeta: "${w}×${h}", badge: "seed ${seed} · ${steps} steps · ${mode}${elapsed}",
    galleryTabOutput: "Output", galleryTabInput: "Input",
    pathOutput: "Generated · Output", pathInput: "Imported · Input", pathData: "Storage",
    openFinder: "Open in Finder",
    referenceImages: "Reference images", fromGallery: "from gallery",
    dropHint: "Drop images here or click to add — up to 10. Adding one switches to Edit.",
    refsHint: "Numbered in prompt order. Click one to add it to the prompt as @name, sent as <imageN>. With no ratio set, the size follows the first image.",
    queue: "Queue", nothingQueued: "Nothing queued.", queuedN: "Queued #${n}", cancelling: "Cancelling", cancel: "cancel",
    terminal: "Terminal", output: "Output", renderLog: "Render log", clear: "clear",
    pathsTitle: "Paths", pathsComfyUI: "ComfyUI",
    comfyHint: "An install directory (the studio starts ComfyUI headless itself) or an http URL (reused). Renders go through its own Qwen-Image-2.1 graphs — nothing is downloaded here.",
    usePaths: "Use paths", cancel2: "Cancel",
    ok: "OK", create: "Create",
    newSessionTitle: "New session",
    clearRefsTitle: "Switch to text-to-image?", clearRefsMsg: "Remove all reference images from this session?",
    deleteSessionTitle: "Delete ${name}?", deleteSessionMsg: "Its settings, references, and takes will be deleted from the gallery.",
    deleteTakeTitle: "Delete this take?", deleteTakeMsg: "${name} leaves the gallery. Takes made from it keep their history.",
    deleteImgTitle: "Delete this image?", deleteImgMsg: "${name} leaves the Input folder and every session that references it.",
    refsRestored: "${n} reference image(s) came back with the settings",
    refsGone: "its reference images are no longer on disk",
    galleryPickTitle: "Use an image as a reference",
    galleryEmpty: "Nothing in the gallery yet — generate a take first.",
    galleryInputEmpty: "No imported images yet.",
    errWritePrompt: "write a prompt",
    errComfyPath: "the ComfyUI path is not set — set it under Paths",
    errImageTypes: "references must be PNG, JPEG or WebP",
    errMaxInputs: "Qwen-Image-2.1 takes at most 10 reference images",
    errSessionExists: "a session with that name already exists",
    errEnterName: "enter a name",
    errNoSession: "no session named ${name}",
    errNoDirectory: "${key}: no directory at ${path}",
    errNotAnImage: "${name} is not an image",
    errBetween: "${name} must be between ${low} and ${high}",
    errWholeNumber: "${name} must be a whole number",
    errMultiple32: "${name} must be a multiple of 32",
    errUnknownRatio: "unknown aspect ratio ${value}",
  },
  zh: {
    langBtn: "EN", themeTitle: "切换浅色 / 深色",
    newSession: "+ 新建", rename: "✎ 重命名", renameTitle: "重命名会话",
    delete: "删除", deleting: "删除",
    gallery: "图库", paths: "⚙ 路径", close: "关闭",
    docs: "文档", docsTitle: "使用说明",
    resetPill: "↻ 刷新", resetTitle2: "清空参考图并恢复默认参数",
    resetTitle: "恢复默认？",
    resetMsg: "提示词、全部设置与全部参考图都会被清空；预览回到默认尺寸的空框。成片不受影响。",
    connecting: "连接中…", idle: "空闲", queuedStatus: "排队中", rendering: "渲染中", reconnecting: "重连中…",
    model: "模型", comfyBad: "未连接", notSet: "未设置",
    mode: "模式", modeHint: "由参考图决定", modeT2I: "文生图", modeEdit: "编辑", modeEditN: "编辑 · ${n} 张图",
    prompt: "提示词", chars: "${n} 字符", promptPlaceholder: "一块写着 QWEN 的霓虹招牌",
    promptHint: "输入 @ 引用参考图；按列表顺序写成 <image1>、<image2>…",
    aspectRatio: "长宽比", ratioChosen: "已选择", ratioAuto: "自动 · ${source}",
    srcLastImage: "跟随第一张图", srcDefault: "默认 1:1",
    ratioAutoLabel: "自动", width: "宽度", height: "高度", auto: "自动",
    whHint: "需为 32 的倍数。选了比例时，改一边另一边会按比例自动调整；清空任一边即回到比例的原始尺寸。选「自动」时宽高自由填写。",
    sizeWarn: "编辑建议贴近参考图自身的尺度——官方推荐此处约 ${w}×${h}；画布过大或过小都会发糊。",
    steps: "步数", seed: "种子", randomSeed: "随机种子",
    transparentBg: "透明背景",
    transparentHint: "请求 alpha 通道；成片始终存为 PNG。",
    generate: "生成", addToQueue: "加入队列",
    gridOk: "符合", gridBad: "非 32 倍数",
    noTake: "还没有成片", useAsRef: "用作参考图", reuseSettings: "复用设置", open: "打开",
    frameEmpty: "生成后在这里查看成片",
    stageNames: { load: "加载", denoise: "去噪", decode: "解码", save: "保存" },
    nSteps: "${n} 步", stepN: "第 ${i}/${n} 步", starting: "启动中",
    takes: "成片", noTakes: "这个会话还没有成片。",
    takeMeta: "${w}×${h}", badge: "种子 ${seed} · ${steps} 步 · ${mode}${elapsed}",
    galleryTabOutput: "输出", galleryTabInput: "输入",
    pathOutput: "生成位置 · Output", pathInput: "导入图片 · Input", pathData: "储存",
    openFinder: "在访达打开",
    referenceImages: "参考图", fromGallery: "从图库选择",
    dropHint: "把图片拖到这里，或点击添加——最多 10 张。添加后切换到编辑模式。",
    refsHint: "按提示词顺序编号。点击一张以 @名称 写入提示词，按位置送作 <imageN>。未设长宽比时，尺寸跟随第一张图。",
    queue: "队列", nothingQueued: "队列为空。", queuedN: "排队 #${n}", cancelling: "取消中", cancel: "取消",
    terminal: "终端", output: "输出", renderLog: "渲染日志", clear: "清空",
    pathsTitle: "路径", pathsComfyUI: "ComfyUI",
    comfyHint: "填安装目录（Studio 会自动无头启动 ComfyUI）或运行中的 http 地址。渲染走它自己的 Qwen-Image-2.1 图——本地不下载任何东西。",
    usePaths: "使用路径", cancel2: "取消",
    ok: "好", create: "创建",
    newSessionTitle: "新建会话",
    clearRefsTitle: "切换为文生图？", clearRefsMsg: "将移除当前会话的全部参考图，已有成片不受影响。",
    deleteSessionTitle: "删除 ${name}？", deleteSessionMsg: "它的设置、参考图和成片都会从图库删除。",
    deleteTakeTitle: "删除这张成片？", deleteTakeMsg: "${name} 将离开图库。由它生成的成片不受影响。",
    deleteImgTitle: "删除这张图？", deleteImgMsg: "${name} 将离开 Input 文件夹，引用它的会话也会移除它。",
    refsRestored: "已随设置恢复 ${n} 张参考图",
    refsGone: "它的参考图已不在磁盘上",
    galleryPickTitle: "选一张图作为参考",
    galleryEmpty: "图库还是空的——先生成一张成片。",
    galleryInputEmpty: "还没有上传的图片。",
    errWritePrompt: "请先写提示词",
    errComfyPath: "ComfyUI 路径未设置——请在「路径」中填写",
    errImageTypes: "参考图必须是 PNG、JPEG 或 WebP",
    errMaxInputs: "Qwen-Image-2.1 最多接受 10 张参考图",
    errSessionExists: "同名会话已存在",
    errEnterName: "请输入名称",
    errNoSession: "没有名为 ${name} 的会话",
    errNoDirectory: "${key}：目录不存在：${path}",
    errNotAnImage: "${name} 不是图片",
    errBetween: "${name} 必须在 ${low} 到 ${high} 之间",
    errWholeNumber: "${name} 必须是整数",
    errMultiple32: "${name} 必须是 32 的倍数",
    errUnknownRatio: "未知长宽比 ${value}",
  },
};

function currentLang() {
  return document.documentElement.dataset.lang === "zh" ? "zh" : "en";
}

function t(key, vars) {
  let text = (I18N[currentLang()][key] ?? I18N.en[key] ?? key);
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll("${" + k + "}", String(v));
  return text;
}

/** The server speaks English; the page shows its common messages in the chosen language. */
function translateServerMessage(message) {
  if (currentLang() !== "zh") return message;
  const map = [
    [/^MPS image editing requires ComfyUI started with --cpu-vae; use a local folder path for automatic safe startup$/, () => "当前 ComfyUI 的 Mac 编辑配置不安全：需使用 --cpu-vae 启动；也可在「路径」中填写本地 ComfyUI 文件夹，让软件自动安全启动"],
    [/^cannot verify ComfyUI device for safe image editing$/, () => "无法确认 ComfyUI 的运行设备，不能安全提交编辑任务"],
    [/^editing needs at least 25 steps; 40 is strongly recommended$/, () => "编辑至少需要 25 步，强烈建议使用默认 40 步"],
    [/^editing needs both width and height, or leave both on Auto$/, () => "编辑自定义尺寸需同时填写宽高，或将两项都留空使用自动尺寸"],
    [/^edit canvas exceeds 1.5 megapixels; use Auto or about 1024 x 1024, then upscale$/, () => "编辑画布超过 150 万像素；请用自动尺寸或约 1024×1024，编辑后再放大"],
    [/^write a prompt$/, () => t("errWritePrompt")],
    [/^the ComfyUI path is not set — set it under Paths$/, () => t("errComfyPath")],
    [/^references must be PNG, JPEG or WebP$/, () => t("errImageTypes")],
    [/^Qwen-Image-2\.1 takes at most 10 reference images$/, () => t("errMaxInputs")],
    [/^a session with that name already exists$/, () => t("errSessionExists")],
    [/^enter a name$/, () => t("errEnterName")],
    [/^no session named (.+)$/, (m) => t("errNoSession", { name: m[1] })],
    [/^(comfyui): no directory at (.+)$/, (m) => t("errNoDirectory", { key: m[1], path: m[2] })],
    [/^(.+\.?\w*) is not an image$/, (m) => t("errNotAnImage", { name: m[1] })],
    [/^(\w+) must be between (\d+) and (\d+)$/, (m) => t("errBetween", { name: m[1], low: m[2], high: m[3] })],
    [/^(\w+) must be a whole number$/, (m) => t("errWholeNumber", { name: m[1] })],
    [/^(\w+) must be a multiple of 32$/, (m) => t("errMultiple32", { name: m[1] })],
    [/^unknown aspect ratio (.+)$/, (m) => t("errUnknownRatio", { value: m[1] })],
  ];
  for (const [re, fn] of map) {
    const m = re.exec(message);
    if (m) return fn(m);
  }
  return message;
}

function applyStaticLang() {
  const lang = currentLang();
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  }
  for (const node of document.querySelectorAll("[data-i18n-title]")) {
    node.setAttribute("title", t(node.dataset.i18nTitle));
  }
  $("langBtn").textContent = t("langBtn");
}

function setLang(lang) {
  document.documentElement.dataset.lang = lang;
  try { localStorage.setItem("qwen-studio-lang", lang); } catch { /* private browsing */ }
  applyStaticLang();
  renderPaths(ui.paths);
  update();
  renderTakes();
  renderQueue();
  showTake();
}

function wireLang() {
  $("langBtn").addEventListener("click", () => setLang(currentLang() === "zh" ? "en" : "zh"));
}

// ── theme ───────────────────────────────────────────────────────────────
function wireTheme() {
  $("themeBtn").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("qwen-studio-theme", next); } catch { /* private browsing */ }
  });
}

// ── the lightbox ────────────────────────────────────────────────────────
// Double-click any image on the page to see it nearly fullscreen over
// everything (a native dialog sits above the gallery dialog too); one
// click anywhere, or Escape, returns to where you were.
function openLightbox(src, alt) {
  if (!src) return;
  $("lightboxImg").src = src;
  $("lightboxImg").alt = alt || "";
  $("lightbox").showModal();
}

function wireLightbox() {
  const box = $("lightbox");
  box.addEventListener("click", () => box.close());
  // nothing left to paint, whatever a renderer does with the closed dialog
  box.addEventListener("close", () => {
    $("lightboxImg").src = "";
    $("lightboxImg").alt = "";
  });
}

// ── page state ──────────────────────────────────────────────────────────
// qwen_image_2_1.generate.ASPECT_RATIOS — the studio's own ratio table.
const RATIOS = {
  "1:1": [2048, 2048], "4:3": [2400, 1792], "3:4": [1792, 2400], "3:2": [2528, 1696],
  "2:3": [1696, 2528], "16:9": [2752, 1536], "9:16": [1536, 2752],
};
const STAGES = [
  ["load", "Load"], ["denoise", "Denoise"], ["decode", "Decode"], ["save", "Save"],
];
const FIELDS = ["prompt", "steps", "seed", "transparent"];

const ui = {
  session: "", paths: {}, dirs: null, ratio: null, inputs: [], takes: [], queue: [],
  selected: null, // gallery item id of the take in the preview
  live: null, // the running job's summary, for the stage bar
};

// ── helpers ─────────────────────────────────────────────────────────────
function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  node.append(...kids.filter((kid) => kid !== null && kid !== undefined && kid !== false));
  return node;
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || (data && data.error)) throw new Error(translateServerMessage((data && data.error) || `HTTP ${res.status}`));
  return data;
}

const q = (path) => `${path}?session=${encodeURIComponent(ui.session)}`;
const snap32 = (v) => Math.round(v / 32) * 32;

function showError(node, err) {
  node.textContent = err ? err.message || String(err) : "";
  node.hidden = !err;
}

/** A small in-page dialog: a name to type, or a yes/no. Resolves to the text, true, or null. */
function ask({ title, message = "", value = null, ok }) {
  const d = $("askDialog");
  $("askTitle").textContent = title;
  $("askMessage").textContent = message;
  $("askInput").hidden = value === null;
  $("askInput").value = value || "";
  $("askOk").textContent = ok || t("ok");
  showError($("askError"), null);
  d.showModal();
  if (value !== null) $("askInput").select();
  return new Promise((resolve) => {
    const done = (result) => { d.close(); cleanup(); resolve(result); };
    const onOk = () => done(value === null ? true : $("askInput").value.trim() || null);
    const onCancel = () => done(null);
    const onKey = (e) => { if (e.key === "Enter" && value !== null) onOk(); };
    const cleanup = () => {
      $("askOk").removeEventListener("click", onOk);
      $("askCancel").removeEventListener("click", onCancel);
      $("askInput").removeEventListener("keydown", onKey);
      d.removeEventListener("cancel", onCancel);
    };
    $("askOk").addEventListener("click", onOk);
    $("askCancel").addEventListener("click", onCancel);
    $("askInput").addEventListener("keydown", onKey);
    d.addEventListener("cancel", onCancel);
  });
}

// ── the form ────────────────────────────────────────────────────────────
function settings() {
  const num = (id) => ($(id).value === "" ? null : Number($(id).value));
  return {
    prompt: $("prompt").value, ratio: ui.ratio, width: num("width"), height: num("height"),
    steps: num("steps") ?? defaultSteps(), seed: num("seed") ?? 42,
    transparent: $("transparent").checked,
  };
}

function applySettings(s) {
  $("prompt").value = s.prompt ?? "";
  $("width").value = s.width ?? "";
  $("height").value = s.height ?? "";
  $("steps").value = s.steps ?? defaultSteps();
  $("seed").value = s.seed ?? 42;
  $("transparent").checked = !!s.transparent;
  ui.ratio = s.ratio || null;
  // a saved size from before this rule may name only one side: complete it
  if (ratioShape() && (($("width").value === "") !== ($("height").value === ""))) {
    syncSize($("width").value === "" ? "height" : "width");
  }
  update();
}

/** Qwen 2.1 model-card example: 40 steps; ComfyUI template: 25. */
function defaultSteps() {
  return 40;
}

/** A ratio's shape as a fraction, e.g. "16:9" → [16, 9]; null for Auto. */
function ratioShape() {
  if (!ui.ratio) return null;
  const [rw, rh] = ui.ratio.split(":").map(Number);
  return rw && rh ? [rw, rh] : null;
}

/** The ratio and the two size fields are one thing, never competing overrides:
 *  with a ratio chosen, editing either side re-derives the other from that ratio,
 *  and clearing either side returns both to the ratio's own size. */
function syncSize(edited) {
  const shape = ratioShape();
  if (!shape) return; // Auto: both sides are free, a custom shape is the point
  const [rw, rh] = shape;
  const width = $("width").value === "" ? null : Number($("width").value);
  const height = $("height").value === "" ? null : Number($("height").value);
  if (edited === "width") {
    if (width === null) clearOverride();
    else if (width > 0) $("height").value = clampSize(snap32(width * rh / rw));
  } else if (edited === "height") {
    if (height === null) clearOverride();
    else if (height > 0) $("width").value = clampSize(snap32(height * rw / rh));
  }
}

function clearOverride() {
  $("width").value = "";
  $("height").value = "";
}

/** The form's own bounds, so a derived side stays something the graphs accept. */
function clampSize(value) {
  return Math.min(4096, Math.max(256, value));
}

/** The form's own bounds, so a derived side stays something the graphs accept. */
function clampSize(value) {
  return Math.min(4096, Math.max(256, value));
}

/** What size the render will use, mirroring the ComfyUI graphs' own defaults. */
function plannedSize() {
  const s = settings();
  let base = null;
  let sourceKey;
  if (ui.inputs.length && s.ratio) {
    // an edit keeps the official ~1 MP pixel budget at the ratio's shape —
    // the 4 MP t2i sizes are far beyond what the references are conditioned at
    const [rw, rh] = s.ratio.split(":").map(Number);
    const r = rw / rh;
    const w = Math.sqrt(1024 * 1024 * r);
    base = [snap32(w), snap32(w / r)];
    sourceKey = null;
  } else if (s.ratio) {
    base = RATIOS[s.ratio];
    sourceKey = null;
  } else if (ui.inputs.length) {
    // TextEncodeQwenImage21: the first reference scaled to a 1024 square
    const first = ui.inputs[0];
    const r = (first.width || 1) / (first.height || 1);
    const w = Math.sqrt(1024 * 1024 * r);
    base = [snap32(w), snap32(w / r)];
    sourceKey = "srcLastImage";
  } else {
    base = RATIOS["1:1"];
    sourceKey = "srcDefault";
  }
  const w = s.width || (base && base[0]);
  const h = s.height || (base && base[1]);
  return { w, h, sourceKey };
}

/** The size the official edit recipe would use: the first reference scaled to a 1024 square. */
function recommendedEditSize() {
  const first = ui.inputs[0];
  if (!first?.width || !first?.height) return null;
  const r = first.width / first.height;
  return { w: Math.max(32, Math.round(Math.sqrt(1024 * 1024 * r) / 32) * 32),
           h: Math.max(32, Math.round(Math.sqrt(1024 * 1024 / r) / 32) * 32) };
}

function plannedRatio() {
  const { w, h } = plannedSize();
  return w && h ? String(w / h) : "1";
}

function update() {
  const edit = ui.inputs.length > 0;
  for (const span of $("modeSeg").children) span.classList.toggle("on", (span.dataset.m === "i2i") === edit);
  $("modeSeg").lastElementChild.textContent = edit
    ? t("modeEditN", { n: ui.inputs.length, s: ui.inputs.length > 1 ? "s" : "" })
    : t("modeEdit");
  $("promptCount").textContent = t("chars", { n: $("prompt").value.length });
  $("refCount").textContent = `${ui.inputs.length}/10`;

  const { w, h, sourceKey } = plannedSize();
  $("ratioSrc").textContent = ui.ratio ? t("ratioChosen") : t("ratioAuto", { source: t(sourceKey) });
  $("dims").textContent = w && h ? `${w} × ${h}` : "—";
  $("mp").textContent = w && h ? ((w * h) / 1e6).toFixed(2) : "—";
  const ok = (!w || w % 32 === 0) && (!h || h % 32 === 0);
  $("grid32").textContent = ok ? t("gridOk") : t("gridBad");
  $("grid32").classList.toggle("warn", !ok);
  // editing far from the reference's own scale goes soft — the official docs' own caution
  const sizeWarn = $("sizeWarn");
  if (comfyBackend() && edit && w && h) {
    const rec = recommendedEditSize();
    const off = rec && (Math.abs(w - rec.w) > rec.w * 0.3 || Math.abs(h - rec.h) > rec.h * 0.3);
    sizeWarn.textContent = t("sizeWarn", { w: rec.w, h: rec.h });
    sizeWarn.hidden = !off;
  } else {
    sizeWarn.hidden = true;
  }
  renderRatios();
  renderRefs();
  renderCommand();
  renderPipeline();
}

function renderRatios() {
  const options = [[null, t("ratioAutoLabel")], ...Object.keys(RATIOS).map((k) => [k, k])];
  $("ratios").replaceChildren(...options.map(([key, label]) => {
    const [w, h] = key ? RATIOS[key] : [1, 1];
    const s = 22 / Math.max(w, h);
    return el("button", {
      type: "button", class: `ratio${key ? "" : " auto"}`, "aria-pressed": String(ui.ratio === key),
      onclick: () => { ui.ratio = key; clearOverride(); update(); markDirty(); saveSoon(); },
    }, el("i", { style: `width:${Math.round(w * s)}px;height:${Math.round(h * s)}px` }), label);
  }));
}

function renderCommand() {
  const s = settings();
  const tagged = resolveMentions(s.prompt);
  const prompt = tagged.length > 40 ? `${tagged.slice(0, 40)}…` : tagged || "…";
  const quote = (value) => JSON.stringify(String(value));
  const parts = [`<span class="k">ComfyUI graph</span>  ${escapeHtml(quote(prompt))}`];
  if (ui.inputs.length) parts.push(`--input ${escapeHtml(ui.inputs.map((i) => i.name).join(","))}`);
  parts.push(`--mode ${ui.inputs.length ? "edit" : "t2i"}`);
  const { w, h } = plannedSize();
  if (w && h) parts.push(`--size ${w}x${h}`);
  parts.push(`--steps ${s.steps}`, `--seed ${s.seed}`, "--cfg 1", "--sampler euler", "--scheduler simple");
  if (s.transparent) parts.push("--transparent");
  $("cmd").innerHTML = parts.join(" \\\n  ");
}

function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

let saveTimer;
function saveSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => api("/api/session/save", { session: ui.session, settings: settings() }).catch(() => {}), 600);
}

// ── references ──────────────────────────────────────────────────────────
// ── @ mentions: a reference image named in the prompt ───────────────────
// The page writes @name; the server turns it into <imageN> by the list's order (web/server.py
// resolve_mentions), so a mention still points at its image after another is removed.
const MENTION_RE = /@([A-Za-z0-9._-]*[A-Za-z0-9_-])/g;
const mention = { start: -1, items: [], at: 0 };

function resolveMentions(text) {
  const index = new Map(ui.inputs.map((input, i) => [input.name, i + 1]));
  return text.replace(MENTION_RE, (m, name) => (index.has(name) ? `<image${index.get(name)}>` : m));
}

/** The "@query" being typed just before the caret, or null. An @ inside a word (an email) is not one. */
function mentionQuery() {
  const box = $("prompt");
  const before = box.value.slice(0, box.selectionStart);
  const m = /(^|[^A-Za-z0-9._-])@([A-Za-z0-9._-]*)$/.exec(before);
  return m ? { start: before.length - m[2].length - 1, query: m[2].toLowerCase() } : null;
}

function renderMentions() {
  const found = ui.inputs.length ? mentionQuery() : null;
  mention.items = found ? ui.inputs.filter((input) => input.name.toLowerCase().includes(found.query)) : [];
  mention.start = found ? found.start : -1;
  mention.at = Math.min(mention.at, Math.max(0, mention.items.length - 1));
  $("mentions").hidden = !mention.items.length;
  $("mentions").replaceChildren(...mention.items.map((input, i) => el("button", {
    type: "button", class: "mention", role: "option", "aria-selected": String(i === mention.at),
    onmousedown: (e) => { e.preventDefault(); pickMention(input.name); }, // before the textarea blurs
  },
  el("img", { src: input.thumb, alt: "" }),
  el("span", { class: "num", text: `<image${ui.inputs.indexOf(input) + 1}>` }),
  el("span", { class: "name", text: input.name }))));
}

function pickMention(name) {
  const box = $("prompt");
  const end = box.selectionStart;
  box.setRangeText(`@${name} `, mention.start, end, "end");
  $("mentions").hidden = true;
  box.dispatchEvent(new Event("input"));
  box.focus();
}

function insertMention(name) {
  const box = $("prompt");
  const at = box.selectionStart ?? box.value.length;
  const pad = at > 0 && !/\s/.test(box.value[at - 1]) ? " " : "";
  box.setRangeText(`${pad}@${name} `, at, box.selectionEnd ?? at, "end");
  box.dispatchEvent(new Event("input"));
  box.focus();
}

function onMentionKey(e) {
  if ($("mentions").hidden) return;
  const n = mention.items.length;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    mention.at = (mention.at + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
    renderMentions();
  } else if (e.key === "Enter" || e.key === "Tab") {
    e.preventDefault();
    pickMention(mention.items[mention.at].name);
  } else if (e.key === "Escape") {
    e.preventDefault();
    $("mentions").hidden = true;
  }
}

// A single click writes @name into the prompt; a double click opens the
// lightbox instead, so the click waits briefly and is cancelled by the
// double click.
/** "session" first; once taken, "session 1", "session 2", … whatever is free. */
function nextSessionName() {
  const taken = [...$("sessionSelect").options].map((o) => o.value.toLowerCase());
  if (!taken.includes("session")) return "session";
  let n = 1;
  while (taken.includes(`session ${n}`)) n++;
  return `session ${n}`;
}

let refClickTimer = null;
let takeClickTimer = null;

function renderRefs() {
  clearTimeout(refClickTimer);
  const followFirst = !ui.ratio;
  const cells = ui.inputs.map((input, i) => el("div", {
    class: `ref${followFirst && i === 0 ? " follow" : ""}`,
    title: `${input.original_name} · ${input.width || "?"}×${input.height || "?"}`,
  },
  el("img", {
    src: input.thumb, alt: input.original_name, loading: "lazy", title: `@${input.name}`,
    onclick: (e) => {
      if (e.detail > 1) return;
      clearTimeout(refClickTimer);
      refClickTimer = setTimeout(() => insertMention(input.name), 220);
    },
    ondblclick: () => { clearTimeout(refClickTimer); openLightbox(input.url || input.thumb, input.original_name); },
  }),
  el("span", { class: "n", text: String(i + 1) }),
  el("button", {
    class: "x", type: "button", "aria-label": `${t("delete")} ${input.original_name}`, text: "✕",
    onclick: async () => { await api("/api/inputs/delete", { session: ui.session, name: input.name }); loadInputs(); },
  })));
  for (let i = ui.inputs.length; i < Math.min(10, Math.max(5, ui.inputs.length + 1)); i++) {
    cells.push(el("div", { class: "ref empty", "aria-hidden": "true" }));
  }
  $("refs").replaceChildren(...cells);
}

async function loadInputs() {
  ui.inputs = await api(q("/api/inputs"));
  update();
}

async function uploadFiles(files) {
  for (const file of files) {
    const res = await fetch(q("/api/upload"), {
      method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { termLine(`[studio] ${file.name}: ${translateServerMessage(data.error) || res.status}`, "e"); break; }
  }
  loadInputs();
}

// ── takes ───────────────────────────────────────────────────────────────
async function loadTakes(selectNewest = false) {
  ui.takes = await api(q("/api/takes"));
  if (selectNewest) ui.selected = ui.takes[0]?.id ?? null;
  else if (!ui.takes.some((tk) => tk.id === ui.selected)) ui.selected = null;
  renderTakes();
  showTake();
}

function renderTakes() {
  clearTimeout(takeClickTimer);
  $("takeCount").textContent = `(${ui.takes.length})`;
  if (!ui.takes.length) {
    $("takes").replaceChildren(el("div", { class: "none", text: t("noTakes") }));
    return;
  }
  $("takes").replaceChildren(...ui.takes.map((take) => el("button", {
    type: "button", class: `take${take.id === ui.selected ? " on" : ""}`,
    title: take.params.name || "",
    // a single click selects; a double click opens — the select waits out the double
    onclick: (e) => {
      if (e.detail > 1) return;
      clearTimeout(takeClickTimer);
      takeClickTimer = setTimeout(() => { ui.selected = take.id; renderTakes(); showTake(); }, 220);
    },
    ondblclick: () => { clearTimeout(takeClickTimer); openLightbox(take.url || take.thumb, take.params.name); },
    oncontextmenu: (e) => showContextMenu(e, takeMenuActions(take)),
  },
  el("div", { class: "thumb" },
    el("img", { src: take.thumb, alt: "", loading: "lazy" })),
  el("div", { class: "meta" }, t("takeMeta", { w: p_width(take), h: p_height(take)   })))));
}

const p_width = (item) => (item.params || {}).width ?? "?";
const p_height = (item) => (item.params || {}).height ?? "?";

function showTake() {
  const take = ui.takes.find((tk) => tk.id === ui.selected);
  const p = take?.params || {};
  $("frameImg").hidden = !take;
  $("frameEmpty").hidden = !!take;
  $("frameBadge").hidden = !take;
  $("stageRatio").hidden = !take;
  if (!take) {
    $("stageTitle").textContent = t("noTake");
    $("frame").style.setProperty("--r", plannedRatio());
    return;
  }
  $("frameImg").src = take.url;
  $("frame").style.setProperty("--r", String(p.width / p.height));
  $("stageTitle").textContent = p.name || take.id;
  $("stageRatio").textContent = `${p.width}×${p.height}`;
  $("frameBadge").textContent = t("badge", {
    seed: p.seed, steps: p.steps, mode: p.mode,
    elapsed: p.elapsed ? ` · ${Math.round(p.elapsed)}s` : "",
  });
}

/**
 * Any settings change invalidates the preview: the take on screen was made with
 * other settings, so drop it and show the frame at the size that will be used.
 */
function markDirty() {
  if (ui.selected !== null) {
    ui.selected = null;
    renderTakes();
  }
  showTake();
}

/** Every parameter back to its default, preview included. References stay. */
function resetParameters() {
  applySettings({});
  ui.selected = null;
  renderTakes();
  showTake();
  saveSoon();
}

async function useTake(take) {
  try {
    await api("/api/takes/use", { session: ui.session, id: take.id });
    loadInputs();
  } catch (err) {
    termLine(`[studio] ${err.message}`, "e");
  }
}

async function reuseTake(take) {
  applySettings(take.params.settings || take.params);
  saveSoon();
  // the references it was made from come back too, when their files still exist
  try {
    const res = await api("/api/takes/reuse", { session: ui.session, take_id: take.id });
    if (res.added > 0) {
      await loadInputs();
      termLine(`[studio] ${t("refsRestored", { n: res.added })}`);
    } else if (res.recorded > 0) {
      termLine(`[studio] ${t("refsGone")}`);
    }
  } catch (err) { termLine(`[studio] ${err.message}`, "e"); }
}

async function deleteTake(take) {
  dismissContextMenu();
  const yes = await ask({ title: t("deleteTakeTitle"), message: t("deleteTakeMsg", { name: take.params.name }), ok: t("deleting") });
  if (!yes) return;
  try {
    await api("/api/takes/delete", { id: take.id });
    await loadTakes();
    if ($("galleryDialog").open) await renderGallery();
  } catch (err) { termLine(`[studio] ${err.message}`, "e"); }
}

// ── the right-click menu ────────────────────────────────────────────────
// Takes in the strip and images in the gallery share it: use as reference,
// reuse settings, open, delete — nothing on the cards themselves.
let contextMenu = null;
function dismissContextMenu() { contextMenu?.remove(); contextMenu = null; }

function showContextMenu(e, actions) {
  e.preventDefault();
  dismissContextMenu();
  contextMenu = el("div", { class: "take-context-menu", role: "menu" },
    ...actions.map((action) => el("button", {
      type: "button", role: "menuitem", class: action.danger ? "danger" : null, text: action.label,
      onclick: () => { dismissContextMenu(); action.fn(); },
    })));
  // an open <dialog> sits in the top layer — the menu has to join it there,
  // and a top-layer dialog is the containing block for its fixed children,
  // so the cursor's viewport coordinates need the dialog's offset subtracted
  const host = $("galleryDialog").open ? $("galleryDialog") : document.body;
  host.append(contextMenu);
  const hostBox = host === document.body
    ? { left: 0, top: 0, width: innerWidth, height: innerHeight }
    : host.getBoundingClientRect();
  const box = contextMenu.getBoundingClientRect();
  contextMenu.style.left = `${Math.max(8, Math.min(e.clientX - hostBox.left, hostBox.width - box.width - 8))}px`;
  contextMenu.style.top = `${Math.max(8, Math.min(e.clientY - hostBox.top, hostBox.height - box.height - 8))}px`;
  contextMenu.querySelector("button").focus();
}
document.addEventListener("pointerdown", (e) => { if (contextMenu && !contextMenu.contains(e.target)) dismissContextMenu(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") dismissContextMenu(); });

function takeMenuActions(item) {
  return [
    { label: t("useAsRef"), fn: () => useTake(item) },
    { label: t("reuseSettings"), fn: () => reuseTake(item) },
    { label: t("open"), fn: () => openLightbox(item.url || item.thumb, item.params.name || item.file) },
    { label: t("deleting"), danger: true, fn: () => deleteTake(item) },
  ];
}

function inputMenuActions(item) {
  return [
    { label: t("useAsRef"), fn: () => useGalleryItem(item) },
    { label: t("open"), fn: () => openLightbox(item.url || item.thumb, item.name) },
    { label: t("deleting"), danger: true, fn: () => deleteInputAsset(item) },
  ];
}

async function deleteInputAsset(item) {
  const yes = await ask({ title: t("deleteImgTitle"), message: t("deleteImgMsg", { name: item.name }), ok: t("deleting") });
  if (!yes) return;
  try {
    await api("/api/inputs/delete-asset", { asset_id: item.asset_id });
    await renderGallery();
  } catch (err) { termLine(`[studio] ${err.message}`, "e"); }
}

// ── queue, progress, terminal ───────────────────────────────────────────
function renderQueue() {
  const running = ui.queue.find((j) => j.status === "running" || j.status === "cancelling");
  $("lamp").className = `dot ${running ? "busy" : "on"}`;
  $("lampText").textContent = running ? t("rendering") : ui.queue.length ? t("queuedStatus") : t("idle");
  if (!ui.queue.length) {
    $("queue").replaceChildren(el("div", { class: "none", text: t("nothingQueued") }));
    return;
  }
  $("queue").replaceChildren(...ui.queue.map((job, i) => el("div", { class: "qi" },
    el("span", { class: `dot ${job.status === "running" ? "busy" : ""}` }),
    el("span", { text: job.status === "running" ? t("rendering") : job.status === "cancelling" ? t("cancelling") : t("queuedN", { n: i + 1 }) }),
    el("button", { class: "link", type: "button", text: t("cancel"), onclick: () => api("/api/cancel", { id: job.id }) }),
    el("small", { text: `${job.prompt} · ${job.ratio || "auto"} · ${t("seed")} ${job.seed}` }))));
}

function renderPipeline() {
  const job = ui.live;
  const at = job ? STAGES.findIndex(([key]) => key === job.progress.stage) : -1;
  const steps = job?.progress.total || $("steps").value || defaultSteps();
  $("pipeline").replaceChildren(...STAGES.map(([key], i) => {
    let cls = "";
    let width = null;
    if (job && i < at) cls = "done";
    else if (job && i === at) {
      cls = "now";
      width = key === "denoise" && job.progress.total ? (100 * job.progress.step) / job.progress.total : 35;
    }
    const sub = { load: "ComfyUI", denoise: t("nSteps", { n: steps }), decode: "VAE", save: "PNG" }[key];
    return el("div", { class: `stepc ${cls}` },
      el("div", { class: "bar" }, el("i", { style: width === null ? null : `width:${width}%` })), t("stageNames")[key], el("small", { text: sub }));
  }));
  $("progressActions").hidden = !job;
  $("frameLive").hidden = !job;
  $("generate").textContent = job ? t("addToQueue") : t("generate");
  if (!job) return;
  const p = job.progress;
  const label = p.stage === "denoise" && p.total ? t("stepN", { i: p.step, n: p.total }) : (t("stageNames")[p.stage] || t("starting")) + "…";
  $("frameLive").textContent = label;
  $("progressText").textContent = label;
}

let lastRewrites = false;
function termLine(text, cls) {
  const term = $("term");
  const line = el("span", { class: cls || null, text: `${text}\n` });
  if (lastRewrites && term.lastChild) term.lastChild.replaceWith(line);
  else term.append(line);
  while (term.childNodes.length > 2000) term.firstChild.remove();
  term.scrollTop = term.scrollHeight;
}

// The render log: one job's stream on its own tab, kept locally from the SSE feed.
const jobLogs = new Map(); // job id → [{text, cls}]
let renderLogJob = null;

function showRenderLog(id) {
  if (!id || renderLogJob === id) return;
  renderLogJob = id;
  const box = $("renderLog");
  box.replaceChildren();
  for (const entry of jobLogs.get(id) || []) {
    box.append(el("span", { class: entry.cls || null, text: `${entry.text}\n` }));
  }
  box.scrollTop = box.scrollHeight;
}

function onEvent(event) {
  const { type, data } = JSON.parse(event.data);
  if (type === "queue") {
    ui.queue = data;
    const running = data.find((j) => j.status === "running" || j.status === "cancelling");
    ui.live = running && running.session === ui.session ? running : null;
    renderQueue();
    renderPipeline();
    if (running) showRenderLog(running.id);
  } else if (type === "progress" && ui.live && data.id === ui.live.id) {
    ui.live.progress = data.progress;
    ui.live.result = data.result;
    renderPipeline();
  } else if (type === "log" && data.session === ui.session) {
    const cls = { cmd: "m", done: "a", failed: "e", cancelled: "e" }[data.kind] || (data.line.startsWith("Saved ") ? "a" : null);
    if (data.job) {
      const entries = jobLogs.get(data.job) || [];
      entries.push({ text: data.line, cls });
      if (entries.length > 2000) entries.splice(0, entries.length - 2000);
      jobLogs.set(data.job, entries);
      if (data.job === renderLogJob) {
        const box = $("renderLog");
        box.append(el("span", { class: cls || null, text: `${data.line}\n` }));
        while (box.childNodes.length > 2000) box.firstChild.remove();
        box.scrollTop = box.scrollHeight;
      }
    }
    termLine(data.line, cls);
    lastRewrites = data.rewrites;
  } else if (type === "job" && data.session === ui.session) {
    if (ui.live && ui.live.id === data.id) ui.live = null;
    renderPipeline();
    if (data.status === "failed") showError($("formError"), new Error(translateServerMessage(data.error || "the render failed")));
    loadTakes(data.status === "done");
  } else if (type === "inputs") {
    loadInputs();
  }
}

function connectEvents() {
  const source = new EventSource("/api/events");
  source.onmessage = onEvent;
  source.onerror = () => {
    $("lamp").className = "dot off";
    $("lampText").textContent = t("reconnecting");
  };
}

// ── sessions and paths ──────────────────────────────────────────────────
function renderSessions(names) {
  $("sessionSelect").replaceChildren(...names.map((n) => el("option", { value: n, text: n, selected: n === ui.session })));
}

async function openSession(name, settingsOverride) {
  const res = await api("/api/session/activate", { session: name });
  ui.session = res.name;
  applySettings(settingsOverride || res.settings || {});
  $("term").replaceChildren();
  const cfg = await api("/api/config");
  ui.dirs = { data: cfg.data_dir, input: cfg.input_dir, output: cfg.output_dir };
  renderSessions(cfg.sessions);
  await Promise.all([loadInputs(), loadTakes()]);
}

function renderPaths(paths) {
  ui.paths = paths;
  const comfy = (paths.comfyui?.path || "").trim();
  $("modelPath").textContent = comfy || t("notSet");
  $("modelBad").hidden = !!(comfy && paths.comfyui?.ok);
  update();
}

function comfyBackend() {
  return !!(ui.paths.comfyui?.ok && (ui.paths.comfyui?.path || "").trim());
}

async function savePaths() {
  try {
    renderPaths(await api("/api/paths", { paths: { comfyui: $("pComfy").value } }));
    $("pathsDialog").close();
  } catch (err) {
    showError($("pathsError"), err);
  }
}

// ── the gallery: every take across sessions, kept by the studio itself ──
// Two parts — Output (finished takes) and Input (imported references) — with
// the folders and a Finder button in the bottom-right corner.
// Picker mode resolves galleryPicker with the chosen item (or null on close).
let galleryPicker = null;
let galleryTab = "output";

function openGallery(asPicker) {
  $("galleryTitle").textContent = asPicker ? t("galleryPickTitle") : t("gallery");
  $("galleryClose").textContent = asPicker ? t("cancel2") : t("close");
  $("galleryTabs").hidden = asPicker;
  $("galleryFoot").hidden = asPicker;
  fillGalleryFoot();
  $("galleryDialog").showModal();
  renderGallery(asPicker);
}

function fillGalleryFoot() {
  $("galleryOutPath").textContent = ui.dirs?.output || "—";
  $("galleryInPath").textContent = ui.dirs?.input || "—";
  $("galleryDataPath").textContent = ui.dirs?.data || "—";
}

let galleryPickerMode = false;
async function renderGallery(asPicker = galleryPickerMode) {
  galleryPickerMode = asPicker;
  try {
    const inputTab = !asPicker && galleryTab === "input";
    const items = inputTab ? await api("/api/inputs/all") : await api("/api/gallery");
    const grid = el("div", { class: "gallery-grid" });
    if (!items.length) grid.append(el("div", { class: "none", text: t(inputTab ? "galleryInputEmpty" : "galleryEmpty") }));
    for (const item of items) {
      // the image number on the card is the file's own name in Output/ or Input/
      const name = inputTab ? item.name : (item.file || item.title || "take");
      const card = el("button", {
        type: "button", class: "gitem",
        oncontextmenu: (e) => showContextMenu(e, inputTab ? inputMenuActions(item) : takeMenuActions(item)),
        ondblclick: () => openLightbox(item.url || item.thumb, name),
      },
        el("div", { class: "thumb" }, el("img", { src: item.thumb, alt: "", loading: "lazy" })),
        el("div", { class: "meta" },
          el("b", { text: name }),
          el("span", { text: item.session })));
      card.addEventListener("click", () => {
        if (!asPicker) return;
        const resolve = galleryPicker;
        galleryPicker = null;
        $("galleryDialog").close();
        resolve?.(item);
      });
      grid.append(card);
    }
    $("galleryMount").replaceChildren(grid);
  } catch (err) { termLine(`[studio] ${err.message}`, "e"); }
}

$("galleryDialog").addEventListener("close", () => {
  dismissContextMenu();
  const resolve = galleryPicker;
  galleryPicker = null;
  resolve?.(null);
});

async function useGalleryItem(item) {
  $("galleryDialog").close();
  // gallery images are already stored — attach the entry, never a second file
  try {
    await api(item.asset_id ? "/api/inputs/attach" : "/api/takes/use",
              item.asset_id ? { asset_id: item.asset_id } : { id: item.id });
    loadInputs();
  } catch (err) {
    termLine(`[studio] ${err.message}`, "e");
  }
}

// ── wiring ──────────────────────────────────────────────────────────────
function wire() {
  wireTheme();
  wireLang();
  $("docsBtn").addEventListener("click", () => $("docsDialog").showModal());
  $("docsClose").addEventListener("click", () => $("docsDialog").close());
  $("modeSeg").addEventListener("click", async (e) => {
    const mode = e.target.closest("button[data-m]")?.dataset.m;
    if (mode === "i2i") { $("fileInput").click(); return; }
    if (mode !== "t2i" || !ui.inputs.length) return;
    const yes = await ask({ title: t("clearRefsTitle"), message: t("clearRefsMsg"), ok: t("delete") });
    if (!yes) return;
    try {
      for (const input of [...ui.inputs]) await api("/api/inputs/delete", { session: ui.session, name: input.name });
      await loadInputs();
      markDirty();
    } catch (err) { termLine(`[studio] ${err.message}`, "e"); }
  });
  for (const id of FIELDS) {
    if (id === "width" || id === "height") continue; // they sync with the ratio instead
    $(id).addEventListener("input", () => { update(); markDirty(); saveSoon(); });
  }
  // width and height follow the chosen ratio, each edited side driving the other
  for (const id of ["width", "height"]) $(id).addEventListener("input", () => { syncSize(id); update(); markDirty(); saveSoon(); });
  $("prompt").addEventListener("input", () => { mention.at = 0; renderMentions(); });
  $("prompt").addEventListener("keydown", onMentionKey);
  $("prompt").addEventListener("click", renderMentions);
  $("prompt").addEventListener("blur", () => { $("mentions").hidden = true; });
  $("dice").addEventListener("click", () => { $("seed").value = Math.floor(Math.random() * 2 ** 31); update(); markDirty(); saveSoon(); });
  $("generate").addEventListener("click", async () => {
    showError($("formError"), null);
    try {
      await api("/api/render", { session: ui.session, ...settings() });
    } catch (err) {
      showError($("formError"), err);
    }
  });
  $("cancel").addEventListener("click", () => ui.live && api("/api/cancel", { id: ui.live.id }));

  $("fileInput").addEventListener("change", (e) => { uploadFiles([...e.target.files]); e.target.value = ""; });
  const drop = $("drop");
  // the picker is opened by the script, not by label-for: a hidden input cannot be
  // relied on there, and this is what a WKWebView file panel needs
  const openPicker = () => $("fileInput").click();
  drop.addEventListener("click", openPicker);
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPicker(); }
  });
  // the whole pane is a drop target, not only the label
  const side = document.querySelector(".panel.side");
  for (const zone of [drop, side]) {
    zone.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
    zone.addEventListener("dragleave", () => drop.classList.remove("drag"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      drop.classList.remove("drag");
      uploadFiles([...e.dataTransfer.files]);
    });
  }

  $("frameImg").addEventListener("dblclick", () => {
    if ($("frameImg").src) openLightbox($("frameImg").src, $("stageTitle").textContent);
  });
  wireLightbox();

  $("sessionSelect").addEventListener("change", (e) => openSession(e.target.value));
  $("sessionNew").addEventListener("click", async () => {
    const name = await ask({ title: t("newSessionTitle"), value: nextSessionName(), ok: t("create") });
    if (name) openSession(name, {});
  });
  $("sessionRename").addEventListener("click", async () => {
    const name = await ask({ title: t("renameTitle"), value: ui.session, ok: t("rename").replace("✎ ", "") });
    if (!name || name === ui.session) return;
    try {
      const res = await api("/api/session/rename", { session: ui.session, new_name: name });
      openSession(res.name);
    } catch (err) {
      termLine(`[studio] ${err.message}`, "e");
    }
  });
  $("sessionDel").addEventListener("click", async () => {
    const yes = await ask({ title: t("deleteSessionTitle", { name: ui.session }), message: t("deleteSessionMsg"), ok: t("deleting") });
    if (!yes) return;
    const res = await api("/api/session/delete", { session: ui.session });
    openSession(res.name);
  });

  $("pathsBtn").addEventListener("click", () => {
    $("pComfy").value = ui.paths.comfyui?.path || "";
    showError($("pathsError"), null);
    $("pathsDialog").showModal();
  });
  $("pathsCancel").addEventListener("click", () => $("pathsDialog").close());
  $("pathsSave").addEventListener("click", savePaths);

  $("galleryBtn").addEventListener("click", () => openGallery(false));
  $("refFromGallery").addEventListener("click", () => {
    galleryPicker = async (item) => {
      if (!item) return;
      await useGalleryItem(item);
    };
    openGallery(true);
  });
  $("galleryClose").addEventListener("click", () => $("galleryDialog").close());
  $("galleryTabs").addEventListener("click", (e) => {
    const tab = e.target.closest("button[data-tab]");
    if (!tab) return;
    for (const b of $("galleryTabs").children) b.setAttribute("aria-selected", String(b === tab));
    galleryTab = tab.dataset.tab;
    renderGallery();
  });
  $("galleryReveal").addEventListener("click", async () => {
    try { await api("/api/reveal", { target: "data" }); }
    catch (err) { termLine(`[studio] ${err.message}`, "e"); }
  });

  $("resetBtn").addEventListener("click", async () => {
    // every click confirms first; confirming clears the references too
    const yes = await ask({ title: t("resetTitle"), message: t("resetMsg"), ok: t("resetPill") });
    if (!yes) return;
    try {
      await api("/api/inputs/clear", { session: ui.session });
      await loadInputs();
    } catch (err) {
      termLine(`[studio] ${err.message}`, "e");
    }
    resetParameters();
  });

  $("termTabs").addEventListener("click", (e) => {
    const tab = e.target.closest("button[data-tab]");
    if (!tab) return;
    for (const b of $("termTabs").children) b.setAttribute("aria-selected", String(b === tab));
    $("term").hidden = tab.dataset.tab !== "output";
    $("renderLog").hidden = tab.dataset.tab !== "render";
    $("termClear").hidden = tab.dataset.tab !== "output";
  });
  $("termClear").addEventListener("click", () => $("term").replaceChildren());
}

async function start() {
  applyStaticLang();
  wire();
  const cfg = await api("/api/config");
  renderPaths(cfg.paths);
  ui.dirs = { data: cfg.data_dir, input: cfg.input_dir, output: cfg.output_dir };
  ui.session = cfg.active;
  renderSessions(cfg.sessions.includes(cfg.active) ? cfg.sessions : [cfg.active, ...cfg.sessions]);
  applySettings(cfg.settings);
  await Promise.all([loadInputs(), loadTakes()]);
  connectEvents();
}

start().catch((err) => {
  $("lamp").className = "dot off";
  $("lampText").textContent = err.message;
});
