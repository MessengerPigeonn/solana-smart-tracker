export interface TradingPlatform {
  id: string;
  name: string;
  shortName: string;
  icon: string;
  buildUrl: (tokenAddress: string) => string;
  color: string;
  description: string;
}

export const TRADING_PLATFORMS: TradingPlatform[] = [
  {
    id: "photon",
    name: "Photon",
    shortName: "Photon",
    icon: "Zap",
    buildUrl: (addr) => `https://photon-sol.tinyastro.io/en/lp/${addr}`,
    color: "#F59E0B",
    description: "Trade on Photon DEX",
  },
  {
    id: "bullx",
    name: "BullX NEO",
    shortName: "BullX",
    icon: "TrendingUp",
    buildUrl: (addr) =>
      `https://neo.bullx.io/terminal?chainId=1399811149&address=${addr}`,
    color: "#EF4444",
    description: "Trade on BullX NEO terminal",
  },
  {
    id: "axiom",
    name: "Axiom",
    shortName: "Axiom",
    icon: "Target",
    buildUrl: (addr) => `https://axiom.trade/t/${addr}`,
    color: "#8B5CF6",
    description: "Trade on Axiom",
  },
  {
    id: "jupiter",
    name: "Jupiter",
    shortName: "Jup",
    icon: "ArrowRightLeft",
    buildUrl: (addr) => `https://jup.ag/swap/SOL-${addr}`,
    color: "#22C55E",
    description: "Swap on Jupiter aggregator",
  },
  {
    id: "padre",
    name: "Padre Terminal",
    shortName: "Padre",
    icon: "Terminal",
    buildUrl: (addr) => `https://trade.padre.gg/trade/solana/${addr}`,
    color: "#06B6D4",
    description: "Trade on Padre Terminal",
  },
];

const STORAGE_KEY = "preferred_trading_platform";

export function getPreferredPlatformId(): string {
  if (typeof window === "undefined") return "photon";
  return localStorage.getItem(STORAGE_KEY) || "photon";
}

export function setPreferredPlatformId(id: string): void {
  localStorage.setItem(STORAGE_KEY, id);
}

export function getPreferredPlatform(): TradingPlatform {
  const id = getPreferredPlatformId();
  return TRADING_PLATFORMS.find((p) => p.id === id) || TRADING_PLATFORMS[0];
}
