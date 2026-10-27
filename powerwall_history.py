"""
Download your full Tesla Powerwall history from Tesla's cloud into CSV files.

For every day since installation, Tesla keeps:
  - power every 5 minutes (solar, battery, grid, home), in watts
  - battery charge level every 15 minutes, in %
  - energy totals, in Wh, including where the energy came from and went to
  - grid outage (backup) events

The script signs in through Tesla's own login window (using the pypowerwall
library, which keeps up with Tesla's login changes) and saves all of the above.
Your sign-in is kept in memory only and never written to disk.

It remembers which days are done, so you can stop it at any time (Ctrl+C) and
run it again later to continue, or to add the days since your last run.

Code written by Claude Opus 5.5 (Anthropic's AI model) using Claude Code.
Not affiliated with or endorsed by Tesla. Uses Tesla's unofficial Owner API
through the pypowerwall library; provided as-is under the MIT License.

Usage:
    python powerwall_history.py                      # everything since installation
    python powerwall_history.py --start 2024-01-01   # from a given day
    python powerwall_history.py --help               # all options
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import requests
    from dateutil import tz
    from dateutil.parser import isoparse
    from pypowerwall.cloud.teslapy import Product, Tesla
    from pypowerwall.tesla_auth import login
except ImportError as err:
    sys.exit(f"Missing Python package '{err.name}'. Run:  python -m pip install -r requirements.txt")

ACCOUNT = "tesla-account"  # key for the in-memory token store; any non-empty value works
AUTH_URLS = {"us": "https://auth.tesla.com/", "cn": "https://auth.tesla.cn/"}

# Preferred column order; any other fields Tesla sends are added after these.
POWER_COLUMNS = ["timestamp", "solar_power", "battery_power", "grid_power", "home_power",
                 "load_power", "generator_power", "grid_services_power"]
SOE_COLUMNS = ["timestamp", "soe"]
ENERGY_COLUMNS = ["timestamp"]
BACKUP_COLUMNS = ["start", "end", "duration_minutes", "duration_ms"]


class AuthError(Exception):
    """Tesla no longer accepts the sign-in token."""


def parse_args():
    default_out = Path(__file__).resolve().parent / "Powerwall data"
    p = argparse.ArgumentParser(description="Download your full Tesla Powerwall history to CSV files.")
    p.add_argument("--out", type=Path, default=default_out,
                   help=f'folder to save the data in (default: "{default_out}")')
    p.add_argument("--start", type=date.fromisoformat,
                   help="first day to download, YYYY-MM-DD (default: installation date)")
    p.add_argument("--end", type=date.fromisoformat,
                   help="last day to download, YYYY-MM-DD (default: yesterday)")
    p.add_argument("--site", type=int, help="only download this energy site ID (if your account has several)")
    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds to wait between requests to Tesla (default: 1)")
    p.add_argument("--region", choices=sorted(AUTH_URLS), default="us",
                   help='Tesla account region: "cn" for China only, "us" for everywhere else (default)')
    return p.parse_args()


def sign_in(region):
    """Open Tesla's login window and return a Tesla API session (token kept in memory)."""
    print("A Tesla sign-in window will open. Sign in there, including any verification code.")
    print("You have about 3 minutes to finish; the window closes by itself when it's done.\n")
    try:
        _, _, token_data = login(region=region)
    except Exception as err:
        sys.exit(f"\nSign-in did not complete ({err}). Nothing was downloaded; run the script again to retry.")
    if not token_data or not token_data.get("access_token"):
        sys.exit("\nSign-in did not return an access token. Run the script again to retry.")

    expires_in = token_data.get("expires_in", 28800)
    sso = {
        "token_type": token_data.get("token_type", "Bearer"),
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_in": expires_in,
        "expires_at": int(time.time()) + expires_in,
    }
    cache = {ACCOUNT: {"url": AUTH_URLS[region], "sso": sso}}
    return Tesla(ACCOUNT, cache_loader=lambda: cache, cache_dumper=lambda _: None)


