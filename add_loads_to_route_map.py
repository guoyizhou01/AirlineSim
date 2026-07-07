#!/usr/bin/env python3
"""
Merge AirlineSim station passenger-load data into an AS Route Map airport list.

Default inputs:
  - --airport DFW, which infers DFW _ Otto _ AirlineSim.html
  - AS Route Map _ Find Airports.html
  - Load monitoring _ Otto _ AirlineSim.html

Default output file:
  - AS Route Map _ Find Airports with Loads.html

The script uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_AIRPORT = "DFW"
DEFAULT_ROUTE_MAP_FILE = "AS Route Map _ Find Airports.html"
DEFAULT_LOAD_MONITORING_FILE = "Load monitoring _ Otto _ AirlineSim.html"
DEFAULT_OUTPUT_FILE = "AS Route Map _ Find Airports with Loads.html"
ROUTE_MAP_REMOVE_COLUMN_INDEXES = {3, 5, 7, 8}  # ICAO, TZ, Cargo, Bearing


@dataclass
class LoadRecord:
    iata: str
    destination: str
    weekly_loads: List[Optional[int]]

    @property
    def average_load(self) -> Optional[float]:
        values = [value for value in self.weekly_loads if value is not None]
        if not values:
            return None
        return sum(values) / len(values)


@dataclass
class EconomyRouteLoad:
    booked: int = 0
    capacity: int = 0

    @property
    def load_percent(self) -> Optional[float]:
        if self.capacity <= 0:
            return None
        return self.booked * 100 / self.capacity


class RouteSegmentsParser(HTMLParser):
    """Extract rows from the AirlineSim routeSegments table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_route_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.current_cell: List[str] = []
        self.current_row: List[str] = []
        self.rows: List[List[str]] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()

        if tag == "table":
            classes = attrs_dict.get("class", "")
            if "routesegments" in classes.lower():
                self.in_route_table = True
                self.table_depth = 1
            elif self.in_route_table:
                self.table_depth += 1
            return

        if not self.in_route_table:
            return

        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.current_cell = []
        elif tag == "img" and self.in_cell:
            # Country cells are often just an image with a title.
            title = attrs_dict.get("title")
            if title:
                self.current_cell.append(title)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.in_route_table:
            return

        if tag in {"td", "th"} and self.in_cell:
            self.current_row.append(clean_text("".join(self.current_cell)))
            self.current_cell = []
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []
            self.in_row = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_route_table = False

    def handle_data(self, data: str) -> None:
        if self.in_route_table and self.in_cell:
            self.current_cell.append(data)


