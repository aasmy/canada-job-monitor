(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const jobs = JSON.parse($("job-data").textContent);
  const health = JSON.parse($("health-data").textContent);
  const icons = JSON.parse($("icon-data").textContent);
  const storageKey = "canada-job-hub-progress-v1";
  const esc = (value) =>
    String(value || "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const icon = (name) => icons[name] || "";
  const sourceNames = {
    greenhouse: "Greenhouse",
    lever: "Lever",
    ashby: "Ashby",
    simplify: "Simplify",
    hackernews: "Hacker News",
    web: "Web",
    linkedin: "LinkedIn",
    indeed: "Indeed",
    googlejobs: "Google Alerts",
  };
  const sourceName = (source) => sourceNames[source] || source;
  let progress = {};
  let view = "recent";
  let visibleLimit = 30;
  let undoAction = null;
  let toastTimer;
  const expanded = new Set();
  const resumeMatches = new Map();
  let previousResumeId = null;
  function resumeMatch(job) {
    const resume = window.ResumeHub?.selected();
    if (!resume) return null;
    if (!resumeMatches.has(job.id))
      resumeMatches.set(job.id, ResumeMatching.score(job, resume));
    return resumeMatches.get(job.id);
  }
  function matchScore(job) {
    return window.ResumeHub?.selected()
      ? (resumeMatch(job)?.score ?? null)
      : job.score;
  }
  function resumeDetails(job) {
    const match = resumeMatch(job);
    if (!match) return "";
    const resume = window.ResumeHub.selected();
    return `<section class="resume-comparison"><h3>Match with ${esc(resume.name)}</h3><p class="resume-evidence">${esc(match.evidence)}. ${esc(match.experience)}.</p>
      ${match.matched.length ? `<h4>Found in your resume</h4><div class="skill-list">${match.matched.map((skill) => `<span class="skill skill-matched">${esc(skill)}</span>`).join("")}</div>` : ""}
      ${match.missing.length ? `<h4>Listed skills not found in your resume</h4><div class="skill-list">${match.missing.map((skill) => `<span class="skill skill-missing">${esc(skill)}</span>`).join("")}</div>` : ""}
      ${match.preferredMatched.length || match.preferredMissing.length ? `<h4>Preferred skills</h4><p>Found: ${esc(match.preferredMatched.join(", ") || "None")}. Not found: ${esc(match.preferredMissing.join(", ") || "None")}.</p>` : ""}
      ${match.score !== null ? `<details class="score-breakdown"><summary>Score breakdown</summary><dl>${match.breakdown.map((item) => `<dt>${esc(item.label)} (${item.weight} weight)</dt><dd>${esc(item.detail)}</dd>`).join("")}</dl><p>Available categories are weighted and normalized to 100. Unstated requirements are not assumed.</p></details>` : ""}
    </section>`;
  }

  try {
    const loaded = JSON.parse(localStorage.getItem(storageKey) || "{}");
    if (loaded && typeof loaded === "object" && !Array.isArray(loaded)) {
      for (const [key, entry] of Object.entries(loaded)) {
        if (/^[a-f0-9]{24}$/.test(key) && entry && typeof entry === "object") {
          progress[key] = {
            saved: entry.saved === true,
            applied: entry.applied === true,
          };
        }
      }
    }
  } catch {
    $("storage-note").textContent =
      "Browser storage unavailable. Changes last for this visit.";
  }

  function persist() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(progress));
    } catch {
      $("storage-note").textContent =
        "Could not save in this browser. Changes last for this visit.";
    }
  }
  function installIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach((element) => {
      element.innerHTML = icon(element.dataset.icon);
      element.querySelector("svg")?.setAttribute("aria-hidden", "true");
    });
  }
  function daysOld(value) {
    const parsed = Date.parse(value);
    const days = (Date.now() - parsed) / 86400000;
    return Number.isFinite(days) && days >= 0 ? days : null;
  }
  function isRecent(job) {
    const age = daysOld(job.published);
    return age !== null && age <= 7;
  }
  function relative(value) {
    const days = daysOld(value);
    if (days === null) return "Unknown";
    if (days < 1 / 24) return "Just now";
    if (days < 1) return `${Math.floor(days * 24)}h ago`;
    if (days < 1.99) return "Yesterday";
    return `${Math.floor(days)} days ago`;
  }
  function absolute(value) {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed)
      ? new Date(parsed).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        })
      : "Unknown";
  }
  function saved(job) {
    return progress[job.id]?.saved === true;
  }
  function applied(job) {
    return progress[job.id]?.applied === true;
  }
  function dateMatch(job) {
    const age = daysOld(job.published);
    switch ($("freshness").value) {
      case "last7":
        return age !== null && age <= 7;
      case "fresh":
        return age !== null && age <= 1;
      case "recent":
        return age !== null && age <= 3;
      case "unknown":
        return age === null;
      case "older":
        return age !== null && age > 7;
      default:
        return true;
    }
  }
  function viewMatch(job) {
    if (view === "saved") return saved(job);
    if (view === "applied") return applied(job);
    if (view === "undated")
      return !applied(job) && daysOld(job.published) === null;
    if (view === "recent") return !applied(job);
    return true;
  }
  function initials(company) {
    const letters = company
      .replace(/[^a-zA-Z0-9 ]/g, "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    return letters.length > 1
      ? letters
          .slice(0, 2)
          .map((word) => word[0])
          .join("")
          .toUpperCase()
      : (letters[0] || "?").slice(0, 2).toUpperCase();
  }
  function updateCounts() {
    const recent = jobs.filter((job) => isRecent(job) && !applied(job)).length;
    $("recent-count").textContent = recent;
    $("count-recent").textContent = recent;
    $("count-saved").textContent = jobs.filter(saved).length;
    $("count-applied").textContent = jobs.filter(applied).length;
    $("count-undated").textContent = jobs.filter(
      (job) => !applied(job) && daysOld(job.published) === null,
    ).length;
    $("count-all").textContent = jobs.length;
  }
  function jobRow(job) {
    const open = expanded.has(job.id);
    const isSaved = saved(job);
    const isApplied = applied(job);
    const age = daysOld(job.published);
    const posted = age === null ? "Date unknown" : relative(job.published);
    const knownWorkplace = job.workplace !== "Not stated" ? job.workplace : "";
    const skills = job.skills
      .split(",")
      .map((skill) => skill.trim())
      .filter(Boolean);
    const personal = Boolean(window.ResumeHub?.selected());
    const score = matchScore(job);
    const scoreLabel =
      score === null
        ? "Not enough detail to score"
        : `${personal ? "Resume" : "Criteria"} match ${score} out of 100`;
    const saveLabel = `${isSaved ? "Unsave" : "Save"} ${job.title}`;
    const appliedLabel = `${isApplied ? "Mark not applied:" : "Mark applied:"} ${job.title}`;
    const dateSubtext =
      age === null ? "Not verified" : age > 7 ? "Older listing" : "Published";
    return `<article class="job" data-job="${job.id}">
      <div class="job-row">
        <div class="role-column"><div class="company-avatar" aria-hidden="true">${esc(initials(job.company))}</div><div class="role-text">
          <h3 style="margin:0"><button class="job-title" data-action="details" data-id="${job.id}" aria-expanded="${open}" aria-controls="details-${job.id}">${esc(job.title)}</button></h3>
          <div class="company-line"><span>${esc(job.company)}</span>${isApplied ? '<span class="job-status">Applied</span>' : ""}${isSaved ? '<span class="job-status">Saved</span>' : ""}</div>
        </div></div>
        <div class="location-column"><div class="location-text" title="${esc(job.location)}">${esc(job.location)}</div>${knownWorkplace ? `<div class="subtext">${esc(knownWorkplace)}</div>` : ""}</div>
        <div class="date-column"><div class="posted ${age === null ? "unknown" : ""}" title="Published: ${esc(absolute(job.published))}">${esc(posted)}</div><div class="subtext">${dateSubtext}</div></div>
        <div class="match-column" title="${esc(scoreLabel)}"><div class="match-value ${score >= 75 ? "high" : ""} ${score === null ? "unscored" : ""}" aria-label="${esc(scoreLabel)}">${score === null ? "Not scored" : `${score}<small> / 100</small>`}</div>${score !== null ? `<div class="match-bar" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, score))}%"></span></div>` : ""}</div>
        <div class="row-actions">
          <button class="icon-button ${isSaved ? "is-active" : ""}" data-action="save" data-id="${job.id}" aria-label="${esc(saveLabel)}" aria-pressed="${isSaved}" title="${isSaved ? "Remove from saved" : "Save job"}">${icon("bookmark")}</button>
          <button class="icon-button ${isApplied ? "is-active" : ""}" data-action="applied" data-id="${job.id}" aria-label="${esc(appliedLabel)}" aria-pressed="${isApplied}" title="${isApplied ? "Mark not applied" : "Mark as applied"}">${icon("check")}</button>
          <a class="apply" href="${esc(job.url)}" target="_blank" rel="noopener noreferrer" aria-label="Apply: ${esc(job.title)} at ${esc(job.company)}">Apply ${icon("arrow-up-right")}</a>
        </div>
      </div>
      <div class="job-detail"><button class="detail-toggle" data-action="details" data-id="${job.id}" aria-expanded="${open}" aria-controls="details-${job.id}">${open ? "Less detail" : "Details"} ${icon("chevron-down")}</button>
        <div class="detail-body" id="details-${job.id}" ${open ? "" : "hidden"}>
          <div class="detail-facts"><span>Published: <strong>${esc(absolute(job.published))}</strong></span><span>First discovered: <strong>${esc(absolute(job.firstSeen))}</strong></span><span>Source: <strong>${esc((job.sources || [job.source]).map(sourceName).join(", "))}</strong></span></div>
          <div class="detail-facts"><span>Location: <strong>${esc(job.location)}</strong></span></div>
          ${resumeDetails(job)}
          <h3>${personal ? "Discovery criteria" : "Why it matches"}</h3><p>${esc(job.why || "Match explanation unavailable.")}</p>
          ${skills.length ? `<div class="skill-list">${skills.map((skill) => `<span class="skill">${esc(skill)}</span>`).join("")}</div>` : ""}
          ${job.description ? `<h3>Listing description</h3><div class="description">${esc(job.description)}</div>` : ""}
        </div>
      </div>
    </article>`;
  }
  function render() {
    const query = $("search").value.trim().toLowerCase();
    const location = $("location").value;
    const source = $("source").value;
    const minScore = Number($("score").value);
    const sort = $("sort").value;
    const filtered = jobs
      .filter((job) => {
        const haystack = [job.company, job.title, job.location, job.skills]
          .join(" ")
          .toLowerCase();
        const locMatch =
          !location ||
          (location === "remote"
            ? /remote/i.test(job.workplace + " " + job.location)
            : /\b(vancouver|british columbia|bc|burnaby|richmond|surrey|victoria)\b/i.test(
                job.location,
              ));
        return (
          viewMatch(job) &&
          dateMatch(job) &&
          (!query || haystack.includes(query)) &&
          locMatch &&
          (!source || (job.sources || [job.source]).includes(source)) &&
          (!minScore ||
            (matchScore(job) !== null && matchScore(job) >= minScore))
        );
      })
      .sort((a, b) =>
        sort === "match"
          ? (matchScore(b) ?? -1) - (matchScore(a) ?? -1) ||
            (Date.parse(b.published) || 0) - (Date.parse(a.published) || 0)
          : sort === "discovered"
            ? (Date.parse(b.firstSeen) || 0) - (Date.parse(a.firstSeen) || 0)
            : (Date.parse(b.published) || 0) - (Date.parse(a.published) || 0) ||
              (matchScore(b) ?? -1) - (matchScore(a) ?? -1),
      );
    updateCounts();
    $("filter-more").classList.toggle("is-active", Boolean(source || minScore));
    $("view-title").textContent = {
      recent: "Recent opportunities",
      saved: "Saved for later",
      applied: "Applications sent",
      undated: "Publication date unknown",
      all: "All opportunities",
    }[view];
    $("results-count").textContent =
      `${filtered.length} ${filtered.length === 1 ? "job" : "jobs"}`;
    $("list").innerHTML =
      filtered.slice(0, visibleLimit).map(jobRow).join("") +
      (filtered.length > visibleLimit
        ? '<button class="secondary load-more" data-action="more">Show more jobs</button>'
        : "");
    $("empty").hidden = filtered.length > 0;
    $("empty-title").textContent =
      view === "recent"
        ? "No recent matches yet"
        : view === "saved"
          ? "No saved jobs here"
          : view === "applied"
            ? "No applications marked yet"
            : "No matching jobs";
    $("empty-copy").textContent =
      view === "recent"
        ? "No jobs with a verified publication date match your filters. Older and undated listings are kept separately."
        : "There are no jobs in this view matching the current filters.";
    $("show-undated").hidden = view !== "recent";
    document.querySelector(".list-head").hidden = !filtered.length;
  }
  function switchView(next, keepDate = false) {
    view = next;
    if (!keepDate)
      $("freshness").value =
        view === "recent" ? "last7" : view === "undated" ? "unknown" : "";
    document.querySelectorAll("[data-view]").forEach((button) => {
      const selected = button.dataset.view === view;
      button.classList.toggle("active", selected);
      if (selected) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    visibleLimit = 30;
    render();
  }
  function toast(text, undo) {
    clearTimeout(toastTimer);
    undoAction = undo;
    $("toast-text").textContent = text;
    $("toast").hidden = false;
    toastTimer = setTimeout(() => {
      $("toast").hidden = true;
      undoAction = null;
    }, 10000);
  }
  function changeProgress(job, field) {
    const previous = { ...(progress[job.id] || {}) };
    progress[job.id] = { ...previous, [field]: !previous[field] };
    persist();
    render();
    toast(
      field === "saved"
        ? progress[job.id].saved
          ? "Job saved"
          : "Job removed from saved"
        : progress[job.id].applied
          ? "Marked as applied"
          : "Marked as not applied",
      () => {
        progress[job.id] = previous;
        persist();
        render();
      },
    );
    const target = $("list").querySelector(
      `[data-action="${field === "saved" ? "save" : "applied"}"][data-id="${job.id}"]`,
    );
    if (target) target.focus({ preventScroll: true });
    else
      document
        .querySelector('[aria-current="page"]')
        .focus({ preventScroll: true });
  }
  function renderHealth() {
    const failures = health.filter((item) => item.failures > 0).length;
    $("health-summary").textContent = health.length
      ? `${health.length} recorded sources${failures ? ` / ${failures} need attention` : ""}`
      : "No checks recorded";
    $("health").innerHTML = health
      .map(
        (item) =>
          `<tr><td>${esc(sourceName(item.source))}</td><td class="${item.failures ? "health-bad" : "health-good"}">${item.failures ? `${item.failures} failures` : esc(item.status)}</td><td>${item.jobs}</td><td>${item.matches}</td><td>${esc(absolute(item.lastSuccess))}</td></tr>`,
      )
      .join("");
  }

  document
    .querySelectorAll("[data-view]")
    .forEach((button) =>
      button.addEventListener("click", () => switchView(button.dataset.view)),
    );
  for (const id of [
    "search",
    "freshness",
    "location",
    "source",
    "score",
    "sort",
  ])
    $(id).addEventListener("input", () => {
      visibleLimit = 30;
      if (id === "freshness" && !["saved", "applied"].includes(view)) {
        const date = $("freshness").value;
        switchView(
          date === "unknown"
            ? "undated"
            : ["last7", "fresh", "recent"].includes(date)
              ? "recent"
              : "all",
          true,
        );
      } else render();
    });
  $("list").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "more") {
      visibleLimit += 30;
      render();
      return;
    }
    const job = jobs.find((item) => item.id === button.dataset.id);
    if (!job) return;
    if (action === "details") {
      const open = !expanded.has(job.id);
      if (open) expanded.add(job.id);
      else expanded.delete(job.id);
      $(`details-${job.id}`).hidden = !open;
      document
        .querySelectorAll(`[data-action="details"][data-id="${job.id}"]`)
        .forEach((toggle) => {
          toggle.setAttribute("aria-expanded", String(open));
          if (toggle.classList.contains("detail-toggle"))
            toggle.innerHTML = `${open ? "Less detail" : "Details"} ${icon("chevron-down")}`;
        });
    } else changeProgress(job, action === "save" ? "saved" : "applied");
  });
  $("undo").addEventListener("click", () => {
    if (undoAction) undoAction();
    undoAction = null;
    $("toast").hidden = true;
    clearTimeout(toastTimer);
  });
  $("reset").addEventListener("click", () => {
    for (const id of ["search", "source", "location"]) $(id).value = "";
    $("score").value = "0";
    $("sort").value = "newest";
    switchView(view);
  });
  $("show-undated").addEventListener("click", () => switchView("undated"));
  $("refresh").addEventListener("click", () => window.location.reload());
  $("filter-more").addEventListener("click", () => {
    const open = $("filter-more").getAttribute("aria-expanded") !== "true";
    $("filter-more").setAttribute("aria-expanded", String(open));
    document.querySelector(".filters").dataset.expanded = String(open);
  });
  window.addEventListener("storage", (event) => {
    if (event.key === storageKey) window.location.reload();
  });
  window.addEventListener("resumes:changed", () => {
    resumeMatches.clear();
    const active = window.ResumeHub?.selected();
    if (active && active.id !== previousResumeId) $("sort").value = "match";
    previousResumeId = active?.id || null;
    $("sort").querySelector('[value="match"]').textContent = active
      ? "Best resume match"
      : "Best criteria match";
    render();
  });
  for (const source of [
    ...new Set(jobs.flatMap((job) => job.sources || [job.source])),
  ].sort()) {
    const option = document.createElement("option");
    option.value = source;
    option.textContent = sourceName(source);
    $("source").appendChild(option);
  }
  $("updated").textContent = relative($("updated").dateTime).toLowerCase();
  $("updated").title = absolute($("updated").dateTime);
  installIcons();
  renderHealth();
  render();
})();
