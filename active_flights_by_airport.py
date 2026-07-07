#!/usr/bin/env python3
"""
Create a sortable report of active flight numbers from one airport to airports
listed by AS Route Map.

Inputs, by default:
  - Guo Air _ Otto _ AirlineSim.html
  - AS Route Map _ Find Airports.html

Example:
  python active_flights_by_airport.py
  python active_flights_by_airport.py --airport DFW --output dfw_active_flights.html

The script uses only Python's standard library.
"""

import argparse
import html
import re
from collections import defaultdict
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path


DEFAULT_SCHEDULE_HTML = "Guo Air _ Otto _ AirlineSim.html"
DEFAULT_AIRPORTS_HTML = "AS Route Map _ Find Airports.html"
DEFAULT_OUTPUT_HTML = "active_flights_by_airport.html"
DEFAULT_AIRPORT = "JFK"


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def has_active_frequency(days_text):
    return bool(re.search(r"[1-7]", days_text or ""))


def numeric_sort_value(value):
    text = clean_text(str(value))
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return match.group(0) if match else ""


class AirportFinderParser(HTMLParser):
    """Parse the airport table from AS Route Map's Find Airports page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_airport_table = False
        self.table_depth = 0
        self.in_header = False
        self.current_row = None
        self.current_cell = None
        self.current_cell_tag = None
        self.headers = []
        self.airports = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if tag == "table":
            if self.in_airport_table:
                self.table_depth += 1
            elif attributes.get("id") == "airport":
                self.in_airport_table = True
                self.table_depth = 1
            return

        if not self.in_airport_table:
            return

        if tag == "thead":
            self.in_header = True
        elif tag == "tr":
            self.current_row = []
        elif tag in ("td", "th") and self.current_row is not None:
            self.current_cell = []
            self.current_cell_tag = tag

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if not self.in_airport_table:
            return

        if tag in ("td", "th") and self.current_cell is not None:
            self.current_row.append(clean_text("".join(self.current_cell)))
            self.current_cell = None
            self.current_cell_tag = None
        elif tag == "tr" and self.current_row is not None:
            self._finish_row()
            self.current_row = None
        elif tag == "thead":
            self.in_header = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_airport_table = False

    def _finish_row(self):
        if not self.current_row:
            return
        if self.in_header:
            self.headers = [cell.lower() for cell in self.current_row]
            return
        if len(self.current_row) < 7:
            return

        # Source columns include country, name, IATA, runway, timezone, pax, cargo, bearing, and distance.
        self.airports.append(
            {
                "country": self.current_row[0],
                "name": self.current_row[1],
                "iata": self.current_row[2].upper(),
                "runway": self.current_row[4],
                "pax": self.current_row[6],
            }
        )


class ScheduleParser(HTMLParser):
    """Parse AirlineSim's saved flight schedule page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current_origin = None
        self.current_destination = None
        self.current_row_classes = set()
        self.current_row_cells = None
        self.current_cell = None
        self.current_cell_classes = set()
        self.current_anchor_text = None
        self.row_links = []
        self.flights = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())

        if tag == "tr":
            self.current_row_classes = classes
            self.current_row_cells = []
            self.row_links = []
        elif tag in ("td", "th") and self.current_row_cells is not None:
            self.current_cell = []
            self.current_cell_classes = classes
            self.current_anchor_text = None
        elif tag == "a" and self.current_row_cells is not None:
            self.current_anchor_text = []

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)
        if self.current_anchor_text is not None:
            self.current_anchor_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_anchor_text is not None:
            link = clean_text("".join(self.current_anchor_text)).upper()
            if link:
                self.row_links.append(link)
            self.current_anchor_text = None
        elif tag in ("td", "th") and self.current_cell is not None:
            cell_text = clean_text("".join(self.current_cell))
            self.current_row_cells.append(
                {
                    "text": cell_text,
                    "classes": set(self.current_cell_classes),
                }
            )
            self.current_cell = None
            self.current_cell_classes = set()
            self.current_anchor_text = None
        elif tag == "tr" and self.current_row_cells is not None:
            self._finish_row()
            self.current_row_classes = set()
            self.current_row_cells = None
            self.row_links = []

    def _finish_row(self):
        classes = self.current_row_classes

        if "origin" in classes:
            code = self._last_airport_code(self.row_links)
            if code:
                self.current_origin = code
            self.current_destination = None
            return

        if "destination" in classes:
            code = self._last_airport_code(self.row_links)
            if code:
                self.current_destination = code
            return

        if "line" not in classes:
            return

        if not self.current_origin or not self.current_destination:
            return

        cells = self.current_row_cells
        if len(cells) < 2:
            return

        flight_number = cells[0]["text"].upper()
        days = cells[1]["text"]
        if not flight_number or not has_active_frequency(days):
            return

        self.flights.append(
            {
                "origin": self.current_origin,
                "destination": self.current_destination,
                "flight_number": flight_number,
                "days": days,
            }
        )

    @staticmethod
    def _last_airport_code(links):
        for link in reversed(links):
            if re.fullmatch(r"[A-Z0-9]{3}", link):
                return link
        return None


