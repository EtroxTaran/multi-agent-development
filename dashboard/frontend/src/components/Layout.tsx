/**
 * Main layout component
 */

import { Link, useLocation } from "@tanstack/react-router";
import { Home, Settings, FolderKanban } from "lucide-react";
import { cn } from "@/lib/utils";

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Projects", icon: FolderKanban },
    { path: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-background font-sans antialiased">
      {/* Glassmorphic Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-8">
            <Link
              to="/"
              className="flex items-center space-x-2 transition-transform hover:scale-105"
            >
              <div className="rounded-lg bg-primary/10 p-1.5 ring-1 ring-primary/20">
                <Home className="h-5 w-5 text-primary" />
              </div>
              <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Conductor
              </span>
            </Link>

            <nav className="flex items-center space-x-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={cn(
                      "group flex items-center space-x-2 rounded-md px-3 py-2 text-sm font-medium transition-all hover:bg-accent hover:text-accent-foreground",
                      isActive
                        ? "bg-secondary text-secondary-foreground shadow-sm ring-1 ring-border"
                        : "text-muted-foreground",
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 transition-colors",
                        isActive ? "text-primary" : "group-hover:text-primary",
                      )}
                    />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center space-x-4">
            {/* Future: User profile or global status indicators */}
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="container py-8 animate-fade-in-up">{children}</main>
    </div>
  );
}
