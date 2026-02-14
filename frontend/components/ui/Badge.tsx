import { ReactNode } from "react";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "info";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-bg-elevated text-text-secondary border border-border-custom",
  success: "bg-theme-success/10 text-theme-success dark:bg-theme-success/20",
  warning: "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400",
  danger: "bg-theme-danger/10 text-theme-danger dark:bg-theme-danger/20",
  info: "bg-theme-primary/10 text-theme-primary dark:bg-theme-primary/20",
};

export function Badge({
  children,
  variant = "default",
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
