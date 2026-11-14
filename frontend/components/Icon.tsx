// Small inline icon set (no icon font dependency).
const PATHS = {
  search: "M11 4a7 7 0 1 0 4.2 12.6l4.1 4.1 1.4-1.4-4.1-4.1A7 7 0 0 0 11 4Zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z",
  check: "M9.5 16.2 5.3 12l-1.4 1.4 5.6 5.6L20.1 8.4 18.7 7z",
  checkCircle: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm-1.5 14.2-4-4 1.4-1.4 2.6 2.6 5.6-5.6 1.4 1.4-7 7Z",
  close: "M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4 17.6 5 12 10.6z",
  add: "M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z",
  upload: "M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm7 1.5V9h5.5L13 3.5ZM12 11l-4 4h3v4h2v-4h3l-4-4Z",
  arrowRight: "M5 11h11.2l-4.6-4.6L13 5l7 7-7 7-1.4-1.4 4.6-4.6H5z",
  chevronRight: "m9.4 6-1.4 1.4 4.6 4.6-4.6 4.6L9.4 18l6-6z",
  link: "M10.6 13.4a1 1 0 0 1 0-1.4l3.5-3.5a3 3 0 0 1 4.2 4.3l-2 2-1.4-1.5 2-2a1 1 0 0 0-1.4-1.4l-3.5 3.5a1 1 0 0 1-1.4 0ZM13.4 10.6a1 1 0 0 1 0 1.4l-3.5 3.5a3 3 0 0 1-4.2-4.3l2-2 1.4 1.5-2 2a1 1 0 0 0 1.4 1.4l3.5-3.5a1 1 0 0 1 1.4 0Z",
  external: "M14 3h7v7h-2V6.4l-9.3 9.3-1.4-1.4L17.6 5H14V3ZM5 5h6v2H5v12h12v-6h2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z",
  bolt: "M13 2 4 14h6l-1 8 9-12h-6z",
  diagnose: "M10 2a8 8 0 0 1 6.3 12.9l5.4 5.4-1.4 1.4-5.4-5.4A8 8 0 1 1 10 2Zm0 2a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm-1 2h2v5H9zm0 6h2v2H9z",
  bank: "M12 2 2 7v2h20V7L12 2ZM4 11v7h2v-7H4Zm5 0v7h2v-7H9Zm4 0v7h2v-7h-2Zm5 0v7h2v-7h-2ZM2 20v2h20v-2H2Z",
  news: "M4 4h14v3h2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 2v12h10V6H6Zm2 2h6v2H8V8Zm0 4h6v2H8v-2Z",
  spinner: "M12 2a10 10 0 1 0 10 10h-2a8 8 0 1 1-8-8V2Z",
  sparkle: "M12 2l2.2 6.3L20.5 10.5 14.2 12.7 12 19l-2.2-6.3L3.5 10.5l6.3-2.2z",
  warning: "M12 2 1 21h22L12 2Zm-1 7h2v6h-2V9Zm0 8h2v2h-2v-2Z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, className = "size-4", title }: { name: IconName; className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden={title ? undefined : true} role={title ? "img" : undefined}>
      {title ? <title>{title}</title> : null}
      <path d={PATHS[name]} />
    </svg>
  );
}
