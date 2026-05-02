const HISTORY_KEY = "anu-assignment-planner-history";
const BACKGROUND_KEY = "anu-assignment-planner-background";

const state = {
  query: "",
  courses: [],
  studentCourses: load(BACKGROUND_KEY, []),
  history: load(HISTORY_KEY, []),
  modalCourse: null,
  assignmentCourse: null,
  file: null,
  assignmentText: "",
  loading: false
};

const el = {
  courseSearch: document.querySelector("#courseSearch"),
  courseGrid: document.querySelector("#courseGrid"),
  backgroundList: document.querySelector("#backgroundList"),
  historyList: document.querySelector("#historyList"),
  clearHistory: document.querySelector("#clearHistory"),
  analysisTitle: document.querySelector("#analysisTitle"),
  analysisSubtitle: document.querySelector("#analysisSubtitle"),
  assignmentFile: document.querySelector("#assignmentFile"),
  assignmentText: document.querySelector("#assignmentText"),
  dropZone: document.querySelector("#dropZone"),
  dropTitle: document.querySelector("#dropTitle"),
  dropSubtitle: document.querySelector("#dropSubtitle"),
  analyzeButton: document.querySelector("#analyzeButton"),
  analyzeHint: document.querySelector("#analyzeHint"),
  errorBox: document.querySelector("#errorBox"),
  reportPanel: document.querySelector("#reportPanel"),
  modalBackdrop: document.querySelector("#modalBackdrop"),
  modalTitle: document.querySelector("#modalTitle"),
  modalSubtitle: document.querySelector("#modalSubtitle"),
  markInput: document.querySelector("#markInput"),
  cancelModal: document.querySelector("#cancelModal"),
  saveMark: document.querySelector("#saveMark")
};

el.courseSearch.addEventListener("input", () => {
  state.query = el.courseSearch.value;
  searchCourses();
});
el.assignmentFile.addEventListener("change", () => {
  state.file = el.assignmentFile.files[0] || null;
  renderAnalysis();
});
el.assignmentText.addEventListener("input", () => {
  state.assignmentText = el.assignmentText.value;
  renderAnalysis();
});
el.dropZone.addEventListener("dragover", (event) => event.preventDefault());
el.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  state.file = event.dataTransfer.files[0] || null;
  renderAnalysis();
});
el.analyzeButton.addEventListener("click", analyze);
el.clearHistory.addEventListener("click", () => {
  state.history = [];
  save(HISTORY_KEY, state.history);
  renderHistory();
});
el.cancelModal.addEventListener("click", closeModal);
el.modalBackdrop.addEventListener("mousedown", (event) => {
  if (event.target === el.modalBackdrop) closeModal();
});
el.saveMark.addEventListener("click", addCourseMark);

searchCourses();
renderBackground();
renderHistory();
renderAnalysis();

async function searchCourses() {
  const response = await fetch(`/api/courses/search?q=${encodeURIComponent(state.query)}`);
  const data = await response.json();
  state.courses = data.courses || [];
  renderCourses();
}

function renderCourses() {
  el.courseGrid.innerHTML = state.courses
    .map(
      (course) => `
      <article class="course-card">
        <div class="course-card-header">
          <div>
            <strong>${escapeHtml(course.course_code)}</strong>
            <h3>${escapeHtml(course.title)}</h3>
          </div>
          <span>${course.unit_value}u</span>
        </div>
        <div class="course-card-body">
          <p>${escapeHtml(course.description || "")}</p>
          <div class="outcomes">
            ${(course.learning_outcomes || [])
              .slice(0, 4)
              .map((item) => `<span>${escapeHtml(item)}</span>`)
              .join("")}
          </div>
        </div>
        <div class="card-actions">
          <button data-add="${course.course_code}">Add course</button>
          <button class="dark" data-analyze="${course.course_code}">Analyze assignment</button>
        </div>
      </article>`
    )
    .join("");
  el.courseGrid.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", () => openModal(findCourse(button.dataset.add)));
  });
  el.courseGrid.querySelectorAll("[data-analyze]").forEach((button) => {
    button.addEventListener("click", () => {
      state.assignmentCourse = findCourse(button.dataset.analyze);
      hideError();
      renderAnalysis();
    });
  });
}

