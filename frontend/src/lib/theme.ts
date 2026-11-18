"use client";

import { useSyncExternalStore } from "react";

export type ThemePref = "light" | "dark" | "system";

const KEY = "testharbor-theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

/**
 * Runs inline in <head> before the first paint, so a dark page never flashes white.
 * Keep it in sync with apply() below.
 */
export const themeScript = `(function(){try{var p=localStorage.getItem("${KEY}");var d=p==="dark"||(p!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);var e=document.documentElement;e.classList.toggle("dark",d);e.style.colorScheme=d?"dark":"light"}catch(_){}})()`;

function readPref(): ThemePref {
  try {
    const p = localStorage.getItem(KEY);
    return p === "light" || p === "dark" ? p : "system";
  } catch {
    return "system"; // storage blocked
  }
}

function apply(pref: ThemePref) {
  const dark = pref === "dark" || (pref === "system" && media().matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

export function setTheme(pref: ThemePref) {
  try {
    if (pref === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, pref);
  } catch {
    // ignore: the choice just won't survive a reload
  }
  apply(pref);
  notify();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  // Follow the OS setting in "system" mode; pick up changes made in other tabs.
  const onMedia = () => {
    if (readPref() === "system") apply("system");
    cb();
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) {
      apply(readPref());
      cb();
    }
  };
  const mq = media();
  mq.addEventListener("change", onMedia);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    mq.removeEventListener("change", onMedia);
    window.removeEventListener("storage", onStorage);
  };
}

/** The stored preference and the theme actually shown. */
export function useTheme(): { pref: ThemePref; resolved: "light" | "dark" } {
  const pref = useSyncExternalStore(subscribe, readPref, () => "system" as ThemePref);
  const resolved = useSyncExternalStore(
    subscribe,
    () => (document.documentElement.classList.contains("dark") ? "dark" : "light"),
    () => "light" as const,
  );
  return { pref, resolved };
}
