# ⛏️ Royalty Automation — Telangana Mines EPermit

Automates submitting royalty records from your Excel file to the Telangana Mines EPermit portal.

---

## 📁 Project Files

| File | Purpose |
|---|---|
| `app.py` | 🖥️ Main dashboard (Streamlit web UI) |
| `automation.py` | 🤖 Browser automation engine (Playwright) |
| `excel_processor.py` | 📊 Excel reader and validator |
| `config.py` | ⚙️ All settings, URLs, and form field selectors |
| `setup.bat` | 🔧 First-time setup (run once) |
| `run.bat` | 🚀 Launch the dashboard |
| `requirements.txt` | 📦 Python dependencies |

---

## 🚀 Getting Started

### Step 1 — Install Python
Download and install Python 3.10 or newer from:  
👉 **https://www.python.org/downloads/**

> ⚠️ During installation, CHECK the box: **"Add Python to PATH"**

### Step 2 — Run Setup (once)
Double-click `setup.bat`

This will:
- Install all required Python packages
- Download the Chromium browser for automation

### Step 3 — Launch Dashboard
Double-click `run.bat`

The dashboard opens at **http://localhost:8501** in your browser.

---

## 🖥️ How to Use the Dashboard

1. **Upload Excel** — Click "Browse files" and select your royalty Excel file
2. **Enter Credentials** — Type your EPermit username and password
3. **Preview Records** — Check the table to confirm all records loaded correctly
4. **Start Automation** — Click "🚀 Start Automation"
5. **Enter OTP** — When prompted, enter the OTP from your mobile and click "Submit OTP"
6. Watch the live log as records are submitted one by one
7. **Download Result** — After completion, download the Excel with Status column added

---

## ⚙️ Configuration (config.py)

After your first login, you may need to update the **form field selectors** in `config.py`:

```python
# Navigate to royalty form URL (update after first login)
ROYALTY_FORM_URL = None   # e.g. "https://mines.telangana.gov.in/EPermit/RoyaltyForm.aspx"

# Form field CSS selectors (update these to match actual form)
SEL_FORM_VEHICLE  = "#ddlVehicleNo"
SEL_FORM_DRIVER   = "#txtDriverName"
SEL_FORM_QUANTITY = "#txtQuantity"
# ... etc.
```

### Delay Between Submissions
```python
DELAY_BETWEEN_RECORDS = 3.0  # seconds (increase if website is slow)
```

---

## 🗂️ Excel Format

Your Excel should have these columns (two sets per row):

**Left block (A–F):**
`VEHICLE.NO | PASS.NO | DRIVER | LICENSE | PHONE | QUANTITY`

**Right block (H–N):**
`VEHICLE.NO2 | PASS.NO3 | DRIVER4 | LICENSES | PHONE6 | material | QUANTITY7`

---

## ❓ Troubleshooting

| Problem | Solution |
|---|---|
| Browser doesn't open | Make sure `setup.bat` was run successfully |
| "Login failed" | Check username/password; make sure OTP was entered correctly |
| Form fields not filled | Update selectors in `config.py` |
| Records skipped | Check the screenshot in the `screenshots/` folder for errors |
| Slow submission | Increase `DELAY_BETWEEN_RECORDS` in `config.py` |

---

## 📞 Support
Save a screenshot from the `screenshots/` folder and share it if you encounter any issues.
