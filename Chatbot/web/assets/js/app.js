import {
  DEFAULT_ROLE,
  DEFAULT_USER_ID,
  MAX_CONCURRENT_REQUESTS,
  MIN_REQUEST_INTERVAL,
  REQUEST_TIMEOUT,
  createSessionId,
  getEndpoint,
} from "./config.js";
import {
  addMessage,
  addRecord,
  addStatisticsResult,
  addTable,
  buildAuditDetailsMarkup,
  buildPatientReport,
  closeModal,
  elements,
  escapeHtml,
  openModal,
  openPrintDialog,
  removeErrorMessage,
  removeTyping,
  showApprovalButtons,
  showErrorMessage,
  showTyping,
  updateSendButtonState,
} from "./ui.js";

let sessionId = createSessionId();
let lastRequestTime = 0;
let pendingRequests = 0;

function canMakeRequest() {
  const now = Date.now();
  return (
    now - lastRequestTime >= MIN_REQUEST_INTERVAL &&
    pendingRequests < MAX_CONCURRENT_REQUESTS
  );
}

async function fetchWithTimeout(url, options = {}, timeout = REQUEST_TIMEOUT) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });

    window.clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      throw new Error(`Server error (${response.status}): ${errorText}`);
    }

    return response;
  } catch (error) {
    window.clearTimeout(timeoutId);

    if (error.name === "AbortError" || error.name === "TimeoutError") {
      throw new Error(
        `Request timeout after ${timeout / 1000} seconds. CrewAI processing can take 30-60 seconds. Please try again.`
      );
    }

    if (
      String(error.message).includes("Failed to fetch") ||
      String(error.message).includes("NetworkError")
    ) {
      throw new Error(
        "Network error. Check your connection and ensure the backend is running."
      );
    }

    throw error;
  }
}

async function resetBackendSessions() {
  try {
    await fetchWithTimeout(await getEndpoint("/reset_sessions"), { method: "POST" }, 5000);
  } catch (error) {
    console.warn("Failed to reset backend sessions", error);
  }
}

async function handleInteractionClick(interactionId) {
  if (!canMakeRequest()) {
    addMessage(
      "Please wait a moment before making another request.",
      "assistant",
      "summary-chip"
    );
    return;
  }

  elements.downloadPdfBtn.disabled = true;
  pendingRequests += 1;

  openModal(
    "Interaction details",
    `<p class="modal-subtle">Fetching interaction details...</p><div class="modal-loading">Loading...</div>`
  );

  try {
    lastRequestTime = Date.now();
    const response = await fetchWithTimeout(await getEndpoint("/interaction_details"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        interaction_id: interactionId,
        user_id: DEFAULT_USER_ID,
      }),
    });

    const data = await response.json();
    if (!data.ok) {
      const message =
        (data && (data.detail || data.message)) ||
        "Unable to fetch interaction details.";
      elements.modalBody.innerHTML = `<p class="modal-subtle">${escapeHtml(message)}</p>`;
      elements.downloadPdfBtn.disabled = true;
      return;
    }

    elements.modalBody.innerHTML = buildAuditDetailsMarkup({
      title: "Interaction details",
      recordLabel: "Interaction ID",
      recordId: interactionId,
      interaction: data.interaction || {},
      serviceCalls: data.service_calls || [],
    });
    elements.downloadPdfBtn.disabled = false;
  } catch (error) {
    console.error("Error loading interaction details:", error);
    const message = error.message || "Unable to load interaction details";
    elements.modalBody.innerHTML = `<p class="modal-subtle">${escapeHtml(message)}. Please try again.</p>`;
    elements.downloadPdfBtn.disabled = true;
    addMessage(`Error: ${message}`, "assistant", "summary-chip");
  } finally {
    pendingRequests = Math.max(0, pendingRequests - 1);
  }
}

async function handleRowClick(medicalRecordNumber, name) {
  if (!medicalRecordNumber && !name) {
    return;
  }

  if (!canMakeRequest()) {
    addMessage(
      "Please wait a moment before making another request.",
      "assistant",
      "summary-chip"
    );
    return;
  }

  elements.downloadPdfBtn.disabled = true;
  pendingRequests += 1;

  openModal(
    "Patient details",
    `<p class="modal-subtle">Fetching patient details based on your role...</p><div class="modal-loading">Loading...</div>`
  );

  if (!medicalRecordNumber) {
    elements.modalBody.innerHTML =
      "<p class='modal-subtle'>This row has no medical record number (MRN). Run a query that includes medical_record_number to view full patient details.</p>";
    pendingRequests = Math.max(0, pendingRequests - 1);
    return;
  }

  if (
    typeof medicalRecordNumber !== "string" &&
    typeof medicalRecordNumber !== "number"
  ) {
    elements.modalBody.innerHTML =
      "<p class='modal-subtle'>Invalid medical record number (MRN) format.</p>";
    pendingRequests = Math.max(0, pendingRequests - 1);
    return;
  }

  try {
    lastRequestTime = Date.now();
    const response = await fetchWithTimeout(await getEndpoint("/patient_details"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        medical_record_number: String(medicalRecordNumber),
        user_id: DEFAULT_USER_ID,
        role: DEFAULT_ROLE,
        session_id: sessionId,
      }),
    });

    const data = await response.json();
    if (!data.ok) {
      const message =
        (data && (data.detail || data.message)) ||
        "Unable to execute the query: validation failed.";
      elements.modalBody.innerHTML = `<p class="modal-subtle">${escapeHtml(message)}</p>`;
      elements.downloadPdfBtn.disabled = true;
      return;
    }

    elements.modalBody.innerHTML = buildPatientReport(data.patient);
    elements.downloadPdfBtn.disabled = false;
  } catch (error) {
    console.error("Error loading patient details:", error);
    const message = error.message || "Unable to load patient details";
    elements.modalBody.innerHTML = `<p class="modal-subtle">${escapeHtml(message)}. Please try again.</p>`;
    elements.downloadPdfBtn.disabled = true;
    addMessage(`Error: ${message}`, "assistant", "summary-chip");
  } finally {
    pendingRequests = Math.max(0, pendingRequests - 1);
  }
}

