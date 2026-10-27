# Powerwall history download

Downloads everything Tesla's cloud keeps about your Powerwall, for every day since installation, into CSV files you can open in Excel, R or Python.

> **Code written by Claude Opus 5.5** (Anthropic's AI model) using Claude Code.
> Not affiliated with or endorsed by Tesla. Use at your own risk; see [License](#license).

## Getting it

1. Install **Python 3.9 or newer** from [python.org](https://www.python.org/downloads/) (on Windows, tick *Add python.exe to PATH* during setup).
2. On this page, click the green **Code** button, then **Download ZIP**, and unzip it anywhere.

The `.bat` launcher is for Windows. On macOS or Linux, run it from a terminal instead (untested there):

```
python3 -m pip install -r requirements.txt
python3 powerwall_history.py
```

## Running it (Windows)

1. **Double-click `Download Powerwall history.bat`.**
   The first run spends a minute or two setting up the Python packages it needs. Later runs only check for updates.

2. **Sign in to Tesla in the window that opens.**
   A small window titled *Tesla Login — pypowerwall* shows Tesla's own sign-in page (auth.tesla.com).
   - Enter your Tesla account email and password, then your verification code if you use two-step verification. Tesla may also show a puzzle or "I'm not a robot" check.
   - Finish within **about 3 minutes**. The window closes by itself when sign-in worked.
   - Your password goes only to Tesla. The script receives a temporary access key (valid about 8 hours), keeps it in memory, and never saves it to disk.

3. **Let it download.**
   It makes about three requests per day of history, with a short pause between each, so expect **roughly 45 minutes per year of history**. Each line shows the day it just saved and the estimated minutes left. Keep the computer awake until it says **Done**.

## Stopping, continuing and updating

- You can stop at any time with **Ctrl+C** or by closing the window. Everything downloaded so far is kept.
- Run it again to continue where it stopped. You will need to sign in again.
- Run it again later (for example monthly) to add the days since the last run. It always downloads up to **yesterday**, so today's partial day isn't saved.
- To start over from scratch, delete the site's folder inside `Powerwall data`.

## What you get

Everything goes into `Powerwall data\<your site name>\`:

| File | Contents |
|---|---|
| `power_5min.csv` | Power in **watts** for each 5-minute interval (see the columns below). |
| `battery_level_15min.csv` | `soe`: battery charge in %, as shown in the Tesla app, every 15 minutes. |
| `energy.csv` | Energy in **Wh** for each 5-minute interval, split by where it came from and went to, e.g. `consumer_energy_imported_from_battery` (battery → home) or `grid_energy_exported_from_solar` (solar → grid). Add up a day's rows for daily totals. |
| `outages.csv` | Grid outages: start, end and duration. |
| `site_info.json` | System details: battery count, capacity, firmware, settings, time zone, installation date. It also contains your address and location, so leave it out if you share the data. |
| `progress.json` | Which days are done. Leave it alone; the script uses it to continue. |

**Columns in `power_5min.csv`:**

| Column | Meaning |
|---|---|
| `solar_power` | Solar production |
| `battery_power` | Positive = Powerwall discharging, negative = charging |
| `grid_power` | Positive = importing from the grid, negative = exporting |
| `home_power` | Home usage. Tesla doesn't send this; the script calculates it as solar + battery + grid + generator. |
| `generator_power`, `grid_services_power` | Usually 0; grid services is battery power used for virtual power plant events |

**Timestamps** are local time at your site with the UTC offset, e.g. `2024-01-07T13:05:00+11:00`. A normal day has 288 five-minute rows. Days when daylight saving starts or ends have 276 or 300.

If Tesla starts sending a new field, it is added as a new column automatically. Older rows leave it blank.

## Options

Open a terminal in this folder to pass options, for example:

```
"Download Powerwall history.bat" --start 2025-01-01 --end 2025-01-31
```

| Option | Meaning |
|---|---|
| `--start YYYY-MM-DD` | First day (default: installation date) |
| `--end YYYY-MM-DD` | Last day (default: yesterday) |
| `--out FOLDER` | Where to save (default: `Powerwall data` next to the script) |
| `--site ID` | Only one site, if your account has several |
| `--delay SECONDS` | Pause between requests (default 1). Raise it if Tesla keeps asking to slow down. |

## If something goes wrong

- **"Sign-in did not complete"**: the window was closed or took longer than 3 minutes. Run it again.
- **"Tesla asked us to slow down"**: nothing to do. The script waits and retries by itself.
- **"Tesla refused the request (HTTP 401 or 403)"**:
  - Midway through a long run: your sign-in expired. Run it again to continue.
  - Straight after signing in: Tesla has probably changed its system again. The `.bat` file installs the latest pypowerwall each run, and that's where fixes arrive, so try again in a few days. Check [pypowerwall's issues](https://github.com/jasonacox/pypowerwall/issues) for news.
- **"Could not run Python"**: install Python from [python.org](https://www.python.org/downloads/), ticking *Add python.exe to PATH*.

## How it works, and its limits

- The script uses Tesla's unofficial "Owner API", the same service older Tesla tools relied on. Login is handled by the [pypowerwall](https://github.com/jasonacox/pypowerwall) library.
- In 2026 Tesla began restricting this API. pypowerwall's maintainers have kept it working, but Tesla could block it at any time. If that happens, the official alternatives are the Tesla Fleet API (needs a developer account) or the Netzero app's bulk download.
- The 5-minute and 15-minute intervals are the finest detail Tesla stores. Finer data (every few seconds) can only be recorded live from the Powerwall itself, from now on.
- The Python packages are installed in `%LOCALAPPDATA%\powerwall-history\venv`. You can delete that folder at any time; it is recreated on the next run.

## Credits

- Sign-in and Tesla API access come from [pypowerwall](https://github.com/jasonacox/pypowerwall) by Jason Cox and contributors.
- Code written by Claude Opus 5.5 (Anthropic) using Claude Code.

## License

MIT License; see [LICENSE](LICENSE). Provided as-is, without warranty. Tesla and Powerwall are trademarks of Tesla, Inc.
