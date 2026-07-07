# AirlineSim Route Planning Tools

## IMPORTANT: AI-Written Scripts

**These scripts were written by AI. Review the code and outputs yourself before
using them for any planning decision.**

The scripts parse saved HTML pages and generate new local HTML reports. AI-written
code can contain bugs, incorrect assumptions, fragile parsing logic, misleading
calculations, or incomplete handling of edge cases. AirlineSim and AS Route Map
pages may also change over time, which can cause the scripts to silently miss,
misread, or mislabel data. Use the generated reports as a convenience tool only,
not as an authoritative source.

By using these scripts, you accept the risk that the output may be wrong and
that route, scheduling, or fleet decisions based on it may be suboptimal.

This repository contains small Python utilities for working with saved
AirlineSim and AS Route Map HTML pages. Both scripts use only the Python
standard library.

## Supported Environments

These scripts are written for Python 3 and use only the standard library.

Supported environments:

- Windows PowerShell with Python 3. The permanent environment setup uses `setx`.
- Linux with Python 3. The permanent environment setup updates `~/.profile`.
- WSL with Python 3. The permanent environment setup updates the WSL user's
  `~/.profile`, not the Windows user's environment.
- macOS with Python 3. The permanent environment setup updates `~/.zprofile`.

After using the permanent save option, open a new terminal before relying on the
new variables.

## Input Files

Save the required pages as HTML files before running the setup script or report
scripts.

- AS Route Map airport list: use an appropriate filter at
  <https://www.asroutemap.info/find.asp>, then save the resulting page.
- Airport load by route: in AirlineSim, go to
  `Operations -> Stations -> click on station name -> view station on top right -> Load Statistics`,
  then save the page.
- Load monitoring: in AirlineSim, go to
  `Commercial -> Load Monitoring -> set reasonable filter -> submit`, then save
  the page. Avoid selecting `48h until 72h` unless you specifically need that
  window. Using `any` for both Origin and Destination can be very slow for a
  large airline.

## Environment Setup

After saving the input files, use `configure_airlinesim_env.py` to save your
AirlineSim airline name and game world as environment variables:

- `AIRLINESIM_AIRLINE_NAME`
- `AIRLINESIM_GAME_WORLD`

Run it from the repository folder:

Windows PowerShell:

```powershell
python configure_airlinesim_env.py
```

Linux, WSL, or macOS:

```sh
python3 configure_airlinesim_env.py
```

The script asks for your airline name, searches the available files for the best
match, and asks you to confirm it. If it cannot find a match above 50%, it
prints an error and exits. If only one game world is found, it uses that world;
otherwise, it asks you to choose one.

When prompted, choose whether to permanently save the values. The script also
prints commands you can run to set the variables in the current terminal
immediately:

Windows PowerShell:

```powershell
$env:AIRLINESIM_AIRLINE_NAME = 'Guo Air'
$env:AIRLINESIM_GAME_WORLD = 'Otto'
```

Linux, WSL, or macOS:

```sh
export AIRLINESIM_AIRLINE_NAME='Guo Air'
export AIRLINESIM_GAME_WORLD='Otto'
```

## active_flights_by_airport.py

Use this script mostly for destination expansion. It compares a saved
AirlineSim schedule with an AS Route Map airport list and creates a sortable
HTML report showing how many active flight numbers already exist from one
origin airport to each destination in the route-map list.

Default inputs:

- `<AIRLINESIM_AIRLINE_NAME> _ <AIRLINESIM_GAME_WORLD> _ AirlineSim.html`
  if environment variables are set; otherwise `Guo Air _ Otto _ AirlineSim.html`
- `AS Route Map _ Find Airports.html`

Default output:

- `active_flights_by_airport.html`

Examples:

```powershell
python active_flights_by_airport.py
python active_flights_by_airport.py --airport DFW --output dfw_active_flights.html
python active_flights_by_airport.py --airport JFK --schedule "Guo Air _ Otto _ AirlineSim.html" --map "AS Route Map _ Find Airports.html" --output jfk_active_flights.html
```

Options:

- `--airport`, `-a`: origin airport IATA code. Default: `JFK`.
- `--schedule`, `-s`: saved AirlineSim schedule HTML file. By default, this is
  inferred from `AIRLINESIM_AIRLINE_NAME` and `AIRLINESIM_GAME_WORLD`.
- `--map`, `-m`: saved AS Route Map Find Airports HTML file.
- `--output`, `-o`: output HTML report file.

Open the generated report in a browser. It includes sortable columns, country
and demand filters, a minimum runway filter, and row highlighting.

## add_loads_to_route_map.py

Use this script mostly for adding flights to existing routes. It merges
AirlineSim station load statistics and optional Load Monitoring data into a
saved AS Route Map airport list, then writes a new HTML file with load columns
and filters.

Default inputs:

- `DFW _ <AIRLINESIM_GAME_WORLD> _ AirlineSim.html`, inferred from
  `--airport DFW` if `AIRLINESIM_GAME_WORLD` is set; otherwise
  `DFW _ Otto _ AirlineSim.html`
- `AS Route Map _ Find Airports.html`
- `Load monitoring _ <AIRLINESIM_GAME_WORLD> _ AirlineSim.html` if
  `AIRLINESIM_GAME_WORLD` is set; otherwise
  `Load monitoring _ Otto _ AirlineSim.html`

Default output:

- `AS Route Map _ Find Airports with Loads.html`

Examples:

```powershell
python add_loads_to_route_map.py
python add_loads_to_route_map.py --airport JFK --station-file "JFK _ Otto _ AirlineSim.html"
python add_loads_to_route_map.py --airport LAX --route-map-file "AS Route Map _ Find Airports.html" --load-monitoring-file "Load monitoring _ Otto _ AirlineSim.html" --output-file "LAX route map with loads.html"
```

Options:

- `--airport`: origin airport IATA code. Default: `DFW`.
- `--station-file`: saved AirlineSim station load statistics HTML. If omitted,
  the script infers `<AIRPORT> _ <AIRLINESIM_GAME_WORLD> _ AirlineSim.html`.
- `--route-map-file`: saved AS Route Map airport-list HTML file.
- `--load-monitoring-file`: saved AirlineSim Load Monitoring HTML file used for
  Economy route-load aggregation. By default, this is inferred from
  `AIRLINESIM_GAME_WORLD`. If the file is missing, the script still runs and
  leaves Economy route-load values blank.
- `--output-file`: output HTML file.

Open the generated route map in a browser. It adds Economy route load, average
station load, and recent weekly load columns, plus filters for country, load
threshold, and demand range.
