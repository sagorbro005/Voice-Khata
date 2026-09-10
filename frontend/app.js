const API_BASE = (window.VoiceKhataConfig ? window.VoiceKhataConfig.getApiBase() : (window.API_BASE || ((window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") && window.location.port === "8001" ? "http://127.0.0.1:8001" : "http://127.0.0.1:8000")));

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let currentTranscript = "";

// Store raw numeric extraction state
let currentExtraction = null;
let currentEntriesList = [];

// DOM Elements
const recordBtn = document.getElementById("recordBtn");
const recordStatus = document.getElementById("recordStatus");
const audioFileInput = document.getElementById("audioFileInput");
const transcriptDisplay = document.getElementById("transcriptDisplay");
const extractBtn = document.getElementById("extractBtn");
const confirmBtn = document.getElementById("confirmBtn");

const editTransactionType = document.getElementById("editTransactionType");
const editCustomer = document.getElementById("editCustomer");
const editItem = document.getElementById("editItem");
const editQuantity = document.getElementById("editQuantity");
const editTotalAmount = document.getElementById("editTotalAmount");
const editPaidAmount = document.getElementById("editPaidAmount");
const editDueAmount = document.getElementById("editDueAmount");
const editMatchedId = document.getElementById("editMatchedId");

const kpiTotalSales = document.getElementById("kpiTotalSales");
const kpiTotalPaid = document.getElementById("kpiTotalPaid");
const kpiTotalDues = document.getElementById("kpiTotalDues");
const kpiCustomerCount = document.getElementById("kpiCustomerCount");

const getSummaryBtn = document.getElementById("getSummaryBtn");
const summaryAudioPlayer = document.getElementById("summaryAudioPlayer");
const summaryTextDisplay = document.getElementById("summaryTextDisplay");
const ledgerTableBody = document.getElementById("ledgerTableBody");
const errorBanner = document.getElementById("errorBanner");
const apiStatusBadge = document.getElementById("apiStatusBadge");

// Edit Modal Elements
const editModalOverlay = document.getElementById("editModalOverlay");
const modalCloseBtn = document.getElementById("modalCloseBtn");
const modalCancelBtn = document.getElementById("modalCancelBtn");
const modalSaveBtn = document.getElementById("modalSaveBtn");
const modalEntryId = document.getElementById("modalEntryId");
const modalCustomer = document.getElementById("modalCustomer");
const modalItem = document.getElementById("modalItem");
const modalQuantity = document.getElementById("modalQuantity");
const modalTotal = document.getElementById("modalTotal");
const modalPaid = document.getElementById("modalPaid");
const modalDue = document.getElementById("modalDue");

// Helper function to convert Western digits to Bengali numerals
function toBanglaNumerals(num) {
    if (num === null || num === undefined || num === "") return "-";
    const banglaDigits = ['০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯'];
    const strVal = typeof num === 'number' ? String(num) : String(num);
    return strVal.replace(/[0-9]/g, (digit) => banglaDigits[parseInt(digit)]);
}

// Parse Western or Bengali numbers from input string
function parseBanglaOrEnglishNumber(val) {
    if (val === null || val === undefined || val === "") return null;
    let s = String(val).replace(/[৳,\s]/g, '').trim();
    if (!s || s === "-") return null;
    const banglaDigits = {'০':'0', '১':'1', '২':'2', '৩':'3', '৪':'4', '৫':'5', '৬':'6', '৭':'7', '৮':'8', '৯':'9'};
    s = s.replace(/[০-৯]/g, d => banglaDigits[d]);
    const num = parseFloat(s);
    return isNaN(num) ? null : num;
}

// Friendly Bangla label for transaction_type
function getTransactionTypeBanglaLabel(type) {
    if (type === "new_sale") return "নতুন বিক্রয়";
    if (type === "update_existing") return "হিসাব আপডেট";
    return type;
}

// Helper to format date into Bangla format
function formatBanglaDate(dateStr) {
    if (!dateStr) return "-";
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString("bn-BD", {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return toBanglaNumerals(dateStr);
    }
}

// Theme Switcher Functions
function initTheme() {
    const savedTheme = localStorage.getItem("theme") || "dark";
    setTheme(savedTheme);

    const themeToggleBtn = document.getElementById("themeToggleBtn");
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
            const newTheme = currentTheme === "dark" ? "light" : "dark";
            setTheme(newTheme);
        });
    }
}

function setTheme(theme) {
    if (theme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
        localStorage.setItem("theme", "light");
        updateThemeUI("light");
    } else {
        document.documentElement.setAttribute("data-theme", "dark");
        localStorage.setItem("theme", "dark");
        updateThemeUI("dark");
    }
}

function updateThemeUI(theme) {
    const icon = document.getElementById("themeToggleIcon");
    const text = document.getElementById("themeToggleText");
    if (icon && text) {
        if (theme === "light") {
            icon.textContent = "☀️";
            text.textContent = "ডে মোড";
        } else {
            icon.textContent = "🌙";
            text.textContent = "নাইট মোড";
        }
    }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    checkHealth();
    fetchLedgerEntries();

    recordBtn.addEventListener("click", toggleRecording);
    if (audioFileInput) audioFileInput.addEventListener("change", handleFileUpload);
    extractBtn.addEventListener("click", runGemmaExtraction);
    confirmBtn.addEventListener("click", saveConfirmedEntry);
    getSummaryBtn.addEventListener("click", fetchDailySummary);

    // Modal listeners
    modalCloseBtn.addEventListener("click", closeModal);
    modalCancelBtn.addEventListener("click", closeModal);
    modalSaveBtn.addEventListener("click", saveModalEdit);

    // Auto-recalculate modal due when total or paid inputs change
    modalTotal.addEventListener("input", updateModalDueCalculation);
    modalPaid.addEventListener("input", updateModalDueCalculation);

    // Auto-recalculate Step 2 due & enable Save button when vendor types
    editTotalAmount.addEventListener("input", updateStep2DueCalculation);
    editPaidAmount.addEventListener("input", updateStep2DueCalculation);
    editCustomer.addEventListener("input", checkConfirmButtonState);

    // Ask about dues Q&A listeners (Dual Input: Text + Voice)
    const askInsightsBtn = document.getElementById("askInsightsBtn");
    const askInsightsRecordBtn = document.getElementById("askInsightsRecordBtn");
    const insightsQuestionInput = document.getElementById("insightsQuestionInput");
    if (insightsQuestionInput && askInsightsBtn) {
        insightsQuestionInput.addEventListener("input", () => {
            askInsightsBtn.disabled = insightsQuestionInput.value.trim() === "";
        });
    }

    if (askInsightsBtn) {
        askInsightsBtn.addEventListener("click", () => {
            const qText = insightsQuestionInput.value.trim();
            if (qText) submitInsightsQuestion(qText);
        });
    }

    document.querySelectorAll("#insightsCard .sample-q-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            insightsQuestionInput.value = btn.textContent.trim();
            if (askInsightsBtn) askInsightsBtn.disabled = false;
            submitInsightsQuestion(btn.textContent.trim());
        });
    });

    // Voice Record Path for Q&A
    let qnaRecorder = null;
    let qnaChunks = [];
    let isQnaRecording = false;

    if (askInsightsRecordBtn) {
        askInsightsRecordBtn.addEventListener("click", async () => {
            const recordLabel = document.getElementById("askInsightsRecordLabel");
            const recordIcon = document.getElementById("askInsightsRecordIcon");

            if (!isQnaRecording) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    qnaRecorder = new MediaRecorder(stream);
                    qnaChunks = [];

                    qnaRecorder.ondataavailable = (e) => qnaChunks.push(e.data);
                    qnaRecorder.onstop = async () => {
                        const audioBlob = new Blob(qnaChunks, { type: 'audio/wav' });
                        const formData = new FormData();
                        formData.append("file", audioBlob, "qna_question.wav");

                        if (insightsQuestionDisplay) {
                            insightsQuestionDisplay.textContent = "🎙️ ভয়েস রেকর্ড ট্রান্সক্রাইব করা হচ্ছে...";
                        }

                        try {
                            const res = await fetch(`${API_BASE}/transcribe`, { method: "POST", body: formData });
                            const data = await res.json();
                            if (data.transcript) {
                                insightsQuestionInput.value = data.transcript;
                                if (askInsightsBtn) askInsightsBtn.disabled = false;
                                submitInsightsQuestion(data.transcript);
                            }
                        } catch (err) {
                            showError("ভয়েস প্রসেস করতে ব্যর্থ হয়েছে: " + err.message);
                        }
                    };

                    qnaRecorder.start();
                    isQnaRecording = true;
                    if (recordLabel) recordLabel.textContent = "রেকর্ডিং হচ্ছে...";
                    if (recordIcon) recordIcon.textContent = "🔴";
                    askInsightsRecordBtn.classList.add("btn-danger");
                } catch (err) {
                    showError("মাইক্রোফোন সংযোগ ব্যর্থ: " + err.message);
                }
            } else {
                qnaRecorder.stop();
                isQnaRecording = false;
                if (recordLabel) recordLabel.textContent = "বলুন";
                if (recordIcon) recordIcon.textContent = "🎤";
                askInsightsRecordBtn.classList.remove("btn-danger");
            }
        });
    }
});