def call(fn, what):
    """Run one Tesla request, waiting and retrying when Tesla is busy or briefly unavailable."""
    wait = 60
    for attempt in range(1, 7):
        try:
            return fn()
        except (requests.exceptions.RequestException, ValueError) as err:
            status = getattr(getattr(err, "response", None), "status_code", None)
            if status in (401, 403):
                raise AuthError(f"Tesla refused the request for {what} (HTTP {status}).") from err
            if attempt == 6 or (status is not None and status < 500 and status != 429):
                raise
            reason = "Tesla asked us to slow down" if status == 429 else f"request failed ({err})"
            print(f"    {reason}; waiting {wait} s and retrying ({attempt}/5)...")
            time.sleep(wait)
            wait = min(wait * 2, 900)


def safe_name(text):
    return re.sub(r'[<>:"/\\|?*]+', "_", text).strip(" .") or "site"


def site_timezone(info):
    name = info.get("installation_time_zone")
    zone = tz.gettz(name) if name else None
    if zone is None and isinstance(info.get("time_zone_offset"), int):
        zone = tz.tzoffset(None, info["time_zone_offset"] * 60)
    if zone is None:
        print("  WARNING: Tesla did not report the site's time zone; using this computer's.")
        zone = tz.tzlocal()
    return zone


class CsvTable:
    """Appends rows to a CSV file, adding columns if Tesla starts sending new fields."""

    def __init__(self, path, preferred_columns):
        self.path = path
        self.preferred = list(preferred_columns)
        self.columns = None
        if path.exists() and path.stat().st_size > 0:
            with path.open(newline="", encoding="utf-8") as f:
                self.columns = next(csv.reader(f), None)

    def append(self, rows):
        if not rows:
            return
        seen = list(dict.fromkeys(k for row in rows for k in row))
        if self.columns is None:
            self.columns = [c for c in self.preferred if c in seen] + [c for c in seen if c not in self.preferred]
            with self.path.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=self.columns).writeheader()
        new = [c for c in seen if c not in self.columns]
        if new:
            self._add_columns(new)
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.columns).writerows(rows)

    def _add_columns(self, new):
        with self.path.open(newline="", encoding="utf-8") as f:
            old_rows = list(csv.DictReader(f))
        self.columns += new
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.columns)
            writer.writeheader()
            writer.writerows(old_rows)
        tmp.replace(self.path)


def rows_for_day(response, day, zone):
    """time_series rows from a calendar_history response that fall on `day` (site local time)."""
    rows = []
    for row in (response or {}).get("time_series") or []:
        try:
            if isoparse(row["timestamp"]).astimezone(zone).date() != day:
                continue
        except (KeyError, TypeError, ValueError):
            pass  # keep rows with an unexpected timestamp rather than lose them
        rows.append(dict(row))
    return rows


def add_home_power(rows):
    """Tesla doesn't send home usage in the 5-minute data; it is solar + battery + grid (+ generator)."""
    for row in rows:
        try:
            row["home_power"] = (row["solar_power"] + row["battery_power"] + row["grid_power"]
                                 + (row.get("generator_power") or 0))
        except (KeyError, TypeError):
            pass


def fetch_day(site, day, zone, has_battery, delay):
    end_of_day = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=zone).isoformat()
    kinds = ["power", "soe", "energy"] if has_battery else ["power", "energy"]
    result = {}
    for kind in kinds:
        response = call(lambda: site.get_calendar_history_data(kind=kind, period="day", end_date=end_of_day),
                        f"{kind} data on {day}")
        result[kind] = rows_for_day(response, day, zone)
        time.sleep(delay)
    add_home_power(result["power"])
    return result


def fetch_backup_events(site, zone, first_day, delay):
    """Grid outage events since `first_day`. Tesla pages through them backwards in time."""
    events = {}
    end = datetime.now(zone).replace(hour=23, minute=59, second=59, microsecond=0)
    oldest = datetime(first_day.year, first_day.month, first_day.day, tzinfo=zone)
    while end > oldest:
        response = call(lambda: site.get_calendar_history_data(kind="backup", period="lifetime",
                                                               end_date=end.isoformat()),
                        "outage history")
        if not response:
            break
        for event in response.get("events") or []:
            events[event.get("timestamp")] = event
        next_end = response.get("next_end_date")
        if not next_end or isoparse(next_end) >= end:
            break
        end = isoparse(next_end)
        time.sleep(delay)

    rows = []
    for event in events.values():
        row = {"start": event.get("timestamp"), "duration_ms": event.get("duration")}
        try:
            row["end"] = (isoparse(row["start"]) + timedelta(milliseconds=row["duration_ms"])).isoformat()
            row["duration_minutes"] = round(row["duration_ms"] / 60000, 2)
        except (TypeError, ValueError):
            pass
        row.update({k: v for k, v in event.items() if k not in ("timestamp", "duration")})
        rows.append(row)
    rows.sort(key=lambda r: str(r["start"]))
    return rows