function renderBackground() {
  if (!state.studentCourses.length) {
    el.backgroundList.innerHTML = `<p class="empty-text">Add completed courses and marks.</p>`;
    renderAnalysis();
    return;
  }
  el.backgroundList.innerHTML = state.studentCourses
    .map(
      (course) => `
      <div class="background-item">
        <div>
          <strong>${escapeHtml(course.courseCode)}</strong>
          <span>${escapeHtml(course.title)}</span>
        </div>
        <div class="background-actions">
          <div class="mark-chip">${course.mark}</div>
          <button class="remove-course" data-remove-course="${escapeHtml(course.courseCode)}" title="Remove course">
            Remove
          </button>
        </div>
      </div>`
    )
    .join("");
  el.backgroundList.querySelectorAll("[data-remove-course]").forEach((button) => {
    button.addEventListener("click", () => removeStudentCourse(button.dataset.removeCourse));
  });
  renderAnalysis();
}

function removeStudentCourse(courseCode) {
  state.studentCourses = state.studentCourses.filter((course) => course.courseCode !== courseCode);
  save(BACKGROUND_KEY, state.studentCourses);
  renderBackground();
}

function renderHistory() {
  if (!state.history.length) {
    el.historyList.innerHTML = `<p class="empty-text">Analyses will appear here.</p>`;
    return;
  }
  el.historyList.innerHTML = state.history
    .map(
      (item) => `
      <button class="history-item" data-id="${item.id}">
        <strong>${escapeHtml(item.targetCourse?.course_code || "")}</strong>
        <span>${escapeHtml(item.fileName || "")}</span>
        <small>${formatDate(item.createdAt)}</small>
      </button>`
    )
    .join("");
  el.historyList.querySelectorAll("[data-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = state.history.find((entry) => entry.id === button.dataset.id);
      if (item) renderReport(item);
    });
  });
}

function renderAnalysis() {
  const assignmentText = getAssignmentText();
  if (state.assignmentCourse) {
    el.analysisTitle.textContent = `Analyze ${state.assignmentCourse.course_code}`;
    el.analysisSubtitle.textContent = state.assignmentCourse.title;
  } else {
    el.analysisTitle.textContent = "Assignment analysis";
    el.analysisSubtitle.textContent = "Choose Analyze assignment from a course card.";
  }
  if (state.file) {
    el.dropZone.classList.add("has-file");
    el.dropTitle.textContent = state.file.name;
    el.dropSubtitle.textContent = `${formatBytes(state.file.size)} selected`;
  } else {
    el.dropZone.classList.remove("has-file");
    el.dropTitle.textContent = "Drop or choose an assignment PDF/TXT file";
    el.dropSubtitle.textContent = "PDF text extraction works for text-based PDFs.";
  }
  const hasAssignmentInput = state.file || assignmentText.length > 0;
  const canAnalyze = state.assignmentCourse && hasAssignmentInput && state.studentCourses.length && !state.loading;
  el.analyzeButton.disabled = !canAnalyze;
  el.analyzeButton.textContent = state.loading ? "Analyzing..." : "Generate estimate";
  el.analyzeHint.textContent = getAnalyzeHint(hasAssignmentInput);
}

function openModal(course) {
  state.modalCourse = course;
  el.modalTitle.textContent = `Add ${course.course_code}`;
  el.modalSubtitle.textContent = course.title;
  el.markInput.value = "";
  el.modalBackdrop.classList.remove("hidden");
  el.markInput.focus();
}

function closeModal() {
  state.modalCourse = null;
  el.modalBackdrop.classList.add("hidden");
}

function addCourseMark() {
  const mark = Number(el.markInput.value);
  if (!state.modalCourse || !Number.isFinite(mark) || mark < 0 || mark > 100) {
    showError("Enter a valid mark from 0 to 100.");
    return;
  }
  state.studentCourses = state.studentCourses
    .filter((item) => item.courseCode !== state.modalCourse.course_code)
    .concat({
      courseCode: state.modalCourse.course_code,
      title: state.modalCourse.title,
      mark
    })
    .sort((a, b) => a.courseCode.localeCompare(b.courseCode));
  save(BACKGROUND_KEY, state.studentCourses);
  closeModal();
  hideError();
  renderBackground();
}

