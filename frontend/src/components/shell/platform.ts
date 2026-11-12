/** Detecção de plataforma sem depender só de `navigator.platform` (obsoleto). */

interface NavigatorWithUAData extends Navigator {
  userAgentData?: { platform?: string };
}

const APPLE_PLATFORM = /Mac|iPhone|iPad|iOS/;

/** True em macOS/iOS/iPadOS. Prefere `userAgentData.platform`; cai para `navigator.platform`. */
export function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  const nav: NavigatorWithUAData = navigator;
  const platform = nav.userAgentData?.platform || nav.platform || "";
  return APPLE_PLATFORM.test(platform);
}
