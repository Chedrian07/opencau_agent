import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "OpenCAU Agent",
  description: "Local desktop agent",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
