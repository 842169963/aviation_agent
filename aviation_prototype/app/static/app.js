const form = document.querySelector("#query-form");
const questionInput = document.querySelector("#question");
const statusBox = document.querySelector("#status");

const procedureName = document.querySelector("#procedure-name");
const procedureTrigger = document.querySelector("#procedure-trigger");
const procedurePhase = document.querySelector("#procedure-phase");
const procedureSource = document.querySelector("#procedure-source");
const procedureEvidence = document.querySelector("#procedure-evidence");
const scorePill = document.querySelector("#score-pill");
const advisorResponse = document.querySelector("#advisor-response");
const actionsList = document.querySelector("#actions-list");
const warningsList = document.querySelector("#warnings-list");
const candidateList = document.querySelector("#candidate-list");

function setStatus(message, isError = false) {
  statusBox.hidden = !message;
  statusBox.textContent = message || "";
  statusBox.classList.toggle("error", isError);
}

function clearChildren(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function stepTypeLabel(value) {
  return (value || "immediate_action").replaceAll("_", " ");
}

function renderProcedure(procedure) {
  if (!procedure) {
    procedureName.textContent = "No procedure retrieved";
    procedureTrigger.textContent = "";
    procedurePhase.textContent = "-";
    procedureSource.textContent = "-";
    procedureEvidence.textContent = "";
    scorePill.textContent = "No match";
    clearChildren(actionsList);
    clearChildren(warningsList);
    return;
  }

  procedureName.textContent = procedure.name;
  procedureTrigger.textContent = procedure.trigger || "";
  procedurePhase.textContent = procedure.aircraft_phase || "-";
  procedureSource.textContent = [procedure.source_file, procedure.source_section].filter(Boolean).join(" | ") || "-";
  procedureEvidence.textContent = procedure.procedure_evidence || "";
  scorePill.textContent = `Final ${procedure.score.final} | KG ${procedure.score.kg} + Vec ${procedure.score.vector}`;

  clearChildren(actionsList);
  procedure.steps.forEach((step) => {
    const li = document.createElement("li");

    const type = document.createElement("span");
    type.className = `step-type ${step.step_type}`;
    type.textContent = stepTypeLabel(step.step_type);
    li.appendChild(type);

    const action = document.createElement("div");
    action.textContent = step.action;
    li.appendChild(action);

    if (step.expected_result) {
      const result = document.createElement("div");
      result.className = "step-evidence";
      result.textContent = `Expected: ${step.expected_result}`;
      li.appendChild(result);
    }

    if (step.source_excerpt) {
      const evidence = document.createElement("div");
      evidence.className = "step-evidence";
      evidence.textContent = `Evidence: ${step.source_excerpt}`;
      li.appendChild(evidence);
    }

    actionsList.appendChild(li);
  });

  clearChildren(warningsList);
  const noteSteps = procedure.steps.filter((step) => step.step_type !== "immediate_action");
  [...noteSteps.map((step) => `${stepTypeLabel(step.step_type)}: ${step.action}`), ...procedure.warnings].forEach((warning) => {
    const item = document.createElement("div");
    item.className = "warning-item";
    item.textContent = warning;
    warningsList.appendChild(item);
  });

  if (!warningsList.childElementCount) {
    const item = document.createElement("div");
    item.className = "muted";
    item.textContent = "No procedure-specific warnings retrieved.";
    warningsList.appendChild(item);
  }
}

function renderCandidates(candidates) {
  clearChildren(candidateList);
  candidates.forEach((candidate) => {
    const row = document.createElement("div");
    row.className = "candidate";

    const title = document.createElement("strong");
    title.textContent = candidate.name;
    row.appendChild(title);

    const score = document.createElement("span");
    const distance = typeof candidate.score.distance === "number" ? candidate.score.distance.toFixed(4) : "N/A";
    score.textContent = `Final ${candidate.score.final}, distance ${distance}`;
    row.appendChild(score);

    candidateList.appendChild(row);
  });
}

function renderResponse(data) {
  renderProcedure(data.top_procedure);
  renderCandidates(data.candidates || []);
  advisorResponse.textContent = data.advisor_response || data.source_policy || "No generated response.";
}

async function ask(question) {
  setStatus("Running hybrid retrieval and grounded synthesis...");
  const response = await fetch("/api/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      top_k: 3,
      vector_top_k: 5,
      synthesize: true,
    }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Query failed");
  }

  renderResponse(data);
  setStatus("");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) {
    setStatus("Enter a question first.", true);
    return;
  }

  try {
    await ask(question);
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    form.requestSubmit();
  });
});

ask(questionInput.value).catch((error) => setStatus(error.message, true));
