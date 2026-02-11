# Deploy on Render

## 1. Connect the repo

1. Go to [render.com](https://render.com) and sign in (use **GitHub**).
2. Click **New +** → **Web Service**.
3. Connect your GitHub account if asked, then select the **lookup-tool** repo (or **rahulkalashetti-ai/lookup-tool**).
4. Render will detect **Python** and may read `render.yaml`. If it shows a form instead, use the settings below.

## 2. Settings (if the form is shown)

- **Name:** `lookup-tool` (or any name)
- **Region:** Choose the one closest to you
- **Branch:** `main`
- **Runtime:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python -m gunicorn -w 1 -b 0.0.0.0:$PORT app:app`

## 3. Deploy

- Click **Create Web Service**.
- Wait for the first build and deploy (a few minutes).
- When it’s live, Render will show a URL like `https://lookup-tool-xxxx.onrender.com`.

## 4. Use the app

- Open that URL. The app will create the DB and default users on first load.
- Log in with **infosec** / **infosec** or **user** / **user**.

## 5. Optional: secret key

- In the Render dashboard: your service → **Environment** → add **SECRET_KEY** with a long random value (or use “Generate” if available).  
- If you don’t set it, Render may auto-generate one when using the blueprint.

## After this

Every **push to `main`** will trigger a new deploy automatically.
