import { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  title?: string;
}

export function Card({ children, className = "", title }: CardProps) {
  return (
    <div
      className={`bg-bg-elevated rounded-lg shadow-sm border border-border-custom p-4 ${className}`}
    >
      {title && (
        <h3 className="text-lg font-semibold text-text-primary mb-3">{title}</h3>
      )}
      {children}
    </div>
  );
}
