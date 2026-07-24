const API_BASE = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") && window.location.port === "8001" ? "http://127.0.0.1:8001" : "http://127.0.0.1:8000";

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let currentTranscript = "";
let currentExtraction = null;
let currentActiveRange = "30days";

// DOM Elements
const recordBtn = document.getElementById("recordBtn");
const recordStatus = document.getElementById("recordStatus");
const audioFileInput = document.getElementById("audioFileInput");
const transcriptDisplay = document.getElementById("transcriptDisplay");
const extractSalesBtn = document.getElementById("extractSalesBtn");
const confirmSaleBtn = document.getElementById("confirmSaleBtn");

const editCustomerName = document.getElementById("editCustomerName");
const itemsListBody = document.getElementById("itemsListBody");
const addItemRowBtn = document.getElementById("addItemRowBtn");
const editTotalAmount = document.getElementById("editTotalAmount");

const runningTotalDisplay = document.getElementById("todayTotalDisplay") || document.getElementById("runningTotalDisplay");
const historySummaryBanner = document.getElementById("historySummaryBanner");
const salesListContainer = document.getElementById("salesListContainer");
const errorBanner = document.getElementById("errorBanner");
const filterButtons = document.querySelectorAll(".filter-btn");

const banglaMonths = [
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"
];

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

// Format date into Bangla Header format, e.g. "২৩ জুলাই, ২০২৬"
function formatBanglaHeaderDate(dateStr) {
    if (!dateStr) return "-";
    try {
        const datePart = dateStr.split("T")[0];
        const parts = datePart.split("-");
        if (parts.length === 3) {
            const year = parts[0];
            const monthIdx = parseInt(parts[1], 10) - 1;
            const day = parseInt(parts[2], 10);
            const monthName = banglaMonths[monthIdx] || "";
            return `${toBanglaNumerals(day)} ${monthName}, ${toBanglaNumerals(year)}`;
        }
        return toBanglaNumerals(dateStr);
    } catch (e) {
        return toBanglaNumerals(dateStr);
    }
}

// Format timestamp into Bangla time (e.g. "০২:৩০ PM")
function formatBanglaTime(dateStr) {
    if (!dateStr) return "-";
    try {
        const d = new Date(dateStr);
        return d.toLocaleTimeString("bn-BD", {
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return toBanglaNumerals(dateStr);
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
    fetchTodayTotal();
    fetchSalesHistory(currentActiveRange);

    recordBtn.addEventListener("click", toggleRecording);
    if (audioFileInput) audioFileInput.addEventListener("change", handleFileUpload);
    extractSalesBtn.addEventListener("click", runSalesExtraction);
    confirmSaleBtn.addEventListener("click", saveConfirmedSale);
    addItemRowBtn.addEventListener("click", () => addEmptyItemRow());

    editTotalAmount.addEventListener("input", () => {
        if (parseBanglaOrEnglishNumber(editTotalAmount.value) !== null) {
            confirmSaleBtn.disabled = false;
        }
    });

    // Quick range filter button listeners
    filterButtons.forEach(btn => {
        btn.addEventListener("click", (e) => {
            filterButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentActiveRange = btn.dataset.range;
            fetchSalesHistory(currentActiveRange);
        });
    });

    // Ask about sales Q&A listeners (Dual Input: Text + Voice)
    const askSalesBtn = document.getElementById("askSalesBtn");
    const askSalesRecordBtn = document.getElementById("askSalesRecordBtn");
    const salesQuestionInput = document.getElementById("salesQuestionInput");

    if (salesQuestionInput && askSalesBtn) {
        salesQuestionInput.addEventListener("input", () => {
            askSalesBtn.disabled = salesQuestionInput.value.trim() === "";
        });
    }

    if (askSalesBtn) {
        askSalesBtn.addEventListener("click", () => {
            const qText = salesQuestionInput.value.trim();
            if (qText) submitSalesQuestion(qText);
        });
    }

    document.querySelectorAll("#salesAskCard .sample-q-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            salesQuestionInput.value = btn.textContent.trim();
            if (askSalesBtn) askSalesBtn.disabled = false;
            submitSalesQuestion(btn.textContent.trim());
        });
    });

    // Voice Record Path for Sales Q&A
    let salesQnaRecorder = null;
    let salesQnaChunks = [];
    let isSalesQnaRecording = false;

    if (askSalesRecordBtn) {
        askSalesRecordBtn.addEventListener("click", async () => {
            const recordLabel = document.getElementById("askSalesRecordLabel");
            const recordIcon = document.getElementById("askSalesRecordIcon");
            const salesQuestionDisplay = document.getElementById("salesQuestionDisplay");

            if (!isSalesQnaRecording) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    salesQnaRecorder = new MediaRecorder(stream);
                    salesQnaChunks = [];

                    salesQnaRecorder.ondataavailable = (e) => salesQnaChunks.push(e.data);
                    salesQnaRecorder.onstop = async () => {
                        const audioBlob = new Blob(salesQnaChunks, { type: 'audio/wav' });
                        const formData = new FormData();
                        formData.append("file", audioBlob, "sales_qna_question.wav");

                        if (salesQuestionDisplay) {
                            salesQuestionDisplay.textContent = "🎙️ ভয়েস রেকর্ড ট্রান্সক্রাইব করা হচ্ছে...";
                        }

                        try {
                            const res = await fetch(`${API_BASE}/transcribe`, { method: "POST", body: formData });
                            const data = await res.json();
                            if (data.transcript) {
                                salesQuestionInput.value = data.transcript;
                                if (askSalesBtn) askSalesBtn.disabled = false;
                                submitSalesQuestion(data.transcript);
                            }
                        } catch (err) {
                            showError("ভয়েস প্রসেস করতে ব্যর্থ হয়েছে: " + err.message);
                        }
                    };

                    salesQnaRecorder.start();
                    isSalesQnaRecording = true;
                    if (recordLabel) recordLabel.textContent = "রেকর্ডিং হচ্ছে...";
                    if (recordIcon) recordIcon.textContent = "🔴";
                    askSalesRecordBtn.classList.add("btn-danger");
                } catch (err) {
                    showError("মাইক্রোফোন সংযোগ ব্যর্থ: " + err.message);
                }
            } else {
                salesQnaRecorder.stop();
                isSalesQnaRecording = false;
                if (recordLabel) recordLabel.textContent = "বলুন";
                if (recordIcon) recordIcon.textContent = "🎤";
                askSalesRecordBtn.classList.remove("btn-danger");
            }
        });
    }
});

