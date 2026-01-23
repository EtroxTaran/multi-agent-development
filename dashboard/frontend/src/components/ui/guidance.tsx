import { HelpCircle } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";
import { cn } from "@/lib/utils";

interface GuidanceProps {
  content: React.ReactNode;
  className?: string;
}

export function Guidance({ content, className }: GuidanceProps) {
  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <HelpCircle
            className={cn(
              "h-4 w-4 text-muted-foreground hover:text-foreground cursor-help transition-colors",
              className,
            )}
          />
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{content}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
