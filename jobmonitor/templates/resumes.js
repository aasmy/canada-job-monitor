/* Resume files and text are stored only in IndexedDB on this origin. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
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
  const icons = JSON.parse($("icon-data").textContent);
  let records = [];
  let activeId = "";
  let editingId = null;
  let originalFile = null;
  let originalName = "";
  let uploadGeneration = 0;
  let importing = false;
  let dirty = false;
  let deletingId = null;
  let pdfLibrary;
  let mammothLibrary;
  const maxBytes = 5 * 1024 * 1024;
  const dbPromise = new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("Browser storage is unavailable"));
      return;
    }
    const request = indexedDB.open("canada-job-hub-resumes", 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("resumes", { keyPath: "id" });
      request.result.createObjectStore("settings", { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(new Error("Could not open private browser storage"));
    request.onblocked = () =>
      reject(new Error("Close other Job Hub tabs and try again"));
  });
  async function transaction(store, mode, operation) {
    const db = await dbPromise;
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const request = operation(tx.objectStore(store));
      tx.oncomplete = () => resolve(request?.result);
      tx.onabort = tx.onerror = () =>
        reject(
          new Error(
            "Could not save resume in this browser. Check available storage and try again.",
          ),
        );
    });
  }
  async function writeProfile(record, nextActive, remove = false) {
    const db = await dbPromise;
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["resumes", "settings"], "readwrite");
      if (remove) tx.objectStore("resumes").delete(record.id);
      else tx.objectStore("resumes").put(record);
      tx.objectStore("settings").put({ key: "active", value: nextActive });
      tx.oncomplete = () => resolve();
      tx.onerror = tx.onabort = () =>
        reject(
          new Error(
            "Could not save changes. Your previous resumes have been kept.",
          ),
        );
    });
  }
  function selected() {
    return records.find((record) => record.id === activeId) || null;
  }
  function notice(text, error = false) {
    $("resume-message").textContent = text;
    $("resume-message").hidden = !text;
    $("resume-message").classList.toggle("is-error", error);
  }
  function sync() {
    $("resume-count").textContent = records.length;
    $("resume-summary").textContent =
      `${records.length} ${records.length === 1 ? "version" : "versions"} stored on this device`;
    const selector = $("active-resume");
    selector.innerHTML =
      '<option value="">Discovery criteria only</option>' +
      records
        .map(
          (record) =>
            `<option value="${esc(record.id)}">${esc(record.name)}</option>`,
        )
        .join("");
    selector.value = activeId;
    selector.disabled = false;
    $("match-basis").textContent = selected()
      ? "Personal resume match"
      : "Discovery criteria";
    $("match-heading").textContent = selected() ? "RESUME MATCH" : "CRITERIA";
    $("resume-empty").hidden = records.length > 0;
    $("resume-list").innerHTML = records
      .map((record) => {
        const skills = ResumeMatching.skills(record.text);
        return `<article class="resume-item"><div class="resume-item-icon" aria-hidden="true">${icons["file-text"] || ""}</div><div class="resume-item-main"><h2>${esc(record.name)}${record.id === activeId ? '<span class="active-badge">Active for matching</span>' : ""}</h2><div class="subtext">${esc(record.filename || "Pasted text")} / Updated ${esc(new Date(record.updatedAt).toLocaleDateString())}${record.years !== null ? ` / ${record.years} years experience` : ""}</div><div class="skill-list">${skills
          .slice(0, 10)
          .map((skill) => `<span class="skill">${esc(skill)}</span>`)
          .join(
            "",
          )}${skills.length > 10 ? `<span class="skill">+${skills.length - 10}</span>` : ""}${!skills.length ? '<span class="subtext">No technical skills detected. Review the text.</span>' : ""}</div></div><div class="resume-item-actions"><button data-resume-action="use" data-resume-id="${esc(record.id)}" class="secondary" ${record.id === activeId ? "disabled" : ""}>${record.id === activeId ? "Selected" : "Use for matching"}</button><button data-resume-action="edit" data-resume-id="${esc(record.id)}" class="text-button">Edit</button><button data-resume-action="download" data-resume-id="${esc(record.id)}" class="icon-button" aria-label="Download ${esc(record.name)}" title="${record.file ? "Download original file" : "Download text"}">${icons.download || ""}</button><button data-resume-action="delete" data-resume-id="${esc(record.id)}" class="icon-button" aria-label="Delete ${esc(record.name)}" title="Delete resume">${icons["trash-2"] || ""}</button></div></article>`;
      })
      .join("");
    window.dispatchEvent(new Event("resumes:changed"));
  }
  async function activate(id) {
    const next = records.some((record) => record.id === id) ? id : "";
    await transaction("settings", "readwrite", (store) =>
      store.put({ key: "active", value: next }),
    );
    activeId = next;
    sync();
  }
  function showSection(section) {
    document.querySelector(".skip").href =
      section === "jobs" ? "#jobs-heading" : "#resumes-heading";
    $("jobs-workspace").hidden = section !== "jobs";
    $("resumes-workspace").hidden = section !== "resumes";
    for (const name of ["jobs", "resumes"]) {
      if (name === section)
        $("section-" + name).setAttribute("aria-current", "page");
      else $("section-" + name).removeAttribute("aria-current");
    }
  }
  function skillPreview() {
    const detected = ResumeMatching.skills($("resume-text").value);
    $("resume-skills").innerHTML = detected.length
      ? detected
          .map((skill) => `<span class="skill">${esc(skill)}</span>`)
          .join("")
      : '<span class="subtext">No technical skills detected yet.</span>';
  }
  function formError(text) {
    $("resume-form-error").textContent = text;
    $("resume-form-error").hidden = !text;
  }
  function editor(record = null) {
    if (!record && records.length >= 10) {
      notice(
        "You can keep up to 10 resumes. Remove one before adding another.",
        true,
      );
      return;
    }
    editingId = record?.id || null;
    originalFile = record?.file || null;
    originalName = record?.filename || "";
    uploadGeneration++;
    importing = false;
    dirty = false;
    $("resume-form").reset();
    $("resume-name").value = record?.name || "";
    $("resume-years").value = record?.years ?? "";
    $("resume-text").value = record?.text || "";
    $("resume-activate").checked = !record || record.id === activeId;
    $("resume-editor-title").textContent = record
      ? "Edit resume"
      : "Add resume";
    $("upload-status").textContent = record?.filename
      ? `Original file: ${record.filename}`
      : "";
    $("save-resume").disabled = false;
    formError("");
    skillPreview();
    $("resume-editor").showModal();
  }
  function closeEditor() {
    if (dirty && !window.confirm("Discard unsaved resume changes?")) return;
    uploadGeneration++;
    originalFile = null;
    $("resume-editor").close();
    $("resume-form").reset();
    $("resume-skills").replaceChildren();
  }
  async function extract(file) {
    if (file.size > maxBytes)
      throw new Error(
        "File is larger than 5 MB. Choose a smaller file or paste the text.",
      );
    const extension = file.name.split(".").pop().toLowerCase();
    if (!["pdf", "docx", "txt"].includes(extension))
      throw new Error("Choose a PDF, DOCX, or TXT file.");
    if (extension === "txt") return file.text();
    const data = await file.arrayBuffer();
    if (extension === "docx") {
      if (!mammothLibrary)
        mammothLibrary = new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = new URL(
            "vendor/mammoth.browser.min.js",
            document.baseURI,
          ).href;
          script.onload = () => resolve(window.mammoth);
          script.onerror = () => {
            mammothLibrary = null;
            reject(
              new Error(
                "Could not load the DOCX reader. Reload and try again.",
              ),
            );
          };
          document.head.appendChild(script);
        });
      const library = await mammothLibrary;
      return (await library.extractRawText({ arrayBuffer: data })).value;
    }
    if (!pdfLibrary)
      pdfLibrary = import(
        new URL("vendor/pdf.min.mjs", document.baseURI).href
      ).catch((error) => {
        pdfLibrary = null;
        throw error;
      });
    const pdf = await pdfLibrary;
    pdf.GlobalWorkerOptions.workerSrc = new URL(
      "vendor/pdf.worker.min.mjs",
      document.baseURI,
    ).href;
    const task = pdf.getDocument({
      data: new Uint8Array(data),
      isEvalSupported: false,
      disableFontFace: true,
      useWorkerFetch: false,
    });
    const timeout = setTimeout(() => task.destroy(), 30000);
    let documentPdf;
    try {
      documentPdf = await task.promise;
      if (documentPdf.numPages > 20)
        throw new Error(
          "This PDF has more than 20 pages. Use a shorter resume.",
        );
      const pages = [];
      for (let page = 1; page <= documentPdf.numPages; page++) {
        const content = await (
          await documentPdf.getPage(page)
        ).getTextContent();
        pages.push(
          content.items
            .map((item) => item.str + (item.hasEOL ? "\n" : " "))
            .join(""),
        );
      }
      return pages.join("\n\n");
    } finally {
      clearTimeout(timeout);
      await task.destroy();
    }
  }
  async function importFile(file) {
    if (!file) return;
    const generation = ++uploadGeneration;
    importing = true;
    dirty = true;
    $("save-resume").disabled = true;
    formError("");
    $("upload-status").textContent = `Reading ${file.name} locally...`;
    try {
      const text = (await extract(file)).trim();
      if (generation !== uploadGeneration) return;
      if (text.length < 40)
        throw new Error(
          "No readable resume text was found. For scanned or image PDFs, paste the text instead.",
        );
      if (text.length > 100000)
        throw new Error(
          "The extracted text is too long. Use a shorter resume or paste up to 100,000 characters.",
        );
      originalFile = file;
      originalName = file.name;
      $("resume-text").value = text;
      if (!$("resume-name").value.trim())
        $("resume-name").value = file.name
          .replace(/\.[^.]+$/, "")
          .slice(0, 100);
      $("upload-status").textContent =
        `${file.name} / ${text.length.toLocaleString()} characters extracted`;
      skillPreview();
    } catch (error) {
      if (generation !== uploadGeneration) return;
      const text =
        error.name === "PasswordException"
          ? "This PDF is password protected. Use an unlocked copy or paste the text."
          : error.message;
      formError(
        text || "Could not read this file. Try another file or paste its text.",
      );
      $("upload-status").textContent = "File was not imported.";
    } finally {
      if (generation === uploadGeneration) {
        importing = false;
        $("save-resume").disabled = false;
      }
    }
  }
  $("resume-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (importing) return;
    const name = $("resume-name").value.trim();
    const text = $("resume-text").value.trim();
    const years =
      $("resume-years").value === "" ? null : Number($("resume-years").value);
    if (!name || text.length < 40 || text.length > 100000) {
      formError("Add a name and at least 40 characters of resume text.");
      return;
    }
    if (
      years !== null &&
      (!Number.isFinite(years) || years < 0 || years > 50)
    ) {
      formError("Experience must be between 0 and 50 years.");
      return;
    }
    $("save-resume").disabled = true;
    formError("");
    try {
      const current = records.find((record) => record.id === editingId);
      const record = {
        id: editingId || crypto.randomUUID(),
        name,
        text,
        years,
        file: originalFile,
        filename: originalName,
        createdAt: current?.createdAt || new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      const nextActive = $("resume-activate").checked
        ? record.id
        : activeId === record.id
          ? ""
          : activeId;
      await writeProfile(record, nextActive);
      records = records.filter((item) => item.id !== record.id).concat(record);
      activeId = nextActive;
      sync();
      dirty = false;
      originalFile = null;
      $("resume-editor").close();
      $("resume-form").reset();
      $("resume-skills").replaceChildren();
      notice("Resume saved in this browser.");
    } catch (error) {
      formError(error.message);
    } finally {
      $("save-resume").disabled = false;
    }
  });
  $("resume-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-resume-action]");
    if (!button) return;
    const record = records.find((item) => item.id === button.dataset.resumeId);
    if (!record) return;
    try {
      if (button.dataset.resumeAction === "use") {
        await activate(record.id);
        showSection("jobs");
      }
      if (button.dataset.resumeAction === "edit") editor(record);
      if (button.dataset.resumeAction === "delete") {
        deletingId = record.id;
        $("resume-delete-name").textContent = record.name;
        $("resume-delete").showModal();
      }
      if (button.dataset.resumeAction === "download") {
        const url = URL.createObjectURL(
          record.file || new Blob([record.text], { type: "text/plain" }),
        );
        const link = document.createElement("a");
        link.href = url;
        link.download = record.filename || record.name + ".txt";
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (error) {
      notice(error.message, true);
    }
  });
  $("resume-delete").addEventListener("close", async () => {
    if ($("resume-delete").returnValue !== "delete" || !deletingId) return;
    try {
      const record = records.find((item) => item.id === deletingId);
      if (!record) return;
      const nextActive = activeId === deletingId ? "" : activeId;
      await writeProfile(record, nextActive, true);
      records = records.filter((record) => record.id !== deletingId);
      activeId = nextActive;
      sync();
      notice("Resume deleted from this browser.");
    } catch (error) {
      notice(error.message, true);
    }
    deletingId = null;
  });
  $("active-resume").addEventListener("change", async () => {
    try {
      await activate($("active-resume").value);
    } catch (error) {
      $("active-resume").value = activeId;
      notice(error.message, true);
      showSection("resumes");
    }
  });
  $("section-jobs").addEventListener("click", () => showSection("jobs"));
  $("section-resumes").addEventListener("click", () => showSection("resumes"));
  $("manage-resumes").addEventListener("click", () => showSection("resumes"));
  for (const id of ["add-resume", "first-resume"])
    $(id).addEventListener("click", () => editor());
  for (const id of ["close-resume-editor", "cancel-resume-editor"])
    $(id).addEventListener("click", closeEditor);
  $("resume-editor").addEventListener("cancel", (event) => {
    event.preventDefault();
    closeEditor();
  });
  $("resume-upload").addEventListener("change", () =>
    importFile($("resume-upload").files[0]),
  );
  $("resume-form").addEventListener("input", () => {
    dirty = true;
  });
  $("resume-text").addEventListener("input", skillPreview);
  $("resume-dropzone").addEventListener("dragover", (event) =>
    event.preventDefault(),
  );
  $("resume-dropzone").addEventListener("drop", (event) => {
    event.preventDefault();
    importFile(event.dataTransfer.files[0]);
  });
  window.ResumeHub = { selected, showSection };
  (async () => {
    try {
      records = (
        await transaction("resumes", "readonly", (store) => store.getAll())
      )
        .filter(
          (record) =>
            typeof record.text === "string" &&
            record.text.length <= 100000 &&
            typeof record.name === "string",
        )
        .map((record) => ({
          ...record,
          years:
            typeof record.years === "number" &&
            Number.isFinite(record.years) &&
            record.years >= 0 &&
            record.years <= 50
              ? record.years
              : null,
        }));
      const pref = await transaction("settings", "readonly", (store) =>
        store.get("active"),
      );
      activeId = records.some((record) => record.id === pref?.value)
        ? pref.value
        : "";
    } catch (error) {
      notice(
        error.message + ". Resumes cannot be saved until storage is available.",
        true,
      );
    }
    sync();
  })();
})();