async function submitInsightsQuestion(questionText) {
    const insightsQuestionInput = document.getElementById("insightsQuestionInput");
    const askInsightsBtn = document.getElementById("askInsightsBtn");
    const insightsQuestionDisplay = document.getElementById("insightsQuestionDisplay");
    const insightsAnswerDisplay = document.getElementById("insightsAnswerDisplay");
    const insightsAudioPlayer = document.getElementById("insightsAudioPlayer");

    if (!questionText) {
        showError("অনুগ্রহ করে প্রশ্ন নির্বাচন অথবা টাইপ করুন।");
        return;
    }

    if (insightsQuestionDisplay) {
        insightsQuestionDisplay.textContent = `❓ প্রশ্ন: "${questionText}"`;
    }
    insightsAnswerDisplay.innerHTML = `<span class="spinner"></span> উত্তর প্রস্তুত করা হচ্ছে...`;
    if (askInsightsBtn) askInsightsBtn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/ledger/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ transcript: questionText })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "উত্তর পেতে ব্যর্থ হয়েছে");
        }

        insightsAnswerDisplay.textContent = data.answer_text;
        if (data.audio_url) {
            insightsAudioPlayer.src = `${API_BASE}${data.audio_url}`;
            insightsAudioPlayer.play().catch(e => console.log("Audio autoplay prevented:", e));
        }
    } catch (err) {
        insightsAnswerDisplay.textContent = "উত্তর পেতে সমস্যা হয়েছে।";
        showError(err.message);
    } finally {
        if (askInsightsBtn) askInsightsBtn.disabled = insightsQuestionInput.value.trim() === "";
    }
}

