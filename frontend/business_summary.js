const API_BASE = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") && window.location.port === "8001" ? "http://127.0.0.1:8001" : "http://127.0.0.1:8000";

function toBanglaNumber(num) {
    if (num === null || num === undefined) return "০";
    const str = typeof num === 'number' ? (Number.isInteger(num) ? num.toString() : num.toFixed(2)) : String(num);
    const banglaDigits = {
        '0': '০', '1': '১', '2': '২', '3': '৩', '4': '৪',
        '5': '৫', '6': '৬', '7': '৭', '8': '৮', '9': '৯', '.': '.'
    };
    return str.split('').map(char => banglaDigits[char] || char).join('');
}

// Light & Dark Theme Manager (Synchronized across all pages via localStorage "theme")
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

let selectedRange = "30days";

document.addEventListener("DOMContentLoaded", () => {
    initTheme();

    const filterBtns = document.querySelectorAll(".filter-btn");
    const generateBtn = document.getElementById("generateBtn");

    filterBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            filterBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            selectedRange = btn.dataset.range;
            clearRenderedSummary();
        });
    });

    if (generateBtn) {
        generateBtn.addEventListener("click", handleGenerateSummary);
    }
});

function clearRenderedSummary() {
    const summaryNarrativeDisplay = document.getElementById("summaryNarrativeDisplay");
    const activityLogsBody = document.getElementById("activityLogsBody");
    const summaryMeta = document.getElementById("summaryMeta");

    const periodMap = {
        "today": "আজ",
        "7days": "গত ৭ দিন",
        "30days": "গত ৩০ দিন",
        "90days": "গত ৯০ দিন",
        "all": "সব সময়"
    };

    if (summaryMeta) {
        summaryMeta.textContent = `সময়কাল: ${periodMap[selectedRange] || "-"} | তারিখ: -`;
    }

    if (summaryNarrativeDisplay) {
        summaryNarrativeDisplay.textContent = '"সারসংক্ষেপ তৈরি করুন" বোতামে চাপ দিয়ে নতুন সময়কালের জন্য প্রাতিষ্ঠানিক প্রতিবেদন তৈরি করুন।';
    }

    if (activityLogsBody) {
        activityLogsBody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 14px;">
                    সারসংক্ষেপ তৈরি করলে সকল লেনদেনের হিসেব প্রদর্শিত হবে।
                </td>
            </tr>
        `;
    }
}

async function handleGenerateSummary() {
    const generateBtn = document.getElementById("generateBtn");
    const summaryNarrativeDisplay = document.getElementById("summaryNarrativeDisplay");
    const summaryStatsBody = document.getElementById("summaryStatsBody");
    const activityLogsBody = document.getElementById("activityLogsBody");
    const summaryMeta = document.getElementById("summaryMeta");

    generateBtn.disabled = true;
    generateBtn.innerHTML = `<span class="spinner"></span> তৈরি করা হচ্ছে...`;

    try {
        const res = await fetch(`${API_BASE}/business-summary?range=${selectedRange}`);
        if (!res.ok) throw new Error("সারসংক্ষেপ তৈরি করতে ব্যর্থ হয়েছে");

        const data = await res.json();
        const ctx = data.context || {};
        const todayStr = new Date().toISOString().split('T')[0];
        const banglaTodayStr = todayStr.split('-').map(part => toBanglaNumber(part)).join('-');

        summaryNarrativeDisplay.textContent = data.summary_text || "কোন সংক্ষিপ্ত বিবরণ পাওয়া যায়নি।";

        const periodLabel = ctx.period_label || "নির্বাচিত সময়কাল";
        if (summaryMeta) {
            summaryMeta.textContent = `সময়কাল: ${periodLabel} | তৈরির তারিখ: ${banglaTodayStr}`;
        }

        // Update Stats Table
        const statsDict = {
            "সময়কাল (Period Covered)": periodLabel,
            "মোট নগদ বিক্রয় (Total Cash Sales)": `${toBanglaNumber(ctx.total_cash_sales_taka || 0)} ৳`,
            "মোট বাকিতে বিক্রয় (Total Credit Sales Issued)": `${toBanglaNumber(ctx.total_credit_sales_issued_taka || 0)} ৳`,
            "বর্তমানে মোট পাওনা (Current Total Receivable Due)": `${toBanglaNumber(ctx.current_total_due_taka || 0)} ৳`,
            "সেবা প্রাপ্ত গ্রাহক সংখ্যা (Unique Customers Served)": `${toBanglaNumber(ctx.unique_customers_served || 0)} জন`,
            "সক্রিয় ব্যবসায়িক দিন (Active Business Days)": `${toBanglaNumber(ctx.active_business_days || 0)} দিন`
        };

        summaryStatsBody.innerHTML = Object.entries(statsDict).map(([label, val]) => `
            <tr>
                <td>${label}</td>
                <td>${val}</td>
            </tr>
        `).join("");

        // Populate Activity Logs Table
        const logs = ctx.activity_logs || [];
        if (logs.length === 0) {
            activityLogsBody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 14px;">
                        এই সময়কালে কোন লেনদেন পাওয়া যায়নি।
                    </td>
                </tr>
            `;
        } else {
            activityLogsBody.innerHTML = logs.map(log => `
                <tr>
                    <td style="font-weight: 500;">${toBanglaNumber(log.date)}</td>
                    <td>
                        <span class="badge" style="padding: 2px 8px; border-radius: 6px; font-size: 12px; background: ${log.type === 'নগদ বিক্রয়' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(99, 102, 241, 0.15)'}; color: ${log.type === 'নগদ বিক্রয়' ? '#10b981' : '#6366f1'};">
                            ${log.type}
                        </span>
                    </td>
                    <td style="font-weight: 600;">${log.customer_name}</td>
                    <td style="font-weight: 700; color: var(--accent-teal);">${toBanglaNumber(log.total_amount_taka)} ৳</td>
                    <td style="font-size: 13px; color: var(--text-muted);">${log.details}</td>
                </tr>
            `).join("");
        }

    } catch (err) {
        summaryNarrativeDisplay.textContent = "সারসংক্ষেপ তৈরি করতে সমস্যা হয়েছে: " + err.message;
        console.error(err);
    } finally {
        generateBtn.disabled = false;
        generateBtn.innerHTML = `<span>✨ এআই দিয়ে ব্যবসার সারসংক্ষেপ তৈরি করুন</span>`;
    }
}