class FlightInstancesParser(HTMLParser):
    """Extract rows from the AirlineSim Load Monitoring flightInstances table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_flight_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.current_cell: List[str] = []
        self.current_row: List[str] = []
        self.rows: List[List[str]] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()

        if tag == "table":
            classes = attrs_dict.get("class", "")
            if "flightinstances" in classes.lower():
                self.in_flight_table = True
                self.table_depth = 1
            elif self.in_flight_table:
                self.table_depth += 1
            return

        if not self.in_flight_table:
            return

        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.in_flight_table:
            return

        if tag in {"td", "th"} and self.in_cell:
            self.current_row.append(clean_text("".join(self.current_cell)))
            self.current_cell = []
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []
            self.in_row = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_flight_table = False

    def handle_data(self, data: str) -> None:
        if self.in_flight_table and self.in_cell:
            self.current_cell.append(data)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_airport_code(value: str) -> str:
    airport = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3}", airport):
        raise argparse.ArgumentTypeError("airport must be a 3-character IATA code, for example DFW or jfk")
    return airport


def station_file_for_airport(airport: str) -> str:
    return f"{airport} _ Otto _ AirlineSim.html"


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def parse_percent(cell_text: str) -> Optional[int]:
    match = re.search(r"(-?\d+)\s*%", cell_text)
    if not match:
        return None
    return int(match.group(1))


def parse_booked_capacity(cell_text: str) -> Optional[tuple[int, int]]:
    match = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", cell_text)
    if not match:
        return None
    booked = int(match.group(1).replace(",", ""))
    capacity = int(match.group(2).replace(",", ""))
    if capacity <= 0:
        return None
    return booked, capacity


def extract_week_labels(station_html: str) -> List[str]:
    labels = re.findall(
        r"<a\b(?=[^>]*sort~pax~load~\d+)[^>]*>\s*<span>([^<]+)</span>",
        station_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    labels = [clean_text(label) for label in labels]
    if len(labels) >= 3:
        return labels[:3]
    return ["Week 1", "Week 2", "Week 3"]


def extract_load_records(station_html: str) -> Dict[str, LoadRecord]:
    parser = RouteSegmentsParser()
    parser.feed(station_html)

    records: Dict[str, LoadRecord] = {}
    for row in parser.rows:
        if len(row) < 5:
            continue

        destination_cell = row[0]
        code_match = re.search(r"\(([A-Z0-9]{3})\)", destination_cell)
        if not code_match:
            continue

        iata = code_match.group(1).upper()
        destination = clean_text(re.sub(r"\([A-Z0-9]{3}\)", "", destination_cell))
        weekly_loads = [parse_percent(cell) for cell in row[2:5]]
        records[iata] = LoadRecord(iata=iata, destination=destination, weekly_loads=weekly_loads)

    return records


def extract_economy_route_loads(load_monitoring_html: str, origin_airport: str) -> Dict[str, EconomyRouteLoad]:
    parser = FlightInstancesParser()
    parser.feed(load_monitoring_html)

    route_loads: Dict[str, EconomyRouteLoad] = {}
    origin_airport = origin_airport.upper()
    for row in parser.rows:
        # Columns are Code, Tail, Origin, Departure, Destination, Arrival,
        # then price/load pairs for Economy, Business, First, and Cargo.
        if len(row) < 8:
            continue

        origin = row[2].upper()
        destination = row[4].upper()
        if origin != origin_airport or not re.fullmatch(r"[A-Z0-9]{3}", destination):
            continue

        booked_capacity = parse_booked_capacity(row[7])
        if not booked_capacity:
            continue

        booked, capacity = booked_capacity
        record = route_loads.setdefault(destination, EconomyRouteLoad())
        record.booked += booked
        record.capacity += capacity

    return route_loads


def format_load_cell(value: Optional[int]) -> str:
    if value is None:
        return '<td class="as-load-cell as-load-missing" data-sort="-1">-</td>'
    return f'<td class="as-load-cell" data-sort="{value}">{value}%</td>'


def format_average_cell(record: Optional[LoadRecord]) -> str:
    if record is None or record.average_load is None:
        return '<td class="as-load-cell as-load-missing" data-sort="-1">-</td>'
    avg = record.average_load
    return f'<td class="as-load-cell as-load-average" data-sort="{avg:.4f}">{avg:.1f}%</td>'


def format_economy_route_load_cell(record: Optional[EconomyRouteLoad]) -> str:
    if record is None or record.load_percent is None:
        return '<td class="as-load-cell as-load-missing" data-sort="-1">-</td>'
    load = record.load_percent
    return f'<td class="as-load-cell" data-sort="{load:.4f}">{load:.1f}%</td>'


def strip_tags(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", "", html.unescape(value)))


def strip_route_map_data_columns(row_inner: str) -> tuple[str, List[str]]:
    full_cells = re.findall(r"<td\b[^>]*>.*?</td>", row_inner, flags=re.IGNORECASE | re.DOTALL)
    cell_values = re.findall(r"<td\b[^>]*>(.*?)</td>", row_inner, flags=re.IGNORECASE | re.DOTALL)
    if not full_cells or len(full_cells) != len(cell_values):
        return row_inner, cell_values
    kept_cells = [
        cell
        for index, cell in enumerate(full_cells)
        if index not in ROUTE_MAP_REMOVE_COLUMN_INDEXES
    ]
    return "".join(kept_cells), cell_values


def strip_route_map_header_columns(table_start: str) -> str:
    def transform_header_row(match: re.Match[str]) -> str:
        row_inner = match.group(1)
        headers = re.findall(r"<th\b[^>]*>.*?</th>", row_inner, flags=re.IGNORECASE | re.DOTALL)
        if not headers:
            return match.group(0)

        kept_headers: List[str] = []
        for index, header in enumerate(headers):
            if index in ROUTE_MAP_REMOVE_COLUMN_INDEXES:
                continue
            if index == 6:
                header = re.sub(r">Pax<", ">Demand<", header, count=1, flags=re.IGNORECASE)
            kept_headers.append(header)
        return "<tr>" + "".join(kept_headers) + "</tr>"

    return re.sub(
        r"<tr>\s*(.*?)\s*</tr>",
        transform_header_row,
        table_start,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )


def add_load_data_to_rows(
    tbody_html: str,
    records: Dict[str, LoadRecord],
    economy_route_loads: Dict[str, EconomyRouteLoad],
) -> tuple[str, int, int]:
    matched = 0
    economy_matched = 0

    def enrich_row(match: re.Match[str]) -> str:
        nonlocal matched, economy_matched
        row_inner = match.group(1)
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row_inner, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 3:
            return match.group(0)

        stripped_row_inner, cells = strip_route_map_data_columns(row_inner)
        iata = strip_tags(cells[2]).upper()
        country = strip_tags(cells[0])
        record = records.get(iata)
        if record:
            matched += 1
            week_cells = "".join(format_load_cell(value) for value in record.weekly_loads)
            avg_value = record.average_load
            avg_attr = f"{avg_value:.4f}" if avg_value is not None else "-1"
        else:
            week_cells = "".join(format_load_cell(None) for _ in range(3))
            avg_attr = "-1"

        avg_cell = format_average_cell(record)
        economy_route_load = economy_route_loads.get(iata)
        if economy_route_load and economy_route_load.load_percent is not None:
            economy_matched += 1
            economy_attr = f"{economy_route_load.load_percent:.4f}"
        else:
            economy_attr = "-1"
        economy_route_cell = format_economy_route_load_cell(economy_route_load)
        attrs = (
            f' data-country="{html.escape(country, quote=True)}"'
            f' data-iata="{html.escape(iata, quote=True)}"'
            f' data-avg-load="{avg_attr}"'
            f' data-economy-route-load="{economy_attr}"'
        )
        return f"<tr{attrs}>{stripped_row_inner}{economy_route_cell}{avg_cell}{week_cells}</tr>"

    enriched = re.sub(r"<tr\b[^>]*>(.*?)</tr>", enrich_row, tbody_html, flags=re.IGNORECASE | re.DOTALL)
    return enriched, matched, economy_matched


def build_controls(week_labels: List[str]) -> str:
    week_options = "".join(
        f'<option value="week{index}">{html.escape(label)}</option>'
        for index, label in enumerate(week_labels)
    )
    return f"""
              <div id="loadControls" class="as-load-controls">
                <label for="countryFilter">Country</label>
                <select id="countryFilter">
                  <option value="">All countries</option>
                </select>
                <label for="loadFilterMetric">Load filter</label>
                <select id="loadFilterMetric">
                  <option value="avg">Avg</option>
                  <option value="econ">Econ Route</option>
                  {week_options}
                </select>
                <input id="minimumAverageLoad" type="number" min="0" max="100" step="1" placeholder="0">
                <div class="as-range-filter" aria-label="Demand range">
                  <span>Demand</span>
                  <select id="paxDemandMin" aria-label="Minimum demand">
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5</option>
                    <option value="6">6</option>
                    <option value="7">7</option>
                    <option value="8">8</option>
                    <option value="9">9</option>
                    <option value="10">10</option>
                  </select>
                  <span>to</span>
                  <select id="paxDemandMax" aria-label="Maximum demand">
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5</option>
                    <option value="6">6</option>
                    <option value="7">7</option>
                    <option value="8">8</option>
                    <option value="9">9</option>
                    <option value="10" selected>10</option>
                  </select>
                </div>
                <button id="clearLoadFilters" type="button">Clear</button>
                <span id="visibleAirportCount" class="as-visible-count"></span>
              </div>
