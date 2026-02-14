import { ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "cta" | "icon";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit" | "reset";
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: "bg-theme-primary text-white hover:opacity-90",
  secondary:
    "bg-bg-elevated border border-border-custom text-text-primary hover:bg-bg-surface",
  cta: "bg-theme-danger text-white hover:opacity-90 font-semibold",
  icon: "bg-bg-elevated border border-border-custom text-text-secondary hover:bg-bg-surface p-2",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-5 py-3 text-sm",
  lg: "px-6 py-3 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  children,
  icon,
  onClick,
  disabled = false,
  className = "",
  type = "button",
}: ButtonProps) {
  const baseStyles =
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed";

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${baseStyles} ${variantStyles[variant]} ${
        variant !== "icon" ? sizeStyles[size] : ""
      } ${className}`}
    >
      {icon && <span className="w-5 h-5">{icon}</span>}
      {children}
    </button>
  );
}
