"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Upload, MessageSquare, FileText, Share2 } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/chat",      label: "Chat",      icon: MessageSquare },
  { href: "/upload",    label: "Upload",    icon: Upload },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/graph",     label: "Graph",     icon: Share2 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-56 shrink-0 flex-col border-r border-border bg-card px-3 py-5">
      <div className="mb-8 px-2">
        <h1 className="text-xl font-bold tracking-tight">Docify</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Document Intelligence</p>
      </div>

      <nav className="flex flex-col gap-1">
        {nav.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              pathname === href
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
