import type { ReactNode } from "react";

const PATHS: Record<string, ReactNode> = {
  detect: <><path d="M3 12h3l2.5-6 4 13 3-9 1.5 2h4" /></>,
  gather: <><path d="M4 7.5 12 4l8 3.5-8 3.5z" /><path d="m4 12 8 3.5 8-3.5M4 16.5 12 20l8-3.5" /></>,
  trace: <><circle cx="5" cy="12" r="2.2" /><circle cx="18" cy="5.5" r="2.2" /><circle cx="18" cy="18.5" r="2.2" /><path d="m7 11 9-4.5M7 13l9 4.5M18 8v8" /></>,
  assess: <><path d="M4 18a8.5 8.5 0 1 1 16 0" /><path d="m12 15 4-5" /><circle cx="12" cy="15.5" r="1.2" /></>,
  explain: <><path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z" /><path d="M14 3v5h5M8.5 14.5l2.3 2.3 4.7-4.6" /></>,
  file: <><path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z" /><path d="M14 3v5h5M8.5 13h2M13.5 13h2M8.5 17h2M13.5 17h2" /></>,
  upload: <><path d="M12 15V4m-4 4 4-4 4 4" /><path d="M4 14v4.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V14" /></>,
  spark: <><path d="m11 3 1.8 5.2L18 10l-5.2 1.8L11 17l-1.8-5.2L4 10l5.2-1.8zM18.5 15v6M15.5 18h6" /></>,
  data: <><ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" /><path d="M4.5 5.5v13c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8v-13M4.5 12c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8" /></>,
  check: <path d="m5 12.5 4.5 4.5L19 7" />,
  cross: <path d="M6 6l12 12M18 6 6 18" />,
};

export function Icon({ name, size = 22 }: { name: string; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {PATHS[name]}
    </svg>
  );
}

export const STAGE_ICONS = ["detect", "gather", "trace", "assess", "explain"];

export function Logo() {
  return <span className="logo" aria-hidden="true">S</span>;
}
