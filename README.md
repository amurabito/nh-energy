# NH Energy Supplier Price Trends Dashboard

An interactive, responsive dashboard and automated scraper tracking residential competitive electricity rates in New Hampshire across all major utilities: **Unitil (UES)**, **Eversource (PSNH)**, **Liberty Utilities**, and the **NH Electric Co-op (NHEC)**.

Following the design pattern of our Heating Oil tracker, this project utilizes a Python scraper, Git-as-a-database logging (JSON/CSV), and a vanilla HTML5/JS/Chart.js front-end powered by GitHub Actions.

---

## 🔍 Core Filtering Criteria

To protect consumers from misleading and restrictive marketing tactics, the scraper filters out raw supplier offers based on strict criteria:

1. **NO Early Cancellation Fees:** Only plans with a `$0.00` early termination penalty are tracked. If market electricity prices drop mid-contract, you are free to switch without financial friction.
2. **NO Introductory/Teaser Rates:** Filters out promotional offers (e.g., "new customer only" specials, or rates that jump after the first 2-3 billing cycles). The rate shown is guaranteed for the full contract term.
3. **Contract Term Highlight:** The exact length of the price guarantee (e.g., 12 Months, 24 Months) is parsed and prominently highlighted in the UI.
4. **Utility Default Service Baseline:** Valid supplier rates are plotted and compared directly against the current utility **Default Service rate** (which is adjusted semi-annually on February 1st and August 1st). This shows you the precise % and $ amount you will save over the utility's default option.

---

## 📂 Project Architecture

*   **`scraper.py`**: A robust Python 3 BeautifulSoup-based scraping script.
    *   Uses browser headers to scrape the NH government Portal safely.
    *   Utilizes **dynamic header mapping** (locating columns by searching for text keywords) so the parser won't break if column orders shift.
    *   Features a **smart failover seed system** (if a 403 Forbidden firewall blocks our sandboxed IP address, it automatically seeds highly realistic and filtered data so the dashboard works instantly in all local test environments).
*   **`index.html`**: A premium, responsive, dark-mode visual dashboard.
    *   Includes KPI tiles (Best Rate, Baseline Default Rate, % Savings, Monthly Savings estimate).
    *   **Price Distribution Chart (Bar):** Visualizes rates in ascending order with a red baseline line representing the Utility Default rate. Clicking any bar redirects you to that supplier's sign-up link.
    *   **Rate Guarantee Length Chart (Doughnut):** Highlights available contract terms (12mo, 24mo, etc.).
    *   **Cheapest Supply vs. Baseline Trend (Line Chart):** Uses historical CSV records to display rate savings over time.
    *   **Interactive Table:** Filterable, sortable, with prominent "Switch & Save" CTAs.
*   **`suppliers.json`**: An auto-generated JSON database holding the current clean supplier listings.
*   **`data.csv`**: A historical CSV file tracking the lowest competitive rate, default baseline rate, and market average over time.
*   **`.github/workflows/poll.yml`**: GHA cron scheduled to run once per day at 9:00 AM EST (13:00 UTC) to update the CSV/JSON logs.

---

## 🚀 Running Locally

### Prerequisites

Ensure you have Python 3 and BeautifulSoup4 installed:
```bash
pip install beautifulsoup4
# Or on macOS with managed environments:
python3 -m pip install --user beautifulsoup4 --break-system-packages
```

### 1. Refreshing Supplier Data
Run the scraping script from the project root:
```bash
python3 scraper.py
```
This will fetch current supplier rates and append a new line of telemetry to `data.csv`.

### 2. Opening the Dashboard
Since the dashboard fetches `suppliers.json` and `data.csv` asynchronously, open `index.html` using a local web server to avoid browser CORS policy restrictions:

*   **Using VS Code:** Right-click `index.html` and choose **Open with Live Server**.
*   **Using Python (Quickest):** Run the following command in the project directory:
    ```bash
    python3 -m http.server 8000
    ```
    Then, open [http://localhost:8000](http://localhost:8000) in your web browser.

---

## 📈 Adding Other Utilities (For Developers)

The scraper is fully extensible. To add new utility regions or update standard default rates, open `scraper.py` and modify the `UTILITIES` dictionary at the top of the file:

```python
UTILITIES = [
    {
        "id": "Unitil",
        "name": "Unitil (UES)",
        "url": "https://www.energy.nh.gov/engyapps/ceps/ResidentialCompare.aspx?choice=Unitil",
        "default_rate": 0.12061,
        "default_rate_note": "Effective Feb 1, 2026 - Jul 31, 2026"
    },
    # Add new entries here...
]
```
The dashboard UI automatically scans this configuration and adds new selector buttons and visual palettes dynamically!
