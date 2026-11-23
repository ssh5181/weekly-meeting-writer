"use strict";

const CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";
const $ = (s) => document.querySelector(s);
const state = { data: null, meta: { dept: "", team: "", leader: "" }, filenameTouched: false };

/* ---------- 유틸 ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function mdToHtml(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
}
function htmlToMd(el) {
  let out = "";
  el.childNodes.forEach((n) => {
    if (n.nodeType === Node.TEXT_NODE) out += n.textContent;
    else if (n.nodeType === Node.ELEMENT_NODE) {
      const tag = n.tagName;
      if (tag === "BR") out += " ";
      else if (tag === "B" || tag === "STRONG") { const t = htmlToMd(n); out += t.trim() ? `**${t}**` : t; }
      else out += htmlToMd(n);
    }
  });
  return out.replace(/ /g, " ").replace(/\*\*\*\*/g, "");
}
function setStatus(msg, kind = "") {
  const el = $("#status");
  el.textContent = msg;
  el.className = "status " + kind;
}
function edit(path, text, ph = "", tag = "span", extraClass = "") {
  return `<${tag} class="txt ${extraClass}" contenteditable="true" spellcheck="false" data-path="${path}" data-ph="${esc(ph)}">${mdToHtml(text)}</${tag}>`;
}
const toolsHtml = () => $("#tpl-item-tools").innerHTML;
const isTotalRow = (row) => ["합계", "계", "총계", "소계"].includes((row[0] || "").replace(/\s/g, ""));

/* ---------- 경로로 상태 읽고 쓰기 ---------- */
function resolve(path) {
  // 예: a.0.title / a.0.s.1.text / a.0.s.1.i.2.text / a.0.s.1.i.2.cell.-1.3 / a.0.kpi
  const p = path.split(".");
  const ag = state.data.agendas[+p[1]];
  if (p[2] === "s") {
    const sec = ag.sections[+p[3]];
    if (p[4] === "i") {
      const it = sec.items[+p[5]];
      if (p[6] === "cell") {
        const r = +p[7], c = +p[8];
        return r < 0 ? { obj: it.header, key: c } : { obj: it.rows[r], key: c };
      }
      return { obj: it, key: p[6] };
    }
    return { obj: sec, key: p[4] };
  }
  return { obj: ag, key: p[2] };
}

/* ---------- 렌더링 ---------- */
function renderItem(it, ai, si, ii) {
  const base = `a.${ai}.s.${si}.i.${ii}`;
  const data = `data-a="${ai}" data-s="${si}" data-i="${ii}"`;
  if (it.type === "table") {
    const head = it.header.map((h, c) => `<th>${edit(`${base}.cell.-1.${c}`, h, "", "div")}</th>`).join("");
    const rows = it.rows.map((row, r) => {
      const cls = isTotalRow(row) ? ' class="total"' : "";
      const tds = row.map((v, c) => {
        const al = isTotalRow(row) && c === 0 ? "center" : (it.align?.[c] || "center");
        return `<td style="text-align:${al}">${edit(`${base}.cell.${r}.${c}`, v, "", "div")}</td>`;
      }).join("");
      return `<tr${cls}>${tds}</tr>`;
    }).join("");
    return `<div class="tblock" data-item ${data}>${toolsHtml()}
      <table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>
      <div class="tbl-actions" contenteditable="false">
        <button data-act="row+">+ 행</button><button data-act="row-">− 행</button>
        <button data-act="col+">+ 열</button><button data-act="col-">− 열</button>
      </div></div>`;
  }
  const ph = { heading: "가. 중항목", bullet: "세부항목", note: "* 참고 문구", text: "내용" }[it.type] || "";
  return `<div class="line ${it.type}" data-item ${data}>${edit(`${base}.text`, it.text, ph)}${toolsHtml()}</div>`;
}