"""


def build_css() -> str:
    return """
      <style>
        .as-load-controls {
          display: flex;
          flex-wrap: wrap;
          gap: 8px 12px;
          align-items: center;
          margin: 12px 0;
        }
        .as-load-controls label {
          font-weight: bold;
          margin: 0;
        }
        .as-load-controls select,
        .as-load-controls input {
          width: auto;
          min-width: 120px;
          margin: 0;
        }
        .as-load-controls button {
          margin: 0;
        }
        .as-range-filter {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          white-space: nowrap;
        }
        .as-range-filter span {
          font-weight: bold;
        }
        .as-range-filter select {
          min-width: 52px;
          width: 52px;
        }
        #airport th {
          cursor: pointer;
          white-space: nowrap;
        }
        #airport th.as-load-heading,
        #airport td.as-load-cell {
          box-sizing: border-box;
          max-width: 58px;
          width: 58px;
          padding-left: 4px;
          padding-right: 4px;
        }
        #airport th.as-load-heading {
          font-size: 11px;
          line-height: 1.15;
          text-align: right;
          white-space: normal;
        }
        #airport th.as-sort-asc::after {
          content: " ^";
        }
        #airport th.as-sort-desc::after {
          content: " v";
        }
        #airport td.as-load-cell {
          text-align: right;
          white-space: nowrap;
        }
        #airport td.as-load-average {
          font-weight: bold;
        }
        #airport td.as-load-missing {
          color: #888;
        }
        .as-visible-count {
          color: #666;
        }
      </style>
