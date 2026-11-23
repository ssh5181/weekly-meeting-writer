"use strict";

const $ = (s) => document.querySelector(s);
const state = { files: [] }; // {name, data(base64), dept, team, agendas, order, ok, error, seq}
let seq = 0;

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function setStatus(msg, kind = "") {
  const el = $("#status");
  el.textContent = msg;
  el.className = "status " + kind;
}
// 다음(또는 오늘) 수요일 14:00
function nextMeeting() {
  const d = new Date();
  d.setDate(d.getDate() + ((3 - d.getDay() + 7) % 7));
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}. ${p(d.getMonth() + 1)}. ${p(d.getDate())}.(수) 14:00`.replace(/ 0(\d)\./g, " $1.");
}
function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

function render() {
  const ok = state.files.filter((f) => f.ok);
  $("#empty").hidden = state.files.length > 0;
  $("#btn-merge").disabled = ok.length === 0;
  let prevDept = null, n = 0;
  $("#list").innerHTML = state.files.map((f, i) => {
    if (!f.ok) {
      return `<li class="file-row bad" data-i="${i}"><span class="no">!</span>
        <div><div class="team">${esc(f.name)}</div><div class="meta">${esc(f.error)}</div></div>
        <span class="acts"><button data-act="del" title="빼기">✕</button></span></li>`;
    }
    n += 1;
    const sep = f.dept && f.dept !== prevDept ? `<div class="dept-sep">${esc(f.dept)}</div>` : "";
    if (f.dept) prevDept = f.dept;
    return `${sep}<li class="file-row" data-i="${i}"><span class="no">${n}</span>
      <div><div class="team">${esc(f.team || "(팀 이름을 찾지 못했어요)")}</div>
      <div class="meta">${esc(f.name)} · 안건 ${f.agendas}건</div></div>
      <span class="acts"><button data-act="up" title="위로">▲</button><button data-act="down" title="아래로">▼</button>
      <button data-act="del" title="빼기">✕</button></span></li>`;
  }).join("");
}

async function addFiles(list) {
  const files = [...list].filter((f) => /\.hwpx$/i.test(f.name));
  if (!files.length) return setStatus("hwpx 파일만 올릴 수 있어요.", "error");
  setStatus("파일 확인 중…");
  try {
    const payload = [];
    for (const f of files) payload.push({ name: f.name, data: toBase64(await f.arrayBuffer()) });
    const r = await fetch("/api/inspect", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ files: payload }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "파일을 확인하지 못했어요.");
    j.files.forEach((info, k) => {
      const dup = state.files.findIndex((x) => x.name === info.name);
      const item = { ...info, data: payload[k].data, seq: seq++ };
      if (dup >= 0) state.files[dup] = item; else state.files.push(item);
    });
    state.files.sort((a, b) => (a.ok === b.ok ? 0 : a.ok ? -1 : 1) || (a.order ?? 99) - (b.order ?? 99) || a.seq - b.seq);
    render();
    const bad = j.files.filter((f) => !f.ok).length;
    setStatus(`${j.files.length - bad}개 파일을 추가했어요.${bad ? ` (${bad}개는 읽지 못했어요)` : ""}`, bad ? "error" : "ok");
  } catch (err) {
    setStatus(err.message, "error");
  }
}

$("#list").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-act]");
  if (!b) return;
  const i = +b.closest("[data-i]").dataset.i;
  const a = state.files;
  if (b.dataset.act === "del") a.splice(i, 1);
  if (b.dataset.act === "up" && i > 0) [a[i - 1], a[i]] = [a[i], a[i - 1]];
  if (b.dataset.act === "down" && i < a.length - 1 && a[i + 1].ok) [a[i + 1], a[i]] = [a[i], a[i + 1]];
  render();
});

const dz = $("#dropzone");
$("#files").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") $("#files").click(); });
["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

$("#cover-date").value = nextMeeting();
$("#cover-on").addEventListener("change", (e) => {
  $("#cover-date").disabled = $("#cover-place").disabled = !e.target.checked;
});
const ymd = (s) => (s.match(/(\d{2})(\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})/) || []).slice(2).map((x) => x.padStart(2, "0")).join(".");
const defaultName = () => `주간회의_(${ymd($("#cover-date").value) || "합본"})_교육혁신처(전체).hwpx`;
let nameTouched = false;
$("#filename").value = defaultName();
$("#filename").addEventListener("input", () => { nameTouched = true; });
$("#cover-date").addEventListener("input", () => { if (!nameTouched) $("#filename").value = defaultName(); });

$("#btn-merge").addEventListener("click", async () => {
  const files = state.files.filter((f) => f.ok).map((f) => ({ name: f.name, data: f.data }));
  if (!files.length) return;
  const btn = $("#btn-merge");
  btn.disabled = true;
  setStatus("합본 만드는 중…");
  try {
    let filename = $("#filename").value.trim() || defaultName();
    if (!/\.hwpx$/i.test(filename)) filename += ".hwpx";
    const r = await fetch("/api/merge", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files, cover: $("#cover-on").checked, date: $("#cover-date").value, place: $("#cover-place").value, filename }),
    });
    if (!r.ok) {
      let msg = "합본을 만들지 못했어요.";
      try { msg = (await r.json()).detail || msg; } catch { if (r.status === 413) msg = "파일이 너무 커요. 파일 수를 줄여 주세요."; }
      throw new Error(msg);
    }
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    setStatus(`${files.length}개 팀 파일을 합쳐서 내려받았어요.`, "ok");
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    btn.disabled = false;
  }
});
render();