async function submitSalesQuestion(questionText) {
    const salesQuestionInput = document.getElementById("salesQuestionInput");
    const askSalesBtn = document.getElementById("askSalesBtn");
    const salesQuestionDisplay = document.getElementById("salesQuestionDisplay");
    const salesAnswerDisplay = document.getElementById("salesAnswerDisplay");
    const salesAudioPlayer = document.getElementById("salesAudioPlayer");

    if (!questionText) {
        showError("অনুগ্রহ করে প্রশ্ন নির্বাচন অথবা টাইপ করুন।");
        return;
    }

    if (salesQuestionDisplay) {
        salesQuestionDisplay.textContent = `❓ প্রশ্ন: "${questionText}"`;
    }
    salesAnswerDisplay.innerHTML = `<span class="spinner"></span> উত্তর প্রস্তুত করা হচ্ছে...`;
    if (askSalesBtn) askSalesBtn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/sales/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ transcript: questionText })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "উত্তর পেতে ব্যর্থ হয়েছে");
        }

        salesAnswerDisplay.textContent = data.answer_text;
        if (data.audio_url) {
            salesAudioPlayer.src = `${API_BASE}${data.audio_url}`;
            salesAudioPlayer.play().catch(e => console.log("Audio autoplay prevented:", e));
        }
    } catch (err) {
        salesAnswerDisplay.textContent = "উত্তর পেতে সমস্যা হয়েছে।";
        showError(err.message);
    } finally {
        if (askSalesBtn) askSalesBtn.disabled = salesQuestionInput.value.trim() === "";
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
                await uploadAndTranscribe(audioBlob, "recorded_sales_audio.wav");
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
    extractSalesBtn.disabled = true;

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
        extractSalesBtn.disabled = false;
        recordStatus.textContent = "নগদ বিক্রির তথ্য বলতে মাইক্রোফোনে চাপ দিন";
        recordStatus.style.color = "var(--text-muted)";
    } catch (err) {
        transcriptDisplay.textContent = "অডিও প্রসেস করতে ব্যর্থ হয়েছে।";
        showError(err.message);
    }
}

// Extract JSON daily sale using Gemma 4 via /daily-sales/extract
async function runSalesExtraction() {
    if (!currentTranscript) {
        showError("অনুগ্রহ করে প্রথমে কথা বলুন বা অডিও দিন।");
        return;
    }

    extractSalesBtn.disabled = true;
    extractSalesBtn.innerHTML = `<span class="spinner"></span> এআই দিয়ে বিক্রি বের করা হচ্ছে...`;

    try {
        const res = await fetch(`${API_BASE}/daily-sales/extract`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ transcript: currentTranscript })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "বিক্রি তথ্য বের করা সম্ভব হয়নি");
        }

        const entry = data.structured_entry;
        currentExtraction = entry;

        editCustomerName.value = entry.customer_name || "";
        editTotalAmount.value = entry.total_amount_taka !== null && entry.total_amount_taka !== undefined ? `${toBanglaNumerals(entry.total_amount_taka)} ৳` : "";

        renderStep2Items(entry.items || []);
        confirmSaleBtn.disabled = false;
    } catch (err) {
        showError(err.message);
    } finally {
        extractSalesBtn.disabled = false;
        extractSalesBtn.innerHTML = `✨ এআই দিয়ে বিক্রি বের করুন`;
    }
}

