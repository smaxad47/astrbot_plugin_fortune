const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;
const $ = (id) => document.getElementById(id);

const badge = $("status-badge");
const themesEl = $("themes");
const imagesEl = $("images");
const dirEl = $("dir");
const urlEl = $("url");
const btn = $("download");
const refreshBtn = $("refresh");
const pw = $("progress-wrap");
const bar = $("bar");
const ptext = $("progress-text");
const logEl = $("log");

let polling = null;

function log(msg) {
  const t = new Date().toLocaleTimeString();
  logEl.textContent += `[${t}] ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function fmtBytes(n) {
  n = Number(n) || 0;
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(1) + " " + u[i];
}

function renderStatus(s) {
  const ready = !!s.ready;
  if (!ready) { badge.textContent = "未安装"; badge.className = "badge warn"; }
  else if (s.source === "downloaded") { badge.textContent = "已安装（下载）"; badge.className = "badge ok"; }
  else { badge.textContent = "已安装（自带）"; badge.className = "badge ok"; }
  themesEl.textContent = s.themes ?? "-";
  imagesEl.textContent = s.images ?? "-";
  dirEl.textContent = s.resource_dir || "-";
  if (s.url && !urlEl.value) urlEl.value = s.url;
}

async function refresh() {
  try {
    const s = await bridge.apiGet("status");
    renderStatus(s);
    if (s.downloading) poll();
  } catch (e) {
    log("读取状态失败: " + e.message);
  }
}

function updateProgress(p) {
  const total = p.total || 0;
  const done = p.downloaded || 0;
  pw.classList.remove("hidden");
  let pct = total ? Math.min(100, (done / total) * 100) : (p.status === "done" ? 100 : 0);
  bar.style.width = pct.toFixed(1) + "%";
  const size = total ? `(${fmtBytes(done)} / ${fmtBytes(total)})` : `(${fmtBytes(done)})`;
  ptext.textContent = `${p.message || ""} ${size}`;
}

async function poll() {
  if (polling) return;
  polling = setInterval(async () => {
    try {
      const p = await bridge.apiGet("progress");
      updateProgress(p);
      if (p.status !== "downloading") {
        clearInterval(polling);
        polling = null;
        btn.disabled = false;
        log(p.message || p.status);
        await refresh();
      }
    } catch (e) { /* 忽略偶发错误，继续轮询 */ }
  }, 800);
}

async function startDownload() {
  const url = urlEl.value.trim();
  btn.disabled = true;
  logEl.textContent = "";
  pw.classList.remove("hidden");
  try {
    const r = await bridge.apiPost("download", { url, save: true });
    log(r.message || "已开始");
    poll();
  } catch (e) {
    log("下载失败: " + e.message);
    btn.disabled = false;
  }
}

btn.addEventListener("click", startDownload);
refreshBtn.addEventListener("click", () => { logEl.textContent = ""; refresh(); });

(async () => {
  try { await bridge.ready(); } catch (e) { /* ignore */ }
  await refresh();
})();
