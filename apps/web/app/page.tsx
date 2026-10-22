import ObservatoryDashboard from "../components/ObservatoryDashboard";
import SiteFooter from "../components/SiteFooter";
import SiteNav from "../components/SiteNav";

export default function Home() {
  return (
    <>
      <SiteNav />
      <main className="shell home">
        <ObservatoryDashboard />
        <section className="notice info-strip" role="status">
          <span className="info-icon" aria-hidden="true">i</span>
          <p><strong>Data status:</strong> Satellite heat detections update about hourly from NASA FIRMS and are analysed automatically. They are unverified observations: a detection can be conflict-related fire, crop burning, wildfire or a gas flare. Verified conflict events and deaths come from UCDP&apos;s monthly releases, which run about 3–7 weeks behind the satellites; UN damage assessments come from UNOSAT.</p>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