function checkConfirmButtonState() {
    if (editCustomer.value.trim() !== "") {
        confirmBtn.disabled = false;
    }
}

function updateStep2DueCalculation() {
    const tot = parseBanglaOrEnglishNumber(editTotalAmount.value);
    const pd = parseBanglaOrEnglishNumber(editPaidAmount.value);
    if (tot !== null && pd !== null) {
        editDueAmount.value = `${toBanglaNumerals(tot - pd)} ৳`;
    }
    checkConfirmButtonState();
}

function updateModalDueCalculation() {
    const tot = parseFloat(modalTotal.value);
    const pd = parseFloat(modalPaid.value);
    if (!isNaN(tot) && !isNaN(pd)) {
        modalDue.value = tot - pd;
    }
}

// Display Error / Notification
function showError(msg) {
    if (!msg) {
        errorBanner.style.display = "none";
        return;
    }
    errorBanner.textContent = msg;
    errorBanner.className = "alert-banner alert-error";
    errorBanner.style.display = "block";
    setTimeout(() => {
        errorBanner.style.display = "none";
    }, 6000);
}

function showSuccessNotification(msg) {
    errorBanner.className = "alert-banner alert-success";
    errorBanner.textContent = msg;
    errorBanner.style.display = "block";
    setTimeout(() => {
        errorBanner.style.display = "none";
        errorBanner.className = "alert-banner alert-error";
    }, 4000);
}

