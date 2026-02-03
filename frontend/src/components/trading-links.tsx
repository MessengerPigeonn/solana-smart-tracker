"use client";

import { useState, useEffect, useCallback } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Zap,
  TrendingUp,
  Target,
  ArrowRightLeft,
  Terminal,
  ChevronDown,
  ExternalLink,
  Star,
  Check,
} from "lucide-react";
import {
  TRADING_PLATFORMS,
  getPreferredPlatform,
  setPreferredPlatformId,
  type TradingPlatform,
} from "@/lib/trading-platforms";

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Zap,
  TrendingUp,
  Target,
  ArrowRightLeft,
  Terminal,
};

interface TradingLinksProps {
  tokenAddress: string;
  variant?: "compact" | "expanded" | "icon-only";
  className?: string;
}

export function TradingLinks({
  tokenAddress,
  variant = "compact",
  className = "",
}: TradingLinksProps) {
  const [preferred, setPreferred] = useState<TradingPlatform>(
    TRADING_PLATFORMS[0]
  );

  useEffect(() => {
    setPreferred(getPreferredPlatform());
  }, []);

  const handleSetDefault = useCallback((platform: TradingPlatform) => {
    setPreferredPlatformId(platform.id);
    setPreferred(platform);
  }, []);

  const openPlatform = useCallback(
    (platform: TradingPlatform) => {
      window.open(platform.buildUrl(tokenAddress), "_blank", "noopener");
    },
    [tokenAddress]
  );

  const stopPropagation = useCallback(
    (e: React.MouseEvent) => e.stopPropagation(),
    []
  );

  if (variant === "icon-only") {
    const IconComp = ICON_MAP[preferred.icon] || Zap;
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={`h-7 w-7 hover:text-primary hover:bg-primary/10 ${className}`}
              onClick={(e) => {
                stopPropagation(e);
                openPlatform(preferred);
              }}
            >
              <IconComp className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Quick buy on {preferred.name}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  if (variant === "expanded") {
    return (
      <div
        className={`flex items-center gap-1.5 flex-wrap ${className}`}
        onClick={stopPropagation}
      >
        <span className="text-xs text-muted-foreground mr-1">Trade on:</span>
        {TRADING_PLATFORMS.map((platform) => {
          const IconComp = ICON_MAP[platform.icon] || Zap;
          const isDefault = platform.id === preferred.id;
          return (
            <TooltipProvider key={platform.id}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className={`h-7 px-2 text-xs gap-1 ${
                      isDefault
                        ? "border-primary/50 text-primary"
                        : "hover:border-primary/30"
                    }`}
                    onClick={() => openPlatform(platform)}
                  >
                    <IconComp className="h-3 w-3" />
                    {platform.shortName}
                    {isDefault && (
                      <Star className="h-2.5 w-2.5 fill-primary text-primary" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{platform.description}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          );
        })}
      </div>
    );
  }

  // Default: "compact" variant — split button + dropdown
  const PreferredIcon = ICON_MAP[preferred.icon] || Zap;

  return (
    <div
      className={`inline-flex items-center ${className}`}
      onClick={stopPropagation}
    >
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs rounded-r-none border-r-0 gap-1 hover:border-primary/50 hover:text-primary"
              onClick={() => openPlatform(preferred)}
            >
              <PreferredIcon className="h-3 w-3" />
              Buy
            </Button>
          </TooltipTrigger>
          <TooltipContent>Quick buy on {preferred.name}</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-1.5 rounded-l-none hover:border-primary/50"
          >
            <ChevronDown className="h-3 w-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel className="text-xs">Trade on</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {TRADING_PLATFORMS.map((platform) => {
            const IconComp = ICON_MAP[platform.icon] || Zap;
            const isDefault = platform.id === preferred.id;
            return (
              <DropdownMenuItem
                key={platform.id}
                onClick={() => openPlatform(platform)}
                className="gap-2"
              >
                <IconComp className="h-4 w-4" />
                <span className="flex-1">{platform.name}</span>
                {isDefault && (
                  <Badge variant="outline" className="text-[10px] px-1 py-0">
                    default
                  </Badge>
                )}
                <ExternalLink className="h-3 w-3 text-muted-foreground" />
              </DropdownMenuItem>
            );
          })}
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs">
            Set default
          </DropdownMenuLabel>
          {TRADING_PLATFORMS.map((platform) => {
            const isDefault = platform.id === preferred.id;
            return (
              <DropdownMenuItem
                key={`default-${platform.id}`}
                onClick={() => handleSetDefault(platform)}
                className="gap-2 text-xs"
              >
                {isDefault ? (
                  <Check className="h-3 w-3 text-primary" />
                ) : (
                  <div className="h-3 w-3" />
                )}
                <span>{platform.name}</span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
