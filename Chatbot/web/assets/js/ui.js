import { buildStatisticsViewModel } from "./statistics_result.js";

export const elements = {
  chatArea: document.getElementById("chatArea"),
  input: document.getElementById("userInput"),
  sendBtn: document.getElementById("sendBtn"),
  clearBtn: document.getElementById("clearBtn"),
  newChatBtn: document.getElementById("newChatBtn"),
  inputArea: document.querySelector(".input-area"),
  patientModal: document.getElementById("patientModal"),
  modalTitle: document.getElementById("modal-title"),
  modalBody: document.getElementById("modalBody"),
  modalCloseBtn: document.getElementById("modalCloseBtn"),
  downloadPdfBtn: document.getElementById("downloadPdfBtn"),
};

let typingDiv = null;
let errorTimeout = null;

export function updateSendButtonState() {
  elements.sendBtn.disabled = elements.input.value.trim() === "";
}

export function showErrorMessage(message) {
  removeErrorMessage();

  const errorDiv = document.createElement("p");
  errorDiv.id = "errorMessage";
  errorDiv.className = "input-error";
  errorDiv.textContent = message;

  elements.input.classList.add("has-error");
  const hint = elements.inputArea.querySelector(".input-hint");
  if (hint) {
    elements.inputArea.insertBefore(errorDiv, hint);
  } else {
    elements.inputArea.appendChild(errorDiv);
  }

  clearTimeout(errorTimeout);
  errorTimeout = window.setTimeout(removeErrorMessage, 2500);
}

export function removeErrorMessage() {
  const existingError = document.getElementById("errorMessage");
  if (existingError) {
    existingError.remove();
  }

  elements.input.classList.remove("has-error");
}

export function sanitizeHtml(text) {
  const wrapper = document.createElement("div");
  wrapper.textContent = text == null ? "" : String(text);
  return wrapper.innerHTML;
}

export function escapeHtml(text) {
  return sanitizeHtml(text);
}

