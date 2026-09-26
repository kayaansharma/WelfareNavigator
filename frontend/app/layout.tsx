import "./globals.css";
export const metadata = { title: "Welfare Navigator", description: "Discover. Verify. Prepare. Apply." };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
