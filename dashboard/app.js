// Cartoon Dash Dashboard — renders dashboard/data.json + live GitHub runs.

const REPO = "Gilbert231-dot/cartoon-clipper";
const GITHUB_API = `https://api.github.com/repos/${REPO}/actions/runs?per_page=5`;

async function loadJSON(url, attempts = 3) {
    // Retry with backoff: the GitHub API rate-limits unauthenticated IPs, so
    // a single cold fetch can fail while the next one succeeds.
    let lastErr = null;
    for (let i = 0; i < attempts; i++) {
        try {
            const res = await fetch(url, { cache: "no-store" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            lastErr = err;
            console.warn(`Attempt ${i + 1}/${attempts} failed for ${url}:`, err);
            await new Promise(r => setTimeout(r, 700 * (i + 1)));
        }
    }
    return { __error: lastErr ? lastErr.message : "unknown" };
}

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
}

function fmtTime(iso) {
    return new Date(iso).toLocaleString(undefined, {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
}

function countdown(iso) {
    const diff = new Date(iso).getTime() - Date.now();
    if (diff <= 0) return "LIVE";
    const s = Math.floor(diff / 1000);
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function renderCards(d) {
    const cards = document.getElementById("stat-cards");
    cards.innerHTML = "";
    const defs = [
        { label: "Total clips scheduled", value: d.total_clips, cls: "",
          sub: `${d.clips_per_day} per day` },
        { label: "Upcoming", value: d.scheduled_count, cls: "blue",
          sub: d.next_publish_utc ? `next ${fmtTime(d.next_publish_utc)}` : "none scheduled" },
        { label: "Published", value: d.published_count, cls: "green",
          sub: d.last_publish_utc ? `last ${fmtTime(d.last_publish_utc)}` : "none yet" },
        { label: "Next publish", value: d.next_publish_utc ? countdown(d.next_publish_utc) : "—",
          cls: "green", sub: d.next_publish_utc ? fmtTime(d.next_publish_utc) : "all clips published" },
    ];
    for (const def of defs) {
        const card = el("div", "card");
        card.appendChild(el("div", "label", def.label));
        card.appendChild(el("div", `value ${def.cls}`, String(def.value)));
        card.appendChild(el("div", "sub", def.sub));
        cards.appendChild(card);
    }
}

function renderClips(rows, listId, hintId) {
    const list = document.getElementById(listId);
    list.innerHTML = "";
    if (hintId) document.getElementById(hintId).textContent = `(${rows.length} total)`;
    if (!rows.length) {
        list.appendChild(el("p", "empty", "Nothing here yet."));
        return;
    }
    for (const r of rows) {
        const item = el("li", "clip-item");

        const info = el("div", "clip-info");
        const a = el("a", "", r.episode);
        a.href = r.url || "#";
        a.target = "_blank";
        info.appendChild(a);
        const meta = el("div", "clip-meta");
        meta.appendChild(el("span", "slot", fmtTime(r.publish_at)));
        meta.appendChild(el("span", "run-meta", `${r.duration}s`));
        info.appendChild(meta);

        const right = el("div", "clip-right");
        const cd = el("span", "countdown", countdown(r.publish_at));
        cd.dataset.iso = r.publish_at;
        right.appendChild(cd);

        item.append(info, right);
        list.appendChild(item);
    }
}

// Refresh the countdowns every 30s.
setInterval(() => {
    document.querySelectorAll(".countdown[data-iso]").forEach(node => {
        const live = new Date(node.dataset.iso).getTime() - Date.now() <= 0;
        node.textContent = countdown(node.dataset.iso);
        node.classList.toggle("live", live);
    });
}, 30000);

function statusBadge(state) {
    const labels = {
        posted: "posted", success: "success", failure: "failed", failed: "failed",
        cancelled: "cancelled", in_progress: "in progress", queued: "queued",
        skipped: "skipped", startup_failure: "startup failure",
    };
    const cls = state === "failed" ? "failure" : state;
    return el("span", `status ${cls}`, labels[state] || state);
}

function statusPill(run) {
    const done = run.status === "completed";
    const state = done ? (run.conclusion || "completed") : run.status;
    return statusBadge(state);
}

function renderRuns(data) {
    const list = document.getElementById("run-list");
    list.innerHTML = "";
    if (data && data.__error) {
        list.appendChild(el("p", "empty",
            `Could not reach the GitHub API (${data.__error}) — run status unavailable.`));
        return;
    }
    const runs = (data && data.workflow_runs) || [];
    if (!runs.length) {
        list.appendChild(el("p", "empty", "No pipeline runs found yet."));
        return;
    }
    for (const run of runs) {
        const item = el("li", "run-item");
        const a = el("a", "", run.name || "workflow");
        a.href = run.html_url;
        a.target = "_blank";
        item.append(statusPill(run), a);
        const when = new Date(run.created_at).toLocaleString(undefined, {
            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        });
        item.appendChild(el("span", "run-meta", when));
        list.appendChild(item);
    }
}

async function main() {
    const data = await loadJSON("data.json");

    if (data && !data.__error) {
        document.getElementById("channel-name").textContent = data.channel || "Cartoon_dash";
        document.getElementById("slots").textContent = (data.slots || []).join(", ");
        document.getElementById("generated-at").textContent =
            `Schedule data generated ${new Date(data.generated_at).toLocaleString()}.`;

        renderCards(data);
        renderClips(data.upcoming, "upcoming-list", "upcoming-hint");
        renderClips(data.published, "published-list", null);
    } else {
        document.getElementById("generated-at").textContent =
            "⚠️ data.json not found — run dashboard/build_data.py first.";
    }

    renderRuns(await loadJSON(GITHUB_API));
}

main();
