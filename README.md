# Solar DCR Portal alerts

This project keeps a history of the public NISE Solar DCR Portal summary data, publishes a fast static dashboard on GitHub Pages every day at 09:00 JST, and sends a Gmail digest every Saturday at 09:00 JST through GitHub Actions.

It collects:

- Solar cells manufactured and sold by month from 2022 onward.
- Solar modules manufactured and sold by month from 2022 onward.
- Current DCR solar-cell and module stock held with manufacturers, including previous-snapshot changes and state/company leaders.
- All manufacturer categories from the summary page, including cells-only, panels-only, and both cells-and-panels manufacturers.
- Every manufacturer field returned by the portal. The dashboard shows the common fields in the table and exposes the complete raw record under **View profile**. The weekly email includes separate top-10 cell-stock and module-stock manufacturer rankings plus a complete CSV attachment.

## Setup

```bash
cd /Users/amirahmedimtiaz/dcr-portal-alerts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```text
EMAIL_SENDER=your-gmail-address@gmail.com
EMAIL_PASSWORD=your-gmail-app-password
EMAIL_RECEIVER=your-gmail-address@gmail.com
```

For Gmail, enable two-step verification and create an App Password. Do not put your normal Gmail password in `.env` or commit `.env`.

## First run

The first run automatically performs the 2022-to-current-year historical backfill and creates the baseline without sending an email:

```bash
python run.py
```

To test the scraper without Gmail configured:

```bash
python run.py --no-email
```

For local testing, the database is stored in `portal.db`. GitHub Actions uses `data/portal.db` so the historical state survives between scheduled runs.

## Local dashboard preview

In another terminal, with the virtual environment active:

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). This is only a local preview; the deployed dashboard is static and does not require Flask to be running.

In the manufacturer table, click **DCR cell stock (MW)** or **DCR module stock (MW)** to sort. Click again to reverse ascending/descending order. These portal fields represent stock with the manufacturer, not nameplate factory capacity. Search, category and state filters, pagination, filtered CSV export, and the full portal record are available in the dashboard. **Reload published data** re-requests the latest deployed snapshot with cache-busting; the portal scrape itself runs in GitHub Actions.

## GitHub Pages deployment and automatic schedule

The repository contains `.github/workflows/update-and-deploy.yml`. It refreshes and publishes data at `00:00 UTC` every day, which is `09:00 JST`, and also supports manual runs from the Actions tab. The Saturday run also sends the Gmail digest; manual runs send email only when the `send_email` input is enabled. Each run:

- scrapes the current year and refreshes the manufacturer register;
- sends the Saturday Gmail digest;
- commits the updated `data/portal.db` state; and
- publishes the static dashboard.

In the repository’s **Settings → Secrets and variables → Actions**, add these repository secrets:

```text
EMAIL_SENDER
EMAIL_PASSWORD
EMAIL_RECEIVER
```

Use the Gmail App Password for `EMAIL_PASSWORD`. Do not commit `.env` or copy its contents into the repository. Under **Settings → Pages**, choose **GitHub Actions** as the publishing source, then run **Update and deploy Solar DCR dashboard** manually from the Actions tab when an immediate refresh is needed.

The live dashboard is [https://amirahmedimtiaz.github.io/dcr-portal-alerts/](https://amirahmedimtiaz.github.io/dcr-portal-alerts/).

Bookmark that URL; it will work without the local Flask server. GitHub’s custom Pages workflow uses the Pages artifact and deployment actions included here. 

## Weekly comparison behavior

The portal returns all twelve months for a selected year, with future/unpublished months represented as zero. The runner uses the latest month with a non-zero value for each of the four series.

- If the latest month is unchanged, the email reports a like-for-like week-on-week MW change and growth rate.
- If a new month becomes the latest published month, the email labels the comparison as **Latest month changed** and shows the previous latest month for context.
- The email ranks the top 10 manufacturers separately by current solar-cell and solar-module stock held, using the portal's **Stock With Manufacturer (MW)** fields.
- The manufacturer list is compared by company ID. Added, removed, and changed records are reported, and the complete current register is attached as CSV.