async function analyze() {
  const assignmentText = getAssignmentText();
  const hasAssignmentInput = state.file || assignmentText.length > 0;
  if (!state.assignmentCourse || !hasAssignmentInput || !state.studentCourses.length) return;
  state.loading = true;
  hideError();
  renderAnalysis();

  const form = new FormData();
  form.append("targetCourseCode", state.assignmentCourse.course_code);
  form.append("studentCourses", JSON.stringify(state.studentCourses));
  form.append("assignmentText", assignmentText);
  if (state.file) {
    form.append("assignmentFile", state.file);
  }

  try {
    const response = await fetch("/api/analyze", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Analysis failed.");
    const item = {
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      targetCourse: data.targetCourse,
      fileName: state.file?.name || "Pasted assignment text",
      estimate: data.estimate
    };
    state.history = [item, ...state.history].slice(0, 30);
    save(HISTORY_KEY, state.history);
    renderHistory();
    renderReport(item);
  } catch (error) {
    showError(error.message);
  } finally {
    state.loading = false;
    renderAnalysis();
  }
}

function getAssignmentText() {
  state.assignmentText = el.assignmentText.value;
  return state.assignmentText.trim();
}

function getAnalyzeHint(hasAssignmentInput) {
  if (state.loading) return "Analyzing the assignment estimate...";
  if (!state.assignmentCourse) return "Choose Analyze assignment from a course card first.";
  if (!state.studentCourses.length) return "Add at least one completed course and mark first.";
  if (!hasAssignmentInput) return "Upload a file or paste assignment text first.";
  return "Ready to generate an estimate.";
}

function renderReport(item) {
  const estimate = item.estimate;
  const total = estimate.totalHours || {};
  const confidence = Math.round((estimate.confidence || 0) * 100);
  el.reportPanel.classList.remove("hidden");
  el.reportPanel.innerHTML = `
    <div class="report-title">
      <div>
        <h3>${escapeHtml(item.targetCourse?.course_code || "")} assignment estimate</h3>
        <p>${escapeHtml(item.fileName || "")}</p>
      </div>
      <div class="metric-row">
        ${metric("Total", `${total.min}-${total.max}h`)}
        ${metric("Difficulty", estimate.difficulty || "Medium")}
        ${metric("Confidence", `${confidence}%`)}
      </div>
    </div>
    ${
      estimate.meta?.usedMock
        ? `<div class="warning-box">Running in demo mode because no DEEPSEEK_API_KEY is configured.</div>`
        : ""
    }
    <p class="summary">${escapeHtml(estimate.summary || "")}</p>
    ${reportGrid("Knowledge likely covered", estimate.coveredKnowledge || [], "covered")}
    ${reportGrid("Knowledge to fill", estimate.missingKnowledge || [], "missing")}
    <div class="breakdown">
      <h4>Work breakdown</h4>
      ${(estimate.workBreakdown || [])
        .map(
          (phase) => `
        <div class="breakdown-row">
          <div>
            <strong>${escapeHtml(phase.phase || "")}</strong>
            <span>${escapeHtml(phase.description || "")}</span>
          </div>
          <b>${phase.hours?.min || 0}-${phase.hours?.max || 0}h</b>
        </div>`
        )
        .join("")}
    </div>
    <div class="two-column">
      ${listBlock("Factors increasing estimate", estimate.estimateFactors?.increased || [])}
      ${listBlock("Factors decreasing estimate", estimate.estimateFactors?.decreased || [])}
    </div>
    <div class="two-column">
      ${listBlock("Risks", estimate.risks || [])}
      ${listBlock("Assumptions", estimate.assumptions || [])}
    </div>`;
  el.reportPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function reportGrid(title, items, kind) {
  return `
    <div class="report-block">
      <h4>${title}</h4>
      <div class="report-card-grid">
        ${items
          .map(
            (item) => `
          <div class="mini-card ${kind}">
            <strong>${escapeHtml(item.topic || "")}</strong>
            <p>${escapeHtml(item.evidence || item.whyItMatters || "")}</p>
            <span>${escapeHtml(item.relevance || item.suggestedAction || "")}</span>
          </div>`
          )
          .join("")}
      </div>
    </div>`;
}

function listBlock(title, items) {
  return `
    <div class="list-block">
      <h4>${title}</h4>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>`;
}

function metric(label, value) {
  return `<div class="metric"><span>${label}</span><strong>${escapeHtml(String(value))}</strong></div>`;
}

function findCourse(code) {
  return state.courses.find((course) => course.course_code === code);
}

function showError(message) {
  el.errorBox.textContent = message;
  el.errorBox.classList.remove("hidden");
}

function hideError() {
  el.errorBox.textContent = "";
  el.errorBox.classList.add("hidden");
}

function load(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback;
  } catch {
    return fallback;
  }
}

function save(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char];
  });
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-AU", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}
