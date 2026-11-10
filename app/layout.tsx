import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "GapFinder AI — Diagnostic Assessment & Revision Engine",
  description: "Find what the student doesn't know and build a personalized revision plan grounded in syllabus and textbooks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