function render() {
  const box = $("#agendas");
  const ags = state.data.agendas;
  box.innerHTML = ags.map((a, ai) => {
    const num = CIRCLED[ai] || `${ai + 1}.`;
    const secs = a.sections.map((s, si) => {
      const showText = s.kind === "purpose" || (s.text || "").trim();
      const head = `<div class="sec" data-sec data-a="${ai}" data-s="${si}">
          ${edit(`a.${ai}.s.${si}.label`, s.label, "항목명", "span", "label")}${showText ? ": " + edit(`a.${ai}.s.${si}.text`, s.text, "내용") : ""}
          <span class="tools" contenteditable="false">
            <button data-act="sec-up" title="위로">▲</button><button data-act="sec-down" title="아래로">▼</button>
            <button data-act="sec-del" title="대항목 삭제">✕</button>
          </span></div>`;
      const items = s.items.map((it, ii) => renderItem(it, ai, si, ii)).join("");
      const add = s.kind === "purpose" && !s.items.length ? "" : `<div class="sec-add" contenteditable="false"><select data-act="sec-add" data-a="${ai}" data-s="${si}" aria-label="항목 추가">
          <option value="">+ 이 항목에 추가</option><option value="heading">가. 중항목</option><option value="bullet">- 세부항목</option>
          <option value="note">* 참고</option><option value="text">일반 문장</option><option value="table">표</option></select></div>`;
      return head + items + add;
    }).join("");
    return `<div class="agenda" data-agenda="${ai}">
      <div class="agenda-tools" contenteditable="false">
        <button data-act="ag-up">▲ 위로</button><button data-act="ag-down">▼ 아래로</button>
        <button data-act="ag-sec">+ 대항목</button><button data-act="ag-del" style="color:var(--danger)">✕ 안건 삭제</button>
      </div>
      <div class="agenda-title"><span class="num">${num}</span> <span class="cat">[${edit(`a.${ai}.category`, a.category, "구분")}]</span> ${edit(`a.${ai}.title`, a.title, "사업명 및 추진 내용")}<span class="agenda-owner">(담당자: ${edit(`a.${ai}.owner`, a.owner, "이름")})</span></div>
      ${secs}
      <div class="kpi">${edit(`a.${ai}.kpi`, (a.kpi || "").replace(/^※\s*/, ""), "[성과지표 목표] 비워 두면 문서에 넣지 않아요")}</div>
    </div>`;
  }).join("");
  $("#empty").hidden = true;
  $("#paper").hidden = false;
  $("#btn-download").disabled = !ags.length;
}

function renderMeta() {
  $("#pv-dept").textContent = state.meta.dept;
  $("#pv-team").textContent = state.meta.team;
  $("#pv-leader").textContent = state.meta.leader;
  if (!state.filenameTouched) $("#filename").value = `주간회의(${state.meta.dept}_${state.meta.team}).hwpx`;
}

/* ---------- 편집 이벤트 ---------- */
$("#agendas").addEventListener("input", (e) => {
  const el = e.target.closest("[data-path]");
  if (!el) return;
  const { obj, key } = resolve(el.dataset.path);
  obj[key] = htmlToMd(el).trim();
  if (el.closest("td") && el.dataset.path.endsWith(".0")) {
    const tr = el.closest("tr");
    const row = [...tr.querySelectorAll("[data-path]")].map((x) => htmlToMd(x).trim());
    tr.classList.toggle("total", isTotalRow(row));
  }
});
$("#agendas").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches("[data-path]")) { e.preventDefault(); e.target.blur(); }
});
$("#agendas").addEventListener("paste", (e) => {
  if (!e.target.closest("[data-path]")) return;
  e.preventDefault();
  const text = (e.clipboardData.getData("text/plain") || "").replace(/\s*\n\s*/g, " ");
  document.execCommand("insertText", false, text);
});

function newItem(type) {
  if (type === "table") return { type, header: ["구분", "내용", "비고"], rows: [["", "", ""]], align: ["center", "left", "center"] };
  return { type, text: type === "heading" ? "가. " : "" };
}
function move(arr, i, d) {
  const j = i + d;
  if (j < 0 || j >= arr.length) return;
  [arr[i], arr[j]] = [arr[j], arr[i]];
}

