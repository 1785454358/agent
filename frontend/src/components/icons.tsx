import type { SVGProps } from "react";

/**
 * 统一线性图标集（stroke = currentColor）。
 * 尺寸由 className / width、height 控制，默认 18px。
 */
export type IconName =
  | "plus"
  | "chat"
  | "chevronLeft"
  | "chevronRight"
  | "clock"
  | "doc"
  | "search"
  | "globe"
  | "database"
  | "wrench"
  | "compass"
  | "clipboard"
  | "network"
  | "robot"
  | "gauge"
  | "bookOpen"
  | "pen"
  | "checkCircle"
  | "rocket"
  | "alert"
  | "send"
  | "users"
  | "link"
  | "activity";

interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

function base({ size = 18, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    ...props,
  };
}

export function IconPlus(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function IconChat(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 0 1 4 11.5 8.5 8.5 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5Z" />
    </svg>
  );
}

export function IconChevronLeft(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

export function IconChevronRight(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

export function IconClock(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function IconDoc(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h6" />
    </svg>
  );
}

export function IconSearch(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export function IconGlobe(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18Z" />
    </svg>
  );
}

export function IconDatabase(p: IconProps) {
  return (
    <svg {...base(p)}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
      <path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
    </svg>
  );
}

export function IconWrench(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M14.5 5.5a3.6 3.6 0 0 0-4.7 4.7L3 17l4 4 6.8-6.8a3.6 3.6 0 0 0 4.7-4.7l-2.6 2.6-2.6-.2-.2-2.6Z" />
    </svg>
  );
}

export function IconCompass(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8Z" />
    </svg>
  );
}

export function IconClipboard(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="5" y="4.5" width="14" height="17" rx="2" />
      <path d="M9 4.5a3 3 0 0 1 6 0" />
      <path d="M9 11.5h6M9 15.5h4" />
    </svg>
  );
}

export function IconNetwork(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="18" cy="5" r="2.6" />
      <circle cx="6" cy="12" r="2.6" />
      <circle cx="18" cy="19" r="2.6" />
      <path d="M8.4 13.3 15.6 17M15.6 7 8.4 10.7" />
    </svg>
  );
}

export function IconRobot(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="4" y="8" width="16" height="11" rx="2.5" />
      <path d="M12 8V4" />
      <circle cx="12" cy="3" r="1" />
      <path d="M2 13v2.5M22 13v2.5" />
      <circle cx="9.2" cy="13.2" r="1.1" />
      <circle cx="14.8" cy="13.2" r="1.1" />
    </svg>
  );
}

export function IconGauge(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3.5 17a9 9 0 1 1 17 0" />
      <path d="m12 13 3.5-3.5" />
      <circle cx="12" cy="13" r="1.2" />
    </svg>
  );
}

export function IconBookOpen(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 6.5C10.5 5.2 8.2 4.5 5.5 4.5H3v14h2.5c2.7 0 5 .7 6.5 2 1.5-1.3 3.8-2 6.5-2H21v-14h-2.5c-2.7 0-5 .7-6.5 2Z" />
      <path d="M12 6.5V20.5" />
    </svg>
  );
}

export function IconPen(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

export function IconCheckCircle(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.4 12.2 2.4 2.4 4.8-5.2" />
    </svg>
  );
}

export function IconRocket(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4.5 16.5c-1.5 1.3-2 5.5-2 5.5s4.2-.5 5.5-2c.7-.8.7-2 0-2.8a2 2 0 0 0-2.8-.7Z" />
      <path d="M12 15l-3-3a10.5 10.5 0 0 1 8-9.5c2 0 4 2 4 4a10.5 10.5 0 0 1-9 8.5Z" />
      <circle cx="14.8" cy="9.2" r="1.4" />
    </svg>
  );
}

export function IconAlert(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4.5" />
      <path d="M12 17h.01" />
    </svg>
  );
}

export function IconSend(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}

export function IconUsers(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
      <path d="M16 4.6a3.2 3.2 0 0 1 0 6.2" />
      <path d="M18 14.2c2.4.6 4 2.8 4 5.8" />
    </svg>
  );
}

export function IconLink(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M10 13a5 5 0 0 0 7.07.46l2.6-2.6a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.07-.46l-2.6 2.6a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

export function IconActivity(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 12h4l2.5 7 5-14L17 12h4" />
    </svg>
  );
}
