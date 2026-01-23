import { AlertTriangle, CheckCircle, Info, XCircle, X } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { useState } from "react";

const alertVariants = cva(
  "relative w-full rounded-lg border p-4 [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground",
  {
    variants: {
      variant: {
        default: "bg-background text-foreground",
        destructive:
          "border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive",
        success:
          "border-green-500/50 text-green-600 dark:text-green-400 dark:border-green-500 [&>svg]:text-green-600 dark:[&>svg]:text-green-400",
        warning:
          "border-yellow-500/50 text-yellow-600 dark:text-yellow-400 dark:border-yellow-500 [&>svg]:text-yellow-600 dark:[&>svg]:text-yellow-400",
      },
      layout: {
        default: "",
        banner: "rounded-none border-x-0 border-t-0",
      },
    },
    defaultVariants: {
      variant: "default",
      layout: "default",
    },
  },
);

interface AlertBannerProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {
  title?: string;
  icon?: React.ReactNode;
  onDismiss?: () => void;
  action?: React.ReactNode;
}

export function AlertBanner({
  className,
  variant,
  layout,
  title,
  icon,
  children,
  onDismiss,
  action,
  ...props
}: AlertBannerProps) {
  const [isVisible, setIsVisible] = useState(true);

  if (!isVisible) return null;

  const handleDismiss = () => {
    setIsVisible(false);
    onDismiss?.();
  };

  const Icon = icon ? (
    <span className="h-4 w-4">{icon}</span>
  ) : variant === "destructive" ? (
    <XCircle className="h-4 w-4" />
  ) : variant === "success" ? (
    <CheckCircle className="h-4 w-4" />
  ) : variant === "warning" ? (
    <AlertTriangle className="h-4 w-4" />
  ) : (
    <Info className="h-4 w-4" />
  );

  return (
    <div
      role="alert"
      className={cn(
        alertVariants({ variant, layout }),
        "animate-fade-in-up",
        className,
      )}
      {...props}
    >
      {Icon}
      <div>
        {title && (
          <h5 className="mb-1 font-medium leading-none tracking-tight">
            {title}
          </h5>
        )}
        <div className="text-sm [&_p]:leading-relaxed">{children}</div>
      </div>
      {(onDismiss || action) && (
        <div className="absolute right-4 top-4 flex items-center gap-2">
          {action}
          {onDismiss && (
            <button
              onClick={handleDismiss}
              className="rounded-md p-1 opacity-70 hover:opacity-100 transition-opacity focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Dismiss</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