// Health Check
async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
            if (apiStatusBadge) {
                apiStatusBadge.className = "badge badge-status";
                apiStatusBadge.innerHTML = `<span class="status-dot"></span> সিস্টেম চালু আছে`;
            }
        } else {
            throw new Error("Health check returned non-200");
        }
    } catch (e) {
        if (apiStatusBadge) {
            apiStatusBadge.className = "badge";
            apiStatusBadge.style.background = "rgba(239, 68, 68, 0.15)";
            apiStatusBadge.style.color = "#fca5a5";
            apiStatusBadge.innerHTML = `<span class="status-dot" style="background:#ef4444;"></span> সংযোগ নেই`;
        }
    }
}

// Microphone Recording
async function toggleRecording() {
    if (!isRecording) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                await uploadAndTranscribe(audioBlob, "recorded_audio.wav");
            };

            mediaRecorder.start();
            isRecording = true;
            recordBtn.classList.add("recording");
            recordStatus.textContent = "রেকর্ডিং হচ্ছে... বন্ধ করতে আবার চাপ দিন";
            recordStatus.style.color = "#ef4444";
        } catch (err) {
            showError("মাইক্রোফোন সংযোগ ব্যর্থ হয়েছে: " + err.message);
        }
    } else {
        mediaRecorder.stop();
        isRecording = false;
        recordBtn.classList.remove("recording");
        recordStatus.textContent = "অডিও প্রসেস করা হচ্ছে...";
        recordStatus.style.color = "var(--text-muted)";
    }
}

// Transcribe uploaded audio file
async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (file) {
        await uploadAndTranscribe(file, file.name);
    }
}

// Send audio to /transcribe endpoint
async function uploadAndTranscribe(audioBlobOrFile, filename) {
    transcriptDisplay.innerHTML = `<span class="spinner"></span> বাংলায় অনুবাদ করা হচ্ছে...`;
    extractBtn.disabled = true;

    const formData = new FormData();
    formData.append("file", audioBlobOrFile, filename);

    try {
        const res = await fetch(`${API_BASE}/transcribe`, {
            method: "POST",
            body: formData
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "ট্রান্সক্রিপশন ব্যর্থ হয়েছে");
        }

        currentTranscript = data.transcript;
        transcriptDisplay.textContent = currentTranscript;
        extractBtn.disabled = false;
        recordStatus.textContent = "হিসাব বলতে মাইক্রোফোনে চাপ দিন";
        recordStatus.style.color = "var(--text-muted)";
    } catch (err) {
        transcriptDisplay.textContent = "অডিও প্রসেস করতে ব্যর্থ হয়েছে।";
        showError(err.message);
    }
}