def download_site(product, tesla, args):
    site = Product(product, tesla)
    site_id = product["energy_site_id"]
    info = call(lambda: site.api("SITE_CONFIG")["response"], "site details")
    name = info.get("site_name") or product.get("site_name") or str(site_id)
    zone = site_timezone(info)
    has_battery = product.get("resource_type") == "battery"

    folder = args.out / safe_name(name)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "site_info.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")

    installed = None
    if info.get("installation_date"):
        try:
            installed = isoparse(info["installation_date"]).astimezone(zone).date()
        except (TypeError, ValueError):
            pass
    first = args.start or installed
    if first is None:
        sys.exit("Tesla did not report an installation date. Run again with --start YYYY-MM-DD.")
    last = args.end or (datetime.now(zone).date() - timedelta(days=1))

    progress_file = folder / "progress.json"
    done = set(json.loads(progress_file.read_text())["days_done"]) if progress_file.exists() else set()
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    todo = [d for d in days if d.isoformat() not in done]

    print(f"\nSite: {name} (ID {site_id})")
    print(f"  Installed: {installed or 'unknown'}   Time zone: {info.get('installation_time_zone', 'unknown')}")
    print(f"  Days {first} to {last}: {len(days) - len(todo)} already downloaded, {len(todo)} to go")
    print(f"  Saving to: {folder}")

    tables = {
        "power": CsvTable(folder / "power_5min.csv", POWER_COLUMNS),
        "soe": CsvTable(folder / "battery_level_15min.csv", SOE_COLUMNS),
        "energy": CsvTable(folder / "energy.csv", ENERGY_COLUMNS),
    }
    started = time.time()
    for n, day in enumerate(todo, 1):
        data = fetch_day(site, day, zone, has_battery, args.delay)
        for kind, rows in data.items():
            tables[kind].append(rows)
        done.add(day.isoformat())
        progress_file.write_text(json.dumps({"days_done": sorted(done)}, indent=0))

        eta = (time.time() - started) / n * (len(todo) - n) / 60
        counts = ", ".join(f"{kind} {len(rows)}" for kind, rows in data.items())
        print(f"  {day}  ({n}/{len(todo)}, about {eta:.0f} min left)  rows: {counts}")

    print("  Downloading outage history...")
    events = fetch_backup_events(site, zone, first, args.delay)
    path = folder / "outages.csv"
    path.unlink(missing_ok=True)  # rebuilt in full each run
    CsvTable(path, BACKUP_COLUMNS).append(events)
    print(f"  {len(events)} outage events saved.")


def main():
    args = parse_args()
    if args.start and args.end and args.start > args.end:
        sys.exit("--start is after --end.")

    try:
        tesla = sign_in(args.region)
        products = call(lambda: tesla.api("PRODUCT_LIST")["response"], "your list of Tesla products")
        sites = {}
        for p in products:
            if p.get("energy_site_id") and p.get("resource_type") in ("battery", "solar"):
                sites.setdefault(p["energy_site_id"], p)
        if args.site:
            sites = {k: v for k, v in sites.items() if k == args.site}
        if not sites:
            sys.exit("No Powerwall or solar site found on this Tesla account"
                     + (f" with ID {args.site}." if args.site else "."))

        for product in sites.values():
            download_site(product, tesla, args)
    except AuthError as err:
        sys.exit(f"\n{err}\nEverything downloaded so far is saved. Run the script again to sign in and "
                 "continue.\nIf this happens straight after signing in, Tesla may have changed its system "
                 "again; the .bat file installs the latest pypowerwall each run, so try again in a few days.")
    except KeyboardInterrupt:
        sys.exit("\nStopped. Everything downloaded so far is saved; run the script again to continue.")

    print(f"\nDone. Your data is in: {args.out}")


if __name__ == "__main__":
    main()
