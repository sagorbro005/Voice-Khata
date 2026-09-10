# Free Deployment Guide: Render (Backend) + Vercel (Frontend)

This guide walks you through deploying **Voice Khata** for **100% free** using:
- **Render** for the Python/FastAPI backend
- **Vercel** for the web frontend
- **cron-job.org / UptimeRobot** to keep Render awake 24/7 without sleeping

---

## 📌 Important: Branch Protection
All deployment files and configurations are placed on the **`deploy`** branch.
Your `main` branch remains untouched.

---

## Step 1: Push the `deploy` Branch to GitHub

In your local terminal, run:

```bash
git push -u origin deploy
```

---

## Step 2: Deploy the Backend to Render (Free)

1. Go to [dashboard.render.com](https://dashboard.render.com) and sign in (using GitHub).
2. Click **New +** → **Web Service**.
3. Connect your **Voice-Khata** GitHub repository.
4. Configure the Web Service:
   - **Name**: `voice-khata-backend` (or your choice)
   - **Region**: Oregon or Frankfurt
   - **Branch**: Select **`deploy`** *(Important!)*
   - **Root Directory**: Leave blank (or `.`)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Plan Type**: **Free** ($0/month)
5. Under **Environment Variables**, add:
   - `PYTHON_VERSION`: `3.10.12`
   - `OPENROUTER_API_KEY`: `your_openrouter_api_key`
   - `GROQ_API_KEY`: *(Highly Recommended)* Free key from [console.groq.com/keys](https://console.groq.com/keys). Groq Whisper runs speech-to-text in 200ms using 0 MB server RAM, preventing any Render memory limit issues.
6. Click **Create Web Service**.
7. Wait 2–3 minutes for deployment. Once complete, copy your service URL:
   `https://your-backend-name.onrender.com`

> **Verification**: Visit `https://your-backend-name.onrender.com/health` in your browser. You should see `{"status":"ok", ...}`.

---

## Step 3: Keep Render Awake 24/7 for Free

Render free web services spin down after 15 minutes of inactivity. Since Render gives 750 free hours per month (enough for 1 service 24/7), you can prevent it from sleeping using a free pinger:

1. Go to [cron-job.org](https://cron-job.org) (100% free forever) or [uptimerobot.com](https://uptimerobot.com).
2. Create a new cron job / monitor:
   - **URL**: `https://your-backend-name.onrender.com/health`
   - **Interval / Schedule**: Every **10 minutes**
3. Save it. Now Render will receive a ping every 10 minutes and **never spin down**!

---

## Step 4: Deploy the Frontend to Vercel (Free)

1. Go to [vercel.com](https://vercel.com) and sign in with GitHub.
2. Click **Add New...** → **Project**.
3. Import your **Voice-Khata** repository.
4. In the Project Configuration:
   - **Framework Preset**: `Other`
   - **Root Directory**: `./` (Vercel automatically detects `vercel.json` and publishes `frontend/`)
   - **Branch to Deploy**: Select **`deploy`**
5. Click **Deploy**.
6. In ~30 seconds, Vercel will give you a live URL, like:
   `https://voice-khata.vercel.app`

---

## Step 5: Connect Frontend to Your Render Backend

You have two easy ways to connect them:

### Method A: Direct from the Browser (Instant, No Redeploy Needed)
1. Open your live Vercel website in your browser.
2. Notice the small **API: Render** badge at the bottom-right corner.
3. Click the badge. A prompt will appear.
4. Paste your Render backend URL (e.g. `https://your-backend-name.onrender.com`) and hit Enter.
5. The badge will turn **green** (Connected!). The setting is saved in your browser.

### Method B: Set as Permanent Default in Code
1. Open [`frontend/config.js`](file:///c:/Users/user1/Downloads/Voice%20Ledger%202/frontend/config.js).
2. Replace:
   ```javascript
   const DEFAULT_RENDER_BACKEND_URL = "https://voice-khata-backend.onrender.com";
   ```
   with your actual Render URL:
   ```javascript
   const DEFAULT_RENDER_BACKEND_URL = "https://your-backend-name.onrender.com";
   ```
3. Commit and push on the `deploy` branch:
   ```bash
   git commit -am "Set production Render backend URL"
   git push origin deploy
   ```
   Vercel will automatically redeploy with the updated URL.