export function prettifyHeader(key) {
  return String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function isPatientIdField(key) {
  const lower = String(key || "").toLowerCase();
  return lower === "patientid" || lower === "patients_id" || lower.includes("patient_id");
}

function isMedicalRecordNumberField(key) {
  const lower = String(key || "").toLowerCase();
  return (
    lower === "mrn" ||
    lower === "medical_record_number" ||
    lower === "medical record number" ||
    lower.includes("medical_record_number") ||
    lower.includes("patient_mrn") ||
    lower.endsWith("_mrn")
  );
}

export function formatTimestamp(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

export function maybeJsonPretty(value) {
  if (value == null) {
    return null;
  }

  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }

  const text = String(value).trim();
  if (!text) {
    return "";
  }

  if (
    (text.startsWith("{") && text.endsWith("}")) ||
    (text.startsWith("[") && text.endsWith("]"))
  ) {
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch (_) {
      return null;
    }
  }

  return null;
}

export function addMessage(text, sender, extraClass = "") {
  const message = document.createElement("div");
  message.classList.add("message", sender);

  if (extraClass) {
    message.classList.add(extraClass);
  }

  if (sender === "assistant") {
    message.innerHTML = sanitizeHtml(text);
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
  } else {
    message.textContent = text;
  }

  elements.chatArea.appendChild(message);
  elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
}

export function showTyping() {
  removeTyping();

  typingDiv = document.createElement("div");
  typingDiv.className = "typing";
  typingDiv.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;

  elements.chatArea.appendChild(typingDiv);
  elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
}

export function removeTyping() {
  if (typingDiv) {
    typingDiv.remove();
    typingDiv = null;
  }
}

export function openModal(titleText, bodyHtml) {
  elements.modalTitle.innerHTML = `
    <span class="modal-title-mark" aria-hidden="true"></span>
    <span>${escapeHtml(titleText)}</span>
  `;
  elements.modalBody.innerHTML = bodyHtml || "";
  elements.patientModal.classList.add("visible");
  elements.patientModal.setAttribute("aria-hidden", "false");
  elements.modalCloseBtn.focus();
}

export function closeModal() {
  elements.patientModal.classList.remove("visible");
  elements.patientModal.setAttribute("aria-hidden", "true");
  elements.modalBody.innerHTML = "";
  elements.downloadPdfBtn.disabled = true;
  elements.input.focus();
}

export function buildDetailsRow(label, value, isCode = false) {
  if (value === null || value === undefined || value === "") {
    return `
      <div class="details-label">${escapeHtml(label)}</div>
      <div class="details-value muted">N/A</div>
    `;
  }

  const valueClass = isCode ? "details-value details-mono" : "details-value";

  return `
    <div class="details-label">${escapeHtml(label)}</div>
    <div class="${valueClass}">${escapeHtml(String(value))}</div>
  `;
}

function buildReportRow(label, value) {
  if (value === null || value === undefined || value === "") {
    return `
      <div class="report-row-label">${escapeHtml(label)}</div>
      <div class="report-row-value muted">N/A</div>
    `;
  }

  return `
    <div class="report-row-label">${escapeHtml(label)}</div>
    <div class="report-row-value">${escapeHtml(String(value))}</div>
  `;
}

export function buildRowDetailsSheet(rowObj, title = "Row details") {
  const keys = Object.keys(rowObj || {}).filter((key) => !isPatientIdField(key));
  if (!rowObj || keys.length === 0) {
    return `<p class="modal-subtle">No details are available for this row.</p>`;
  }

  const rowsHtml = keys
    .map((key) => {
      const label = prettifyHeader(key);
      const raw = rowObj[key];

      if (raw === null || raw === undefined || raw === "") {
        return `
          <div class="details-label">${escapeHtml(label)}</div>
          <div class="details-value muted">N/A</div>
        `;
      }

      const pretty = maybeJsonPretty(raw);
      const valueHtml =
        pretty !== null
          ? `<div class="details-value details-mono">${escapeHtml(pretty)}</div>`
          : `<div class="details-value">${escapeHtml(raw)}</div>`;

      return `
        <div class="details-label">${escapeHtml(label)}</div>
        ${valueHtml}
      `;
    })
    .join("");

  return `
    <div class="details-sheet">
      <div class="report-heading">
        <div class="report-heading-left">${escapeHtml(title.toUpperCase())}</div>
        <div class="report-heading-right">Generated: ${escapeHtml(formatTimestamp())}</div>
      </div>
      <div class="report-section">
        <div class="report-section-title">Details</div>
        <div class="details-grid">
          ${rowsHtml}
        </div>
      </div>
    </div>
  `;
}

export function buildPatientReport(patient) {
  if (!patient) {
    return "<p class='modal-subtle'>No data was found for this patient.</p>";
  }

  const formatValue = (value) => {
    if (
      value === null ||
      value === undefined ||
      value === "" ||
      value === "null" ||
      value === "undefined"
    ) {
      return "N/A";
    }

    return value;
  };

  const formatGender = (gender) => {
    if (!gender) {
      return "N/A";
    }

    if (
      gender === "1" ||
      gender === 1 ||
      gender === "male" ||
      gender === "Male"
    ) {
      return "Male";
    }

    if (
      gender === "2" ||
      gender === 2 ||
      gender === "female" ||
      gender === "Female"
    ) {
      return "Female";
    }

    return gender;
  };

  const formatBoolean = (value) => {
    if (value === null || value === undefined || value === "") {
      return "N/A";
    }

    if (value === true || value === "true" || value === "TRUE" || value === 1 || value === "1") {
      return "Yes";
    }

    if (value === false || value === "false" || value === "FALSE" || value === 0 || value === "0") {
      return "No";
    }

    return value;
  };

  const compactDate = (value) => {
    if (!value) {
      return "N/A";
    }

    const text = String(value);
    return text.length >= 10 ? text.slice(0, 10) : text;
  };

  const fullName =
    patient.full_name ||
    [patient.first_name, patient.second_name, patient.third_name, patient.last_name]
      .filter(Boolean)
      .join(" ")
      .trim();

  const addressParts = [
    patient.address_street_name,
    patient.address_house_apartment_number,
    patient.address_additional_address_line,
    patient.address_postal_zip_code,
  ].filter(Boolean);

  const bloodPressure =
    patient.patient_health_blood_pressure === "/"
      ? null
      : patient.patient_health_blood_pressure;

  const overviewHtml = `
    <div class="report-section">
      <div class="report-section-title">Patient Identity</div>
      <div class="report-grid">
        ${buildReportRow("Medical Record Number", formatValue(patient.medical_record_number))}
        ${buildReportRow("Full Name", formatValue(fullName))}
        ${buildReportRow("Date of Birth", compactDate(patient.date_of_birth))}
        ${buildReportRow("Sex At Birth", formatGender(patient.sex_at_birth))}
        ${buildReportRow("Patient Class", formatValue(patient.patient_classes))}
        ${buildReportRow("Verified", formatBoolean(patient.is_verified))}
        ${buildReportRow("Completed Profile", formatBoolean(patient.is_completed_patient))}
      </div>
    </div>
  `;

  const contactHtml = `
    <div class="report-section">
      <div class="report-section-title">Contact and Preferences</div>
      <div class="report-grid">
        ${buildReportRow("Primary Mobile", formatValue(patient.primary_mobile_number))}
        ${buildReportRow("Secondary Mobile", formatValue(patient.second_mobile_number))}
        ${buildReportRow("Home Phone", formatValue(patient.home_phone))}
        ${buildReportRow("Work Phone", formatValue(patient.work_phone))}
        ${buildReportRow("Email", formatValue(patient.email))}
        ${buildReportRow("Preferred Contact", formatValue(patient.preferred_way_of_contact))}
        ${buildReportRow("Receive SMS", formatBoolean(patient.receive_sms))}
        ${buildReportRow("Receive Email", formatBoolean(patient.receive_email))}
        ${buildReportRow("Native Language", formatValue(patient.native_language))}
      </div>
    </div>
  `;

  const personalHtml = `
    <div class="report-section">
      <div class="report-section-title">Personal and Address</div>
      <div class="report-grid">
        ${buildReportRow("Marital Status", formatValue(patient.marital_status))}
        ${buildReportRow("Nationality", formatValue(patient.nationality))}
        ${buildReportRow("Religion", formatValue(patient.religion))}
        ${buildReportRow("Ethnicity", formatValue(patient.ethnicity))}
        ${buildReportRow("Occupation", formatValue(patient.occupation))}
        ${buildReportRow("Educational Level", formatValue(patient.educational_level))}
        ${buildReportRow("Responsible Party", formatValue(patient.responsible_party))}
        ${buildReportRow("Emergency Contact", formatValue(patient.emergency_contact_name))}
        ${buildReportRow("Emergency Relation", formatValue(patient.emergency_contact_relation))}
        ${buildReportRow("Emergency Phone", formatValue(patient.emergency_contact_phone))}
        ${buildReportRow("Address", formatValue(addressParts.join(", ")))}
      </div>
    </div>
  `;

  const clinicalHtml = `
    <div class="report-section">
      <div class="report-section-title">Clinical Summary</div>
      <div class="report-grid">
        ${buildReportRow("Diagnosis", formatValue(patient.patient_details_description))}
        ${buildReportRow("Diagnosis Code", formatValue(patient.patient_details_diagnose_code))}
        ${buildReportRow("Diagnosis Type", formatValue(patient.patient_details_diagnosis_type))}
        ${buildReportRow("Allergies", formatValue(patient.patient_health_allergies))}
        ${buildReportRow("Allergy Severity", formatValue(patient.patient_health_allergy_severity))}
        ${buildReportRow("Allergy Note", formatValue(patient.patient_health_allergy_note))}
        ${buildReportRow("Chronic Conditions", formatValue(patient.patient_health_chronic_conditions))}
        ${buildReportRow("Problem Status", formatValue(patient.patient_health_problem_status))}
        ${buildReportRow("Blood Pressure", formatValue(bloodPressure))}
        ${buildReportRow("Heart Rate", formatValue(patient.patient_health_heart_rate))}
        ${buildReportRow("Temperature", formatValue(patient.patient_health_temperature))}
        ${buildReportRow("Oxygen Saturation", formatValue(patient.patient_health_oxygen_saturation))}
        ${buildReportRow("Respiratory Rate", formatValue(patient.patient_health_respiratory_rate))}
        ${buildReportRow("Smoking Status", formatValue(patient.patient_health_smoking_status))}
        ${buildReportRow("Alcohol Use", formatValue(patient.patient_health_alcohol_use))}
        ${buildReportRow("Substance Use", formatValue(patient.patient_health_substance_use))}
        ${buildReportRow("Physical Limitation", formatValue(patient.patient_health_physical_limitation))}
        ${buildReportRow("Last Checkup Date", compactDate(patient.patient_health_last_checkup_date))}
        ${buildReportRow("Reason Of Visit", formatValue(patient.patient_health_reason_of_visit))}
        ${buildReportRow("Patient Conditions", formatValue(patient.patient_health_patient_conditions))}
        ${buildReportRow("Functional Status", formatValue(patient.patient_health_functional_status))}
        ${buildReportRow("Cognitive Check", formatValue(patient.patient_health_cognitive_check))}
        ${buildReportRow("Clinical Notes", formatValue(patient.patient_health_notes))}
      </div>
    </div>
  `;

  const adminHtml = `
    <div class="report-section">
      <div class="report-section-title">Insurance and Administrative</div>
      <div class="report-grid">
        ${buildReportRow("Insurance Provider", formatValue(patient.patient_details_insurance_provider))}
        ${buildReportRow("Policy Number", formatValue(patient.patient_details_policy_number))}
        ${buildReportRow("Group Number", formatValue(patient.patient_details_group_number))}
        ${buildReportRow("Expiration Date", compactDate(patient.patient_details_expiration_date))}
        ${buildReportRow("Remaining Benefits", formatValue(patient.patient_details_remaining_benefits))}
        ${buildReportRow("Remaining Deductibles", formatValue(patient.patient_details_remaining_deductibles))}
        ${buildReportRow("Private Patient", formatBoolean(patient.is_private_patient))}
        ${buildReportRow("Role", formatValue(patient.role))}
        ${buildReportRow("Previous ID", formatValue(patient.previous_id))}
        ${buildReportRow("Archiving Number", formatValue(patient.archiving_number))}
        ${buildReportRow("Unknown Patient", formatBoolean(patient.is_unknown))}
        ${buildReportRow("Created Date", compactDate(patient.created_date))}
        ${buildReportRow("Last Modified", compactDate(patient.last_modified_date))}
        ${buildReportRow("Details", formatValue(patient.details))}
      </div>
    </div>
  `;

  return `
    <div class="patient-report">
      <div class="report-heading">
        <div class="report-heading-left">Patient Information Sheet</div>
        <div class="report-heading-right">Generated: ${formatTimestamp()}</div>
      </div>
      ${overviewHtml}
      ${contactHtml}
      ${personalHtml}
      ${clinicalHtml}
      ${adminHtml}
    </div>
  `;
}

export function buildAuditDetailsMarkup({
  title,
  recordLabel,
  recordId,
  interaction,
  serviceCalls,
}) {
  const serviceCallRows =
    serviceCalls.length > 0
      ? serviceCalls
          .map((call, index) => {
            let requestJson = null;
            let responseJson = null;

            try {
              if (call.request_json) {
                requestJson =
                  typeof call.request_json === "string"
                    ? JSON.stringify(JSON.parse(call.request_json), null, 2)
                    : JSON.stringify(call.request_json, null, 2);
              }
            } catch (_) {
              requestJson = String(call.request_json);
            }

            try {
              if (call.response_json) {
                responseJson =
                  typeof call.response_json === "string"
                    ? JSON.stringify(JSON.parse(call.response_json), null, 2)
                    : JSON.stringify(call.response_json, null, 2);
              }
            } catch (_) {
              responseJson = String(call.response_json);
            }

            return `
              ${buildDetailsRow(`Service ${index + 1}`, call.service)}
              ${buildDetailsRow("URL", call.url)}
              ${buildDetailsRow("Status", call.ok ? "OK" : "Error")}
              ${buildDetailsRow("HTTP Code", call.status_code)}
              ${buildDetailsRow("Latency", call.latency_ms ? `${call.latency_ms}ms` : null)}
              ${buildDetailsRow("Request", requestJson, true)}
              ${buildDetailsRow("Response", responseJson, true)}
              ${buildDetailsRow("Error", call.error)}
            `;
          })
          .join("")
      : "";

  return `
    <div class="details-sheet">
      <div class="report-heading">
        <div class="report-heading-left">${escapeHtml(title)}</div>
        <div class="report-heading-right">${escapeHtml(recordLabel)}: ${escapeHtml(recordId)}</div>
      </div>
      <div class="report-section">
        <div class="report-section-title">Interaction</div>
        <div class="details-grid">
          ${buildDetailsRow("ID", interaction.id)}
          ${buildDetailsRow("Timestamp (UTC)", interaction.ts_utc)}
          ${buildDetailsRow("User ID", interaction.user_id)}
          ${buildDetailsRow("Session ID", interaction.session_id)}
          ${buildDetailsRow("Role", interaction.role)}
          ${buildDetailsRow("Intent", interaction.intent)}
          ${buildDetailsRow("Approved", interaction.approved ? "Yes" : "No")}
          ${buildDetailsRow("Raw Message", interaction.raw_message)}
          ${buildDetailsRow("Final Message", interaction.final_message)}
          ${buildDetailsRow("Reply Text", interaction.reply_text)}
          ${buildDetailsRow("SQL Query", interaction.sql_query, true)}
          ${buildDetailsRow("Row Count", interaction.row_count)}
          ${buildDetailsRow("Status", interaction.ok ? "OK" : "Error")}
          ${buildDetailsRow("Error", interaction.error)}
        </div>
      </div>
      ${
        serviceCalls.length > 0
          ? `
            <div class="report-section">
              <div class="report-section-title">Service Calls (${serviceCalls.length})</div>
              <div class="details-grid">
                ${serviceCallRows}
              </div>
            </div>
          `
          : ""
      }
    </div>
  `;
}

export function addTable(rows, columns, contextMessage = null, handlers = {}) {
  if (!rows || rows.length === 0) {
    return;
  }

  const normalizeContext = (context) => {
    if (!context) {
      return { userMessage: null, summaryText: null, intent: null, title: null };
    }

    if (typeof context === "string") {
      return { userMessage: null, summaryText: context, intent: null, title: null };
    }

    if (typeof context === "object") {
      return {
        userMessage: typeof context.userMessage === "string" ? context.userMessage : null,
        summaryText: typeof context.summaryText === "string" ? context.summaryText : null,
        intent: typeof context.intent === "string" ? context.intent : null,
        title: typeof context.title === "string" ? context.title : null,
      };
    }

    return { userMessage: null, summaryText: null, intent: null, title: null };
  };

  const context = normalizeContext(contextMessage);
  const contextText = [context.userMessage, context.summaryText].filter(Boolean).join("\n");

  const headers = columns && columns.length ? columns : Object.keys(rows[0]);
  const displayHeaders = headers.filter((header) => !isPatientIdField(header));
  if (displayHeaders.length === 0) {
    addMessage(
      "Results returned, but patient identifiers are hidden. Include medical_record_number (MRN) in your query to view patient details.",
      "assistant",
      "summary-chip"
    );
    return;
  }
  const renderAsRecordView = rows.length === 1 && displayHeaders.length > 6;
  const wrapper = document.createElement("div");
  wrapper.classList.add("message", "assistant", "results-card");

  const headerDiv = document.createElement("div");
  headerDiv.className = "results-header";

  const title = document.createElement("div");
  title.className = "results-title";
  title.textContent = "Query results";

  const meta = document.createElement("div");
  meta.className = "results-meta";
  meta.textContent = rows.length === 1 ? "1 record" : `${rows.length} records`;

  headerDiv.append(title, meta);
  wrapper.appendChild(headerDiv);

  const formatGender = (gender) => {
    if (gender === null || gender === undefined || gender === "") {
      return "";
    }

    const genderText = String(gender).toLowerCase();
    if (genderText === "1" || genderText === "male") {
      return "Male";
    }

    if (genderText === "2" || genderText === "female") {
      return "Female";
    }

    return gender;
  };

  if (renderAsRecordView) {
    const recordContainer = document.createElement("div");
    recordContainer.className = "results-record";

    displayHeaders.forEach((header) => {
      const keyDiv = document.createElement("div");
      keyDiv.className = "results-record-key";
      keyDiv.textContent = prettifyHeader(header);

      const valueDiv = document.createElement("div");
      valueDiv.className = "results-record-value";

      const rawValue = rows[0][header];
      const pretty = maybeJsonPretty(rawValue);
      const lower = header.toLowerCase();
      const displayValue =
        lower.includes("gender") || lower === "gender_lkey"
          ? formatGender(rawValue)
          : pretty !== null
            ? pretty
            : rawValue == null || rawValue === ""
              ? "N/A"
              : String(rawValue);

      valueDiv.textContent = displayValue;
      valueDiv.title = displayValue;
      if (pretty !== null) {
        valueDiv.classList.add("results-record-value-mono");
      }

      recordContainer.append(keyDiv, valueDiv);
    });

    wrapper.appendChild(recordContainer);
    elements.chatArea.appendChild(wrapper);
    elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
    return;
  }

  const tableContainer = document.createElement("div");
  tableContainer.className = "results-table-wrapper";

  const table = document.createElement("table");
  const columnWidthPercent = 100 / displayHeaders.length;
  table.style.width = "100%";

  const colgroup = document.createElement("colgroup");
  displayHeaders.forEach(() => {
    const col = document.createElement("col");
    col.style.width = `${columnWidthPercent}%`;
    colgroup.appendChild(col);
  });

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  displayHeaders.forEach((header) => {
    const th = document.createElement("th");
    const label = prettifyHeader(header);
    th.textContent = label;
    th.title = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  const tbody = document.createElement("tbody");
  const isAuditTable = headers.some((header) => {
    const lower = header.toLowerCase();
    return (
      (lower === "id" && headers.some((candidate) => candidate.toLowerCase() === "ts_utc")) ||
      lower === "ts_utc" ||
      lower === "raw_message" ||
      lower === "sql_query" ||
      lower === "interaction_id"
    );
  });

  const mrnKey = headers.find((header) => isMedicalRecordNumberField(header));
  const nameKey = headers.find((header) => header.toLowerCase().includes("name"));
  const eventIdKey = isAuditTable
    ? headers.find((header) => header.toLowerCase() === "id")
    : null;

  const inferWantsPatientDetails = () => {
    const text = (context.userMessage || "").toLowerCase();
    if (!text) {
      return false;
    }

    // Only treat as patient-profile intent when the user explicitly asks for patient info,
    // not when they ask for orders/results/etc that happen to include patient identifiers.
    return (
      (text.includes("patient") && (text.includes("detail") || text.includes("profile"))) ||
      text.includes("demographics") ||
      text.includes("who is this patient") ||
      text.includes("show patient") ||
      text.includes("open patient")
    );
  };

  const inferLikelyPatientTable = () => {
    const lowerHeaders = headers.map((h) => String(h).toLowerCase());
    const patientSignals = [
      "dob",
      "date_of_birth",
      "birth",
      "gender",
      "mrn",
      "medical_record_number",
      "address",
      "phone",
      "email",
      "insurance",
    ];
    const nonPatientSignals = [
      "lab",
      "order",
      "result",
      "diagnos",
      "procedure",
      "medication",
      "allerg",
      "specimen",
      "imaging",
      "status",
    ];

    const patientSignalCount = patientSignals.reduce(
      (acc, sig) => acc + (lowerHeaders.some((h) => h.includes(sig)) ? 1 : 0),
      0
    );
    const hasNonPatientSignal = nonPatientSignals.some((sig) =>
      lowerHeaders.some((h) => h.includes(sig))
    );

    // Conservative: auto-open patient details only for tables that look like patient demographic lists.
    return patientSignalCount >= 2 && !hasNonPatientSignal;
  };

  const wantsPatientDetails = inferWantsPatientDetails();
  const likelyPatientTable = inferLikelyPatientTable();

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    displayHeaders.forEach((header) => {
      const td = document.createElement("td");
      const value = row[header];
      const lower = header.toLowerCase();
      const text =
        lower.includes("gender") || lower === "gender_lkey"
          ? formatGender(value)
          : value == null
            ? ""
            : String(value);

      td.textContent = text;
      td.title = text;
      tr.appendChild(td);
    });

    tr.addEventListener("click", async () => {
      if (isAuditTable && eventIdKey && row[eventIdKey] != null && handlers.onInteractionRow) {
        await handlers.onInteractionRow(row[eventIdKey]);
        return;
      }

      let medicalRecordNumber = null;
      let mrnSource = null;

      if (mrnKey && row[mrnKey] != null && row[mrnKey] !== "") {
        medicalRecordNumber = row[mrnKey];
        mrnSource = "mrn_column";
      }

      if (!medicalRecordNumber) {
        for (const key of Object.keys(row)) {
          if (isMedicalRecordNumberField(key) && row[key] != null && row[key] !== "") {
            medicalRecordNumber = row[key];
            mrnSource = "mrn_column";
            break;
          }
        }
      }

      if (!medicalRecordNumber && contextText) {
        const match = contextText.match(
          /\b(?:mrn|medical\s+record(?:\s+number)?|record|medical\s+number)\s*#?\s*:?\s*([A-Za-z0-9_-]{1,30})\b/i
        );
        if (match) {
          medicalRecordNumber = match[1];
          mrnSource = "context";
        }
      }

      const name = nameKey ? row[nameKey] : null;

      const hasConfidentMrn =
        Boolean(medicalRecordNumber) && (mrnSource === "mrn_column" || mrnSource === "context");

      const shouldOpenPatientDetails =
        hasConfidentMrn &&
        Boolean(handlers.onPatientRow) &&
        (wantsPatientDetails || likelyPatientTable);

      if (shouldOpenPatientDetails) {
        await handlers.onPatientRow(String(medicalRecordNumber), name);
        return;
      }

      elements.downloadPdfBtn.disabled = false;
      const actionId = "viewPatientDetailsBtn";
      const actionsHtml =
        hasConfidentMrn && handlers.onPatientRow
          ? `
            <div class="modal-inline-actions">
              <button type="button" class="header-btn" id="${actionId}">
                View patient details
              </button>
            </div>
          `
          : "";

      openModal("Row details", `${actionsHtml}${buildRowDetailsSheet(row, "Row details")}`);

      if (medicalRecordNumber && handlers.onPatientRow) {
        const btn = elements.modalBody.querySelector(`#${actionId}`);
        if (btn) {
          btn.addEventListener("click", async (event) => {
            event.preventDefault();
            btn.disabled = true;
            await handlers.onPatientRow(String(medicalRecordNumber), name);
          });
        }
      }
    });

    tbody.appendChild(tr);
  });

  table.append(colgroup, thead, tbody);
  tableContainer.appendChild(table);
  wrapper.appendChild(tableContainer);

  elements.chatArea.appendChild(wrapper);
  elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
}

function formatFilterLabel(value) {
  if (!value) {
    return null;
  }
  return String(value).replace(/_/g, " ");
}

function buildKpiValue(viewModel) {
  if (Array.isArray(viewModel.y) && viewModel.y.length) {
    const first = viewModel.y[0];
    if (first == null) {
      return "0";
    }
    return String(first);
  }

  if (Array.isArray(viewModel.rows) && viewModel.rows.length) {
    const firstRow = viewModel.rows[0];
    if (Array.isArray(firstRow) && firstRow.length > 1) {
      return firstRow[1] == null ? "0" : String(firstRow[1]);
    }
  }

  return "0";
}

function renderBarChart(viewModel) {
  const chart = document.createElement("div");
  chart.className = "stats-chart stats-chart-bar";

  const values = viewModel.y.map((val) => Number(val) || 0);
  const max = Math.max(1, ...values);

  viewModel.x.forEach((label, idx) => {
    const row = document.createElement("div");
    row.className = "stats-bar-row";

    const labelDiv = document.createElement("div");
    labelDiv.className = "stats-bar-label";
    labelDiv.textContent = label == null ? "" : String(label);

    const barTrack = document.createElement("div");
    barTrack.className = "stats-bar-track";

    const barFill = document.createElement("div");
    barFill.className = "stats-bar-fill";

    const value = values[idx] || 0;
    barFill.style.width = `${Math.round((value / max) * 100)}%`;
    barFill.setAttribute("aria-label", `${labelDiv.textContent}: ${value}`);

    const valueDiv = document.createElement("div");
    valueDiv.className = "stats-bar-value";
    valueDiv.textContent = String(value);

    barTrack.appendChild(barFill);
    row.append(labelDiv, barTrack, valueDiv);
    chart.appendChild(row);
  });

  return chart;
}

function renderLineChart(viewModel) {
  const wrap = document.createElement("div");
  wrap.className = "stats-chart stats-chart-line";

  const values = viewModel.y.map((val) => Number(val) || 0);
  const max = Math.max(1, ...values);
  const min = Math.min(0, ...values);
  const range = Math.max(1, max - min);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 40");
  svg.setAttribute("class", "stats-line-svg");
  svg.setAttribute("role", "img");

  const n = Math.max(1, values.length);
  const points = values
    .map((v, i) => {
      const x = n === 1 ? 50 : (i / (n - 1)) * 100;
      const y = 36 - ((v - min) / range) * 32;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  polyline.setAttribute("points", points);
  polyline.setAttribute("fill", "none");
  polyline.setAttribute("stroke", "currentColor");
  polyline.setAttribute("stroke-width", "2.2");
  polyline.setAttribute("stroke-linecap", "round");
  polyline.setAttribute("stroke-linejoin", "round");

  svg.appendChild(polyline);

  const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  axis.setAttribute("x1", "0");
  axis.setAttribute("x2", "100");
  axis.setAttribute("y1", "36");
  axis.setAttribute("y2", "36");
  axis.setAttribute("stroke", "rgba(120, 140, 160, 0.35)");
  axis.setAttribute("stroke-width", "1");
  svg.appendChild(axis);

  wrap.appendChild(svg);

  const legend = document.createElement("div");
  legend.className = "stats-line-labels";
  const firstLabel = viewModel.x[0];
  const lastLabel = viewModel.x[viewModel.x.length - 1];
  legend.textContent =
    viewModel.x.length > 1
      ? `${firstLabel == null ? "" : String(firstLabel)} → ${lastLabel == null ? "" : String(lastLabel)}`
      : firstLabel == null
        ? ""
        : String(firstLabel);
  wrap.appendChild(legend);
  return wrap;
}

function renderPieChart(viewModel) {
  const wrap = document.createElement("div");
  wrap.className = "stats-chart stats-chart-pie";

  const palette = ["#2f6fed", "#26a6a6", "#f2a93b", "#ef5a5a", "#7b61ff", "#22c55e"];

  const values = viewModel.y.map((val) => Math.max(0, Number(val) || 0));
  const total = values.reduce((sum, v) => sum + v, 0) || 1;

  let start = 0;
  const segments = values.map((v, idx) => {
    const pct = (v / total) * 100;
    const end = start + pct;
    const seg = `${palette[idx % palette.length]} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
    start = end;
    return seg;
  });

  const pie = document.createElement("div");
  pie.className = "stats-pie";
  pie.style.background = `conic-gradient(${segments.join(", ")})`;

  const legend = document.createElement("div");
  legend.className = "stats-pie-legend";
  viewModel.x.forEach((label, idx) => {
    const item = document.createElement("div");
    item.className = "stats-pie-item";

    const swatch = document.createElement("span");
    swatch.className = "stats-pie-swatch";
    swatch.style.backgroundColor = palette[idx % palette.length];

    const text = document.createElement("span");
    const pct = Math.round((values[idx] / total) * 100);
    text.textContent = `${label == null ? "" : String(label)} (${pct}%)`;

    item.append(swatch, text);
    legend.appendChild(item);
  });

  wrap.append(pie, legend);
  return wrap;
}

export function addStatisticsResult(payload) {
  const vm = buildStatisticsViewModel(payload);

  const wrapper = document.createElement("div");
  wrapper.className = "message assistant statistics-card";
  wrapper.setAttribute("role", "status");
  wrapper.setAttribute("aria-live", "polite");

  const header = document.createElement("div");
  header.className = "statistics-header";

  const title = document.createElement("div");
  title.className = "statistics-title";
  title.textContent = vm.title;

  const filters = document.createElement("div");
  filters.className = "statistics-filters";
  const dateLabel = formatFilterLabel(vm.dateRange);
  if (dateLabel) {
    const chip = document.createElement("span");
    chip.className = "statistics-filter-chip";
    chip.textContent = dateLabel;
    filters.appendChild(chip);
  }

  header.append(title, filters);

  const summary = document.createElement("div");
  summary.className = "statistics-summary";
  summary.textContent = vm.summary;

  const content = document.createElement("div");
  content.className = "statistics-content";

  const chartPanel = document.createElement("div");
  chartPanel.className = "statistics-panel";

  const chartHeading = document.createElement("div");
  chartHeading.className = "statistics-panel-title";
  chartHeading.textContent = "Chart";
  chartPanel.appendChild(chartHeading);

  if (vm.chartType === "bar_chart") {
    chartPanel.appendChild(renderBarChart(vm));
  } else if (vm.chartType === "line_chart") {
    chartPanel.appendChild(renderLineChart(vm));
  } else if (vm.chartType === "pie_chart") {
    chartPanel.appendChild(renderPieChart(vm));
  } else {
    const kpi = document.createElement("div");
    kpi.className = "stats-kpi";
    kpi.textContent = buildKpiValue(vm);
    chartPanel.appendChild(kpi);
  }

  const tablePanel = document.createElement("div");
  tablePanel.className = "statistics-panel";

  const tableHeading = document.createElement("div");
  tableHeading.className = "statistics-panel-title";
  tableHeading.textContent = "Table";
  tablePanel.appendChild(tableHeading);

  const tableEl = document.createElement("table");
  tableEl.className = "statistics-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  vm.columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = String(col);
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  tableEl.appendChild(thead);

  const tbody = document.createElement("tbody");
  vm.rows.forEach((row) => {
    const tr = document.createElement("tr");
    if (Array.isArray(row)) {
      row.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = cell == null ? "" : String(cell);
        tr.appendChild(td);
      });
    }
    tbody.appendChild(tr);
  });
  tableEl.appendChild(tbody);
  tablePanel.appendChild(tableEl);

  content.append(chartPanel, tablePanel);
  wrapper.append(header, summary, content);

  elements.chatArea.appendChild(wrapper);
  elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
}

export function addRecord(record, columns = null, titleText = "Query results") {
  if (!record || typeof record !== "object") {
    return;
  }

  const headers = (columns && columns.length ? columns : Object.keys(record)).filter(
    (header) => !isPatientIdField(header)
  );
  const wrapper = document.createElement("div");
  wrapper.classList.add("message", "assistant", "results-card");

  const headerDiv = document.createElement("div");
  headerDiv.className = "results-header";

  const title = document.createElement("div");
  title.className = "results-title";
  title.textContent = titleText;

  const meta = document.createElement("div");
  meta.className = "results-meta";
  meta.textContent = "Profile view";

  headerDiv.append(title, meta);
  wrapper.appendChild(headerDiv);

  const recordContainer = document.createElement("div");
  recordContainer.className = "results-record";

  const formatGender = (gender) => {
    if (gender === null || gender === undefined || gender === "") {
      return "";
    }

    const genderText = String(gender).toLowerCase();
    if (genderText === "1" || genderText === "male") {
      return "Male";
    }

    if (genderText === "2" || genderText === "female") {
      return "Female";
    }

    return gender;
  };

  headers.forEach((header) => {
    const keyDiv = document.createElement("div");
    keyDiv.className = "results-record-key";
    keyDiv.textContent = prettifyHeader(header);

    const valueDiv = document.createElement("div");
    valueDiv.className = "results-record-value";

    const rawValue = record[header];
    const pretty = maybeJsonPretty(rawValue);
    const lower = header.toLowerCase();
    const displayValue =
      lower.includes("gender") || lower === "gender_lkey"
        ? formatGender(rawValue)
        : pretty !== null
          ? pretty
          : rawValue == null || rawValue === ""
            ? "N/A"
            : String(rawValue);

    valueDiv.textContent = displayValue;
    valueDiv.title = displayValue;
    if (pretty !== null) {
      valueDiv.classList.add("results-record-value-mono");
    }

    recordContainer.append(keyDiv, valueDiv);
  });

  wrapper.appendChild(recordContainer);
  elements.chatArea.appendChild(wrapper);
  elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
}

export function showApprovalButtons(original, corrected, userId, onApprove, onReject) {
  const wrapper = document.createElement("div");
  wrapper.className = "approval-buttons";

  const approveBtn = document.createElement("button");
  approveBtn.className = "approval-btn approve";
  approveBtn.type = "button";
  approveBtn.textContent = "Approve";
  approveBtn.addEventListener("click", async () => {
    wrapper.remove();
    addMessage("Approved correction.", "user");
    await onApprove(corrected, userId, true, original);
  });

  const rejectBtn = document.createElement("button");
  rejectBtn.className = "approval-btn reject";
  rejectBtn.type = "button";
  rejectBtn.textContent = "Reject";
  rejectBtn.addEventListener("click", async () => {
    wrapper.remove();
    addMessage("Proceeding with your original message.", "assistant", "summary-chip");
    await onReject(original, userId);
  });

  wrapper.append(approveBtn, rejectBtn);
  elements.chatArea.appendChild(wrapper);
  elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
}

export function openPrintDialog() {
  const report = elements.patientModal.querySelector(".patient-report, .details-sheet");
  if (!report) {
    return { ok: false, error: "No details are available to export." };
  }

  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    return {
      ok: false,
      error: "The browser blocked the print window. Allow pop-ups to export PDF files.",
    };
  }

  printWindow.document.write(`
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <title>Details</title>
        <style>
          body {
            margin: 24px;
            color: #132238;
            background: #ffffff;
            font-family: "Segoe UI", Arial, sans-serif;
          }
          .details-sheet,
          .patient-report {
            width: 100%;
            overflow: hidden;
            border-radius: 18px;
            border: 1px solid #d5dfeb;
            background: #ffffff;
          }
          .report-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 14px 16px;
            border-bottom: 1px solid #d5dfeb;
            background: #f5f9fc;
          }
          .report-heading-left {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
          }
          .report-heading-right {
            color: #6f8096;
            font-size: 11px;
          }
          .report-section {
            border-top: 1px solid #e4ebf4;
          }
          .report-section:first-of-type {
            border-top: none;
          }
          .report-section-title {
            padding: 10px 16px;
            border-bottom: 1px solid #e4ebf4;
            background: #f8fbfd;
            font-size: 11px;
            font-weight: 700;
          }
          .report-grid {
            display: grid;
            grid-template-columns: 1.15fr 2.2fr 1.15fr 2.2fr;
          }
          .details-grid {
            display: grid;
            grid-template-columns: 1.2fr 2.8fr;
          }
          .report-row-label,
          .details-label {
            padding: 10px 12px;
            border-right: 1px solid #e4ebf4;
            border-bottom: 1px solid #e4ebf4;
            background: #f8fbfd;
            font-size: 11px;
            font-weight: 700;
          }
          .report-row-value,
          .details-value {
            padding: 10px 12px;
            border-bottom: 1px solid #e4ebf4;
            color: #43556f;
            font-size: 11px;
            white-space: pre-wrap;
          }
          .details-mono {
            font-family: Consolas, "Courier New", monospace;
          }
          @media print {
            body {
              margin: 0;
            }
          }
        </style>
      </head>
      <body>${report.outerHTML}</body>
    </html>
  `);
  printWindow.document.close();
  window.setTimeout(() => {
    printWindow.focus();
    printWindow.print();
  }, 150);

  return { ok: true };
}
