import type { Metadata } from "next";
import DemoExperience from "./DemoExperience";
import "./demo.css";

export const metadata: Metadata = {
  title: "Interactive Prototype | MCHO",
  description: "A clearly synthetic, offline-friendly preview of the MENA Conflict & Humanitarian Observatory interface.",
};

export default function DemoPage() {
  return <DemoExperience />;
}
