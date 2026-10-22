# UN satellite damage assessments (UNOSAT)

## Source and licence

- **Publisher:** United Nations Satellite Centre (UNOSAT), on the Humanitarian Data Exchange (HDX):
  <https://data.humdata.org/organization/unosat>.
- **Access:** the public HDX CKAN API (`package_search`). No account or key is needed.
- **Licence:** recorded per dataset as HDX publishes it. UNOSAT's MENA datasets are *Creative Commons Attribution
  Share-Alike (CC BY-SA)*. Attribution: "Source: United Nations Satellite Centre (UNOSAT), via the Humanitarian Data
  Exchange (HDX)". MCHO's derived damage grid is shared under the same licence (share-alike), and the transformation
  is stated in the API response and on the page.

## What is kept

- **Conflict damage only.** These are UNOSAT "complex emergency" activations, whose code starts with `CE`, from the
  notes or the file URL. The title must be about damage or destruction. Floods, water extent, earthquakes, cropland,
  greenhouses, roads, density and percentage summaries, and environmental assessments are left out.
- **Countries:** the 22 MENA countries in `country_boundaries`, matched on HDX group (ISO3).
- **Catalogue for every eligible dataset:** title, UNOSAT code, publication date, licence, UNOSAT's description and
  caveats, and a link to HDX.
- **Map grid where the geodata can be read.** A zipped File Geodatabase or shapefile of 25 MB or less, from
  `unosat.org` or CERN's UNOSAT map server, is downloaded and read with GDAL (pyogrio).
  - The damage-site layer with the latest imagery date is used.
  - Each structure takes the most recent non-empty `Main_Damage_Site_Class*` value.
  - The classes are UNOSAT's own: 1 destroyed, 2 severe, 3 moderate, 4 and 11 possible. Class 6 (no visible
    damage) and other codes are not counted.
  - Layers that hold damage sites without a class (for example El Fasher, 2024) count as "damaged or destroyed, class
    not given".
- **Storage:** structures are counted per class in 0.005° (~500 m) cells. Individual structure locations are not
  stored or served.
- **Shared data files:** when several HDX entries share one data file, only the newest entry is processed. The others
  stay in the catalogue with a note.

## Avoiding double counting

UNOSAT's comprehensive assessments are cumulative. The map draws an assessment only if no newer mapped assessment
covers at least 80% of its extent. Covered assessments stay in the list, marked "Covered by newer".

## Checks against UNOSAT's published figures

| Assessment | UNOSAT's text | MCHO count from the geodata |
|---|---|---|
| Gaza Strip, 11 Oct 2025 | 123,464 destroyed; 17,116 severe; 33,857 moderate; 23,836 possible | Identical |
| El Fasher, 31 Jul 2024 | "more than 23,600 structures" damaged or destroyed | 23,646 (class not given) |

## Refresh

- `GET /api/v1/damage/overview` triggers a background sync at most once a day (UNOSAT publishes rarely). It also
  triggers one every 10 minutes while files are still waiting to be processed, which handles the first backfill.
- Each sync processes up to 6 files.
- Downloads are streamed with a size cap, and redirects are followed only to allowed hosts.
- No database transaction is held during downloads.
- A file that cannot be read marks only that assessment as `failed`, with the reason.

## Limits

- Assessments are preliminary and mostly not validated in the field.
- Only significant structural damage is visible from above.
- Coverage is patchy in space and time. Many MENA assessments date from 2014–2018. The newest on HDX are Gaza, October
  2025.
- Some older files use layouts or coordinate systems MCHO does not read. These stay catalogue-only, with the reason
  shown.