// Extract JSON entry using Gemma 4 via /extract
async function runGemmaExtraction() {
    if (!currentTranscript) {
        showError("অনুগ্রহ করে প্রথমে কথা বলুন বা অডিও দিন।");
        return;
    }

    extractBtn.disabled = true;
    extractBtn.innerHTML = `<span class="spinner"></span> এআই দিয়ে হিসাব বের করা হচ্ছে...`;

    try {
        const res = await fetch(`${API_BASE}/extract`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ transcript: currentTranscript })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "হিসাব বের করা সম্ভব হয়নি");
        }

        const entry = data.structured_entry;
        const preview = data.preview_update;
        currentExtraction = entry;

        editTransactionType.value = entry.transaction_type || "new_sale";
        editCustomer.value = entry.customer_name || "";
        editItem.value = entry.item || "";
        editQuantity.value = entry.quantity || "";
        editMatchedId.value = entry.matched_entry_id !== null && entry.matched_entry_id !== undefined ? entry.matched_entry_id : "";

        // Display preview update values in Bangla numerals
        if (preview) {
            const sampleOp = Array.isArray(preview) ? preview[0] : preview;
            editTotalAmount.value = sampleOp && sampleOp.total_amount_taka !== null && sampleOp.total_amount_taka !== undefined 
                ? `${toBanglaNumerals(sampleOp.total_amount_taka)} ৳` : "-";
            editPaidAmount.value = sampleOp && sampleOp.paid_amount_taka !== null && sampleOp.paid_amount_taka !== undefined 
                ? `${toBanglaNumerals(sampleOp.paid_amount_taka)} ৳` : "-";
            editDueAmount.value = sampleOp && sampleOp.due_amount_taka !== null && sampleOp.due_amount_taka !== undefined 
                ? `${toBanglaNumerals(sampleOp.due_amount_taka)} ৳` : "-";
        } else {
            editTotalAmount.value = "-";
            editPaidAmount.value = "-";
            editDueAmount.value = "-";
        }

        confirmBtn.disabled = false;
    } catch (err) {
        showError(err.message);
    } finally {
        extractBtn.disabled = false;
        extractBtn.innerHTML = `✨ এআই দিয়ে হিসাব বের করুন`;
    }
}

// Confirm and save entry to SQLite via /confirm
async function saveConfirmedEntry() {
    const customerName = editCustomer.value.trim();
    if (!customerName) {
        showError("গ্রাহকের নাম আবশ্যক।");
        return;
    }

    // Dynamically parse values from Step 2 form input fields (supports both Bengali & Western numerals)
    const userTotal = parseBanglaOrEnglishNumber(editTotalAmount.value);
    const userPaid = parseBanglaOrEnglishNumber(editPaidAmount.value);
    const userDue = parseBanglaOrEnglishNumber(editDueAmount.value);

    const payload = {
        transaction_type: editTransactionType.value,
        customer_name: customerName,
        item: editItem.value.trim() || null,
        quantity: editQuantity.value.trim() || null,
        total_amount_taka: userTotal !== null ? userTotal : (currentExtraction ? currentExtraction.total_amount_taka : null),
        paid_amount_taka: userPaid,
        due_amount_taka: userDue,
        paid_now_taka: currentExtraction ? currentExtraction.paid_now_taka : null,
        stated_due_taka: (userDue !== null && !currentExtraction) ? userDue : (currentExtraction ? currentExtraction.stated_due_taka : null),
        full_settlement: currentExtraction ? Boolean(currentExtraction.full_settlement) : false,
        matched_entry_id: editMatchedId.value ? parseInt(editMatchedId.value) : null
    };

    confirmBtn.disabled = true;
    confirmBtn.innerHTML = `<span class="spinner"></span> সংরক্ষণ হচ্ছে...`;

    try {
        const res = await fetch(`${API_BASE}/confirm`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ entry: payload })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "হিসাব জমা হতে ব্যর্থ হয়েছে");
        }

        renderLedgerTable(data.all_entries);
        showSuccessNotification("হালখাতায় সফলভাবে জমা হয়েছে!");

        // Reset form inputs for next entry
        currentTranscript = "";
        currentExtraction = null;
        transcriptDisplay.textContent = "এন্ট্রি নিশ্চিত ও সংরক্ষিত হয়েছে। পরবর্তী হিসাবের জন্য প্রস্তুত।";
        
        editCustomer.value = "";
        editItem.value = "";
        editQuantity.value = "";
        editMatchedId.value = "";
        editTotalAmount.value = "-";
        editPaidAmount.value = "-";
        editDueAmount.value = "-";
    } catch (err) {
        showError(err.message);
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = `💾 হালখাতায় জমা করুন (Save to Ledger)`;
    }
}

