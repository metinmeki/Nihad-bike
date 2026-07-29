# NIHAD BIKE — Local POS

A fully offline point-of-sale app for the bike shop: inventory, purchases, sales, profit
tracking, and printable invoices in Arabic and Kurdish (Badini). Everything runs on the
shop's own computer — no internet, no server, no hosting required. All data is stored in
a local file (`nihadbike.db`) right next to the app.

## Requirements

- Python 3.9 or newer installed on the computer. Get it from https://python.org if it's
  not already installed (on Windows, check "Add Python to PATH" during install).

## Running it

**Windows:** double-click `run.bat`.

**Mac / Linux:** open a terminal in this folder and run:
```
chmod +x run.sh
./run.sh
```

Either way, it will:
1. Set up a local Python environment (first run only, takes a minute).
2. Start the app.
3. Open `http://127.0.0.1:5000` in the browser automatically.

To use it again later, just run the same script — it starts instantly after the first time.

To stop the app, close the terminal/command window it's running in.

## Manual start (if the script doesn't work)

```
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in any browser.

## Backing up your data

All the shop's data — items, purchases, sales — lives in one file: `nihadbike.db`,
in this same folder. Copy that file somewhere safe (a USB drive, cloud folder) every so
often to keep a backup. To restore, just put that file back in this folder before starting
the app.

## Printing invoices

From the Dashboard, click the printer icon next to any sale, or use "Print Invoice" right
after completing a sale in New Sale — it opens a print-ready page styled like a normal
paper invoice, in whichever language (Arabic / Kurdish) is currently selected.

## Notes

- Low stock warning shows automatically once an item's quantity drops to 5 or below
  (adjust `LOW_STOCK` in `app.py` if a different threshold is wanted).
- The app only listens on `127.0.0.1` (this computer only) — no one outside can reach it
  over the network.
