"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

/** The signed-in user (cached; refetched rarely). */
export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: 60_000 });
}

export function useIsAdmin() {
  return useMe().data?.role === "admin";
}