// Fetch Daily Summary via /summary (uses Gemma 4 + gTTS)
async function fetchDailySummary() {
    getSummaryBtn.disabled = true;
    getSummaryBtn.innerHTML = `<span class="spinner"></span> এআই সারসংক্ষেপ তৈরি করছে...`;
    summaryTextDisplay.textContent = "সারসংক্ষেপ তৈরি হচ্ছে...";

    try {
        const res = await fetch(`${API_BASE}/summary`);
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "সারসংক্ষেপ তৈরি করা যায়নি");
        }

        summaryTextDisplay.textContent = data.summary_text;
        if (data.audio_url) {
            summaryAudioPlayer.src = `${API_BASE}${data.audio_url}`;
            summaryAudioPlayer.play().catch(() => {});
        }
    } catch (err) {
        summaryTextDisplay.textContent = "সারসংক্ষেপ তৈরি করতে ব্যর্থ হয়েছে।";
        showError(err.message);
    } finally {
        getSummaryBtn.disabled = false;
        getSummaryBtn.innerHTML = `🔊 দৈনিক হিসাবের সংক্ষিপ্ত বিবরণ শুনুন`;
    }
}

// Fetch ledger entries for table
async function fetchLedgerEntries() {
    try {
        const res = await fetch(`${API_BASE}/entries`);
        const data = await res.json();
        if (data.all_entries) {
            renderLedgerTable(data.all_entries);
        }
    } catch (e) {
        console.error("Failed to fetch ledger entries:", e);
    }
}

// Update the 4 Dashboard KPI Cards dynamically in Bangla numerals
function updateDashboardMetrics(entries) {
    if (!entries || entries.length === 0) {
        kpiTotalSales.textContent = "০ ৳";
        kpiTotalPaid.textContent = "০ ৳";
        kpiTotalDues.textContent = "০ ৳";
        kpiCustomerCount.textContent = "০ জন";
        return;
    }

    let totalSales = 0;
    let totalPaid = 0;
    let totalDues = 0;
    const uniqueCustomers = new Set();

    entries.forEach(e => {
        if (e.total_amount_taka) totalSales += Number(e.total_amount_taka);
        if (e.paid_amount_taka) totalPaid += Number(e.paid_amount_taka);
        if (e.due_amount_taka && e.due_amount_taka > 0) totalDues += Number(e.due_amount_taka);
        if (e.customer_name) uniqueCustomers.add(e.customer_name.trim());
    });

    kpiTotalSales.textContent = `${toBanglaNumerals(Math.round(totalSales))} ৳`;
    kpiTotalPaid.textContent = `${toBanglaNumerals(Math.round(totalPaid))} ৳`;
    kpiTotalDues.textContent = `${toBanglaNumerals(Math.round(totalDues))} ৳`;
    kpiCustomerCount.textContent = `${toBanglaNumerals(uniqueCustomers.size)} জন`;
}