// Render item input rows for Step 2 preview
function renderStep2Items(items) {
    itemsListBody.innerHTML = "";
    if (!items || items.length === 0) {
        addEmptyItemRow();
        return;
    }

    items.forEach(itemObj => {
        addEmptyItemRow(itemObj.item || "", itemObj.quantity || "", itemObj.unit_price_taka);
    });
}

function addEmptyItemRow(name = "", qty = "", price = null) {
    if (itemsListBody.rows.length === 1 && itemsListBody.rows[0].cells.length === 1) {
        itemsListBody.innerHTML = "";
    }

    const tr = document.createElement("tr");
    const formattedPrice = price !== null && price !== undefined ? price : "";

    tr.innerHTML = `
        <td><input type="text" class="item-name-input" placeholder="পণ্যের নাম" value="${escapeHtml(name)}"></td>
        <td><input type="text" class="item-qty-input" placeholder="পরিমাণ" value="${escapeHtml(qty)}"></td>
        <td><input type="text" class="item-price-input" placeholder="দাম" value="${formattedPrice !== "" ? toBanglaNumerals(formattedPrice) : ""}"></td>
        <td style="text-align: center;">
            <button class="btn btn-danger btn-sm" onclick="this.closest('tr').remove();" title="মুছে ফেলুন">&times;</button>
        </td>
    `;
    itemsListBody.appendChild(tr);
}

// Confirm and save sale via /daily-sales/confirm
async function saveConfirmedSale() {
    const totalVal = parseBanglaOrEnglishNumber(editTotalAmount.value);
    if (totalVal === null || totalVal <= 0) {
        showError("অনুগ্রহ করে সঠিক সর্বমোট টাকা দিন।");
        return;
    }

    const rows = Array.from(itemsListBody.querySelectorAll("tr"));
    const items = [];

    rows.forEach(tr => {
        const nameInput = tr.querySelector(".item-name-input");
        const qtyInput = tr.querySelector(".item-qty-input");
        const priceInput = tr.querySelector(".item-price-input");

        if (nameInput && nameInput.value.trim()) {
            items.push({
                item: nameInput.value.trim(),
                quantity: qtyInput ? (qtyInput.value.trim() || null) : null,
                unit_price_taka: priceInput ? parseBanglaOrEnglishNumber(priceInput.value) : null
            });
        }
    });

    if (items.length === 0) {
        showError("কমপক্ষে একটি পণ্যের নাম আবশ্যক।");
        return;
    }

    const payload = {
        customer_name: editCustomerName.value.trim() || null,
        items: items,
        total_amount_taka: totalVal
    };

    confirmSaleBtn.disabled = true;
    confirmSaleBtn.innerHTML = `<span class="spinner"></span> সংরক্ষণ হচ্ছে...`;

    try {
        const res = await fetch(`${API_BASE}/daily-sales/confirm`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ entry: payload })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "বিক্রি জমা হতে ব্যর্থ হয়েছে");
        }

        // Update hero banner today's total
        if (data.today_total_taka !== undefined) {
            runningTotalDisplay.textContent = `${toBanglaNumerals(Math.round(data.today_total_taka))} ৳`;
        }

        // Refresh sales history for current active range
        fetchSalesHistory(currentActiveRange);
        showSuccessNotification("বিক্রি সফলভাবে জমা হয়েছে!");

        // Reset form
        currentTranscript = "";
        currentExtraction = null;
        transcriptDisplay.textContent = "বিক্রি নিশ্চিত ও সংরক্ষিত হয়েছে। পরবর্তী হিসাবের জন্য প্রস্তুত।";
        editCustomerName.value = "";
        editTotalAmount.value = "";
        itemsListBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 12px;">কোন পণ্য যুক্ত করা হয়নি।</td></tr>`;
        confirmSaleBtn.disabled = true;
    } catch (err) {
        showError(err.message);
    } finally {
        confirmSaleBtn.disabled = false;
        confirmSaleBtn.innerHTML = `💾 বিক্রয় জমা করুন (Confirm and Save)`;
    }
}

// Fetch Today's Running Total for Hero Banner
async function fetchTodayTotal() {
    try {
        const res = await fetch(`${API_BASE}/daily-sales/today`);
        const data = await res.json();
        const displayElem = document.getElementById("todayTotalDisplay") || document.getElementById("runningTotalDisplay");
        if (displayElem && data.today_total_taka !== undefined) {
            displayElem.textContent = `${toBanglaNumerals(Math.round(data.today_total_taka))} ৳`;
        }
    } catch (e) {
        console.error("Failed to fetch today's sales total:", e);
    }
}