function handleAction(el) {
  const act = el.dataset.act;
  const ags = state.data.agendas;
  const agEl = el.closest("[data-agenda]");
  const ai = agEl ? +agEl.dataset.agenda : -1;
  const itemEl = el.closest("[data-item]");
  const secEl = el.closest("[data-sec]");

  if (act.startsWith("ag-")) {
    if (act === "ag-up") move(ags, ai, -1);
    if (act === "ag-down") move(ags, ai, 1);
    if (act === "ag-del" && confirm("이 안건을 삭제할까요?")) ags.splice(ai, 1);
    if (act === "ag-sec") ags[ai].sections.push({ kind: "other", label: "새 항목", text: "", items: [] });
  } else if (act.startsWith("sec-") && act !== "sec-add") {
    const si = +secEl.dataset.s, secs = ags[ai].sections;
    if (act === "sec-up") move(secs, si, -1);
    if (act === "sec-down") move(secs, si, 1);
    if (act === "sec-del" && confirm("이 대항목과 아래 내용을 모두 삭제할까요?")) secs.splice(si, 1);
  } else if (act === "sec-add") {
    if (!el.value) return;
    ags[+el.dataset.a].sections[+el.dataset.s].items.push(newItem(el.value));
  } else if (itemEl) {
    const si = +itemEl.dataset.s, ii = +itemEl.dataset.i;
    const items = ags[+itemEl.dataset.a].sections[si].items;
    const it = items[ii];
    if (act === "up") move(items, ii, -1);
    if (act === "down") move(items, ii, 1);
    if (act === "del") items.splice(ii, 1);
    if (act === "add") { if (!el.value) return; items.splice(ii + 1, 0, newItem(el.value)); }
    if (act === "type") { if (!el.value || it.type === "table") return; it.type = el.value; }
    if (act === "row+") it.rows.push(it.header.map(() => ""));
    if (act === "row-" && it.rows.length > 1) it.rows.pop();
    if (act === "col+") { it.header.push("새 열"); it.rows.forEach((r) => r.push("")); it.align.push("center"); }
    if (act === "col-" && it.header.length > 1) { it.header.pop(); it.rows.forEach((r) => r.pop()); it.align.pop(); }
  } else return;
  render();
}
$("#agendas").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-act]");
  if (b) handleAction(b);
});
$("#agendas").addEventListener("change", (e) => {
  if (e.target.matches("select[data-act]")) handleAction(e.target);
});
$("#btn-add-agenda").addEventListener("click", () => {
  state.data.agendas.push({
    number: 0, category: "육성", title: "", owner: "", kpi: "",
    sections: [
      { kind: "purpose", label: "목적", text: "", items: [] },
      { kind: "main", label: "주요내용", text: "", items: [newItem("bullet")] },
      { kind: "schedule", label: "향후 추진일정", text: "", items: [newItem("bullet")] },
    ],
  });
  render();
});

/* ---------- 불러오기 ---------- */
async function loadMarkdown(md, source) {
  setStatus("분석 중…");
  try {
    const r = await fetch("/api/parse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ markdown: md }) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "분석하지 못했어요.");
    state.data = j;
    render();
    renderMeta();
    setStatus(`${source}: 안건 ${j.agendas.length}건을 불러왔어요.`, "ok");
  } catch (err) {
    setStatus(err.message, "error");
  }
}
function readFile(file) {
  if (!file) return;
  if (file.size > 1_000_000) return setStatus("파일이 너무 커요 (1MB 이하).", "error");
  const fr = new FileReader();
  fr.onload = () => loadMarkdown(String(fr.result), file.name);
  fr.readAsText(file, "utf-8");
}
const dz = $("#dropzone");
$("#file").addEventListener("change", (e) => readFile(e.target.files[0]));
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") $("#file").click(); });
["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => readFile(e.dataTransfer.files[0]));
$("#btn-parse").addEventListener("click", () => {
  const md = $("#md-input").value;
  if (!md.trim()) return setStatus("붙여넣은 내용이 없어요.", "error");
  loadMarkdown(md, "붙여넣은 내용");
});
$("#btn-sample").addEventListener("click", async () => {
  const r = await fetch("/static/sample.md");
  loadMarkdown(await r.text(), "샘플 초안");
});

/* ---------- 머리 정보 ---------- */
["dept", "team", "leader"].forEach((k) => {
  $(`#meta-${k}`).addEventListener("input", (e) => { state.meta[k] = e.target.value.trim(); renderMeta(); });
});
$("#filename").addEventListener("input", () => { state.filenameTouched = true; });
(async () => {
  try {
    const d = await (await fetch("/api/defaults")).json();
    Object.assign(state.meta, d);
    ["dept", "team", "leader"].forEach((k) => ($(`#meta-${k}`).value = d[k]));
    renderMeta();
  } catch { /* 기본값 없이도 동작 */ }
})();

/* ---------- 다운로드 ---------- */
$("#btn-download").addEventListener("click", async () => {
  if (!state.data) return;
  document.activeElement?.blur?.();
  state.data.agendas.forEach((a, i) => (a.number = i + 1));
  const btn = $("#btn-download");
  btn.disabled = true;
  setStatus("hwpx 만드는 중…");
  try {
    const filename = $("#filename").value.trim() || "주간회의.hwpx";
    const r = await fetch("/api/build", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: state.data, meta: state.meta, filename }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || "만들지 못했어요.");
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename.endsWith(".hwpx") ? filename : filename + ".hwpx";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    setStatus("다운로드했어요.", "ok");
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    btn.disabled = false;
  }
});
