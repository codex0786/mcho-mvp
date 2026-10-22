import type { Metadata } from "next";

import SiteFooter from "../../components/SiteFooter";
import SiteNav from "../../components/SiteNav";

export const metadata: Metadata = {
  title: "About the data | MCHO",
  description: "Where MCHO's satellite data comes from, how it is analysed, and what it can and cannot tell you.",
};

export default function About() {
  return (
    <>
    <SiteNav page="about" />
    <main className="shell about">
      <header className="topbar">
        <div><div className="eyebrow">ABOUT THE DATA</div><h1>How MCHO reads satellite heat</h1></div>
        <div className="header-actions"><a className="text-link" href="/">← Back to the live map</a></div>
      </header>

      <section className="notice"><strong>In one sentence:</strong> MCHO shows where NASA satellites detected unusual heat across the Middle
        East and North Africa, and points out what is new or above normal — leads for people to investigate, not confirmed events.</section>

      <article className="about-body">
        <h2>Where the data comes from</h2>
        <p>
          NASA&apos;s <a className="text-link" href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">Fire Information for Resource
          Management System (FIRMS)</a> publishes heat detections from the VIIRS instrument on three satellites (Suomi NPP, NOAA-20 and NOAA-21).
          Each detection is a pixel of about 375 m that was much hotter than its surroundings when a satellite passed over, with its time, a
          confidence level and its <em>fire radiative power</em> (how intense the heat was). Detections usually arrive within about three hours.
          MCHO downloads them about every hour and keeps the last 21 days for 22 countries.
        </p>

        <h2>What the colours mean</h2>
        <ul>
          <li><strong>New activity (red):</strong> heat at a spot (~2 km) with no detections in the previous 7 days.</li>
          <li><strong>Recurring (amber):</strong> heat at a spot seen on 1–3 of the previous 7 days.</li>
          <li><strong>Persistent site (grey):</strong> heat on 4 or more of the previous 7 days — usually gas flares, refineries or other
            industry. These are left out of activity counts so they don&apos;t drown out change.</li>
        </ul>
        <p>
          A country is marked <strong>above normal</strong> when it has at least 10 non-persistent detections in the time window and at least twice
          its daily average over the previous 7 days. <strong>New-activity clusters</strong> group new detections that fall within the same ~10 km area.
          The country trend chart shows each day of the last three weeks; days before collection started show as &ldquo;no data&rdquo;, never as zero.
          It also marks each day&apos;s total on the <strong>same calendar day last year</strong>, from NASA&apos;s FIRMS archive, counting only the
          satellites available in both years — the clearest way to tell an unusual week from a normal burning season.
        </p>

        <h2>Moving fronts</h2>
        <p>
          Heat clusters on consecutive days that lie within 30 km of each other are linked into a <strong>moving front</strong> (cyan lines on the
          map), so you can see whether activity is spreading or shifting and in which direction. Gas flares and other persistent sites are left out.
          A front shows how heat moved, not what caused it: separate fires close together can be linked, and clouds can break a front.
        </p>

        <h2>Looking at the ground</h2>
        <p>
          For each new-activity cluster, &ldquo;Satellite image&rdquo; shows recent Copernicus Sentinel-2 pictures of the area, with a link to view them at
          full 10 m resolution. Sentinel-2 is a different satellite: it passes roughly every five days, so its image can be from before or after the
          heat was detected, and clouds or smoke can hide the ground. Burn scars and smoke are often visible; small or short fires may not be.
        </p>

        <h2>Shipping</h2>
        <p>
          The shipping panel shows how many ships pass the region&apos;s chokepoints each day — Suez, Bab el-Mandeb, Hormuz, the Bosporus,
          Gibraltar and the Cape of Good Hope, where ships diverted from the Red Sea go round Africa — and how many call at MENA ports, compared
          with the same days last year. The figures are the IMF&apos;s PortWatch daily aggregates, built from ships&apos; AIS signals; MCHO computes
          the 7-day averages and comparisons. Ships that switch off AIS aren&apos;t counted, and no individual ship is shown.
        </p>

        <h2>Verified events and deaths</h2>
        <p>
          The Uppsala Conflict Data Program (UCDP) codes every incident of organised violence that kills at least one person, from news and
          NGO reports: where and when, who fought whom, and how many died (a best estimate with a low–high range). MCHO shows UCDP&apos;s
          monthly Candidate releases, which are preliminary and appear about three weeks after each month ends, and sums them by country and
          month. A month that was not downloaded is shown as missing, never as zero.
        </p>
        <p>
          <strong>Heat cross-check.</strong> For each UCDP event whose place is known to within about 25 km and date to within a few days,
          MCHO fetches NASA FIRMS archive detections from two VIIRS satellites around it and records whether heat was seen within 5 km
          (exact place) or 25 km, from the day before to the day after, leaving out persistent sites such as gas flares. This links a verified
          event to a satellite signal; it does not prove the event caused the fire, and no heat does not mean nothing burned. MCHO also lists
          today&apos;s moving heat fronts that lie within 25 km of UCDP events in the previous 180 days, as context rather than cause.
        </p>

        <h2>UN damage assessments</h2>
        <p>
          The United Nations Satellite Centre (UNOSAT) compares satellite images taken before and after attacks and marks each building it
          judges destroyed, severely, moderately or possibly damaged. MCHO lists UNOSAT&apos;s conflict damage assessments for the region and,
          where the published geodata can be read, counts those buildings by UNOSAT&apos;s own class in cells of about 500 m. When a newer
          assessment covers the same area, only the newer one is drawn, because UNOSAT&apos;s assessments are cumulative. Assessments are
          preliminary, cover specific areas on specific dates, and appear months apart: a place without an assessment is unassessed, not
          undamaged.
        </p>

        <h2>What it can&apos;t tell you</h2>
        <ul>
          <li><strong>The cause.</strong> Heat can come from fighting, shelling-related fires, crop and stubble burning, wildfires, waste burning
            or industry. The satellite can&apos;t tell them apart.</li>
          <li><strong>Seasons matter.</strong> From about October to March, dry-season savanna and farm burning produces most detections in Sudan and
            the Sahel. High numbers there in that period are expected.</li>
          <li><strong>Absence isn&apos;t evidence.</strong> Clouds, smoke and satellite timing leave gaps. Small or short fires may never be detected.</li>
          <li><strong>Borders are approximate.</strong> Detections within about 1 km of a border may be counted for the neighbouring country.
            Offshore detections (e.g. platform flares) are not included.</li>
        </ul>

        <h2>How it should be used</h2>
        <p>
          As a starting point for questions — &ldquo;why is there new heat here?&rdquo; — to be checked against reporting, imagery and people on the
          ground. MCHO never turns a detection into a published event automatically, and nothing here is for targeting or tactical decisions.
        </p>

        <h2>Sources and credits</h2>
        <ul>
          <li>Satellite detections: NASA FIRMS, VIIRS 375 m near-real-time products (NASA open data).</li>
          <li>Imagery: Copernicus Sentinel-2 L2A (free and open), found via <a className="text-link" href="https://earth-search.aws.element84.com/v1" target="_blank" rel="noreferrer">Earth Search</a> (Element 84, AWS Open Data); full-resolution viewing in Copernicus Browser.</li>
          <li>Shipping: Source: International Monetary Fund, <a className="text-link" href="https://portwatch.imf.org" target="_blank" rel="noreferrer">PortWatch</a> (daily chokepoint transits and port calls, AIS-based); averages and comparisons computed by MCHO.</li>
          <li>Conflict events: <a className="text-link" href="https://ucdp.uu.se/downloads/" target="_blank" rel="noreferrer">UCDP Candidate Events Dataset</a>, Uppsala University, CC BY 4.0. Hegre, Croicu, Eck and Högbladh (2020), &ldquo;Introducing the UCDP Candidate Events Dataset&rdquo;, <em>Research &amp; Politics</em>.</li>
          <li>Damage assessments: United Nations Satellite Centre (UNOSAT), via the <a className="text-link" href="https://data.humdata.org/organization/unosat" target="_blank" rel="noreferrer">Humanitarian Data Exchange</a>, CC BY-SA; MCHO&apos;s ~500 m damage grid is shared under the same licence.</li>
          <li>Country borders: <a className="text-link" href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a> 1:50m (public domain).</li>
          <li>Basemap: <a className="text-link" href="https://openfreemap.org/" target="_blank" rel="noreferrer">OpenFreeMap</a>, map data © OpenStreetMap contributors.</li>
        </ul>
        <p className="muted">
          This is a demonstration. The <a className="text-link" href="/demo">design preview</a> uses invented sample data to show planned features; the
          live map uses real satellite data only.
        </p>
      </article>
    </main>
    <SiteFooter />
    </>
  );
}
