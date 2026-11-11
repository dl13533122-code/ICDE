# Data sources and preprocessing

Raw public datasets are obtained separately. They are not needed to rerender
the archived figures or run the self-contained implementation tests.

## Electricity

- Official source: [UCI ElectricityLoadDiagrams20112014](https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014).
- Citation: Artur Trindade (2015), DOI [10.24432/C58C86](https://doi.org/10.24432/C58C86).
- Original file: `LD2011_2014.txt`; semicolon-separated timestamp and client columns.
- The UCI page specifies [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The paper converts quarter-hour kW values to kWh, clips to [0,1000], normalizes,
and forms daily averages from 96 readings per complete day. The current
coverage table reports 370 owners, 140,256 raw rows, 1,460 complete dates, and
487 evaluation dates. The public finite-report schedule selects 336 of those
487 evaluation dates.

## Intel

- Official source: [Intel Lab Data at MIT CSAIL](https://db.csail.mit.edu/labdata/labdata.html).
- Data collectors: Peter Bodik, Wei Hong, Carlos Guestrin, Sam Madden,
  Mark Paskin, and Romain Thibaux.
- The official page links the measurement archive and the public mote locations.
- The provider permits use or reproduction with acknowledgment of the collectors.

The paper retains 54 public owners and represents absence by (0,0). Temperature,
humidity, voltage, and light must be finite; temperature/humidity/voltage must
lie within [-50,100]/[0,100]/[2,3]. Temperatures are clipped to [0,100] and
normalized before daily averaging. Current manuscript coverage is 2,313,682
raw rows, 28 qualified dates, and ten evaluation dates. These are the current
paper's preprocessing conventions; older tests and drivers have their own
explicit roster/calendar fixtures.

## Included derived data

`results/` contains the supplied aggregate analysis snapshots, not the raw
dataset releases or complete original remote run directories. `plotting/data/`
contains the exact values used by the current rendering scripts. Original
paths inside archived JSON are provenance labels; they do not need to exist
to regenerate the CSVs or plots.

Local downloads and processed datasets belong under `data/` and should not be
committed automatically. Dataset terms are independent of the authors' code
and do not grant rights to unrelated third-party code.