// Render ledger table rows directly from response in Bangla numerals with Edit and Delete row actions
function renderLedgerTable(entries) {
    currentEntriesList = entries || [];
    updateDashboardMetrics(entries);

    if (!entries || entries.length === 0) {
        ledgerTableBody.innerHTML = `
            <tr>
                <td colspan="10" style="text-align: center; color: var(--text-muted);">এখনো কোন হিসাব জমা হয়নি।</td>
            </tr>`;
        return;
    }

    ledgerTableBody.innerHTML = entries.map(e => {
        let statusClass = "status-baki";
        if (e.status_bn === "পরিশোধিত") statusClass = "status-paid";
        else if (e.status_bn === "অগ্রিম") statusClass = "status-advance";

        return `
            <tr>
                <td>#${toBanglaNumerals(e.id)}</td>
                <td><strong>${escapeHtml(e.customer_name)}</strong></td>
                <td>${e.item ? escapeHtml(e.item) : '-'}</td>
                <td>${e.quantity ? escapeHtml(e.quantity) : '-'}</td>
                <td>${e.total_amount_taka !== null && e.total_amount_taka !== undefined ? toBanglaNumerals(e.total_amount_taka) + ' ৳' : '-'}</td>
                <td>${e.paid_amount_taka !== null && e.paid_amount_taka !== undefined ? toBanglaNumerals(e.paid_amount_taka) + ' ৳' : '-'}</td>
                <td>${e.due_amount_taka !== null && e.due_amount_taka !== undefined ? toBanglaNumerals(e.due_amount_taka) + ' ৳' : '-'}</td>
                <td><span class="status-pill ${statusClass}">${escapeHtml(e.status_bn || 'বাকি')}</span></td>
                <td style="font-size: 12px; color: var(--text-muted);">${formatBanglaDate(e.updated_at)}</td>
                <td style="text-align: center;">
                    <div style="display: flex; gap: 6px; justify-content: center;">
                        <button class="btn btn-secondary btn-sm" onclick="openEditModalById(${e.id})" title="পরিবর্তন করুন">✏️</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteLedgerRow(${e.id})" title="মুছে ফেলুন">🗑️</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// Open Edit Modal for a specific row ID
window.openEditModalById = function(id) {
    const entry = currentEntriesList.find(e => e.id === id);
    if (!entry) return;

    modalEntryId.value = entry.id;
    modalCustomer.value = entry.customer_name || "";
    modalItem.value = entry.item || "";
    modalQuantity.value = entry.quantity || "";
    modalTotal.value = entry.total_amount_taka !== null && entry.total_amount_taka !== undefined ? entry.total_amount_taka : "";
    modalPaid.value = entry.paid_amount_taka !== null && entry.paid_amount_taka !== undefined ? entry.paid_amount_taka : "";
    modalDue.value = entry.due_amount_taka !== null && entry.due_amount_taka !== undefined ? entry.due_amount_taka : "";

    editModalOverlay.style.display = "flex";
};

function closeModal() {
    editModalOverlay.style.display = "none";
}

// Save row edits via PUT /entries/{id}
async function saveModalEdit() {
    const id = parseInt(modalEntryId.value);
    if (!id) return;

    const payload = {
        customer_name: modalCustomer.value.trim(),
        item: modalItem.value.trim() || null,
        quantity: modalQuantity.value.trim() || null,
        total_amount_taka: modalTotal.value !== "" ? parseFloat(modalTotal.value) : null,
        paid_amount_taka: modalPaid.value !== "" ? parseFloat(modalPaid.value) : null,
        due_amount_taka: modalDue.value !== "" ? parseFloat(modalDue.value) : null
    };

    if (!payload.customer_name) {
        showError("গ্রাহকের নাম আবশ্যক।");
        return;
    }

    modalSaveBtn.disabled = true;
    modalSaveBtn.innerHTML = `<span class="spinner"></span> আপডেট হচ্ছে...`;

    try {
        const res = await fetch(`${API_BASE}/entries/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "আপডেট ব্যর্থ হয়েছে");
        }

        closeModal();
        renderLedgerTable(data.all_entries);
        showSuccessNotification("এন্ট্রি সফলভাবে আপডেট করা হয়েছে!");
    } catch (err) {
        showError(err.message);
    } finally {
        modalSaveBtn.disabled = false;
        modalSaveBtn.innerHTML = `সংরক্ষণ করুন`;
    }
}

// Delete row via DELETE /entries/{id}
window.deleteLedgerRow = async function(id) {
    if (!confirm(`আপনি কি নিশ্চিত যে #${toBanglaNumerals(id)} নম্বর এন্ট্রিটি মুছে ফেলতে চান?`)) {
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/entries/${id}`, {
            method: "DELETE"
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "মুছে ফেলা সম্ভব হয়নি");
        }

        renderLedgerTable(data.all_entries);
        showSuccessNotification("এন্ট্রি সফলভাবে মুছে ফেলা হয়েছে!");
    } catch (err) {
        showError(err.message);
    }
};

function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
