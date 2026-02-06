"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { isAuthenticated, getMe, type User } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { TradingPlatformSelector } from "@/components/trading-platform-selector";
import {
  LayoutDashboard,
  Radar,
  Bell,
  Wallet,
  Brain,
  CreditCard,
  Bot,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/scanner", label: "Scanner", icon: Radar },
  { href: "/dashboard/callouts", label: "Callouts", icon: Bell },
  { href: "/dashboard/wallets", label: "Wallets", icon: Wallet },
  { href: "/dashboard/smart-money", label: "Smart Money", icon: Brain },
  { href: "/dashboard/copy-trade", label: "Copy Trade", icon: Bot },
  { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
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
      <aside className="hidden md:flex w-60 flex-col border-r border-border/20 bg-card/30 backdrop-blur-md">
        <div className="p-4 border-b border-border/20">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <span className="text-sm font-bold text-primary">
                {user.email[0].toUpperCase()}
              </span>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{user.email}</p>
              <Badge variant="teal" className="mt-0.5 capitalize text-[10px]">
                {user.tier}
              </Badge>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-0.5">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all duration-200",
                pathname === item.href
                  ? "bg-primary/10 text-primary border-l-2 border-primary font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              )}
            >
              <item.icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  pathname === item.href
                    ? "text-primary"
                    : "text-muted-foreground"
                )}
              />
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="p-3 border-t border-border/20">
          <TradingPlatformSelector />
        </div>
      </aside>

      {/* Mobile nav */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 border-t border-border/30 bg-background/95 backdrop-blur-md z-50 flex">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex-1 flex flex-col items-center gap-0.5 py-2 text-xs transition-colors",
              pathname === item.href
                ? "text-primary font-medium border-t-2 border-primary"
                : "text-muted-foreground"
            )}
          >
            <item.icon className="h-4 w-4" />
            <span className="text-[10px]">{item.label}</span>
          </Link>
        ))}
      </div>

      {/* Main content */}
      <div className="flex-1 p-6 pb-20 md:pb-6 overflow-auto">{children}</div>
    </div>
  );
}