def parse_html(path, parser):
    with path.open("r", encoding="utf-8", errors="ignore") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            parser.feed(chunk)
    parser.close()
    return parser


def count_active_flight_numbers(schedule_rows, origin):
    origin = origin.upper()
    by_destination = defaultdict(set)

    for row in schedule_rows:
        if row["origin"] != origin:
            continue
        by_destination[row["destination"]].add(row["flight_number"])

    return {destination: len(numbers) for destination, numbers in by_destination.items()}


def build_report_rows(airports, counts):
    rows = []
    for airport in airports:
        code = airport["iata"].upper()
        rows.append(
            {
                "active_flight_numbers": counts.get(code, 0),
                "country": airport["country"],
                "name": airport["name"],
                "iata": code,
                "runway": airport["runway"],
                "pax": airport["pax"],
            }
        )
    return sorted(rows, key=lambda row: (-row["active_flight_numbers"], row["country"], row["iata"]))


def render_html(rows, origin, schedule_path, airports_path):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    served = sum(1 for row in rows if row["active_flight_numbers"] > 0)
    total_active = sum(row["active_flight_numbers"] for row in rows)

    body = []
    for row in rows:
        active = row["active_flight_numbers"]
        code = html.escape(row["iata"])
        country = html.escape(row["country"])
        pax_sort = html.escape(numeric_sort_value(row["pax"]))
        runway_sort = html.escape(numeric_sort_value(row["runway"]))
        body.append(
            f'      <tr data-airport-code="{code}" data-country="{country}" data-pax="{pax_sort}" data-runway="{runway_sort}">'
            '<td class="select-cell" data-sort="0"><input type="checkbox" class="highlight-toggle" aria-label="Highlight row"></td>'
            f'<td class="num flight-count-col" data-sort="{active}">{active}</td>'
            f'<td class="country-col">{country}</td>'
            f'<td class="airport-name-col">{html.escape(row["name"])}</td>'
            f'<td class="airport-code-col">{code}</td>'
            f'<td class="num runway-col" data-sort="{runway_sort}">{html.escape(row["runway"])}</td>'
            f'<td class="num pax-col" data-sort="{pax_sort}">{html.escape(row["pax"])}</td>'
            "</tr>"
        )

    rows_html = "\n".join(body)
    country_options = "\n".join(
        f'        <option value="{html.escape(country)}">{html.escape(country)}</option>'
        for country in sorted({row["country"] for row in rows}, key=str.casefold)
    )
    pax_values = sorted(
        {numeric_sort_value(row["pax"]) for row in rows if numeric_sort_value(row["pax"])},
        key=float,
    )
    pax_options = "\n".join(
        f'        <option value="{html.escape(value)}">{html.escape(value)}</option>'
        for value in pax_values
    )
    title = f"Active Flight Numbers from {html.escape(origin)}"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #667085;
      --line: #d7dde5;
      --header: #edf2f7;
      --accent: #0f766e;
      --hover: #eef8f6;
      --highlight: #fff2a8;
      --highlight-hover: #ffec7a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Segoe UI, Arial, sans-serif;
      font-size: 14px;
    }}
    main {{
      max-width: 1180px;
      margin: 24px auto;
      padding: 0 16px 28px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 24px;
      font-weight: 650;
    }}
    .meta {{
      margin: 0 0 16px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 0 0 14px;
    }}
    .summary span {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 6px;
      padding: 7px 10px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin: 0 0 14px;
    }}
    .filter-group {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .filter-group label {{
      color: var(--muted);
      font-weight: 600;
    }}
    select, input[type="number"] {{
      min-height: 34px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      border-radius: 6px;
      padding: 6px 8px;
      font: inherit;
    }}
    input[type="number"] {{ width: 88px; }}
    select:focus, input[type="number"]:focus {{
      border-color: var(--accent);
      outline: 2px solid rgba(15, 118, 110, 0.14);
    }}
    button {{
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      border-radius: 6px;
      padding: 7px 10px;
      cursor: pointer;
      font: inherit;
    }}
    button:hover {{ border-color: var(--accent); }}
    .highlight-count {{ color: var(--muted); }}
    .table-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: auto;
    }}
    table {{
      width: 100%;
      min-width: 680px;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    th, td {{
      padding: 9px 11px;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
      text-align: left;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: var(--header);
      cursor: pointer;
      user-select: none;
      font-weight: 650;
    }}
    thead th::after {{
      content: "  <>";
      color: var(--muted);
      font-size: 11px;
    }}
    thead th.sort-asc::after {{
      content: "  ^";
      color: var(--accent);
    }}
    thead th.sort-desc::after {{
      content: "  v";
      color: var(--accent);
    }}
    tbody tr:hover td {{ background: var(--hover); }}
    tbody tr.highlighted td {{ background: var(--highlight); }}
    tbody tr.highlighted:hover td {{ background: var(--highlight-hover); }}
    .select-cell {{
      width: 66px;
      text-align: center;
    }}
    .flight-count-col {{ width: 96px; }}
    .country-col {{ width: 150px; }}
    .airport-code-col {{ width: 82px; }}
    .runway-col {{ width: 92px; }}
    .pax-col {{ width: 84px; }}
    .airport-name-col {{
      width: auto;
      white-space: normal;
    }}
    td.airport-name-col {{
      line-height: 1.25;
    }}
    .highlight-toggle {{
      width: 16px;
      height: 16px;
      cursor: pointer;
      vertical-align: middle;
    }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p class="meta">
      Generated {html.escape(generated_at)} from
      {html.escape(str(schedule_path))} and {html.escape(str(airports_path))}.
    </p>
    <div class="summary">
      <span>{len(rows)} available airports</span>
      <span>{served} airports with active flight numbers from {html.escape(origin)}</span>
      <span>{total_active} total active flight numbers matched</span>
    </div>
    <div class="actions">
      <div class="filter-group">
        <label for="country-filter">Country</label>
        <select id="country-filter">
          <option value="">All countries</option>
{country_options}
        </select>
      </div>
      <div class="filter-group">
        <label for="pax-filter">Pax</label>
        <select id="pax-filter">
          <option value="">All demand levels</option>
{pax_options}
        </select>
      </div>
      <div class="filter-group">
        <label for="runway-filter">Minimum runway</label>
        <input type="number" id="runway-filter" min="0" step="1" placeholder="Any">
      </div>
      <button type="button" id="clear-filters">Clear filters</button>
      <button type="button" id="clear-highlights">Clear highlights</button>
      <span class="highlight-count"><span id="visible-count">{len(rows)}</span> visible</span>
      <span class="highlight-count"><span id="highlight-count">0</span> highlighted</span>
    </div>
    <div class="table-wrap">
      <table id="report">
        <thead>
          <tr>
            <th data-type="number" class="select-cell">Highlight</th>
            <th data-type="number" class="flight-count-col">Flights</th>
            <th class="country-col">Country</th>
            <th class="airport-name-col">Airport name</th>
            <th class="airport-code-col">Code</th>
            <th data-type="number" class="num runway-col">Runway</th>
            <th data-type="number" class="num pax-col">Pax</th>
          </tr>
        </thead>
        <tbody>
{rows_html}
        </tbody>
      </table>
    </div>
  </main>
  <script>
    (function () {{
      const table = document.getElementById("report");
      const tbody = table.tBodies[0];
      const headers = Array.from(table.tHead.rows[0].cells);
      const storageKey = "active-flight-highlight:{html.escape(origin)}";
      const countEl = document.getElementById("highlight-count");
      const clearButton = document.getElementById("clear-highlights");
      const countryFilter = document.getElementById("country-filter");
      const paxFilter = document.getElementById("pax-filter");
      const runwayFilter = document.getElementById("runway-filter");
      const clearFiltersButton = document.getElementById("clear-filters");
      const visibleCountEl = document.getElementById("visible-count");
      let highlightedCodes = loadHighlights();
      let currentIndex = 1;
      let currentDirection = "desc";

      function loadHighlights() {{
        try {{
          return new Set(JSON.parse(localStorage.getItem(storageKey) || "[]"));
        }} catch (error) {{
          return new Set();
        }}
      }}

      function saveHighlights() {{
        try {{
          localStorage.setItem(storageKey, JSON.stringify(Array.from(highlightedCodes).sort()));
        }} catch (error) {{
          // Highlighting still works for the current page even if storage is unavailable.
        }}
      }}

      function updateHighlightCount() {{
        countEl.textContent = String(highlightedCodes.size);
      }}

      function setRowHighlighted(row, highlighted) {{
        const code = row.dataset.airportCode;
        const checkbox = row.querySelector(".highlight-toggle");
        row.classList.toggle("highlighted", highlighted);
        row.cells[0].dataset.sort = highlighted ? "1" : "0";
        checkbox.checked = highlighted;
        if (highlighted) {{
          highlightedCodes.add(code);
        }} else {{
          highlightedCodes.delete(code);
        }}
      }}

      function applyStoredHighlights() {{
        Array.from(tbody.rows).forEach(row => {{
          setRowHighlighted(row, highlightedCodes.has(row.dataset.airportCode));
        }});
        updateHighlightCount();
      }}

      function applyFilters() {{
        const selectedCountry = countryFilter.value;
        const selectedPax = paxFilter.value;
        const minimumRunway = runwayFilter.value === "" ? null : Number(runwayFilter.value);
        let visibleCount = 0;

        Array.from(tbody.rows).forEach(row => {{
          const matchesCountry = !selectedCountry || row.dataset.country === selectedCountry;
          const matchesPax = !selectedPax || row.dataset.pax === selectedPax;
          const runway = Number(row.dataset.runway || 0);
          const matchesRunway = minimumRunway === null || runway >= minimumRunway;
          const visible = matchesCountry && matchesPax && matchesRunway;
          row.hidden = !visible;
          if (visible) {{
            visibleCount += 1;
          }}
        }});
        visibleCountEl.textContent = String(visibleCount);
      }}

      function cellValue(row, index) {{
        const cell = row.cells[index];
        return cell.dataset.sort || cell.textContent.trim();
      }}

      function compareRows(index, direction, type) {{
        const multiplier = direction === "asc" ? 1 : -1;
        return function (left, right) {{
          let a = cellValue(left, index);
          let b = cellValue(right, index);
          if (type === "number") {{
            a = Number(a || 0);
            b = Number(b || 0);
            return (a - b) * multiplier;
          }}
          return a.localeCompare(b, undefined, {{ numeric: true, sensitivity: "base" }}) * multiplier;
        }};
      }}

      function sortBy(index, forceDirection) {{
        const header = headers[index];
        const type = header.dataset.type || "text";
        const direction = forceDirection || (currentIndex === index && currentDirection === "asc" ? "desc" : "asc");
        const rows = Array.from(tbody.rows);

        rows.sort(compareRows(index, direction, type));
        rows.forEach(row => tbody.appendChild(row));

        headers.forEach(th => th.classList.remove("sort-asc", "sort-desc"));
        header.classList.add(direction === "asc" ? "sort-asc" : "sort-desc");
        currentIndex = index;
        currentDirection = direction;
      }}

      headers.forEach((header, index) => {{
        header.addEventListener("click", () => sortBy(index));
      }});
      tbody.addEventListener("change", event => {{
        if (!event.target.classList.contains("highlight-toggle")) {{
          return;
        }}
        setRowHighlighted(event.target.closest("tr"), event.target.checked);
        saveHighlights();
        updateHighlightCount();
      }});
      clearButton.addEventListener("click", () => {{
        highlightedCodes.clear();
        applyStoredHighlights();
        saveHighlights();
      }});
      countryFilter.addEventListener("change", applyFilters);
      paxFilter.addEventListener("change", applyFilters);
      runwayFilter.addEventListener("input", applyFilters);
      clearFiltersButton.addEventListener("click", () => {{
        countryFilter.value = "";
        paxFilter.value = "";
        runwayFilter.value = "";
        applyFilters();
      }});
      applyStoredHighlights();
      applyFilters();
      sortBy(1, "desc");
    }}());
  </script>
</body>
</html>
"""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare an AirlineSim schedule to AS Route Map airports and write a sortable HTML report."
    )
    parser.add_argument(
        "-a",
        "--airport",
        default=DEFAULT_AIRPORT,
        help=f"Origin airport IATA code to count from. Default: {DEFAULT_AIRPORT}",
    )
    parser.add_argument(
        "-s",
        "--schedule",
        default=DEFAULT_SCHEDULE_HTML,
        help=f"Saved AirlineSim schedule HTML. Default: {DEFAULT_SCHEDULE_HTML}",
    )
    parser.add_argument(
        "-m",
        "--map",
        dest="airports",
        default=DEFAULT_AIRPORTS_HTML,
        help=f"Saved AS Route Map Find Airports HTML. Default: {DEFAULT_AIRPORTS_HTML}",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT_HTML,
        help=f"Output HTML report. Default: {DEFAULT_OUTPUT_HTML}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    origin = args.airport.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3}", origin):
        raise SystemExit("--airport must be a 3-character airport code, such as JFK")

    schedule_path = Path(args.schedule)
    airports_path = Path(args.airports)
    output_path = Path(args.output)

    if not schedule_path.exists():
        raise SystemExit(f"Schedule HTML not found: {schedule_path}")
    if not airports_path.exists():
        raise SystemExit(f"Airports HTML not found: {airports_path}")

    schedule = parse_html(schedule_path, ScheduleParser()).flights
    airports = parse_html(airports_path, AirportFinderParser()).airports

    if not schedule:
        raise SystemExit(f"No active schedule rows found in {schedule_path}")
    if not airports:
        raise SystemExit(f"No airports found in {airports_path}")

    counts = count_active_flight_numbers(schedule, origin)
    rows = build_report_rows(airports, counts)
    output_path.write_text(
        render_html(rows, origin, schedule_path, airports_path),
        encoding="utf-8",
    )

    matched = sum(1 for row in rows if row["active_flight_numbers"] > 0)
    print(f"Wrote {output_path}")
    print(f"Origin: {origin}")
    print(f"Available airports: {len(rows)}")
    print(f"Airports with active flight numbers from {origin}: {matched}")


if __name__ == "__main__":
    main()
