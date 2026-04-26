import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "OpenCAU Agent",
  description: "Local desktop agent",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23147262'/%3E%3Cpath d='M8 11h16v10H8z' fill='white'/%3E%3Cpath d='M12 25h8' stroke='white' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E",
  },
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