"""


def build_script() -> str:
    return """
    <script>
      (function () {
        function textValue(cell) {
          return (cell ? cell.textContent : "").trim();
        }

        function numericValue(cell) {
          if (!cell) return Number.NEGATIVE_INFINITY;
          var raw = cell.getAttribute("data-sort");
          if (raw === null || raw === "") raw = cell.textContent;
          raw = String(raw).replace(/[^0-9.+-]/g, "");
          if (raw === "") return Number.NEGATIVE_INFINITY;
          var value = parseFloat(raw);
          return isNaN(value) ? Number.NEGATIVE_INFINITY : value;
        }

        function isNumericColumn(index) {
          return index >= 3;
        }

        var table = document.getElementById("airport");
        if (!table || !table.tBodies.length) return;

        var tbody = table.tBodies[0];
        var headers = Array.prototype.slice.call(table.tHead.rows[0].cells);
        var allRows = Array.prototype.slice.call(tbody.rows);
        var countryFilter = document.getElementById("countryFilter");
        var loadFilterMetric = document.getElementById("loadFilterMetric");
        var minimumAverageLoad = document.getElementById("minimumAverageLoad");
        var paxDemandMin = document.getElementById("paxDemandMin");
        var paxDemandMax = document.getElementById("paxDemandMax");
        var clearButton = document.getElementById("clearLoadFilters");
        var visibleAirportCount = document.getElementById("visibleAirportCount");
        var sortState = { index: null, direction: 1 };

        function populateCountries() {
          if (!countryFilter) return;
          var countries = {};
          allRows.forEach(function (row) {
            var country = row.getAttribute("data-country") || textValue(row.cells[0]);
            if (country) countries[country] = true;
          });
          Object.keys(countries).sort().forEach(function (country) {
            var option = document.createElement("option");
            option.value = country;
            option.textContent = country;
            countryFilter.appendChild(option);
          });
        }

        function normalizePaxDemandRange(changedSelect) {
          if (!paxDemandMin || !paxDemandMax) return { min: 1, max: 10 };
          var minDemand = parseInt(paxDemandMin.value, 10);
          var maxDemand = parseInt(paxDemandMax.value, 10);

          if (minDemand > maxDemand) {
            if (changedSelect === paxDemandMin) {
              maxDemand = minDemand;
              paxDemandMax.value = String(maxDemand);
            } else {
              minDemand = maxDemand;
              paxDemandMin.value = String(minDemand);
            }
          }

          return { min: minDemand, max: maxDemand };
        }

        function selectedLoadFilterValue(row) {
          var metric = loadFilterMetric ? loadFilterMetric.value : "avg";
          var cellIndexes = {
            econ: 6,
            avg: 7,
            week0: 8,
            week1: 9,
            week2: 10
          };
          return numericValue(row.cells[cellIndexes[metric] || cellIndexes.avg]);
        }

        function rowPassesFilters(row) {
          var selectedCountry = countryFilter ? countryFilter.value : "";
          var rowCountry = row.getAttribute("data-country") || textValue(row.cells[0]);
          if (selectedCountry && rowCountry !== selectedCountry) return false;

          var demandRange = normalizePaxDemandRange();
          var paxDemand = numericValue(row.cells[4]);
          if (paxDemand < demandRange.min || paxDemand > demandRange.max) return false;

          var minLoad = minimumAverageLoad ? parseFloat(minimumAverageLoad.value) : NaN;
          if (!isNaN(minLoad)) {
            var selectedLoad = selectedLoadFilterValue(row);
            if (isNaN(selectedLoad) || selectedLoad < minLoad) return false;
          }

          return true;
        }

        function compareRows(a, b) {
          if (sortState.index === null) return 0;
          var aCell = a.cells[sortState.index];
          var bCell = b.cells[sortState.index];
          var result;
          if (isNumericColumn(sortState.index)) {
            result = numericValue(aCell) - numericValue(bCell);
          } else {
            result = textValue(aCell).localeCompare(textValue(bCell), undefined, {
              numeric: true,
              sensitivity: "base"
            });
          }
          return result * sortState.direction;
        }

        function render() {
          var visible = allRows.filter(rowPassesFilters).sort(compareRows);
          tbody.textContent = "";
          visible.forEach(function (row) {
            tbody.appendChild(row);
          });
          if (visibleAirportCount) {
            visibleAirportCount.textContent = visible.length + " of " + allRows.length + " airports shown";
          }
        }

        headers.forEach(function (header, index) {
          header.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopImmediatePropagation();
            if (sortState.index === index) {
              sortState.direction = -sortState.direction;
            } else {
              sortState.index = index;
              sortState.direction = isNumericColumn(index) ? -1 : 1;
            }
            headers.forEach(function (item) {
              item.classList.remove("as-sort-asc", "as-sort-desc");
            });
            header.classList.add(sortState.direction === 1 ? "as-sort-asc" : "as-sort-desc");
            render();
          }, true);
        });

        if (countryFilter) countryFilter.addEventListener("change", render);
        if (loadFilterMetric) loadFilterMetric.addEventListener("change", render);
        if (minimumAverageLoad) minimumAverageLoad.addEventListener("input", render);
        if (paxDemandMin) {
          paxDemandMin.addEventListener("change", function () {
            normalizePaxDemandRange(paxDemandMin);
            render();
          });
        }
        if (paxDemandMax) {
          paxDemandMax.addEventListener("change", function () {
            normalizePaxDemandRange(paxDemandMax);
            render();
          });
        }
        if (clearButton) {
          clearButton.addEventListener("click", function () {
            if (countryFilter) countryFilter.value = "";
            if (loadFilterMetric) loadFilterMetric.value = "avg";
            if (minimumAverageLoad) minimumAverageLoad.value = "";
            if (paxDemandMin) paxDemandMin.value = "1";
            if (paxDemandMax) paxDemandMax.value = "10";
            normalizePaxDemandRange();
            render();
          });
        }

        populateCountries();
        normalizePaxDemandRange();
        render();
      }());
    </script>
