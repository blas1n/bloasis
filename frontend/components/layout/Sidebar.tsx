"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  name: string;
  href: string;
  icon: React.ReactNode;
}

const navigation: NavItem[] = [
  {
    name: "Dashboard",
    href: "/dashboard",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    name: "Portfolio",
    href: "/dashboard/portfolio",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    name: "Trading",
    href: "/dashboard/trading",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex flex-col w-[180px] bg-bg-base min-h-screen">
      {/* Logo */}
      <div className="flex items-center h-16 px-6 bg-bg-base">
        <span className="text-xl font-bold text-text-primary">BLOASIS</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-6 space-y-3">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center px-4 py-3 text-sm rounded-lg transition-colors ${
                isActive
                  ? "bg-[rgba(0,217,255,0.1)] text-theme-primary font-semibold"
                  : "text-text-secondary font-medium hover:bg-[rgba(0,217,255,0.05)] hover:text-text-primary"
              }`}
            >
              <span className="mr-3">{item.icon}</span>
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* User Section */}
      <div className="flex items-center px-4 py-4 border-t border-border-custom">
        <div className="flex-shrink-0">
          <div className="h-8 w-8 rounded-full bg-bg-elevated flex items-center justify-center">
            <span className="text-sm font-medium text-text-primary">U</span>
          </div>
        </div>
        <div className="ml-3">
          <p className="text-sm font-medium text-text-primary">Demo User</p>
          <p className="text-xs text-text-secondary">Paper Trading</p>
        </div>
      </div>
    </div>
  );
}
