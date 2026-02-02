"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { isAuthenticated, getMe, type User } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";

const navItems = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/scanner", label: "Scanner" },
  { href: "/dashboard/callouts", label: "Callouts" },
  { href: "/dashboard/wallets", label: "Wallets" },
  { href: "/dashboard/smart-money", label: "Smart Money" },
  { href: "/dashboard/billing", label: "Billing" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    getMe().then(setUser).catch(() => router.push("/login"));
  }, [router]);

  if (!user) {
    return (
      <div className="flex min-h-[80vh] items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)]">
      {/* Sidebar */}
      <aside className="hidden md:flex w-56 flex-col border-r border-border/30 bg-card/50 backdrop-blur-sm p-4 gap-1">
        <div className="mb-4">
          <p className="text-sm text-muted-foreground">Signed in as</p>
          <p className="text-sm font-medium truncate">{user.email}</p>
          <Badge variant="teal" className="mt-1 capitalize">
            {user.tier}
          </Badge>
        </div>
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "px-3 py-2 rounded-md text-sm transition-colors",
              pathname === item.href
                ? "bg-primary/15 text-primary border-l-2 border-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
            )}
          >
            {item.label}
          </Link>
        ))}
      </aside>

      {/* Mobile nav */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 border-t border-border/30 bg-background z-50 flex">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex-1 text-center py-3 text-xs transition-colors",
              pathname === item.href
                ? "text-primary font-medium border-t-2 border-primary"
                : "text-muted-foreground"
            )}
          >
            {item.label}
          </Link>
        ))}
      </div>

      {/* Main content */}
      <div className="flex-1 p-6 pb-20 md:pb-6 overflow-auto">{children}</div>
    </div>
  );
}