// Fetch Sales History via /daily-sales/history?range=...
async function fetchSalesHistory(range = "30days") {
    salesListContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 16px;"><span class="spinner"></span> বিক্রয় ইতিহাস লোড করা হচ্ছে...</div>`;

    try {
        const res = await fetch(`${API_BASE}/daily-sales/history?range=${range}`);
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "বিক্রয় ইতিহাস লোড করা সম্ভব হয়নি");
        }
        renderSalesHistoryData(data);
    } catch (e) {
        console.error("Failed to fetch sales history:", e);
        salesListContainer.innerHTML = `<div style="text-align: center; color: #fca5a5; padding: 16px;">বিক্রয় ইতিহাস লোড করতে ব্যর্থ হয়েছে।</div>`;
    }
}

// Render sales history grouped by date with header subtotal and range summary
function renderSalesHistoryData(data) {
    const summary = data.summary || {};
    const totalTaka = summary.total_amount_taka || 0;
    const txCount = summary.transaction_count || 0;

    historySummaryBanner.textContent = `নির্বাচিত সময়ে মোট বিক্রয়: ${toBanglaNumerals(Math.round(totalTaka))} টাকা (${toBanglaNumerals(txCount)}টি লেনদেন)`;

    const txs = data.transactions || [];
    if (txs.length === 0) {
        salesListContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">এই সময়সীমার মধ্যে কোনো বিক্রি পাওয়া যায়নি।</div>`;
        return;
    }

    // Group transactions by date string YYYY-MM-DD
    const grouped = {};
    txs.forEach(tx => {
        const dateKey = tx.created_at ? tx.created_at.substring(0, 10) : "অজানা";
        if (!grouped[dateKey]) {
            grouped[dateKey] = {
                transactions: [],
                subtotal: 0
            };
        }
        grouped[dateKey].transactions.push(tx);
        grouped[dateKey].subtotal += (tx.total_amount_taka || 0);
    });

    let html = "";
    Object.keys(grouped).forEach(dateKey => {
        const group = grouped[dateKey];
        const formattedDate = formatBanglaHeaderDate(dateKey);
        const subtotalBn = toBanglaNumerals(Math.round(group.subtotal));

        html += `
            <div class="date-group-header">
                <div>📅 ${formattedDate}</div>
                <div>দিনের মোট: ${subtotalBn} ৳</div>
            </div>
        `;

        group.transactions.forEach(tx => {
            const custName = tx.customer_name ? escapeHtml(tx.customer_name) : "সাধারণ খরিদ্দার";
            const items = tx.items || [];
            const itemCountBn = toBanglaNumerals(items.length);
            
            const itemsHtml = items.map(item => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <td style="padding: 6px 10px;">${escapeHtml(item.item)}</td>
                    <td style="padding: 6px 10px;">${item.quantity ? escapeHtml(item.quantity) : '-'}</td>
                    <td style="padding: 6px 10px;">${item.unit_price_taka !== null && item.unit_price_taka !== undefined ? toBanglaNumerals(item.unit_price_taka) + ' ৳' : '-'}</td>
                </tr>
            `).join('');

            html += `
                <div class="tx-card">
                    <div class="tx-header" onclick="toggleTxDetails(${tx.id})">
                        <div class="tx-title">
                            <span>#${toBanglaNumerals(tx.id)}</span>
                            <span>👤 ${custName}</span>
                            <span class="sale-item-chip">${itemCountBn}টি পণ্য</span>
                            <span style="font-size: 12px; color: var(--text-muted); margin-left: 6px;">🕒 ${formatBanglaTime(tx.created_at)}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <span class="tx-amount">${toBanglaNumerals(tx.total_amount_taka)} ৳</span>
                            <span id="arrow-${tx.id}" style="font-size: 13px; color: var(--text-muted);">▼</span>
                        </div>
                    </div>
                    <div class="tx-details" id="tx-details-${tx.id}">
                        <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 4px;">
                            <thead>
                                <tr style="color: var(--text-muted); border-bottom: 1px solid rgba(255,255,255,0.08);">
                                    <th style="text-align: left; padding: 6px 10px;">পণ্য</th>
                                    <th style="text-align: left; padding: 6px 10px;">পরিমাণ</th>
                                    <th style="text-align: left; padding: 6px 10px;">একক দাম</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${itemsHtml}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        });
    });

    salesListContainer.innerHTML = html;
}

window.toggleTxDetails = function(txId) {
    const details = document.getElementById(`tx-details-${txId}`);
    const arrow = document.getElementById(`arrow-${txId}`);
    if (details) {
        details.classList.toggle("open");
        if (arrow) {
            arrow.textContent = details.classList.contains("open") ? "▲" : "▼";
        }
    }
};

function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
