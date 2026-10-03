(function () {
  const RESULT_LABEL = {
    passed: "成功",
    failed: "失敗",
    skipped: "スキップ",
    inconclusive: "不明",
  };
  const FORMAT_LABEL = {
    junit: "JUnit",
  };
  const PALETTE = ["#1565c0", "#c62828", "#2e7d32", "#ef6c00", "#6a1b9a", "#00838f"];

  const state = { summary: null, index: null };
  const charts = [];
  const zipCache = new Map();
  let renderToken = 0;

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));
  }

  function asset(path) {
    return new URL(path, document.baseURI).href;
  }

  function currentHash() {
    const href = location.href;
    const index = href.indexOf("#");
    return index < 0 ? "" : href.slice(index + 1);
  }

  function parseRoute() {
    const hash = currentHash();
    if (hash === "" || hash === "/") return { name: "home" };
    const slash = hash.indexOf("/");
    const head = slash === -1 ? hash : hash.slice(0, slash);
    const tail = slash === -1 ? "" : hash.slice(slash + 1);
    if (head === "run" && tail) return { name: "run", id: decodeURIComponent(tail) };
    if (head === "file" && tail) return { name: "file", id: decodeURIComponent(tail) };
    if (head === "case" && tail) return { name: "case", id: decodeURIComponent(tail) };
    return { name: "missing" };
  }

  function hrefRun(id) {
    return `#run/${encodeURIComponent(id)}`;
  }

  function hrefFile(id) {
    return `#file/${encodeURIComponent(id)}`;
  }

  function hrefCase(id) {
    return `#case/${encodeURIComponent(id)}`;
  }

  function when(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return new Intl.DateTimeFormat("ja-JP", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Tokyo",
    }).format(date);
  }

  function percent(rate) {
    if (rate === null || rate === undefined) return "—";
    return `${(Number(rate) * 100).toFixed(1)}%`;
  }

  function seconds(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    if (number < 10) return `${number.toFixed(2)}s`;
    return `${number.toFixed(1)}s`;
  }

  function shortSha(sha) {
    return sha ? String(sha).slice(0, 7) : "—";
  }

  function badge(result) {
    const key = RESULT_LABEL[result] ? result : "inconclusive";
    return `<span class="badge ${key}">${esc(RESULT_LABEL[key])}</span>`;
  }

  function findRun(id) {
    return (state.summary.runs || []).find((run) => run.id === id);
  }

  function findFile(id) {
    for (const run of state.summary.runs || []) {
      const file = (run.files || []).find((item) => item.id === id);
      if (file) return { run, file };
    }
    return null;
  }

  function findCase(id) {
    return (state.summary.cases || []).find((item) => item.id === id);
  }

  function commitLink(run) {
    const sha = shortSha(run.sha);
    const repo = state.summary.repository;
    if (!run.sha || !repo) return esc(sha);
    const url = `https://github.com/${repo}/commit/${run.sha}`;
    return `<a href="${esc(url)}">${esc(sha)}</a>`;
  }

  function runLabel(run) {
    if (run.run_number) return `#${run.run_number}`;
    return run.id;
  }

  function statCards(totals) {
    const items = [
      ["成功率", percent(totals.success_rate)],
      ["成功", totals.passed],
      ["失敗", totals.failed],
      ["スキップ", totals.skipped],
      ["合計時間", seconds(totals.duration_seconds)],
    ];
    return `<div class="stats">${items
      .map(
        ([label, value]) =>
          `<article class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong></article>`,
      )
      .join("")}</div>`;
  }

  function fileRows(files) {
    return (files || [])
      .map(
        (file) => `<tr>
          <td><a href="${hrefFile(file.id)}">${esc(file.name)}</a></td>
          <td>${esc(file.tool)}</td>
          <td>${esc(FORMAT_LABEL[file.format] || file.format)}</td>
          <td>${badge(file.result)}</td>
          <td>${esc(percent(file.success_rate))}</td>
          <td>${esc(file.passed)}</td>
          <td>${esc(file.failed)}</td>
          <td>${esc(file.skipped)}</td>
          <td>${esc(seconds(file.duration_seconds))}</td>
        </tr>`,
      )
      .join("");
  }

  function filesTable(files) {
    if (!files || !files.length) return "<p>ファイルはありません。</p>";
    return `<div class="table-wrap"><table>
      <thead><tr>
        <th>ファイル</th><th>ツール</th><th>形式</th><th>結果</th>
        <th>成功率</th><th>成功</th><th>失敗</th><th>スキップ</th><th>合計時間</th>
      </tr></thead>
      <tbody>${fileRows(files)}</tbody>
    </table></div>`;
  }

  function clearCharts() {
    while (charts.length) charts.pop().destroy();
  }

  function chartRuns() {
    return (state.summary.runs || []).slice().reverse().slice(-60);
  }

  function drawCharts() {
    if (typeof Chart === "undefined") return;
    const runs = chartRuns();
    if (!runs.length) return;
    const labels = runs.map((run) => when(run.created_at));
    const rate = document.getElementById("rate-chart");
    const counts = document.getElementById("count-chart");
    if (rate) {
      const tools = [];
      for (const run of runs) {
        for (const tool of run.tools || []) {
          if (!tools.includes(tool.tool)) tools.push(tool.tool);
        }
      }
      charts.push(
        new Chart(rate, {
          type: "line",
          data: {
            labels,
            datasets: tools.map((tool, index) => ({
              label: tool,
              data: runs.map((run) => {
                const found = (run.tools || []).find((item) => item.tool === tool);
                return found ? found.success_rate : null;
              }),
              borderColor: PALETTE[index % PALETTE.length],
              backgroundColor: PALETTE[index % PALETTE.length],
              spanGaps: false,
              tension: 0.15,
            })),
          },
          options: chartOptions("成功率", (value) => percent(value)),
        }),
      );
    }
    if (counts) {
      charts.push(
        new Chart(counts, {
          type: "bar",
          data: {
            labels,
            datasets: [
              barSet("成功", runs.map((run) => run.totals.passed), "#2e7d32"),
              barSet("失敗", runs.map((run) => run.totals.failed), "#c62828"),
              barSet("スキップ", runs.map((run) => run.totals.skipped), "#78909c"),
              barSet("不明", runs.map((run) => run.totals.inconclusive), "#ef6c00"),
            ],
          },
          options: {
            ...chartOptions("件数", (value) => String(value)),
            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
          },
        }),
      );
    }
  }

  function barSet(label, data, color) {
    return { label, data, backgroundColor: color };
  }

  function chartOptions(title, tick) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: { display: true, text: title },
        tooltip: {
          callbacks: {
            label(context) {
              const value = context.parsed.y;
              return `${context.dataset.label}: ${tick(value)}`;
            },
          },
        },
      },
    };
  }

  function drawCaseChart(item) {
    if (typeof Chart === "undefined") return;
    const canvas = document.getElementById("case-chart");
    if (!canvas) return;
    const points = item.points || [];
    charts.push(
      new Chart(canvas, {
        type: "line",
        data: {
          labels: points.map((point) => when(point.created_at)),
          datasets: [
            {
              label: "時間",
              data: points.map((point) => point.duration_seconds),
              borderColor: "#1565c0",
              backgroundColor: "#1565c0",
              tension: 0.15,
            },
          ],
        },
        options: chartOptions("所要時間", (value) => seconds(value)),
      }),
    );
  }

  function homeHtml() {
    const runs = state.summary.runs || [];
    const latest = runs[0];
    if (!latest) return "<p>まだテスト結果がありません。</p>";
    const failed = (state.summary.cases || []).filter((item) => item.latest_result === "failed");
    const caseRows = (state.summary.cases || [])
      .slice()
      .sort((a, b) => rank(a.latest_result) - rank(b.latest_result) || a.id.localeCompare(b.id))
      .map(
        (item) => `<tr data-case="${esc(`${item.id} ${item.name}`)}">
          <td>${badge(item.latest_result)}</td>
          <td class="wrap"><a href="${hrefCase(item.id)}"><code>${esc(item.id)}</code></a></td>
          <td>${esc(when(item.latest_at))}</td>
        </tr>`,
      )
      .join("");
    return `
      <p>最新の実行 ${esc(when(latest.created_at))} / ${commitLink(latest)}
        ${latest.url ? `/ <a href="${esc(latest.url)}">ログ</a>` : ""}</p>
      ${statCards(latest.totals)}
      <h2>ツール</h2>
      ${toolsTable(latest.tools)}
      <h2>この実行のファイル</h2>
      ${filesTable(latest.files)}
      <h2>成功率の推移</h2>
      <div class="chart-box"><canvas id="rate-chart"></canvas></div>
      <h2>件数の推移</h2>
      <div class="chart-box"><canvas id="count-chart"></canvas></div>
      <h2>実行一覧</h2>
      ${runsTable(runs)}
      <h2>失敗 ${failed.length} 件</h2>
      ${failed.length ? caseList(failed.slice(0, 30)) : "<p>最新の結果で失敗しているテストはありません。</p>"}
      <h2>テスト項目</h2>
      <input id="case-filter" type="search" placeholder="名前で絞り込む" aria-label="テスト項目を絞り込む" />
      <div class="table-wrap"><table>
        <thead><tr><th>最新</th><th>テスト</th><th>日時</th></tr></thead>
        <tbody>${caseRows}</tbody>
      </table></div>`;
  }

  function rank(result) {
    return { failed: 0, inconclusive: 1, skipped: 2, passed: 3 }[result] ?? 9;
  }

  function toolsTable(tools) {
    if (!tools || !tools.length) return "<p>ツールはありません。</p>";
    const rows = tools
      .map(
        (tool) => `<tr>
          <td>${esc(tool.tool)}</td>
          <td>${esc(tool.files)}</td>
          <td>${badge(tool.result)}</td>
          <td>${esc(percent(tool.success_rate))}</td>
          <td>${esc(tool.passed)}</td>
          <td>${esc(tool.failed)}</td>
          <td>${esc(tool.skipped)}</td>
        </tr>`,
      )
      .join("");
    return `<div class="table-wrap"><table>
      <thead><tr><th>ツール</th><th>ファイル</th><th>結果</th><th>成功率</th><th>成功</th><th>失敗</th><th>スキップ</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
  }

  function runsTable(runs) {
    const rows = runs
      .map(
        (run) => `<tr>
          <td><a href="${hrefRun(run.id)}">${esc(when(run.created_at))}</a></td>
          <td>${commitLink(run)}</td>
          <td>${badge(run.totals.result)}</td>
          <td>${esc(percent(run.totals.success_rate))}</td>
          <td>${esc(run.totals.passed)}</td>
          <td>${esc(run.totals.failed)}</td>
          <td>${esc(run.totals.files)}</td>
          <td>${run.url ? `<a href="${esc(run.url)}">${esc(runLabel(run))}</a>` : esc(runLabel(run))}</td>
        </tr>`,
      )
      .join("");
    return `<div class="table-wrap"><table>
      <thead><tr>
        <th>日時</th><th>コミット</th><th>結果</th><th>成功率</th>
        <th>成功</th><th>失敗</th><th>ファイル</th><th>ログ</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
  }

  function caseList(items) {
    const rows = items
      .map(
        (item) => `<tr>
          <td>${badge(item.latest_result)}</td>
          <td class="wrap"><a href="${hrefCase(item.id)}"><code>${esc(item.id)}</code></a></td>
        </tr>`,
      )
      .join("");
    return `<div class="table-wrap"><table><tbody>${rows}</tbody></table></div>`;
  }

  function runHtml(run) {
    return `
      <p><a href="#/">トップ</a></p>
      <h2>${esc(when(run.created_at))}</h2>
      <p>${commitLink(run)} / ${esc(run.ref || "")} / ${esc(run.actor || "")}
        ${run.url ? `/ <a href="${esc(run.url)}">ログ</a>` : ""}</p>
      ${statCards(run.totals)}
      <h3>ツール</h3>
      ${toolsTable(run.tools)}
      <h3>ファイル</h3>
      ${filesTable(run.files)}`;
  }

  function caseHtml(item) {
    const rows = (item.points || [])
      .slice()
      .reverse()
      .map((point) => {
        const located = findFile(point.file_id);
        const fileLink = located
          ? `<a href="${hrefFile(point.file_id)}">${esc(located.file.name)}</a>`
          : esc(point.file_id);
        return `<tr>
          <td>${esc(when(point.created_at))}</td>
          <td>${badge(point.result)}</td>
          <td>${esc(seconds(point.duration_seconds))}</td>
          <td>${fileLink}</td>
          <td><a href="${hrefRun(point.run_id)}">実行</a></td>
        </tr>`;
      })
      .join("");
    return `
      <p><a href="#/">トップ</a></p>
      <h2><code>${esc(item.id)}</code></h2>
      <p>最新 ${badge(item.latest_result)} / ${esc(when(item.latest_at))}</p>
      <div class="chart-box"><canvas id="case-chart"></canvas></div>
      <div class="table-wrap"><table>
        <thead><tr><th>日時</th><th>結果</th><th>時間</th><th>ファイル</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  }

  function localName(node) {
    return node.localName || (node.tagName || "").replace(/^.*:/, "");
  }

  function resultFromChildren(node) {
    const tags = new Set([...node.children].map(localName));
    if (tags.has("failure") || tags.has("error")) return "failed";
    if (tags.has("skipped")) return "skipped";
    return "passed";
  }

  function messageOf(node) {
    for (const child of node.children) {
      const tag = localName(child);
      if (!["failure", "error", "skipped"].includes(tag)) continue;
      for (const grand of child.children) {
        if (localName(grand) === "message" && grand.textContent.trim()) {
          return grand.textContent.trim();
        }
      }
      const attr = child.getAttribute("message");
      if (attr) return attr.trim();
      const text = (child.textContent || "").trim();
      if (text) return text;
    }
    return "";
  }

  function xmlCases(doc) {
    const cases = [];
    for (const node of doc.getElementsByTagName("testcase")) {
      const name = node.getAttribute("name") || "(unknown)";
      const classname = node.getAttribute("classname") || "";
      const file = (node.getAttribute("file") || "").replaceAll("\\", "/");
      let id = name;
      if (file && name) id = `${file}::${name}`;
      else if (classname && name) id = `${classname}::${name}`;
      cases.push({
        id,
        name,
        result: resultFromChildren(node),
        duration: Number(node.getAttribute("time") || 0),
        message: messageOf(node),
      });
    }
    return cases;
  }

  function loadZip(path) {
    let pending = zipCache.get(path);
    if (pending) return pending;
    pending = fetch(asset(path))
      .then((response) => {
        if (!response.ok) throw new Error(`zip を取得できませんでした (${response.status})`);
        return response.arrayBuffer();
      })
      .then((buffer) => {
        if (typeof fflate === "undefined" || !fflate.unzipSync) {
          throw new Error("zip を解凍するライブラリが読み込まれていません。");
        }
        return fflate.unzipSync(new Uint8Array(buffer));
      })
      .catch((error) => {
        zipCache.delete(path);
        throw error;
      });
    zipCache.set(path, pending);
    return pending;
  }

  async function readXml(fileId) {
    const located = state.index && state.index.files ? state.index.files[fileId] : null;
    if (!located) throw new Error("XML の索引にこのファイルがありません。");
    const entries = await loadZip(located.zip);
    const bytes = entries[located.name];
    if (!bytes) throw new Error("zip の中に XML がありません。");
    return new TextDecoder().decode(bytes);
  }

  async function fileHtml(found) {
    const text = await readXml(found.file.id);
    const doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.querySelector("parsererror")) throw new Error("XML を読めませんでした");
    const xmlUrl = URL.createObjectURL(new Blob([text], { type: "application/xml" }));
    const cases = xmlCases(doc);
    const rows = cases
      .map(
        (item) => `<tr>
          <td>${badge(item.result)}</td>
          <td class="wrap"><a href="${hrefCase(item.id)}"><code>${esc(item.id)}</code></a></td>
          <td>${esc(seconds(item.duration))}</td>
        </tr>
        ${
          item.message
            ? `<tr><td></td><td class="wrap" colspan="2"><pre class="message">${esc(item.message)}</pre></td></tr>`
            : ""
        }`,
      )
      .join("");
    return `
      <p><a href="#/">トップ</a> / <a href="${hrefRun(found.run.id)}">この実行</a></p>
      <h2>${esc(found.file.name)}</h2>
      <p>${esc(found.file.tool)} / ${esc(FORMAT_LABEL[found.file.format] || found.file.format)}
        / <a href="${esc(xmlUrl)}" download="${esc(found.file.name)}">XML を開く</a></p>
      ${statCards(found.file)}
      <div class="table-wrap"><table>
        <thead><tr><th>結果</th><th>テスト</th><th>時間</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="3">テストケースはありません。</td></tr>`}</tbody>
      </table></div>`;
  }

  function bindHome() {
    const input = document.getElementById("case-filter");
    if (!input) return;
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      for (const row of document.querySelectorAll("[data-case]")) {
        const hay = (row.getAttribute("data-case") || "").toLowerCase();
        row.hidden = query !== "" && !hay.includes(query);
      }
    });
  }

  async function render() {
    const token = ++renderToken;
    clearCharts();
    const app = document.getElementById("app");
    const route = parseRoute();
    try {
      if (route.name === "home") {
        app.innerHTML = homeHtml();
        if (token !== renderToken) return;
        bindHome();
        drawCharts();
        return;
      }
      if (route.name === "run") {
        const run = findRun(route.id);
        app.innerHTML = run ? runHtml(run) : "<p>実行が見つかりません。</p>";
        return;
      }
      if (route.name === "case") {
        const item = findCase(route.id);
        app.innerHTML = item ? caseHtml(item) : "<p>テストが見つかりません。</p>";
        if (token !== renderToken) return;
        if (item) drawCaseChart(item);
        return;
      }
      if (route.name === "file") {
        app.innerHTML = "<p aria-busy='true'>XML を読み込み中…</p>";
        const found = findFile(route.id);
        if (!found) {
          app.innerHTML = "<p>ファイルが見つかりません。</p>";
          return;
        }
        const html = await fileHtml(found);
        if (token !== renderToken) return;
        app.innerHTML = html;
        return;
      }
      app.innerHTML = `<p>ページが見つかりません。</p><p><a href="#/">トップ</a></p>`;
    } catch (error) {
      if (token !== renderToken) return;
      app.textContent = error && error.message ? error.message : String(error);
    }
  }

  async function init() {
    const app = document.getElementById("app");
    try {
      const [summaryResponse, indexResponse] = await Promise.all([
        fetch(asset("summary.json")),
        fetch(asset("xml-index.json")),
      ]);
      if (!summaryResponse.ok) throw new Error(`summary.json を取得できませんでした (${summaryResponse.status})`);
      if (!indexResponse.ok) throw new Error(`xml-index.json を取得できませんでした (${indexResponse.status})`);
      state.summary = await summaryResponse.json();
      state.index = await indexResponse.json();
      if (state.summary.schema_version !== 1) {
        throw new Error("このページでは読めない summary.json です。");
      }
      if (state.index.schema_version !== 1) {
        throw new Error("このページでは読めない xml-index.json です。");
      }
      const repo = document.getElementById("repo");
      const generated = document.getElementById("generated");
      if (state.summary.repository) {
        repo.textContent = state.summary.repository;
        document.title = `${state.summary.repository} のテスト結果`;
      }
      generated.textContent = when(state.summary.generated_at);
      window.addEventListener("hashchange", () => {
        render();
      });
      await render();
    } catch (error) {
      app.textContent = error && error.message ? error.message : String(error);
    }
  }

  init();
})();