async function sendMessage(
  textParam = null,
  userIdParam = null,
  approved = false,
  correctionRejected = false
) {
  const text = textParam || elements.input.value.trim();
  const userId = userIdParam || DEFAULT_USER_ID;

  if (!text) {
    showErrorMessage("You cannot send an empty message.");
    return;
  }

  if (text.length > 1000) {
    showErrorMessage("Message is too long. Maximum 1000 characters.");
    return;
  }

  if (!canMakeRequest()) {
    showErrorMessage("Please wait a moment before sending another message.");
    return;
  }

  removeErrorMessage();

  if (!textParam) {
    addMessage(text, "user");
  }

  elements.input.value = "";
  updateSendButtonState();
  showTyping();
  elements.sendBtn.disabled = true;
  pendingRequests += 1;

  try {
    lastRequestTime = Date.now();
    const response = await fetchWithTimeout(await getEndpoint("/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text.substring(0, 1000),
        session_id: sessionId,
        user_id: userId,
        approved,
        correction_rejected: correctionRejected,
      }),
    });

    const data = await response.json();
    removeTyping();

    if (data.intent === "approval_required") {
      addMessage(data.text, "assistant");
      showApprovalButtons(
        data.original,
        text,
        userId,
        async (correctedMessage, correctedUserId) => {
          await sendMessage(correctedMessage, correctedUserId, true, false);
        },
        async (originalMessage, rejectedUserId) => {
          await sendMessage(originalMessage, rejectedUserId, false, true);
        }
      );
      return;
    }

    if (
      data &&
      (data.mode === "statistics" ||
        (data.data_json && data.data_json.mode === "statistics"))
    ) {
      addStatisticsResult(data.data_json || {});
      return;
    }

    if (
      data.data_json &&
      data.data_json.type === "record" &&
      data.data_json.record &&
      typeof data.data_json.record === "object"
    ) {
      const summaryText = data.text || "1 record found.";
      addMessage(summaryText, "assistant", "summary-chip");
      addRecord(
        data.data_json.record,
        data.data_json.columns || null,
        data.data_json.title || "Patient details"
      );
      return;
    }

    if (
      data.data_json &&
      data.data_json.type === "table" &&
      Array.isArray(data.data_json.table)
    ) {
      const summaryText =
        data.text || `${data.data_json.table.length} record(s) found.`;
      addMessage(summaryText, "assistant", "summary-chip");

      if (data.data_json.table.length > 0) {
        addTable(
          data.data_json.table,
          data.data_json.columns || null,
          {
            userMessage: text,
            summaryText,
            intent: data.intent || null,
            title: (data.data_json && data.data_json.title) || null,
          },
          {
          onInteractionRow: handleInteractionClick,
          onPatientRow: handleRowClick,
          }
        );
      }

      return;
    }

    addMessage(data.text || "No response.", "assistant");
  } catch (error) {
    console.error("Error sending message:", error);
    removeTyping();

    let message = error.message || "Connection error";
    if (message.includes("timeout") || message.includes("AbortError")) {
      message =
        "Request took too long. CrewAI processing can take 30-60 seconds. Please try again.";
    } else if (message.includes("Failed to fetch") || message.includes("Network error")) {
      message =
        "Network error. Check your connection and ensure the backend is running.";
    } else if (message.includes("Connection error")) {
      message = "Connection error. Ensure the backend is running on port 8000.";
    }

    addMessage(message, "assistant");
  } finally {
    removeTyping();
    elements.sendBtn.disabled = false;
    pendingRequests = Math.max(0, pendingRequests - 1);
    updateSendButtonState();
  }
}

function wireEvents() {
  elements.input.addEventListener("input", updateSendButtonState);
  elements.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!elements.sendBtn.disabled) {
        sendMessage();
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && elements.patientModal.classList.contains("visible")) {
      closeModal();
    }
  });

  elements.sendBtn.addEventListener("click", () => {
    sendMessage();
  });

  elements.clearBtn.addEventListener("click", async () => {
    await resetBackendSessions();
    elements.chatArea.innerHTML = "";
    addMessage("Conversation cleared.", "assistant", "summary-chip");
    sessionId = createSessionId();
  });

  elements.newChatBtn.addEventListener("click", async () => {
    await resetBackendSessions();
    elements.chatArea.innerHTML = "";
    sessionId = createSessionId();
    addMessage(
      "New session started. Hello, Doctor. How can I help today?",
      "assistant"
    );
  });

  elements.modalCloseBtn.addEventListener("click", closeModal);
  elements.patientModal.addEventListener("click", (event) => {
    if (event.target === elements.patientModal) {
      closeModal();
    }
  });

  elements.downloadPdfBtn.addEventListener("click", () => {
    const result = openPrintDialog();
    if (result.ok) {
      addMessage(
        "Print dialog opened. Choose Save as PDF to export the sheet.",
        "assistant",
        "summary-chip"
      );
      return;
    }

    addMessage(result.error, "assistant", "summary-chip");
  });
}

function init() {
  updateSendButtonState();
  elements.downloadPdfBtn.disabled = true;
  wireEvents();
  addMessage(
    "Workspace ready. Ask about admissions, allergies, results, or patient details.",
    "assistant",
    "summary-chip"
  );
}

init();
