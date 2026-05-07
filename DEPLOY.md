# Deploying to Streamlit Community Cloud

Target URL: **`https://equitysense.streamlit.app`**

This guide takes you from a local project to a public URL your friends
can open in any browser. No backend, no database, no payment.

---

## Privacy & isolation — how the cloud build behaves

The app has been refactored so it's safe to share publicly:

- **Portfolio data lives in `st.session_state`**, not on disk. Every
  visitor gets their own private session. Closing the tab clears it.
- **Each user imports their own JSON** via the sidebar. Nothing is
  shared between sessions.
- **Users export their portfolio** via the sidebar's "Download
  portfolio JSON" button to keep a local copy.
- The yfinance cache (`cache/*.joblib`) is shared across visitors —
  that's fine, it only contains public market data and makes the app
  faster.

---

## Prerequisites

1. A free **GitHub account** — sign up at [github.com](https://github.com).
2. **Git** installed locally — verify with `git --version`.
3. The project committed to a GitHub repository.

---

## Step 1 — Push the project to GitHub

From the project root (`c:\Muthu_PC\Programming\StockAnalyzer`):

```powershell
git init
git add .
git commit -m "Initial commit — EquitySense"
```

Create a new repository on GitHub (you can call it anything — e.g.
`equitysense` — the repo name does **not** have to match the URL
subdomain). Then connect and push:

```powershell
git remote add origin https://github.com/<your-username>/equitysense.git
git branch -M main
git push -u origin main
```

The included [.gitignore](.gitignore) keeps `cache/`, virtualenvs, and
local secrets out of the repo.

---

## Step 2 — Deploy on Streamlit Community Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign
   in with your GitHub account.
2. Click **"Create app"** → **"Deploy a public app from GitHub"**.
3. Fill the form:
   - **Repository:** `<your-username>/equitysense`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL (subdomain):** `equitysense`
     → final URL: `https://equitysense.streamlit.app`
   - **Python version:** auto-detected from `runtime.txt` (3.11)
4. Click **"Deploy"**. The first build takes ~2–5 minutes (Streamlit
   installs everything in `requirements.txt`).

When the build finishes, share the URL with your friends.

> If `equitysense` is already taken, Streamlit will tell you. Pick
> another short subdomain (e.g. `equitysense-app`, `eqsense`) — the
> rest of this guide is unaffected.

---

## Step 3 — Sharing with friends

Send them: **`https://equitysense.streamlit.app`**

What they do:

1. Open the link in any browser (mobile or desktop both work).
2. In the sidebar, open **Portfolio (holdings)**.
3. Either:
   - **Paste their own JSON** into the import box and click
     **Merge import**, or
   - **Type holdings** directly into the editor and click
     **Save portfolio**.
4. Set **Source = Portfolio** and click **RUN ANALYSIS**.

Their data only exists in their browser session. Closing the tab wipes
it. To keep it, they click **Download portfolio JSON** in the sidebar
and save the file locally — next visit they upload it again.

---

## Updating the deployed app

Streamlit Cloud auto-redeploys on every `git push` to `main`:

```powershell
git add .
git commit -m "Tweak scoring weights"
git push
```

The live URL updates within ~1 minute.

---

## Troubleshooting

**Build fails with `ModuleNotFoundError`.** Add the missing package to
[requirements.txt](requirements.txt) and push.

**App takes ~30s on first visit after a quiet day.** Free apps sleep
after ~7 days idle and cold-start on first request. Subsequent visits
are instant.

**"Out of memory" errors.** Free tier is 1 GB RAM — the curated ticker
universes plus a few user-imported holdings sit well under that. If
you ever exceed it, reduce the default region universe in
[data/ticker_loader.py](data/ticker_loader.py) or limit the number of
parallel fetches in [config/settings.py](config/settings.py)
(`FETCH_MAX_WORKERS`).

**A friend says their portfolio disappeared.** That's expected —
sessions don't persist on the server. They should download the JSON
each time and re-import next visit.