"""


def enrich_route_map(
    route_map_html: str,
    records: Dict[str, LoadRecord],
    week_labels: List[str],
    economy_route_loads: Dict[str, EconomyRouteLoad],
) -> tuple[str, int, int]:
    table_pattern = re.compile(
        r"(<table\b[^>]*\bid=[\"']airport[\"'][^>]*>.*?<thead>.*?</thead>\s*<tbody>)(.*?)(</tbody>\s*</table>)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = table_pattern.search(route_map_html)
    if not match:
        raise ValueError('Could not find the route-map table with id="airport".')

    table_start, tbody_html, table_end = match.groups()
    enriched_tbody, matched_count, economy_matched_count = add_load_data_to_rows(
        tbody_html,
        records,
        economy_route_loads,
    )

    load_headers = (
        '<th class="header as-load-heading" data-sort-type="number">Econ Route</th>'
        '<th class="header as-load-heading" data-sort-type="number">Avg</th>'
        f'<th class="header as-load-heading" data-sort-type="number">{html.escape(week_labels[0])}</th>'
        f'<th class="header as-load-heading" data-sort-type="number">{html.escape(week_labels[1])}</th>'
        f'<th class="header as-load-heading" data-sort-type="number">{html.escape(week_labels[2])}</th>'
    )
    table_start = strip_route_map_header_columns(table_start)
    table_start = re.sub(
        r"(</tr>\s*</thead>)",
        load_headers + r"\1",
        table_start,
        count=1,
        flags=re.IGNORECASE,
    )

    replacement = table_start + enriched_tbody + table_end
    route_map_html = route_map_html[: match.start()] + replacement + route_map_html[match.end() :]

    route_map_html = route_map_html.replace(
        '<table id="airport"',
        build_controls(week_labels) + '              <table id="airport"',
        1,
    )

    if "</head>" in route_map_html.lower():
        route_map_html = re.sub(r"</head>", build_css() + "  </head>", route_map_html, count=1, flags=re.IGNORECASE)
    else:
        route_map_html = build_css() + route_map_html

    if "</body>" in route_map_html.lower():
        route_map_html = re.sub(r"</body>", build_script() + "  </body>", route_map_html, count=1, flags=re.IGNORECASE)
    else:
        route_map_html += build_script()

    return route_map_html, matched_count, economy_matched_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--airport",
        default=DEFAULT_AIRPORT,
        type=normalize_airport_code,
        help="Origin airport IATA code used to infer the load file name, e.g. DFW or jfk.",
    )
    parser.add_argument(
        "--station-file",
        default=None,
        help=(
            "Saved AirlineSim station load HTML file. "
            f"If omitted, this is inferred as '<AIRPORT> _ Otto _ AirlineSim.html' from --airport."
        ),
    )
    parser.add_argument("--route-map-file", default=DEFAULT_ROUTE_MAP_FILE, help="Saved AS Route Map airport-list HTML file.")
    parser.add_argument(
        "--load-monitoring-file",
        default=DEFAULT_LOAD_MONITORING_FILE,
        help="Saved AirlineSim Load Monitoring HTML file used for Economy route-load aggregation.",
    )
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE, help="Destination HTML file to write.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    station_file = args.station_file or station_file_for_airport(args.airport)
    station_path = Path(station_file)
    route_map_path = Path(args.route_map_file)
    load_monitoring_path = Path(args.load_monitoring_file)
    output_path = Path(args.output_file)

    station_html = read_text(station_path)
    route_map_html = read_text(route_map_path)
    if load_monitoring_path.exists():
        load_monitoring_html = read_text(load_monitoring_path)
        economy_route_loads = extract_economy_route_loads(load_monitoring_html, args.airport)
    else:
        economy_route_loads = {}

    week_labels = extract_week_labels(station_html)
    records = extract_load_records(station_html)
    if not records:
        raise ValueError("No passenger-load records were extracted from the AirlineSim station file.")

    enriched_html, matched_count, economy_matched_count = enrich_route_map(
        route_map_html,
        records,
        week_labels,
        economy_route_loads,
    )
    write_text(output_path, enriched_html)

    print(f"Airport: {args.airport}")
    print(f"Load file: {station_path}")
    print(f"Load monitoring file: {load_monitoring_path}")
    print(f"Extracted {len(records)} AirlineSim passenger-load records.")
    print(f"Matched {matched_count} airports in the AS Route Map table by IATA code.")
    print(f"Extracted Economy route-load data for {len(economy_route_loads)} routes.")
    print(f"Matched {economy_matched_count} Economy route-load rows in the AS Route Map table.")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
