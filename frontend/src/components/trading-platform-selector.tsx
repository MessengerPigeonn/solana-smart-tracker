"use client";

import { useState, useEffect } from "react";
import {
  TRADING_PLATFORMS,
  getPreferredPlatform,
  setPreferredPlatformId,
  type TradingPlatform,
} from "@/lib/trading-platforms";
import { Check, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

export function TradingPlatformSelector() {
  const [preferred, setPreferred] = useState<TradingPlatform>(
    TRADING_PLATFORMS[0]
  );

  useEffect(() => {
    setPreferred(getPreferredPlatform());
  }, []);

  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted-foreground px-3">Default Exchange</p>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-between text-xs px-3"
          >
            {preferred.name}
            <ChevronDown className="h-3 w-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-48">
          {TRADING_PLATFORMS.map((platform) => (
            <DropdownMenuItem
              key={platform.id}
              onClick={() => {
                setPreferredPlatformId(platform.id);
                setPreferred(platform);
              }}
              className="gap-2 text-xs"
            >
              {preferred.id === platform.id ? (
                <Check className="h-3 w-3 text-primary" />
              ) : (
                <div className="h-3 w-3" />
              )}
              {platform.name}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
